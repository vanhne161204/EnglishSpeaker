// Voice conversation with the AI coach (PRD §8.8 "Voice With AI").
//
// One spoken turn: the user speaks, the browser transcribes it (Web Speech API),
// the AI coach replies via `POST /assist`, and the reply is read back with the
// Speech Synthesis API. The session loops turn-by-turn until stopped.
//
// The whole session is gated by the caller so it can enforce the room-mic
// interlock: while a session is active the room microphone must be muted so
// other members never hear the user's private AI practice (PRD §8.8).
//
// Speech recognition is browser-native (Chrome/Edge). `supported` reports
// whether it is available so the UI can hide voice and keep text-chat with AI.

import { useCallback, useEffect, useRef, useState } from "react";

import { assist } from "@/lib/api";

/** One line of the spoken AI conversation. */
export interface AiVoiceTurn {
  readonly role: "user" | "ai";
  readonly text: string;
}

/** What the AI voice session is currently doing (for status UI). */
export type AiVoicePhase = "idle" | "listening" | "thinking" | "speaking";

export interface UseAiVoiceResult {
  /** Whether this browser can capture speech at all. */
  readonly supported: boolean;
  /** True between {@link start} and {@link stop}; drives the mic interlock. */
  readonly active: boolean;
  readonly phase: AiVoicePhase;
  readonly transcript: readonly AiVoiceTurn[];
  readonly error: string | null;
  start: () => void;
  stop: () => void;
}

/** Recognition language; en-US keeps the practice target consistent. */
const RECOGNITION_LANG = "en-US";

/**
 * Run a hands-free spoken conversation with the AI coach.
 *
 * @param topicId - Optional topic to ground the AI's replies (RAG, §8.8).
 * @returns Session state and start/stop controls; see {@link UseAiVoiceResult}.
 */
export function useAiVoice(topicId: string | null): UseAiVoiceResult {
  const [active, setActive] = useState(false);
  const [phase, setPhase] = useState<AiVoicePhase>("idle");
  const [transcript, setTranscript] = useState<readonly AiVoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const activeRef = useRef(false); // Mirror of `active` for use inside async callbacks.
  const topicIdRef = useRef(topicId);
  topicIdRef.current = topicId;

  const supported =
    typeof window !== "undefined" &&
    (window.SpeechRecognition !== undefined || window.webkitSpeechRecognition !== undefined) &&
    typeof window.speechSynthesis !== "undefined";

  /** Speak text aloud, resolving when playback finishes (or immediately if unsupported). */
  const speak = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (typeof window === "undefined" || !window.speechSynthesis) {
        resolve();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = RECOGNITION_LANG;
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve(); // Never block the loop on a TTS failure.
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });
  }, []);

  /** Begin listening for one utterance; forward declared so turns can re-arm it. */
  const listenRef = useRef<() => void>(() => {});

  /** Ask the AI for a reply to the user's utterance, speak it, then listen again. */
  const handleUserUtterance = useCallback(
    async (utterance: string) => {
      const text = utterance.trim();
      if (!text) {
        if (activeRef.current) listenRef.current();
        return;
      }
      setTranscript((prev) => [...prev, { role: "user", text }]);
      setPhase("thinking");
      try {
        const result = await assist({
          kind: "reply",
          context: text,
          topic_id: topicIdRef.current,
        });
        if (!activeRef.current) return; // Session was stopped while we waited.
        const reply = result.suggestion.trim() || "Let's keep going — tell me more.";
        setTranscript((prev) => [...prev, { role: "ai", text: reply }]);
        setPhase("speaking");
        await speak(reply);
      } catch (err) {
        if (activeRef.current) setError(`AI voice failed: ${(err as Error).message}`);
      } finally {
        if (activeRef.current) listenRef.current();
      }
    },
    [speak],
  );

  const listen = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition || !activeRef.current) return;
    setPhase("listening");
    try {
      recognition.start();
    } catch {
      // start() throws if already started; the current turn will complete normally.
    }
  }, []);
  listenRef.current = listen;

  // Track phase in a ref so recognition callbacks can read it without re-binding.
  const phaseRef = useRef<AiVoicePhase>("idle");
  phaseRef.current = phase;

  const stopInternal = useCallback(() => {
    activeRef.current = false;
    const recognition = recognitionRef.current;
    if (recognition) {
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;
      try {
        recognition.abort();
      } catch {
        // Ignore — recognition may not have been started.
      }
    }
    recognitionRef.current = null;
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    setActive(false);
    setPhase("idle");
  }, []);

  const stop = useCallback(() => stopInternal(), [stopInternal]);

  const start = useCallback(() => {
    if (activeRef.current) return;
    if (!supported) {
      setError("Voice with AI needs Chrome or Edge (speech recognition isn't available here).");
      return;
    }
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) return;

    const recognition = new Recognition();
    recognition.lang = RECOGNITION_LANG;
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      const result = event.results[event.results.length - 1];
      const phrase = result?.[0]?.transcript ?? "";
      void handleUserUtterance(phrase);
    };
    recognition.onerror = (event: SpeechRecognitionErrorLike) => {
      // "no-speech" / "aborted" are benign; just re-arm. Others surface once.
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setError("Microphone permission was blocked for Voice with AI.");
        stopInternal();
      } else if (event.error !== "no-speech" && event.error !== "aborted") {
        setError(`Voice with AI error: ${event.error}`);
      }
    };
    recognition.onend = () => {
      // Recognition auto-stops after each phrase; the turn handler re-arms it.
      // If it ended without a result (silence) and we're still active, re-listen.
      if (activeRef.current && phaseRef.current === "listening") listenRef.current();
    };

    recognitionRef.current = recognition;
    activeRef.current = true;
    setActive(true);
    setError(null);
    setTranscript([]);
    listen();
  }, [handleUserUtterance, listen, stopInternal, supported]);

  // Ensure the session is fully torn down if the component unmounts.
  useEffect(() => stopInternal, [stopInternal]);

  return { supported, active, phase, transcript, error, start, stop };
}

/* ---------- Minimal Web Speech API typings (not in the standard TS lib) ---------- */

interface SpeechRecognitionAlternativeLike {
  readonly transcript: string;
}
interface SpeechRecognitionResultLike {
  /** True once this result is finalized (not an interim guess). */
  readonly isFinal: boolean;
  readonly [index: number]: SpeechRecognitionAlternativeLike | undefined;
}
interface SpeechRecognitionResultListLike {
  readonly length: number;
  readonly [index: number]: SpeechRecognitionResultLike | undefined;
}
interface SpeechRecognitionEventLike {
  /** Index of the first result changed in this event (for continuous mode). */
  readonly resultIndex?: number;
  readonly results: SpeechRecognitionResultListLike;
}
interface SpeechRecognitionErrorLike {
  readonly error: string;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  /** Finalize the current utterance and deliver its result via onresult. */
  stop: () => void;
  /** Stop immediately and discard any pending result (no onresult). */
  abort: () => void;
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}
