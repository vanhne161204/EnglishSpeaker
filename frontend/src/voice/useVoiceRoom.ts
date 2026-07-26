import { useCallback, useEffect, useRef, useState } from "react";
import type { MediaStream, RTCIceCandidate, RTCPeerConnection } from "react-native-webrtc";
import { VoiceSocket } from "../api/voiceSocket";
import type { SignalingMessage } from "../api/voiceSocket";
import { rtcConfig } from "./iceConfig";

export interface VoicePeer {
  id: string;
  name: string;
  state: string;
}

// react-native-webrtc is a native module that is NOT present in Expo Go. Importing
// it eagerly crashes app startup there, so it is loaded lazily — only when a user
// actually joins a voice call (which requires a custom dev build). The rest of the
// app keeps working everywhere.
type WebRTCModule = typeof import("react-native-webrtc");

let webrtcModule: WebRTCModule | null = null;
async function loadWebRTC(): Promise<WebRTCModule> {
  if (!webrtcModule) {
    webrtcModule = await import("react-native-webrtc");
  }
  return webrtcModule;
}

// addEventListener is inherited from event-target-shim and doesn't surface cleanly
// through react-native-webrtc's published types under strict TS. This narrow
// accessor types just the two events we use, without resorting to `any`.
interface PeerEventTarget {
  addEventListener(
    type: "icecandidate",
    listener: (event: { candidate: RTCIceCandidate | null }) => void,
  ): void;
  addEventListener(type: "connectionstatechange", listener: () => void): void;
}

/**
 * Manages a WebRTC mesh voice call for one room: local mic, one peer connection
 * per other participant, and signaling over {@link VoiceSocket}. Audio plays
 * automatically once tracks arrive (audio-only needs no view).
 */
export function useVoiceRoom(roomId: string, userId: string, name: string) {
  const [active, setActive] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [peers, setPeers] = useState<VoicePeer[]>([]);

  const socketRef = useRef<VoiceSocket | null>(null);
  const wRef = useRef<WebRTCModule | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const pcsRef = useRef<Map<string, RTCPeerConnection>>(new Map());
  const namesRef = useRef<Map<string, string>>(new Map());

  const setPeerState = useCallback((id: string, state: string) => {
    setPeers((prev) => prev.map((p) => (p.id === id ? { ...p, state } : p)));
  }, []);

  const closePeer = useCallback((id: string) => {
    const pc = pcsRef.current.get(id);
    if (pc) {
      pc.close();
      pcsRef.current.delete(id);
    }
    namesRef.current.delete(id);
    setPeers((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const createPeer = useCallback(
    (peerId: string, peerName: string, initiator: boolean): RTCPeerConnection => {
      const w = wRef.current;
      if (!w) throw new Error("WebRTC not loaded");

      const pc = new w.RTCPeerConnection(rtcConfig);
      const local = localStreamRef.current;
      if (local) {
        local.getTracks().forEach((track) => pc.addTrack(track, local));
      }

      const events = pc as unknown as PeerEventTarget;
      events.addEventListener("icecandidate", (event) => {
        if (event.candidate) {
          socketRef.current?.send({ type: "ice-candidate", to: peerId, data: event.candidate });
        }
      });
      events.addEventListener("connectionstatechange", () => {
        setPeerState(peerId, pc.connectionState);
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          closePeer(peerId);
        }
      });

      pcsRef.current.set(peerId, pc);
      namesRef.current.set(peerId, peerName);
      setPeers((prev) =>
        prev.some((p) => p.id === peerId)
          ? prev
          : [...prev, { id: peerId, name: peerName, state: "connecting" }],
      );

      if (initiator) {
        void (async () => {
          const offer = await pc.createOffer({});
          await pc.setLocalDescription(offer);
          socketRef.current?.send({ type: "offer", to: peerId, data: offer });
        })();
      }
      return pc;
    },
    [closePeer, setPeerState],
  );

  const handleSignal = useCallback(
    async (message: SignalingMessage) => {
      const w = wRef.current;
      if (!w) return;
      switch (message.type) {
        case "peers":
          // We are the newcomer: initiate an offer to everyone already here.
          message.peers.forEach((p) => {
            namesRef.current.set(p.id, p.name);
            createPeer(p.id, p.name, true);
          });
          break;
        case "peer-joined":
          // Wait for the newcomer's offer; just remember their name.
          namesRef.current.set(message.peer.id, message.peer.name);
          break;
        case "offer": {
          const peerName = namesRef.current.get(message.from) ?? "Guest";
          const pc =
            pcsRef.current.get(message.from) ?? createPeer(message.from, peerName, false);
          await pc.setRemoteDescription(
            new w.RTCSessionDescription(
              message.data as ConstructorParameters<typeof w.RTCSessionDescription>[0],
            ),
          );
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          socketRef.current?.send({ type: "answer", to: message.from, data: answer });
          break;
        }
        case "answer": {
          const pc = pcsRef.current.get(message.from);
          if (pc) {
            await pc.setRemoteDescription(
              new w.RTCSessionDescription(
                message.data as ConstructorParameters<typeof w.RTCSessionDescription>[0],
              ),
            );
          }
          break;
        }
        case "ice-candidate": {
          const pc = pcsRef.current.get(message.from);
          if (pc && message.data) {
            await pc.addIceCandidate(
              new w.RTCIceCandidate(
                message.data as ConstructorParameters<typeof w.RTCIceCandidate>[0],
              ),
            );
          }
          break;
        }
        case "peer-left":
          closePeer(message.peer.id);
          break;
      }
    },
    [createPeer, closePeer],
  );

  const cleanup = useCallback(() => {
    pcsRef.current.forEach((pc) => pc.close());
    pcsRef.current.clear();
    namesRef.current.clear();
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    setPeers([]);
    setActive(false);
    setMuted(false);
  }, []);

  const join = useCallback(async () => {
    if (active || connecting) return;
    setConnecting(true);
    try {
      const w = await loadWebRTC();
      wRef.current = w;
      const stream = await w.mediaDevices.getUserMedia({ audio: true, video: false });
      localStreamRef.current = stream;
      const socket = new VoiceSocket(roomId, userId, name, (m) => void handleSignal(m));
      socket.connect();
      socketRef.current = socket;
      setActive(true);
    } catch (err) {
      cleanup();
      throw err;
    } finally {
      setConnecting(false);
    }
  }, [active, connecting, roomId, userId, name, handleSignal, cleanup]);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      localStreamRef.current?.getAudioTracks().forEach((track) => {
        track.enabled = !next;
      });
      return next;
    });
  }, []);

  // Always tear down the call (mic + sockets) when the screen unmounts.
  useEffect(() => () => cleanup(), [cleanup]);

  return { active, connecting, muted, peers, join, leave: cleanup, toggleMute };
}
