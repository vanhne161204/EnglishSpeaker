// Real-time voice disguise for incognito rooms (PRD §7.2 / §8.3).
//
// Incognito mode promises anonymity — but a raw microphone exposes a user's real
// voice and accent, which undermines that promise and keeps shy beginners from
// speaking. This module transforms the local mic in real time so the person is
// not identifiable, offering a few selectable "filters" (see VOICE_FILTERS).
//
// Pitch filters use the classic "Jungle" pitch shifter (Chris Wilson): two delay
// lines whose delay times are modulated by looping ramp buffers and cross-faded,
// which shifts pitch without any external library and with low latency. "Robot"
// uses ring modulation. We only ever transform the *outbound* stream sent to
// peers; the raw capture stream is kept for muting and the local speaking meter,
// so those still reflect the user's real voice.

/** Selectable voice filters, shared by the incognito setup UI and the audio engine. */
export type VoiceFilterId = "none" | "deep" | "bright" | "robot" | "chipmunk" | "whisper";

export interface VoiceFilterMeta {
  readonly id: VoiceFilterId;
  readonly label: string;
  readonly emoji: string;
  readonly desc: string;
}

/** Filter presets shown in the incognito setup modal (order = display order). */
export const VOICE_FILTERS: readonly VoiceFilterMeta[] = [
  { id: "none", label: "Natural", emoji: "🎙️", desc: "Your real voice" },
  { id: "deep", label: "Deep", emoji: "🐻", desc: "Lower pitch, warm tone" },
  { id: "bright", label: "Bright", emoji: "🌟", desc: "Higher, clearer tone" },
  { id: "robot", label: "Robot", emoji: "🤖", desc: "Synthetic voice mask" },
  { id: "chipmunk", label: "Chipmunk", emoji: "🐿️", desc: "Fast, high pitch" },
  { id: "whisper", label: "Whisper", emoji: "🌬️", desc: "Soft & breathy" },
];

/** Look up a filter's label (falls back to the id for unknown values). */
export function voiceFilterLabel(id: VoiceFilterId): string {
  return VOICE_FILTERS.find((f) => f.id === id)?.label ?? id;
}

/** Per-filter audio config. `pitch` is a fraction of an octave; `robot` = ring-mod Hz. */
const FILTER_CONFIG: Record<
  Exclude<VoiceFilterId, "none">,
  { pitch?: number; lowpass?: number; robot?: number }
> = {
  deep: { pitch: -0.45 },
  bright: { pitch: 0.35 },
  chipmunk: { pitch: 0.65 },
  whisper: { pitch: -0.12, lowpass: 2500 },
  robot: { robot: 55 },
};

const DELAY_TIME = 0.1; // base delay line length, seconds
const FADE_TIME = 0.05; // cross-fade between the two delay lines, seconds
const BUFFER_TIME = 0.1; // modulation buffer length, seconds

export interface VoiceMask {
  /** A MediaStream carrying the single, disguised audio track to send to peers. */
  readonly stream: MediaStream;
  /** Tear down the audio graph (stop the modulation sources, disconnect nodes). */
  disconnect: () => void;
}

/**
 * Build a voice-disguise graph over a captured microphone stream.
 *
 * @param ctx - A running {@link AudioContext} (shared with the speaking meter).
 * @param input - The raw microphone {@link MediaStream}.
 * @param filter - Which disguise to apply; `"none"` yields no transformation.
 * @returns The masked output stream plus a {@link VoiceMask.disconnect} teardown.
 */
export function createVoiceMask(
  ctx: AudioContext,
  input: MediaStream,
  filter: VoiceFilterId,
): VoiceMask {
  const source = ctx.createMediaStreamSource(input);
  const destination = ctx.createMediaStreamDestination();
  const teardown: Array<() => void> = [
    () => {
      try {
        source.disconnect();
      } catch {
        /* already gone */
      }
    },
  ];

  if (filter === "none") {
    // No transformation — pass the raw mic straight through.
    source.connect(destination);
  } else if (FILTER_CONFIG[filter].robot) {
    // Ring modulation: multiply the voice by a low-frequency carrier.
    const ring = ctx.createGain();
    ring.gain.value = 0;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = FILTER_CONFIG[filter].robot!;
    osc.connect(ring.gain);
    source.connect(ring);
    ring.connect(destination);
    osc.start();
    teardown.push(() => {
      try {
        osc.stop();
        ring.disconnect();
      } catch {
        /* already gone */
      }
    });
  } else {
    // Pitch shift (optionally softened by a low-pass for "whisper").
    const cfg = FILTER_CONFIG[filter];
    const jungle = new Jungle(ctx);
    jungle.setPitchOffset(cfg.pitch ?? 0);
    source.connect(jungle.input);

    let tail: AudioNode = jungle.output;
    if (cfg.lowpass) {
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = cfg.lowpass;
      jungle.output.connect(lp);
      tail = lp;
      teardown.push(() => {
        try {
          lp.disconnect();
        } catch {
          /* already gone */
        }
      });
    }
    tail.connect(destination);
    teardown.push(() => jungle.stop());
  }

  return {
    stream: destination.stream,
    disconnect: () => {
      for (const fn of teardown) fn();
    },
  };
}

/** A looping ramp that modulates a delay line's delay time (one shift period). */
function createDelayTimeBuffer(ctx: AudioContext, shiftUp: boolean): AudioBuffer {
  const length1 = Math.floor(BUFFER_TIME * ctx.sampleRate);
  const length2 = Math.floor((BUFFER_TIME - 2 * FADE_TIME) * ctx.sampleRate);
  const length = length1 + length2;
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const p = buffer.getChannelData(0);
  for (let i = 0; i < length1; ++i) {
    p[i] = shiftUp ? (length1 - i) / length : i / length1;
  }
  for (let i = length1; i < length; ++i) p[i] = 0;
  return buffer;
}

/** A looping equal-power cross-fade envelope for one delay line. */
function createFadeBuffer(ctx: AudioContext): AudioBuffer {
  const length1 = Math.floor(BUFFER_TIME * ctx.sampleRate);
  const length2 = Math.floor((BUFFER_TIME - 2 * FADE_TIME) * ctx.sampleRate);
  const length = length1 + length2;
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const p = buffer.getChannelData(0);
  const fadeLength = Math.floor(FADE_TIME * ctx.sampleRate);
  const fadeIndex2 = length1 - fadeLength;
  for (let i = 0; i < length1; ++i) {
    if (i < fadeLength) p[i] = Math.sqrt(i / fadeLength);
    else if (i >= fadeIndex2) p[i] = Math.sqrt(1 - (i - fadeIndex2) / fadeLength);
    else p[i] = 1;
  }
  for (let i = length1; i < length; ++i) p[i] = 0;
  return buffer;
}

/**
 * The Jungle pitch shifter: two delay lines, modulated a half period apart and
 * cross-faded, so the output pitch is shifted continuously without clicks.
 */
class Jungle {
  readonly input: GainNode;
  readonly output: GainNode;

  private readonly mod1Gain: GainNode;
  private readonly mod2Gain: GainNode;
  private readonly mod3Gain: GainNode;
  private readonly mod4Gain: GainNode;
  private readonly sources: AudioBufferSourceNode[];

  constructor(ctx: AudioContext) {
    this.input = ctx.createGain();
    this.output = ctx.createGain();

    const shiftDown = createDelayTimeBuffer(ctx, false);
    const shiftUp = createDelayTimeBuffer(ctx, true);
    const fadeBuffer = createFadeBuffer(ctx);

    // Delay-time modulators: mod1/2 drive the "shift down" ramp, mod3/4 "shift up".
    const mod1 = ctx.createBufferSource();
    const mod2 = ctx.createBufferSource();
    const mod3 = ctx.createBufferSource();
    const mod4 = ctx.createBufferSource();
    mod1.buffer = shiftDown;
    mod2.buffer = shiftDown;
    mod3.buffer = shiftUp;
    mod4.buffer = shiftUp;
    for (const m of [mod1, mod2, mod3, mod4]) m.loop = true;

    this.mod1Gain = ctx.createGain();
    this.mod2Gain = ctx.createGain();
    this.mod3Gain = ctx.createGain();
    this.mod4Gain = ctx.createGain();
    mod1.connect(this.mod1Gain);
    mod2.connect(this.mod2Gain);
    mod3.connect(this.mod3Gain);
    mod4.connect(this.mod4Gain);

    const delay1 = ctx.createDelay();
    const delay2 = ctx.createDelay();
    this.mod1Gain.connect(delay1.delayTime);
    this.mod2Gain.connect(delay2.delayTime);
    this.mod3Gain.connect(delay1.delayTime);
    this.mod4Gain.connect(delay2.delayTime);

    // Cross-fade envelopes that alternate which delay line is heard.
    const fade1 = ctx.createBufferSource();
    const fade2 = ctx.createBufferSource();
    fade1.buffer = fadeBuffer;
    fade2.buffer = fadeBuffer;
    fade1.loop = true;
    fade2.loop = true;

    const mix1 = ctx.createGain();
    const mix2 = ctx.createGain();
    mix1.gain.value = 0;
    mix2.gain.value = 0;
    fade1.connect(mix1.gain);
    fade2.connect(mix2.gain);

    this.input.connect(delay1);
    this.input.connect(delay2);
    delay1.connect(mix1);
    delay2.connect(mix2);
    mix1.connect(this.output);
    mix2.connect(this.output);

    // Start the second line half a period after the first so they cross-fade.
    const t = ctx.currentTime + 0.05;
    const t2 = t + BUFFER_TIME - FADE_TIME;
    mod1.start(t);
    mod2.start(t2);
    mod3.start(t);
    mod4.start(t2);
    fade1.start(t);
    fade2.start(t2);

    this.sources = [mod1, mod2, mod3, mod4, fade1, fade2];
  }

  /** Set the pitch offset as a fraction of an octave (negative lowers the voice). */
  setPitchOffset(mult: number): void {
    const amount = 0.5 * DELAY_TIME * Math.abs(mult);
    const up = mult > 0;
    // Enable the ramp pair matching the direction; silence the other.
    this.mod1Gain.gain.value = up ? 0 : amount;
    this.mod2Gain.gain.value = up ? 0 : amount;
    this.mod3Gain.gain.value = up ? amount : 0;
    this.mod4Gain.gain.value = up ? amount : 0;
  }

  /** Stop the looping modulation/fade sources (call once, on teardown). */
  stop(): void {
    for (const s of this.sources) {
      try {
        s.stop();
      } catch {
        // Already stopped, or never started — safe to ignore.
      }
    }
  }
}
