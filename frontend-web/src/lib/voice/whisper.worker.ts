// Whisper on the learner's device (PRD §8.9), in a background thread.
//
// It cannot run on the main thread: one Whisper pass over a 5-second clip keeps
// a CPU core busy for about a second, and on the main thread that is a frozen page.
//
// transformers.js is loaded from the jsDelivr CDN when the worker starts, not
// bundled. The npm package pulls in ~350 MB of Node-only dependencies
// (onnxruntime-node, sharp) that every Cloudflare build would have to install.
// Its wasm runtime comes from jsDelivr either way. The version is pinned, so the
// file behind the URL never changes.

const TRANSFORMERS_URL =
  "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0/dist/transformers.min.js";

/** What the page asks of the worker. */
export type WorkerRequest =
  | { type: "load"; model: string }
  | { type: "transcribe"; id: number; audio: Float32Array };

/** What the worker tells the page. */
export type WorkerResponse =
  | { type: "progress"; progress: number }
  | { type: "ready" }
  | { type: "failed"; message: string }
  | { type: "result"; id: number; text: string }
  | { type: "error"; id: number; message: string };

// The slice of transformers.js used here. Typed locally: the library is not an
// npm dependency, so its own types are not installed.
interface ProgressInfo {
  readonly status: string;
  /** 0–100, on "progress_total": all model files together. */
  readonly progress?: number;
}
type Recognizer = (
  audio: Float32Array,
  options?: { chunk_length_s?: number },
) => Promise<{ text: string } | { text: string }[]>;
interface TransformersModule {
  env: { allowLocalModels: boolean };
  pipeline: (
    task: "automatic-speech-recognition",
    model: string,
    options: {
      dtype: string;
      device: string;
      session_options?: { graphOptimizationLevel: "disabled" | "basic" | "extended" | "all" };
      progress_callback?: (info: ProgressInfo) => void;
    },
  ) => Promise<Recognizer>;
}

// The DOM library types `self` as a Window, whose postMessage wants a target
// origin. Adding the WebWorker library instead clashes with DOM in this project,
// so only the two members used are typed.
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null;
  postMessage: (message: WorkerResponse) => void;
};

let recognizer: Promise<Recognizer> | null = null;
// ONNX Runtime runs one inference at a time, so clips wait their turn.
let queue: Promise<unknown> = Promise.resolve();

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function load(model: string): Promise<Recognizer> {
  recognizer ??= (async () => {
    const lib = (await import(/* @vite-ignore */ TRANSFORMERS_URL)) as TransformersModule;
    // Models come from Hugging Face only. Looking on our own origin first would
    // be a 404 per file through Cloudflare.
    lib.env.allowLocalModels = false;
    return lib.pipeline("automatic-speech-recognition", model, {
      // 8-bit weights: about a quarter of the full size, and the same words on
      // short English clips. Plain wasm runs everywhere; WebGPU does not yet.
      dtype: "q8",
      device: "wasm",
      // The ONNX Runtime inside transformers.js 4.x (1.25/1.26 dev builds) cannot
      // build the 8-bit Whisper decoder with its full graph optimisations: "Missing
      // required scale ... TransposeDQWeightsForMatMulNBits". "basic" skips that
      // pass. Tested in Chrome on 2026-09-12: same words, and the same speed as
      // transformers.js 3.8.1 with full optimisations.
      session_options: { graphOptimizationLevel: "basic" },
      progress_callback: (info) => {
        if (info.status === "progress_total" && typeof info.progress === "number") {
          scope.postMessage({ type: "progress", progress: info.progress });
        }
      },
    });
  })();
  return recognizer;
}

async function transcribe(audio: Float32Array): Promise<string> {
  if (!recognizer) throw new Error("The speech model is not loaded.");
  const run = await recognizer;
  // Whisper hears 30 seconds at a time; longer clips are cut into windows.
  const output = await run(audio, { chunk_length_s: 30 });
  return Array.isArray(output) ? output.map((part) => part.text).join(" ") : output.text;
}

scope.onmessage = (event) => {
  const request = event.data;
  if (request.type === "load") {
    load(request.model).then(
      () => scope.postMessage({ type: "ready" }),
      (err: unknown) => {
        recognizer = null;
        scope.postMessage({ type: "failed", message: messageOf(err) });
      },
    );
    return;
  }
  const { id, audio } = request;
  queue = queue.then(() =>
    transcribe(audio).then(
      (text) => scope.postMessage({ type: "result", id, text }),
      (err: unknown) => scope.postMessage({ type: "error", id, message: messageOf(err) }),
    ),
  );
};
