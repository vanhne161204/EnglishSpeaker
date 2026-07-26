// Push-to-talk speech-to-text (PRD §8.9, used by Warm-up §8.12).
//
// The user taps to talk, speaks one answer for as long as they like — pausing to
// think is fine — and taps Stop when done; the full transcript is handed back
// once. Under the hood the browser Web Speech API (Chrome/Edge) ends a segment
// after a few seconds of silence, so we run it in `continuous` mode and
// auto-restart on `onend` while the user still wants to listen, accumulating the
// finalized text. Without this the mic appears to "turn off after ~5 seconds"
// the moment the speaker pauses.
//
// `supported` lets callers fall back to a typed answer where recognition is
// unavailable, so the flow is never blocked. The global `Window.SpeechRecognition`
// typing is declared once in `use-ai-voice.ts` and reused here.

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseSpeechToTextResult {
  /** Whether this browser can capture speech at all. */
  readonly supported: boolean;
  /** True while actively listening for the current answer. */
  readonly listening: boolean;
  readonly error: string | null;
  /** Start listening for one answer (stays on through pauses until `stop`). */
  start: () => void;
  /** Stop listening and deliver everything heard as the final transcript. */
  stop: () => void;
}

/** Recognition language; en-US keeps the practice target consistent. */
const RECOGNITION_LANG = "en-US";

/**
 * Capture a spoken answer and deliver its transcript.
 *
 * @param onResult - Called once with the final transcript when the user taps Stop.
 * @returns Listening state and start/stop controls; see {@link UseSpeechToTextResult}.
 */
export function useSpeechToText(onResult: (text: string) => void): UseSpeechToTextResult {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  // Whether the user still intends to listen. Drives auto-restart: while true, an
  // `onend` from a silence timeout restarts recognition instead of ending it.
  const wantListeningRef = useRef(false);
  // Finalized transcript accumulated across auto-restarted segments.
  const finalTranscriptRef = useRef("");

  // Keep the callback current so a long-lived recognition uses the latest handler.
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  const supported =
    typeof window !== "undefined" &&
    (window.SpeechRecognition !== undefined || window.webkitSpeechRecognition !== undefined);

  const buildRecognition = useCallback((): SpeechRecognitionInstance | null => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) return null;

    const recognition = new Recognition();
    recognition.lang = RECOGNITION_LANG;
    // continuous: keep listening across pauses. interimResults: keeps the engine
    // active and lets Chrome deliver partials (we only keep the finalized ones).
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      // Append only newly-finalized results to the running transcript.
      let finalized = "";
      for (let i = event.resultIndex ?? 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result?.isFinal) finalized += result[0]?.transcript ?? "";
      }
      finalized = finalized.trim();
      if (finalized) {
        finalTranscriptRef.current = `${finalTranscriptRef.current} ${finalized}`.trim();
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        // Permission denied — stop for good so onend doesn't loop restarting.
        wantListeningRef.current = false;
        setError("Microphone permission was blocked — allow it, or type your answer.");
      } else if (event.error === "no-speech") {
        // Silence timeout while still listening: let onend auto-restart, no error.
      } else if (event.error !== "aborted") {
        setError(`Speech error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      // Chrome ended this segment (silence or a natural break). If the user still
      // wants to listen, transparently restart so the mic stays on.
      if (wantListeningRef.current) {
        try {
          recognition.start();
          return;
        } catch {
          // Fall through to a real stop if it can't be restarted.
        }
      }
      recognitionRef.current = null;
      setListening(false);
      const text = finalTranscriptRef.current.trim();
      if (text) onResultRef.current(text);
    };

    return recognition;
  }, []);

  const start = useCallback(() => {
    if (wantListeningRef.current) return;
    if (!supported) {
      setError("Speech isn't available in this browser — type your answer instead.");
      return;
    }
    const recognition = buildRecognition();
    if (!recognition) return;

    finalTranscriptRef.current = "";
    wantListeningRef.current = true;
    recognitionRef.current = recognition;
    setError(null);
    setListening(true);
    try {
      recognition.start();
    } catch {
      wantListeningRef.current = false;
      recognitionRef.current = null;
      setListening(false);
      setError("Couldn't start listening — try again.");
    }
  }, [supported, buildRecognition]);

  // Stop listening and DELIVER the accumulated transcript. Clears the intent
  // first so onend won't auto-restart, then finalizes via stop() (not abort(),
  // which would discard the last words).
  const stop = useCallback(() => {
    wantListeningRef.current = false;
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      recognition.stop();
    } catch {
      // Not started yet; nothing to finalize.
    }
    // onend delivers the accumulated transcript and clears `listening`.
  }, []);

  // Cancel WITHOUT delivering a transcript (used on unmount): drop the handlers
  // and abort so a half-captured answer is discarded and no callback fires late
  // into an unmounted component.
  const cancel = useCallback(() => {
    wantListeningRef.current = false;
    const recognition = recognitionRef.current;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try {
        recognition.abort();
      } catch {
        // Ignore — recognition may not have been started.
      }
      recognitionRef.current = null;
    }
    finalTranscriptRef.current = "";
    setListening(false);
  }, []);

  // Tear down any active recognition if the component unmounts mid-listen —
  // cancel (discard), so no late transcript fires into an unmounted tree.
  useEffect(() => cancel, [cancel]);

  return { supported, listening, error, start, stop };
}

/* ---------- Minimal Web Speech API instance typing (event `Window` decl lives elsewhere) ---------- */

interface SpeechRecognitionAlternativeLike {
  readonly transcript: string;
}
interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly [index: number]: SpeechRecognitionAlternativeLike | undefined;
}
interface SpeechRecognitionResultListLike {
  readonly length: number;
  readonly [index: number]: SpeechRecognitionResultLike | undefined;
}
interface SpeechRecognitionEventLike {
  /** Index of the first result that changed in this event. */
  readonly resultIndex?: number;
  readonly results: SpeechRecognitionResultListLike;
}
interface SpeechRecognitionErrorLike {
  readonly error: string;
}
interface SpeechRecognitionInstance {
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
