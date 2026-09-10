// Talk to the AI voice coach over Gemini Live (PRD §8.12).
//
// Same shape as the TalkHub integration, with its weak spots closed:
//   1. Ask OUR server for a one-use token (POST /voice-coach/sessions). The real
//      Gemini key never reaches the browser, and the token locks the model, the
//      coach instructions and a hard end time — nothing here can change them.
//   2. Open the WebSocket to Gemini ourselves and stream the mic as 16-bit PCM.
//   3. Play the coach's 24 kHz audio and show both sides as captions.
//   4. Tell the server when we stop. The server counts time on its own clock, so
//      this call only gives unused minutes back early — skipping it cannot make
//      a session free.

import type { LiveServerMessage, Session } from "@google/genai";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  endVoiceCoachSession,
  startVoiceCoachSession,
  type VoiceCoachSession,
} from "@/lib/api";

import {
  floatToPcm16Base64,
  loadMicWorklet,
  MIC_WORKLET_NAME,
  OUTPUT_SAMPLE_RATE,
  pcm16Base64ToFloat,
} from "./pcm-audio";

export type LiveStatus = "idle" | "connecting" | "listening" | "speaking" | "ended" | "error";

/** One finished line of the conversation. */
export interface LiveLine {
  readonly id: string;
  readonly role: "coach" | "user";
  readonly text: string;
}

/** Words of the current turn that are still arriving. */
export interface LiveCaptions {
  readonly user: string;
  readonly coach: string;
}

export interface UseGeminiLiveResult {
  readonly status: LiveStatus;
  readonly lines: readonly LiveLine[];
  readonly captions: LiveCaptions;
  /** Mic level (RMS, roughly 0–0.3) for a simple meter. */
  readonly level: number;
  readonly muted: boolean;
  /** Seconds before this session's hard limit, while it runs. */
  readonly secondsLeft: number | null;
  /** Set when the session failed; `endReason` is set when it ended normally. */
  readonly error: string | null;
  readonly endReason: string | null;
  readonly session: VoiceCoachSession | null;
  start: (topicId: string | null) => Promise<void>;
  stop: () => void;
  toggleMute: () => void;
}

/** Mic level above this counts as the learner speaking (resets the idle timer). */
const VOICE_LEVEL = 0.02;
/** End the session after this long with nobody speaking: silence still costs. */
const IDLE_LIMIT_MS = 120_000;
/** The first thing we say, so the coach opens the conversation. */
const KICKOFF =
  "Start the warm-up now: greet me in one short sentence, then ask the first question.";

const EMPTY_CAPTIONS: LiveCaptions = { user: "", coach: "" };

let lineSeq = 0;
const newLineId = (role: LiveLine["role"]) => `${role}-${Date.now()}-${++lineSeq}`;

function friendlyError(err: unknown): string {
  // The server's messages (limit reached, coach off) are already written for learners.
  if (err instanceof ApiError) return err.message;
  const name = (err as DOMException | undefined)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone permission was blocked. Allow it in your browser, then try again.";
  }
  if (name === "NotFoundError") return "No microphone was found on this device.";
  const message = (err as Error | undefined)?.message;
  return message
    ? `Couldn't start the AI coach: ${message}`
    : "Couldn't start the AI coach. Please try again.";
}

export function useGeminiLive(): UseGeminiLiveResult {
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [lines, setLines] = useState<LiveLine[]>([]);
  const [captions, setCaptions] = useState<LiveCaptions>(EMPTY_CAPTIONS);
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [endReason, setEndReason] = useState<string | null>(null);
  const [session, setSession] = useState<VoiceCoachSession | null>(null);

  const liveRef = useRef<Session | null>(null);
  const infoRef = useRef<VoiceCoachSession | null>(null);
  const micRef = useRef<MediaStream | null>(null);
  const inCtxRef = useRef<AudioContext | null>(null);
  const outCtxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const playingRef = useRef(new Set<AudioBufferSourceNode>());
  const playheadRef = useRef(0);
  const captionsRef = useRef<{ user: string; coach: string }>({ user: "", coach: "" });
  const mutedRef = useRef(false);
  const deadlineRef = useRef(0);
  const lastActivityRef = useRef(0);
  // True when nothing is running, so `finish` runs once per session.
  const endedRef = useRef(true);
  // Bumped on every start and teardown. A callback from an older attempt sees a
  // different number and does nothing.
  const attemptRef = useRef(0);

  /** Move the current turn's captions into finished lines: learner first, then coach. */
  const flushTurn = useCallback(() => {
    const { user, coach } = captionsRef.current;
    captionsRef.current = { user: "", coach: "" };
    setCaptions(EMPTY_CAPTIONS);
    const done: LiveLine[] = [];
    if (user.trim()) done.push({ id: newLineId("user"), role: "user", text: user.trim() });
    if (coach.trim()) done.push({ id: newLineId("coach"), role: "coach", text: coach.trim() });
    if (done.length) setLines((prev) => [...prev, ...done]);
  }, []);

  const stopPlayback = useCallback(() => {
    for (const source of playingRef.current) {
      try {
        source.stop();
      } catch {
        // Already finished.
      }
    }
    playingRef.current.clear();
    playheadRef.current = 0;
  }, []);

  /** Queue one chunk of the coach's voice right after the previous one. */
  const playChunk = useCallback((b64: string) => {
    const ctx = outCtxRef.current;
    if (!ctx) return;
    const samples = pcm16Base64ToFloat(b64);
    if (samples.length === 0) return;
    const buffer = ctx.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, playheadRef.current);
    source.start(startAt);
    playheadRef.current = startAt + buffer.duration;
    playingRef.current.add(source);
    source.onended = () => {
      playingRef.current.delete(source);
      if (playingRef.current.size === 0 && liveRef.current) setStatus("listening");
    };
    lastActivityRef.current = Date.now();
    setStatus("speaking");
  }, []);

  const handleMessage = useCallback(
    (message: LiveServerMessage) => {
      const content = message.serverContent;
      if (!content) return;
      // The learner talked over the coach: drop what is still queued to play.
      if (content.interrupted) {
        stopPlayback();
        flushTurn();
        setStatus("listening");
      }
      for (const part of content.modelTurn?.parts ?? []) {
        const data = part.inlineData?.data;
        if (data) playChunk(data);
      }
      const heard = content.inputTranscription?.text;
      if (heard) {
        captionsRef.current.user += heard;
        lastActivityRef.current = Date.now();
        setCaptions({ ...captionsRef.current });
      }
      const said = content.outputTranscription?.text;
      if (said) {
        captionsRef.current.coach += said;
        setCaptions({ ...captionsRef.current });
      }
      if (content.turnComplete) flushTurn();
    },
    [flushTurn, playChunk, stopPlayback],
  );

  /** Release the mic, the audio and the socket. Safe to call more than once. */
  const teardown = useCallback(() => {
    attemptRef.current += 1;
    const live = liveRef.current;
    liveRef.current = null;
    if (live) {
      try {
        live.sendRealtimeInput({ audioStreamEnd: true });
      } catch {
        // Socket already closed.
      }
      try {
        live.close();
      } catch {
        // Socket already closed.
      }
    }
    if (nodeRef.current) {
      nodeRef.current.port.onmessage = null;
      nodeRef.current.disconnect();
      nodeRef.current = null;
    }
    micRef.current?.getTracks().forEach((track) => track.stop());
    micRef.current = null;
    stopPlayback();
    void inCtxRef.current?.close().catch(() => undefined);
    void outCtxRef.current?.close().catch(() => undefined);
    inCtxRef.current = null;
    outCtxRef.current = null;
    setLevel(0);
  }, [stopPlayback]);

  const finish = useCallback(
    (reason: string | null, opts: { failed?: boolean; keepalive?: boolean } = {}) => {
      if (endedRef.current) return;
      endedRef.current = true;
      teardown();
      flushTurn();
      setSecondsLeft(null);
      const info = infoRef.current;
      if (info) {
        void endVoiceCoachSession(info.id, { keepalive: opts.keepalive }).catch(() => {
          // Not fatal: the server settles an un-ended session once it expires.
        });
      }
      if (opts.failed) {
        setError(reason);
        setStatus("error");
      } else {
        setEndReason(reason);
        setStatus("ended");
      }
    },
    [flushTurn, teardown],
  );

  const start = useCallback(
    async (topicId: string | null) => {
      teardown();
      const attempt = attemptRef.current;
      const stale = () => attempt !== attemptRef.current;
      endedRef.current = false;
      infoRef.current = null;
      captionsRef.current = { user: "", coach: "" };
      mutedRef.current = false;
      setLines([]);
      setCaptions(EMPTY_CAPTIONS);
      setError(null);
      setEndReason(null);
      setMuted(false);
      setSecondsLeft(null);
      setSession(null);
      setStatus("connecting");

      // Create both audio contexts inside the click, before any await: browsers
      // only let a page start audio right after a user gesture.
      const inCtx = new AudioContext();
      const outCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
      inCtxRef.current = inCtx;
      outCtxRef.current = outCtx;

      try {
        if (!window.isSecureContext) throw new Error("the microphone needs a secure page (HTTPS)");
        // Mic before the token: if the learner blocks it, no minutes are held.
        const mic = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        if (stale()) {
          mic.getTracks().forEach((track) => track.stop());
          return;
        }
        micRef.current = mic;
        await Promise.all([inCtx.resume(), outCtx.resume(), loadMicWorklet(inCtx)]);
        if (stale()) return;

        const info = await startVoiceCoachSession({ topic_id: topicId });
        if (stale()) {
          void endVoiceCoachSession(info.id).catch(() => undefined);
          return;
        }
        infoRef.current = info;
        // Count down from our own clock: the server's clock may not match ours.
        deadlineRef.current = Date.now() + info.max_seconds * 1000;
        setSession(info);

        // Loaded on demand: only learners who start a session download the SDK.
        const { GoogleGenAI, Modality } = await import("@google/genai");
        const ai = new GoogleGenAI({ apiKey: info.token, apiVersion: "v1beta" });
        const live = await ai.live.connect({
          model: info.model,
          // The token locks the real config. This only has to agree with it.
          config: {
            responseModalities: [Modality.AUDIO],
            inputAudioTranscription: {},
            outputAudioTranscription: {},
          },
          callbacks: {
            onmessage: (message) => {
              if (!stale()) handleMessage(message);
            },
            onerror: () => {
              if (!stale()) {
                finish("The connection to the coach failed. Please try again.", { failed: true });
              }
            },
            onclose: (event) => {
              if (!stale()) {
                finish(
                  event.reason
                    ? `The coach ended the session (${event.reason}).`
                    : "The coach ended the session.",
                );
              }
            },
          },
        });
        if (stale()) {
          live.close();
          return;
        }
        liveRef.current = live;

        const node = new AudioWorkletNode(inCtx, MIC_WORKLET_NAME);
        node.port.onmessage = (event: MessageEvent<{ samples: Float32Array; level: number }>) => {
          const { samples, level: rms } = event.data;
          setLevel(rms);
          const current = liveRef.current;
          if (!current || mutedRef.current) return;
          if (rms > VOICE_LEVEL) lastActivityRef.current = Date.now();
          try {
            current.sendRealtimeInput({
              audio: {
                data: floatToPcm16Base64(samples),
                mimeType: `audio/pcm;rate=${inCtx.sampleRate}`,
              },
            });
          } catch {
            // Socket closing; `onclose` reports it.
          }
        };
        inCtx.createMediaStreamSource(mic).connect(node);
        // The node only outputs silence. Connecting it keeps the browser pulling
        // audio through it.
        node.connect(inCtx.destination);
        nodeRef.current = node;

        lastActivityRef.current = Date.now();
        setStatus("listening");
        live.sendRealtimeInput({ text: KICKOFF });
      } catch (err) {
        if (!stale()) finish(friendlyError(err), { failed: true });
      }
    },
    [finish, handleMessage, teardown],
  );

  const stop = useCallback(() => finish(null), [finish]);

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    micRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = !next;
    });
    if (next) {
      try {
        // Tells Gemini's voice detection the learner stopped, so it can answer.
        liveRef.current?.sendRealtimeInput({ audioStreamEnd: true });
      } catch {
        // Socket closing.
      }
    }
    lastActivityRef.current = Date.now();
  }, []);

  // Countdown, the hard limit, and the idle timeout.
  useEffect(() => {
    if (status !== "listening" && status !== "speaking") return;
    const tick = () => {
      const left = Math.max(0, Math.round((deadlineRef.current - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left <= 0) {
        finish("You reached the time limit for this session.");
      } else if (Date.now() - lastActivityRef.current > IDLE_LIMIT_MS) {
        finish("The session ended after 2 minutes of silence, to save your minutes.");
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [status, finish]);

  // Leaving the page (or this screen) ends the session and gives the time back.
  useEffect(() => {
    const onPageHide = () => finish(null, { keepalive: true });
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      finish(null, { keepalive: true });
    };
  }, [finish]);

  return {
    status,
    lines,
    captions,
    level,
    muted,
    secondsLeft,
    error,
    endReason,
    session,
    start,
    stop,
    toggleMute,
  };
}
