// Continuous speech-to-text for the room transcript (PRD §8.9).
//
// Differs from `use-speech-to-text.ts` (push-to-talk, one answer, delivered on
// stop) in the way that matters here: this runs for the WHOLE call and reports
// every sentence as it is finished, plus a live preview of the one in progress.
//
// WHY THE BROWSER: the Web Speech API is free, needs no key, and adds zero
// server CPU — the audio never leaves the machine. On a 2 GB EC2 already running
// Postgres, Redis, Caddy and coturn, running Whisper for several continuous
// speakers is not an option (docs/10_AI_Design.md §8.9). The cost of that choice
// is browser support: Chrome, Edge and Safari yes, Firefox no. `supported` lets
// the room fall back to the existing push-to-talk mic there.
//
// The auto-restart loop is the load-bearing part. Chrome ends a recognition
// session after a few seconds of silence, so without restarting on `onend` the
// transcript would simply stop the first time someone paused to think.

import { useCallback, useEffect, useRef, useState } from "react";

// The Web Speech API typing (and the `Window.SpeechRecognition` global) is
// declared once in `use-ai-voice.ts` and shared by all three speech hooks.
import type { SpeechRecognitionLike } from "@/lib/voice/use-ai-voice";

export interface LiveSegment {
  text: string;
  /** Rises once per finished sentence. Lets the UI replace a preview in place. */
  seq: number;
  /** Engine confidence 0-1 when reported — feeds the pronunciation work later. */
  confidence?: number;
}

export interface UseLiveTranscribeResult {
  readonly supported: boolean;
  readonly listening: boolean;
  readonly error: string | null;
  start: () => void;
  stop: () => void;
}

const RECOGNITION_LANG = "en-US";

/** Throttle for interim frames. ~3/sec keeps the preview smooth without
 *  flooding the socket with text that is replaced immediately. */
const INTERIM_MS = 350;

export function useLiveTranscribe(
  onFinal: (segment: LiveSegment) => void,
  onInterim: (segment: LiveSegment) => void,
): UseLiveTranscribeResult {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  // Whether the user still WANTS to listen. Drives auto-restart: an `onend`
  // from a silence timeout restarts instead of ending the session.
  const wantRef = useRef(false);
  const seqRef = useRef(0);
  const lastInterimRef = useRef(0);

  // Keep the callbacks current so a long-lived recognition always uses the
  // latest handlers rather than the ones captured on the first render.
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;
  const onInterimRef = useRef(onInterim);
  onInterimRef.current = onInterim;

  const supported =
    typeof window !== "undefined" &&
    (window.SpeechRecognition !== undefined || window.webkitSpeechRecognition !== undefined);

  const build = useCallback((): SpeechRecognitionLike | null => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) return null;

    const recognition = new Recognition();
    recognition.lang = RECOGNITION_LANG;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex ?? 0; i < event.results.length; i++) {
        const result = event.results[i];
        const alternative = result?.[0];
        if (!result || !alternative) continue;

        if (result.isFinal) {
          const text = alternative.transcript.trim();
          if (text) {
            // One finished sentence: gets its own seq, and is the only thing
            // the server stores.
            onFinalRef.current({
              text,
              seq: seqRef.current,
              confidence: alternative.confidence,
            });
            seqRef.current += 1;
          }
        } else {
          interim += alternative.transcript;
        }
      }

      interim = interim.trim();
      if (!interim) return;
      const now = Date.now();
      if (now - lastInterimRef.current < INTERIM_MS) return;
      lastInterimRef.current = now;
      // Shares the seq of the sentence being spoken, so the UI replaces the
      // preview rather than stacking a new line per keystroke of speech.
      onInterimRef.current({ text: interim, seq: seqRef.current });
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        wantRef.current = false; // permission denied: stop for good, no restart loop
        setError("Microphone permission was blocked — allow it to see your transcript.");
      } else if (event.error === "no-speech" || event.error === "aborted") {
        // Normal during a pause. `onend` restarts; nothing to report.
      } else {
        setError(`Speech error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      // Chrome ends a session after a few seconds of silence. If the user still
      // wants to listen, restart transparently — otherwise the transcript stops
      // the first time somebody pauses to think.
      if (wantRef.current) {
        try {
          recognition.start();
          return;
        } catch {
          // Could not restart; fall through to a real stop.
        }
      }
      recognitionRef.current = null;
      setListening(false);
    };

    return recognition;
  }, []);

  const start = useCallback(() => {
    if (wantRef.current) return;
    if (!supported) {
      setError("Live transcript needs Chrome, Edge or Safari.");
      return;
    }
    const recognition = build();
    if (!recognition) return;

    wantRef.current = true;
    recognitionRef.current = recognition;
    setError(null);
    setListening(true);
    try {
      recognition.start();
    } catch {
      wantRef.current = false;
      recognitionRef.current = null;
      setListening(false);
      setError("Couldn't start the transcript — try again.");
    }
  }, [supported, build]);

  const stop = useCallback(() => {
    wantRef.current = false;
    const recognition = recognitionRef.current;
    if (!recognition) {
      setListening(false);
      return;
    }
    try {
      recognition.stop(); // finalises the last sentence before ending
    } catch {
      // Not started; nothing to finalise.
    }
  }, []);

  // Hard stop on unmount: drop the handlers first so a late result cannot fire
  // into an unmounted tree, then abort without finalising.
  useEffect(() => {
    return () => {
      wantRef.current = false;
      const recognition = recognitionRef.current;
      if (!recognition) return;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try {
        recognition.abort();
      } catch {
        // Never started.
      }
      recognitionRef.current = null;
    };
  }, []);

  return { supported, listening, error, start, stop };
}
