// Room voice call over WebRTC (PRD §8.3 "Voice calls").
//
// Audio flows peer-to-peer in a mesh; the backend only relays signaling on
// `/ws/voice/{room_id}` (see backend/app/api/v1/routes/voice_ws.py). This hook
// owns the browser side of that mesh:
//   - captures one local microphone stream,
//   - creates an RTCPeerConnection per remote peer,
//   - exposes microphone / speaker toggles and per-member speaking indicators,
//   - and a suspend/resume pair used to enforce the "Voice With AI mutes the
//     room mic" interlock (PRD §8.8), restoring the mic to its prior state.
//
// Single audio track per peer keeps the mesh cheap; large rooms would move to an
// SFU (noted in the backend manager). Everything that affects rendering lives in
// React state; the mutable WebRTC objects live in refs.

import { useCallback, useEffect, useRef, useState } from "react";

import { voiceSocketUrl } from "@/lib/api";
import { buildIceServers, hasTurnConfigured } from "@/lib/voice/ice-config";
import { createVoiceMask, type VoiceFilterId, type VoiceMask } from "@/lib/voice/voice-mask";

/** A remote participant in the voice call, as shown in the member list. */
export interface VoiceMember {
  readonly id: string;
  readonly name: string;
  /** True while recent audio energy from this peer is above the speaking threshold. */
  readonly speaking: boolean;
}

/** Connection lifecycle for the voice call. */
export type VoiceStatus = "idle" | "connecting" | "connected" | "error";

export interface UseRoomVoiceResult {
  readonly status: VoiceStatus;
  readonly error: string | null;
  readonly joined: boolean;
  readonly members: readonly VoiceMember[];
  readonly micOn: boolean;
  readonly speakerOn: boolean;
  /** Browser blocked remote audio autoplay — call `unlockSpeaker()` after a click. */
  readonly speakerBlocked: boolean;
  /** True when the outbound voice is disguised for incognito privacy (§7.2). */
  readonly voiceMasked: boolean;
  /** True while the mic is force-muted by the AI-voice interlock (§8.8). */
  readonly micSuspended: boolean;
  /** True while the room owner has muted this member (§8.3). */
  readonly hostMuted: boolean;
  /** True when the local user is speaking (drives the "you" indicator). */
  readonly selfSpeaking: boolean;
  join: () => Promise<void>;
  leave: () => void;
  toggleMic: () => void;
  toggleSpeaker: () => void;
  /** Retry remote audio playback (needed when autoplay policy blocks the first play). */
  unlockSpeaker: () => void;
  /** Force the mic off for an AI-voice session; the user's intent is preserved. */
  suspendMic: () => void;
  /** Release the AI-voice mic force-off, restoring the user's intent. */
  resumeMic: () => void;
  /** Owner moderation: force this member's mic off (`true`) or release it (`false`). */
  setHostMuted: (muted: boolean) => void;
}

/** ICE config is built per join so env changes apply without a full reload. */
const iceServers = (): RTCIceServer[] => buildIceServers();

/**
 * Shown when WebRTC cannot establish a media path.
 *
 * The two failures look identical to the user but have different fixes, so the
 * message is chosen from whether a TURN relay is even configured.
 */
const connectFailedMessage = (): string =>
  hasTurnConfigured()
    ? "Could not connect voice to the other device. The TURN relay did not answer — check that it is running and reachable on its ports (see docs/DEPLOYMENT.md §10)."
    : "Could not connect voice to the other device. Calls between two devices need a TURN relay, and none is configured. Set VITE_TURN_URL / VITE_TURN_USERNAME / VITE_TURN_CREDENTIAL for this deployment (see docs/DEPLOYMENT.md §10). Two browsers on one machine work without it.";

/** RMS amplitude above which a stream is considered "speaking" (0..1). */
const SPEAKING_THRESHOLD = 0.045;
/** How often to sample audio energy for speaking indicators, in milliseconds. */
const SPEAKING_SAMPLE_MS = 200;

/** The special peer id used for the local user's own speaking meter. */
const SELF_ID = "__self__";

interface SignalPeer {
  readonly id: string;
  readonly name: string;
}

type SignalMessage =
  | { type: "peers"; peers: SignalPeer[] }
  | { type: "peer-joined"; peer: SignalPeer }
  | { type: "peer-left"; peer: { id: string } }
  | { type: "offer" | "answer"; from: string; data: RTCSessionDescriptionInit }
  | { type: "ice-candidate"; from: string; data: RTCIceCandidateInit };

/**
 * Manage a room's peer-to-peer voice call and its microphone/speaker controls.
 *
 * @param roomId - Room to join (its voice signaling channel).
 * @param userId - Stable identity for this participant (from the lightweight profile).
 * @param displayName - Name shown to other members.
 * @param voiceFilter - Disguise applied to the outbound voice (incognito, §7.2); "none" = real voice.
 * @returns Call state plus imperative controls; see {@link UseRoomVoiceResult}.
 */
export function useRoomVoice(
  roomId: string,
  userId: string | null,
  displayName: string,
  voiceFilter: VoiceFilterId = "none",
): UseRoomVoiceResult {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [members, setMembers] = useState<readonly VoiceMember[]>([]);
  const [micOn, setMicOn] = useState(true);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [speakerBlocked, setSpeakerBlocked] = useState(false);
  const [micSuspended, setMicSuspended] = useState(false);
  const [hostMuted, setHostMutedState] = useState(false);
  const [selfSpeaking, setSelfSpeaking] = useState(false);
  const [voiceMasked, setVoiceMasked] = useState(false);

  // Mutable WebRTC state — never triggers a re-render directly.
  const wsRef = useRef<WebSocket | null>(null);
  // The raw mic capture (drives muting + the local speaking meter — always the
  // user's real voice) and the outbound stream actually sent to peers. They are
  // the same object in normal rooms; in incognito the outbound one is disguised.
  const localStreamRef = useRef<MediaStream | null>(null);
  const outboundStreamRef = useRef<MediaStream | null>(null);
  const maskRef = useRef<VoiceMask | null>(null);
  const peersRef = useRef<Map<string, RTCPeerConnection>>(new Map());
  // ICE candidates that arrived before the matching SDP. `addIceCandidate`
  // throws while `remoteDescription` is still null, so they are parked here and
  // replayed once the description lands. Dropping them is invisible on one
  // machine (the host candidate already connects) but breaks cross-device calls,
  // where the relay candidate is often the only one that works.
  const pendingCandidatesRef = useRef<Map<string, RTCIceCandidateInit[]>>(new Map());
  const remoteAudioRef = useRef<Map<string, HTMLAudioElement>>(new Map());
  const peerNamesRef = useRef<Map<string, string>>(new Map());
  // Signaling frames must be applied in arrival order. `ws.onmessage` is sync but
  // each handler awaits, so without this chain a candidate could be processed
  // while the offer before it is still mid-`setRemoteDescription`.
  const signalQueueRef = useRef<Promise<void>>(Promise.resolve());
  const speakerOnRef = useRef(true);
  // The mic has one intent (`micOnRef`) and two independent "force off" reasons:
  // the AI-voice interlock (`suspendedRef`) and an owner mute (`hostMutedRef`).
  // The track is live only when the user wants it on and neither reason applies.
  // Refs are the single source of truth so mic side effects never live inside a
  // setState updater (StrictMode double-invokes those).
  const micOnRef = useRef(true);
  const suspendedRef = useRef(false);
  const hostMutedRef = useRef(false);

  // Speaking-level detection (Web Audio). One context, one analyser per stream.
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analysersRef = useRef<Map<string, AnalyserNode>>(new Map());
  const speakingTimerRef = useRef<number | null>(null);

  const cleanupSpeakingMeter = useCallback((id: string) => {
    analysersRef.current.delete(id);
  }, []);

  const attachSpeakingMeter = useCallback((id: string, stream: MediaStream) => {
    if (typeof window === "undefined") return;
    const AudioCtx = window.AudioContext ?? (window as WindowWithWebkitAudio).webkitAudioContext;
    if (!AudioCtx) return; // Speaking meters are best-effort; skip if unavailable.
    try {
      if (!audioCtxRef.current) audioCtxRef.current = new AudioCtx();
      const ctx = audioCtxRef.current;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analysersRef.current.set(id, analyser);
    } catch {
      // A failed meter must never break the call; indicators simply stay off.
    }
  }, []);

  /** Root-mean-square amplitude of an analyser's current frame, normalized 0..1. */
  const readLevel = (analyser: AnalyserNode): number => {
    const buffer = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buffer);
    let sumSquares = 0;
    for (const sample of buffer) {
      const centered = (sample - 128) / 128;
      sumSquares += centered * centered;
    }
    return Math.sqrt(sumSquares / buffer.length);
  };

  // Sample every analyser on an interval and publish speaking flags.
  useEffect(() => {
    if (status !== "connected") return;
    speakingTimerRef.current = window.setInterval(() => {
      const speaking = new Set<string>();
      for (const [id, analyser] of analysersRef.current) {
        if (readLevel(analyser) >= SPEAKING_THRESHOLD) speaking.add(id);
      }
      // Only count the local user as speaking when the mic is actually live.
      setSelfSpeaking(
        speaking.has(SELF_ID) && (localStreamRef.current?.getAudioTracks()[0]?.enabled ?? false),
      );
      setMembers((prev) =>
        prev.map((m) => {
          const isSpeaking = speaking.has(m.id);
          return m.speaking === isSpeaking ? m : { ...m, speaking: isSpeaking };
        }),
      );
    }, SPEAKING_SAMPLE_MS);
    return () => {
      if (speakingTimerRef.current !== null) window.clearInterval(speakingTimerRef.current);
      speakingTimerRef.current = null;
    };
  }, [status]);

  const sendSignal = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const removePeer = useCallback(
    (peerId: string) => {
      peersRef.current.get(peerId)?.close();
      peersRef.current.delete(peerId);
      pendingCandidatesRef.current.delete(peerId);
      const audio = remoteAudioRef.current.get(peerId);
      if (audio) {
        audio.srcObject = null;
        audio.remove();
        remoteAudioRef.current.delete(peerId);
      }
      peerNamesRef.current.delete(peerId);
      cleanupSpeakingMeter(peerId);
      setMembers((prev) => prev.filter((m) => m.id !== peerId));
    },
    [cleanupSpeakingMeter],
  );

  /** Play (or restart) a remote peer's audio, honoring the current speaker state. */
  const playRemote = useCallback((peerId: string, stream: MediaStream) => {
    let audio = remoteAudioRef.current.get(peerId);
    if (!audio) {
      audio = new Audio();
      audio.autoplay = true;
      // Mobile Safari needs inline playback; attaching to DOM helps some browsers unlock audio.
      audio.setAttribute("playsinline", "true");
      audio.style.display = "none";
      document.body.appendChild(audio);
      remoteAudioRef.current.set(peerId, audio);
    }
    audio.srcObject = stream;
    audio.muted = !speakerOnRef.current;
    void audio.play().then(
      () => setSpeakerBlocked(false),
      () => {
        // WebRTC `ontrack` runs outside the click gesture chain, so autoplay is often blocked.
        if (speakerOnRef.current) setSpeakerBlocked(true);
      },
    );
  }, []);

  /** Retry playback on all remote streams (call from a user click). */
  const unlockSpeaker = useCallback(() => {
    void audioCtxRef.current?.resume().catch(() => {});
    let blocked = false;
    for (const audio of remoteAudioRef.current.values()) {
      audio.muted = !speakerOnRef.current;
      void audio.play().then(
        () => {},
        () => {
          blocked = true;
        },
      );
    }
    setSpeakerBlocked(blocked && speakerOnRef.current);
  }, []);

  /** Create (or reuse) the peer connection for `peerId`, wiring tracks + ICE relay. */
  const ensurePeer = useCallback(
    (peerId: string, name: string): RTCPeerConnection => {
      const existing = peersRef.current.get(peerId);
      if (existing) return existing;

      const pc = new RTCPeerConnection({ iceServers: iceServers() });
      peersRef.current.set(peerId, pc);
      peerNamesRef.current.set(peerId, name);

      // Send the outbound stream (disguised in incognito), not the raw capture.
      const outbound = outboundStreamRef.current;
      if (outbound) {
        for (const track of outbound.getTracks()) pc.addTrack(track, outbound);
      }

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          sendSignal({ type: "ice-candidate", to: peerId, data: event.candidate.toJSON() });
        }
      };

      pc.ontrack = (event) => {
        const [stream] = event.streams;
        if (!stream) return;
        playRemote(peerId, stream);
        attachSpeakingMeter(peerId, stream);
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed") {
          setError(connectFailedMessage());
          setStatus("error");
          removePeer(peerId);
        } else if (pc.connectionState === "closed") {
          removePeer(peerId);
        }
      };

      pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === "failed") {
          setError(connectFailedMessage());
          setStatus("error");
        }
      };

      setMembers((prev) =>
        prev.some((m) => m.id === peerId) ? prev : [...prev, { id: peerId, name, speaking: false }],
      );
      return pc;
    },
    [attachSpeakingMeter, playRemote, removePeer, sendSignal],
  );

  /** Make an SDP offer to an existing peer (we are the newcomer joining the mesh). */
  const callPeer = useCallback(
    async (peer: SignalPeer) => {
      const pc = ensurePeer(peer.id, peer.name);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      sendSignal({ type: "offer", to: peer.id, data: offer });
    },
    [ensurePeer, sendSignal],
  );

  /** Replay the candidates that arrived for `peerId` before its remote SDP did. */
  const flushPendingCandidates = useCallback(async (peerId: string, pc: RTCPeerConnection) => {
    const queued = pendingCandidatesRef.current.get(peerId);
    if (!queued) return;
    pendingCandidatesRef.current.delete(peerId);
    for (const candidate of queued) {
      // One bad candidate must not discard the rest — a single working pair is enough.
      await pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {});
    }
  }, []);

  const handleSignal = useCallback(
    async (message: SignalMessage) => {
      switch (message.type) {
        case "peers":
          // Existing peers present at join time — we initiate the offer to each.
          for (const peer of message.peers) await callPeer(peer);
          break;
        case "peer-joined":
          // A newcomer arrived; register and wait for their offer (glare-free).
          ensurePeer(message.peer.id, message.peer.name);
          break;
        case "peer-left":
          removePeer(message.peer.id);
          break;
        case "offer": {
          const name = peerNamesRef.current.get(message.from) ?? "Guest";
          const pc = ensurePeer(message.from, name);
          await pc.setRemoteDescription(new RTCSessionDescription(message.data));
          await flushPendingCandidates(message.from, pc);
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          sendSignal({ type: "answer", to: message.from, data: answer });
          break;
        }
        case "answer": {
          const pc = peersRef.current.get(message.from);
          if (!pc) break;
          await pc.setRemoteDescription(new RTCSessionDescription(message.data));
          await flushPendingCandidates(message.from, pc);
          break;
        }
        case "ice-candidate": {
          const pc = peersRef.current.get(message.from);
          if (!pc) break;
          if (!pc.remoteDescription) {
            // The SDP has not arrived (or applied) yet — park the candidate.
            const queued = pendingCandidatesRef.current.get(message.from) ?? [];
            queued.push(message.data);
            pendingCandidatesRef.current.set(message.from, queued);
            break;
          }
          await pc.addIceCandidate(new RTCIceCandidate(message.data)).catch(() => {});
          break;
        }
      }
    },
    [callPeer, ensurePeer, flushPendingCandidates, removePeer, sendSignal],
  );

  /** Push the effective mic state (intent AND no force-off reason) onto the track. */
  const applyTrack = useCallback(() => {
    const track = localStreamRef.current?.getAudioTracks()[0];
    if (track) track.enabled = micOnRef.current && !suspendedRef.current && !hostMutedRef.current;
  }, []);

  /** Set the user's mic intent, then reconcile the track. */
  const setMic = useCallback(
    (on: boolean) => {
      micOnRef.current = on;
      setMicOn(on);
      applyTrack();
    },
    [applyTrack],
  );

  const leave = useCallback(() => {
    if (speakingTimerRef.current !== null) {
      window.clearInterval(speakingTimerRef.current);
      speakingTimerRef.current = null;
    }
    const ws = wsRef.current;
    wsRef.current = null;
    ws?.close();
    for (const pc of peersRef.current.values()) pc.close();
    peersRef.current.clear();
    pendingCandidatesRef.current.clear();
    signalQueueRef.current = Promise.resolve();
    for (const audio of remoteAudioRef.current.values()) {
      audio.srcObject = null;
      audio.remove();
    }
    remoteAudioRef.current.clear();
    setSpeakerBlocked(false);
    peerNamesRef.current.clear();
    analysersRef.current.clear();
    // Tear down the voice-disguise graph before closing the shared audio context.
    maskRef.current?.disconnect();
    maskRef.current = null;
    outboundStreamRef.current = null;
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    void audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    suspendedRef.current = false;
    hostMutedRef.current = false;
    micOnRef.current = true;
    setMembers([]);
    setSelfSpeaking(false);
    setMicSuspended(false);
    setVoiceMasked(false);
    setHostMutedState(false);
    setMicOn(true);
    setStatus("idle");
  }, []);

  const join = useCallback(async () => {
    if (!userId) {
      setError("You need a profile before joining the voice call.");
      return;
    }
    if (status === "connecting" || status === "connected") return;

    // Drop stale mic/peer state from a prior disconnect before rejoining.
    if (localStreamRef.current || wsRef.current || peersRef.current.size > 0) {
      leave();
    }

    setError(null);
    setStatus("connecting");
    setSpeakerBlocked(false);

    if (typeof window !== "undefined" && !window.isSecureContext) {
      setError(
        "Voice needs HTTPS or localhost. Phones cannot use http://192.168.x.x — use HTTPS (deploy) or test with two browsers on the same PC.",
      );
      setStatus("error");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't access the microphone here. Try Chrome or Edge on localhost.");
      setStatus("error");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (err) {
      const name = (err as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setError("Microphone permission was blocked. Allow it via the 🔒 icon in the address bar.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        setError("No microphone was found on this device.");
      } else {
        setError(`Couldn't start the microphone${name ? ` (${name})` : ""}.`);
      }
      setStatus("error");
      return;
    }

    localStreamRef.current = stream;
    applyTrack();
    // The speaking meter reads the raw mic, so "you're speaking" reflects the
    // user's real voice even when the outbound stream is disguised.
    attachSpeakingMeter(SELF_ID, stream);
    // Join is always triggered by a click — resume the shared AudioContext now.
    void audioCtxRef.current?.resume().catch(() => {});

    // In incognito, disguise the outbound voice so identity/accent isn't exposed.
    // Falls back to the raw stream if Web Audio is unavailable, so the call still
    // works — privacy is best-effort, never a blocker to talking.
    let outbound = stream;
    if (voiceFilter !== "none" && audioCtxRef.current) {
      try {
        void audioCtxRef.current.resume().catch(() => {});
        const mask = createVoiceMask(audioCtxRef.current, stream, voiceFilter);
        maskRef.current = mask;
        outbound = mask.stream;
        setVoiceMasked(true);
      } catch {
        // Disguise failed to build — send the real voice rather than nothing.
        setVoiceMasked(false);
      }
    }
    outboundStreamRef.current = outbound;

    const ws = new WebSocket(voiceSocketUrl(roomId, userId, displayName));
    wsRef.current = ws;
    ws.onopen = () => setStatus("connected");
    ws.onerror = () => {
      setError("Lost the voice connection. Try rejoining.");
      setStatus("error");
      if (wsRef.current === ws) leave();
    };
    ws.onclose = () => {
      // leave() nulls wsRef before closing; skip if it already handled this socket.
      if (wsRef.current !== ws) return;
      leave();
    };
    ws.onmessage = (event) => {
      let message: SignalMessage;
      try {
        message = JSON.parse(event.data as string) as SignalMessage;
      } catch {
        return;
      }
      // Chain onto the previous frame so offers/answers/candidates are applied
      // strictly in arrival order. A rejected handler must not stall the chain.
      signalQueueRef.current = signalQueueRef.current.then(
        () => handleSignal(message),
        () => handleSignal(message),
      );
      void signalQueueRef.current.catch(() => {});
    };
  }, [
    attachSpeakingMeter,
    applyTrack,
    displayName,
    handleSignal,
    leave,
    voiceFilter,
    roomId,
    status,
    userId,
  ]);

  const toggleMic = useCallback(() => {
    // While the AI interlock or the owner holds the mic, the user can't change it.
    if (suspendedRef.current || hostMutedRef.current) return;
    setMic(!micOnRef.current);
  }, [setMic]);

  const toggleSpeaker = useCallback(() => {
    const next = !speakerOnRef.current;
    speakerOnRef.current = next;
    let blocked = false;
    for (const audio of remoteAudioRef.current.values()) {
      audio.muted = !next;
      if (next) {
        void audio.play().then(
          () => {},
          () => {
            blocked = true;
          },
        );
      }
    }
    setSpeakerOn(next);
    setSpeakerBlocked(blocked && next);
  }, []);

  // Interlock (PRD §8.8): force the mic off for the duration of an AI-voice session,
  // then release it — the user's intent (`micOnRef`) is untouched, so it returns to
  // exactly what it was. Idempotent via `suspendedRef`, so repeat/StrictMode calls
  // are safe and no side effect lives inside a setState updater.
  const suspendMic = useCallback(() => {
    if (suspendedRef.current) return;
    suspendedRef.current = true;
    setMicSuspended(true);
    applyTrack();
  }, [applyTrack]);

  const resumeMic = useCallback(() => {
    if (!suspendedRef.current) return;
    suspendedRef.current = false;
    setMicSuspended(false);
    applyTrack();
  }, [applyTrack]);

  // Owner moderation (PRD §8.3): the room owner can force this member's mic off or
  // release it. Like the interlock, the user's own intent is preserved underneath.
  const setHostMuted = useCallback(
    (muted: boolean) => {
      hostMutedRef.current = muted;
      setHostMutedState(muted);
      applyTrack();
    },
    [applyTrack],
  );

  // Tear the call down if the component using the hook unmounts mid-call.
  useEffect(() => leave, [leave]);

  return {
    status,
    error,
    joined: status === "connecting" || status === "connected",
    members,
    micOn,
    speakerOn,
    speakerBlocked,
    voiceMasked,
    micSuspended,
    hostMuted,
    selfSpeaking,
    join,
    leave,
    toggleMic,
    toggleSpeaker,
    unlockSpeaker,
    suspendMic,
    resumeMic,
    setHostMuted,
  };
}

/** Safari exposes the audio context under a webkit prefix. */
interface WindowWithWebkitAudio extends Window {
  webkitAudioContext?: typeof AudioContext;
}
