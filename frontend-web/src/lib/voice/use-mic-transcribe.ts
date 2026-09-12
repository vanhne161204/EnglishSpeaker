// Record a short audio clip and turn it into text (PRD §8.9). Used by Warm-up.
// Whisper runs on the learner's device when its model is ready; otherwise the
// clip goes to the server `/transcribe` endpoint (see `browser-whisper.ts`).
// Unlike the browser Web Speech API, both work in every browser.
//
// Flow: tap to start (records, and starts loading the model), tap to stop →
// the clip is transcribed → the text is delivered once via `onResult`.

import { useCallback, useRef, useState } from "react";

import { clipToText, preloadWhisper } from "@/lib/voice/browser-whisper";

export interface UseMicTranscribeResult {
  /** Whether this browser can record audio at all. */
  readonly supported: boolean;
  /** True while actively recording. */
  readonly listening: boolean;
  /** True while the clip is uploading/transcribing. */
  readonly busy: boolean;
  readonly error: string | null;
  /** Start recording. */
  start: () => void;
  /** Stop recording; the clip is transcribed and delivered via onResult. */
  stop: () => void;
}

/**
 * Capture a spoken answer and deliver its transcript from the server.
 *
 * @param onResult - Called once with the transcript when transcription finishes.
 * @param language - BCP-47 hint (e.g. "en"); helps the engine.
 */
export function useMicTranscribe(
  onResult: (text: string) => void,
  language?: string,
): UseMicTranscribeResult {
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Keep the callback current so a long-lived recorder uses the latest handler.
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  const supported =
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  const stop = useCallback(() => {
    recorderRef.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    // Mic access needs a secure context: HTTPS, or http on localhost/127.0.0.1.
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setError("Mic needs a secure page (HTTPS). Open the site over https://.");
      return;
    }
    if (!supported) {
      setError("Audio recording isn't supported in this browser — type your answer.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setError("Microphone permission was blocked — allow it, or type your answer.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        setError("No microphone was found on this device.");
      } else {
        setError(`Couldn't start the microphone${name ? ` (${name})` : ""}.`);
      }
      return;
    }

    try {
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) {
          setError("No audio was captured — hold the mic a little longer.");
          return;
        }
        setBusy(true);
        try {
          const { text } = await clipToText(blob, language);
          if (text) onResultRef.current(text);
          else setError("Couldn't hear any words. Try again, a little louder.");
        } catch (e) {
          setError(`Transcription failed: ${(e as Error).message}`);
        } finally {
          setBusy(false);
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setListening(true);
      // Load the model while the learner speaks. A no-op after the first time.
      if (!language || language.startsWith("en")) preloadWhisper();
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setError("Couldn't start recording on this device.");
    }
  }, [supported, language]);

  return { supported, listening, busy, error, start, stop };
}
