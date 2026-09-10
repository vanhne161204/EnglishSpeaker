// PCM helpers for the AI voice coach (PRD §8.12).
//
// Gemini Live speaks raw 16-bit little-endian PCM both ways. It takes the mic at
// any sample rate (it resamples) and always answers at 24 kHz. The Web Audio API
// works in Float32 samples, so these convert between the two, and hold the tiny
// AudioWorklet that taps the microphone.

/** Gemini Live always answers at this rate. */
export const OUTPUT_SAMPLE_RATE = 24_000;

/** The AudioWorklet registers under this name. */
export const MIC_WORKLET_NAME = "mic-chunker";

// Batches mic samples into ~100 ms chunks and reports each chunk's level (RMS).
// It runs on the audio thread, so it is plain JavaScript in a string, loaded from
// a Blob URL — no extra file to wire into the build.
const MIC_WORKLET_SOURCE = `
class MicChunker extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = Math.round(sampleRate / 10);
    this.buf = new Float32Array(this.size);
    this.len = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    let i = 0;
    while (i < channel.length) {
      const n = Math.min(channel.length - i, this.size - this.len);
      this.buf.set(channel.subarray(i, i + n), this.len);
      this.len += n;
      i += n;
      if (this.len === this.size) {
        let sum = 0;
        for (let k = 0; k < this.size; k++) sum += this.buf[k] * this.buf[k];
        const level = Math.sqrt(sum / this.size);
        this.port.postMessage({ samples: this.buf, level }, [this.buf.buffer]);
        this.buf = new Float32Array(this.size);
        this.len = 0;
      }
    }
    return true;
  }
}
registerProcessor("${MIC_WORKLET_NAME}", MicChunker);
`;

/** Register the mic worklet on an AudioContext. */
export async function loadMicWorklet(ctx: AudioContext): Promise<void> {
  const url = URL.createObjectURL(
    new Blob([MIC_WORKLET_SOURCE], { type: "application/javascript" }),
  );
  try {
    await ctx.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Float32 samples in [-1, 1] → base64 of 16-bit little-endian PCM. */
export function floatToPcm16Base64(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  // Build the binary string in slices: spreading a whole chunk at once can
  // overflow the call stack on long buffers.
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** base64 of 16-bit little-endian PCM → Float32 samples in [-1, 1]. */
export function pcm16Base64ToFloat(b64: string): Float32Array<ArrayBuffer> {
  const binary = atob(b64);
  const count = Math.floor(binary.length / 2);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    let value = binary.charCodeAt(i * 2) | (binary.charCodeAt(i * 2 + 1) << 8);
    if (value >= 0x8000) value -= 0x10000;
    out[i] = value / 0x8000;
  }
  return out;
}
