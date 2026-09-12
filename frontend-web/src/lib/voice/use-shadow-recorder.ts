// Record one try at a Shadowing sentence (PRD §8.14).
//
// Three things share the microphone while the learner speaks:
//   - MediaRecorder keeps the audio, so they can play their try right after the
//     model voice (A/B). It stays in the browser: nothing is uploaded unless the
//     browser has no speech recognition (below).
//   - The Web Speech API turns it into words, for free. Where it does not exist
//     (Firefox), Whisper runs on the device instead, still engine "browser"
//     (PRD §8.9). Only when that cannot run does the clip go to POST /transcribe
//     (engine "server").
//   - An AnalyserNode notes when speech starts and stops, so "how fast did you
//     say it" measures the words, not the time it took to reach the Stop button.

import { useCallback, useEffect, useRef, useState } from "react";

import { clipToText, preloadWhisper } from "@/lib/voice/browser-whisper";

export interface ShadowTake {
  readonly blob: Blob;
  /** What was heard; empty when no words came through. */
  readonly heardText: string;
  /** First to last loud moment, in ms; null when no speech was detected. */
  readonly speechMs: number | null;
  readonly engine: "browser" | "server";
}

export interface UseShadowRecorderResult {
  readonly recording: boolean;
  /** True while stopping and turning the audio into words. */
  readonly busy: boolean;
  /** Mic level (RMS, roughly 0–0.3) for a simple meter. */
  readonly level: number;
  readonly error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<ShadowTake | null>;
  /** Stop without a result (used when the sentence changes). */
  cancel: () => void;
}

/** RMS above this counts as speech when timing the learner. */
const SPEECH_LEVEL = 0.02;
const METER_MS = 50;
/** How long to wait for the recognizer to hand over its last words. */
const RECOGNITION_GRACE_MS = 1500;
const RECOGNITION_LANG = "en-US";

// Minimal Web Speech API shape. Browsers disagree on the global's name and the
// DOM library does not declare it, so it is typed locally.
interface RecognitionAlternative {
  readonly transcript: string;
}
interface RecognitionResult {
  readonly isFinal: boolean;
  readonly [index: number]: RecognitionAlternative | undefined;
}
interface RecognitionEvent {
  readonly resultIndex?: number;
  readonly results: {
    readonly length: number;
    readonly [index: number]: RecognitionResult | undefined;
  };
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { readonly error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function micError(err: unknown): string {
  const name = (err as DOMException | undefined)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone permission was blocked. Allow it in your browser, then try again.";
  }
  if (name === "NotFoundError") return "No microphone was found on this device.";
  return "Couldn't start the microphone.";
}

export function useShadowRecorder(): UseShadowRecorderResult {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const ctxRef = useRef<AudioContext | null>(null);
  const meterRef = useRef<number | null>(null);
  const firstLoudRef = useRef<number | null>(null);
  const lastLoudRef = useRef<number | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const wantRecognitionRef = useRef(false);
  const finalTextRef = useRef("");
  const interimTextRef = useRef("");
  const recognitionEndedRef = useRef<(() => void) | null>(null);

  /** Free the microphone and the meter. */
  const release = useCallback(() => {
    if (meterRef.current !== null) {
      window.clearInterval(meterRef.current);
      meterRef.current = null;
    }
    void ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setLevel(0);
  }, []);

  const start = useCallback(async () => {
    if (recorderRef.current) return;
    setError(null);
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setError("The microphone needs a secure page (HTTPS).");
      return;
    }
    // Created inside the click, before any await: browsers only let a page run
    // audio right after a user gesture.
    const ctx = new AudioContext();
    ctxRef.current = ctx;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      release();
      setError(micError(err));
      return;
    }
    streamRef.current = stream;
    void ctx.resume().catch(() => undefined);

    // Level meter and speech timing.
    firstLoudRef.current = null;
    lastLoudRef.current = null;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    meterRef.current = window.setInterval(() => {
      analyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += (buffer[i] ?? 0) ** 2;
      const rms = Math.sqrt(sum / buffer.length);
      setLevel(rms);
      if (rms > SPEECH_LEVEL) {
        const now = performance.now();
        firstLoudRef.current ??= now;
        lastLoudRef.current = now;
      }
    }, METER_MS);

    // Keep the audio for A/B playback.
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorderRef.current = recorder;
    recorder.start();

    // Words, for free, where the browser can.
    finalTextRef.current = "";
    interimTextRef.current = "";
    const Ctor = recognitionCtor();
    if (Ctor) {
      const recognition = new Ctor();
      recognition.lang = RECOGNITION_LANG;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex ?? 0; i < event.results.length; i++) {
          const result = event.results[i];
          const text = result?.[0]?.transcript ?? "";
          if (result?.isFinal) finalTextRef.current = `${finalTextRef.current} ${text}`.trim();
          else interim += text;
        }
        interimTextRef.current = interim.trim();
      };
      recognition.onerror = (event) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          wantRecognitionRef.current = false;
          setError("Speech recognition was blocked. Allow the microphone, then try again.");
        }
      };
      recognition.onend = () => {
        // Chrome ends a segment after a pause. Keep listening until Stop.
        if (wantRecognitionRef.current) {
          try {
            recognition.start();
            return;
          } catch {
            // Fall through to a real end.
          }
        }
        recognitionRef.current = null;
        recognitionEndedRef.current?.();
        recognitionEndedRef.current = null;
      };
      wantRecognitionRef.current = true;
      recognitionRef.current = recognition;
      try {
        recognition.start();
      } catch {
        wantRecognitionRef.current = false;
        recognitionRef.current = null;
      }
    } else {
      // No live recognition: load Whisper while the learner speaks.
      preloadWhisper();
    }
    setRecording(true);
  }, [release]);

  const stop = useCallback(async (): Promise<ShadowTake | null> => {
    const recorder = recorderRef.current;
    if (!recorder) return null;
    recorderRef.current = null;
    setRecording(false);
    setBusy(true);

    // Stop both, and wait for each to hand over what it has.
    const audioDone = new Promise<Blob>((resolve) => {
      const finish = () =>
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      if (recorder.state === "inactive") finish();
      else recorder.onstop = finish;
    });
    try {
      recorder.stop();
    } catch {
      // Already stopped.
    }
    const recognition = recognitionRef.current;
    const wordsDone = recognition
      ? new Promise<void>((resolve) => {
          recognitionEndedRef.current = resolve;
          window.setTimeout(resolve, RECOGNITION_GRACE_MS);
        })
      : Promise.resolve();
    wantRecognitionRef.current = false;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        // Not started.
      }
    }

    const [blob] = await Promise.all([audioDone, wordsDone]);
    const first = firstLoudRef.current;
    const last = lastLoudRef.current;
    const speechMs = first !== null && last !== null ? Math.round(last - first) : null;
    release();

    try {
      if (recognition) {
        // A short sentence can end before Chrome finalises it: keep the interim words.
        const heardText = (finalTextRef.current || interimTextRef.current).trim();
        return { blob, heardText, speechMs, engine: "browser" };
      }
      const result = await clipToText(blob, "en");
      // Whisper on the device is still speech-to-text in the browser.
      const engine = result.engine === "device" ? "browser" : "server";
      return { blob, heardText: result.text, speechMs, engine };
    } catch (err) {
      setError(`Couldn't check your words: ${(err as Error).message}`);
      return { blob, heardText: "", speechMs, engine: recognition ? "browser" : "server" };
    } finally {
      setBusy(false);
    }
  }, [release]);

  const cancel = useCallback(() => {
    wantRecognitionRef.current = false;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try {
        recognition.abort();
      } catch {
        // Not started.
      }
    }
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      try {
        recorder.stop();
      } catch {
        // Already stopped.
      }
    }
    release();
    setRecording(false);
    setBusy(false);
  }, [release]);

  // Never leave the microphone on after the screen closes.
  useEffect(() => cancel, [cancel]);

  return { recording, busy, level, error, start, stop, cancel };
}
