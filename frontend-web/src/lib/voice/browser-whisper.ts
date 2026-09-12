// Whisper on the learner's device (PRD §8.9): the record-then-text path for the
// room mic, the Warm-up mic, and Shadowing in a browser without live recognition.
//
// One worker per tab, made on first use and kept. The model is about 41 MB, and
// loading it again for every clip would cost more than the transcription.
//
// The server's POST /transcribe stays as the fallback. It is used while the model
// is still downloading (the learner's very first clip), when the device cannot
// run it, or for a language other than English. So nobody waits on a download
// to get their text.

import { useSyncExternalStore } from "react";

import { transcribe } from "@/lib/api";

import { decode16kMono } from "./wav16k";
import type { WorkerRequest, WorkerResponse } from "./whisper.worker";

/**
 * - off: this device will not run it (no Worker/WebAssembly, or Data Saver is on).
 * - idle: not asked for yet. loading → ready, or failed for the rest of the tab.
 */
export type WhisperState = "off" | "idle" | "loading" | "ready" | "failed";

export interface WhisperStatus {
  readonly state: WhisperState;
  /** Download progress, 0–100, while loading. */
  readonly progress: number;
  readonly model: string | null;
}

export interface ClipText {
  readonly text: string;
  /** "device" = Whisper in this browser; "server" = POST /transcribe. */
  readonly engine: "device" | "server";
}

// English only: more accurate on English than the multilingual model of the same
// size. tiny, not base: in Chrome on a laptop (2026-09-12), tiny turned a 6-second
// clip into text in about 1.5 s against 3–6 s for base, with the same words, and
// it is half the download (8-bit files: 41 MB against 77 MB). The server fallback
// runs tiny as well.
const MODEL = "onnx-community/whisper-tiny.en";

/** Longest clip decoded for Whisper. A room message is a few sentences. */
const MAX_CLIP_SECONDS = 120;
/** A slow device should not hold the learner's text hostage: use the server. */
const DEVICE_TIMEOUT_MS = 30_000;

const SERVER_RENDER: WhisperStatus = { state: "idle", progress: 0, model: null };

let status: WhisperStatus = SERVER_RENDER;
const listeners = new Set<() => void>();
let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, { resolve: (text: string) => void; reject: (e: Error) => void }>();

function setStatus(next: Partial<WhisperStatus>): void {
  status = { ...status, ...next };
  listeners.forEach((listener) => listener());
}

/** Can this device run Whisper at all? Checked before any download starts. */
export function browserWhisperSupported(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof Worker === "undefined" || typeof WebAssembly !== "object") return false;
  if (typeof OfflineAudioContext === "undefined") return false;
  // Data Saver asks sites not to pull large files; 41 MB is large.
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return !connection?.saveData;
}

function fail(message: string): void {
  console.warn(`On-device speech-to-text is off for this tab: ${message}`);
  worker?.terminate();
  worker = null;
  pending.forEach(({ reject }) => reject(new Error(message)));
  pending.clear();
  setStatus({ state: "failed", progress: 0 });
}

function handle(message: WorkerResponse): void {
  switch (message.type) {
    case "progress": {
      const progress = Math.floor(message.progress);
      if (progress !== status.progress) setStatus({ progress });
      break;
    }
    case "ready":
      setStatus({ state: "ready", progress: 100 });
      break;
    case "failed":
      fail(message.message);
      break;
    case "result":
      pending.get(message.id)?.resolve(message.text);
      pending.delete(message.id);
      break;
    case "error":
      pending.get(message.id)?.reject(new Error(message.message));
      pending.delete(message.id);
      break;
  }
}

/**
 * Start loading the model, once per tab. Call it when recording starts: the
 * download (or the load from the browser's cache) then runs while the learner
 * speaks.
 */
export function preloadWhisper(): void {
  if (worker || status.state === "failed" || status.state === "off") return;
  if (!browserWhisperSupported()) {
    setStatus({ state: "off" });
    return;
  }
  const model = MODEL;
  try {
    worker = new Worker(new URL("./whisper.worker.ts", import.meta.url), { type: "module" });
  } catch (err) {
    fail((err as Error).message);
    return;
  }
  worker.onmessage = (event: MessageEvent<WorkerResponse>) => handle(event.data);
  // A crash (out of memory, the CDN unreachable) lands here, not in "failed".
  worker.onerror = (event) => {
    event.preventDefault();
    fail(event.message || "the speech worker stopped");
  };
  setStatus({ state: "loading", progress: 0, model });
  worker.postMessage({ type: "load", model } satisfies WorkerRequest);
}

async function runOnDevice(clip: Blob): Promise<string> {
  const target = worker;
  if (!target || status.state !== "ready") throw new Error("The speech model is not ready.");
  const audio = await decode16kMono(clip, MAX_CLIP_SECONDS);
  const id = nextId++;
  return new Promise<string>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pending.delete(id);
      reject(new Error("The speech model took too long."));
    }, DEVICE_TIMEOUT_MS);
    pending.set(id, {
      resolve: (text) => {
        window.clearTimeout(timer);
        resolve(text);
      },
      reject: (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    });
    // Hand the samples over instead of copying them.
    target.postMessage({ type: "transcribe", id, audio } satisfies WorkerRequest, [audio.buffer]);
  });
}

/** Whisper writes sound tags ("[BLANK_AUDIO]", "(music)") for audio without words. */
export function cleanWhisperText(text: string): string {
  return text
    .replace(/\[[^\]]*\]|\([^)]*\)/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Turn a recorded clip into text: on the device when the model is ready, else on
 * the server. Empty text means no words were heard.
 *
 * @param language - BCP-47 hint. The on-device models are English only, so any
 *   other language goes to the server.
 */
export async function clipToText(clip: Blob, language?: string): Promise<ClipText> {
  const english = !language || language.toLowerCase().startsWith("en");
  if (english) {
    preloadWhisper();
    if (status.state === "ready") {
      try {
        return { text: cleanWhisperText(await runOnDevice(clip)), engine: "device" };
      } catch (err) {
        console.warn("On-device speech-to-text failed for this clip; using the server.", err);
      }
    }
  }
  const result = await transcribe(clip, language);
  return { text: result.text.trim(), engine: "server" };
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The model's state, for a download hint in the UI. */
export function useWhisperStatus(): WhisperStatus {
  return useSyncExternalStore(
    subscribe,
    () => status,
    () => SERVER_RENDER,
  );
}
