// Turn a MediaRecorder clip (webm/opus in Chrome and Firefox, mp4/aac in Safari)
// into the one format Azure pronunciation assessment takes over REST: WAV,
// 16-bit PCM, 16 kHz, mono (PRD §8.14 Phase 2). Done in the browser with the Web
// Audio API, so the server needs no audio codecs and never decodes anything.

/** Azure's REST format for pronunciation assessment. */
export const ASSESS_SAMPLE_RATE = 16_000;
/** Azure takes at most 30 seconds for pronunciation assessment. */
export const ASSESS_MAX_SECONDS = 30;

/** Decode any clip the browser can play and re-encode it as 16 kHz mono WAV. */
export async function toWav16kMono(clip: Blob): Promise<Blob> {
  const encoded = await clip.arrayBuffer();
  // An OfflineAudioContext can decode without a user gesture or an audio device.
  const decoder = new OfflineAudioContext(1, 1, ASSESS_SAMPLE_RATE);
  const decoded = await decoder.decodeAudioData(encoded);

  const seconds = Math.min(decoded.duration, ASSESS_MAX_SECONDS);
  const length = Math.max(1, Math.ceil(seconds * ASSESS_SAMPLE_RATE));
  // One output channel at 16 kHz: the browser resamples, and mixes stereo down.
  const renderer = new OfflineAudioContext(1, length, ASSESS_SAMPLE_RATE);
  const source = renderer.createBufferSource();
  source.buffer = decoded;
  source.connect(renderer.destination);
  source.start();
  const rendered = await renderer.startRendering();
  return encodeWav(rendered.getChannelData(0), ASSESS_SAMPLE_RATE);
}

/** Float32 samples in [-1, 1] → a 16-bit PCM mono WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}
