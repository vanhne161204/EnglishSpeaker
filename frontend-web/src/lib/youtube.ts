// YouTube's IFrame Player API, for Shadowing video lessons (PRD §8.14 Phase 4).
//
// The video always plays in YouTube's own player, visible and uncovered:
// YouTube's Developer Policies forbid hiding the player or separating its sound.
// The page only uses the documented controls: seek, play, pause, and speed.

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

/** The slice of YouTube's player object used here. */
export interface YouTubePlayer {
  playVideo(): void;
  pauseVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  setPlaybackRate(rate: number): void;
  destroy(): void;
}

interface PlayerOptions {
  videoId: string;
  host?: string;
  width?: string | number;
  height?: string | number;
  playerVars?: Record<string, string | number>;
  events?: {
    onReady?: (event: { target: YouTubePlayer }) => void;
    onStateChange?: (event: { data: number }) => void;
    onError?: (event: { data: number }) => void;
  };
}

interface YouTubeNamespace {
  Player: new (element: HTMLElement, options: PlayerOptions) => YouTubePlayer;
}

declare global {
  interface Window {
    YT?: YouTubeNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** YouTube's player states (the `data` of onStateChange). */
export const PLAYER_STATE = { unstarted: -1, ended: 0, playing: 1, paused: 2 } as const;

const API_URL = "https://www.youtube.com/iframe_api";
/** Privacy-enhanced mode: YouTube sets no cookies until the video is played. */
const PLAYER_HOST = "https://www.youtube-nocookie.com";

let loading: Promise<YouTubeNamespace> | null = null;

/** Load YouTube's player script once per page. */
export function loadYouTubeApi(): Promise<YouTubeNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  loading ??= new Promise<YouTubeNamespace>((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = API_URL;
    script.async = true;
    script.onerror = () => {
      loading = null;
      script.remove();
      reject(new Error("Couldn't load the YouTube player. Check your connection."));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export function youtubeErrorMessage(code: number): string {
  if (code === 101 || code === 150) {
    return "The video's owner does not allow it to be played on other sites. Pick another video.";
  }
  if (code === 100) return "This video was removed or is private.";
  if (code === 2) return "That is not a valid YouTube video.";
  return "YouTube couldn't play this video.";
}

export function youtubeThumbnail(youtubeId: string): string {
  return `https://i.ytimg.com/vi/${youtubeId}/mqdefault.jpg`;
}

/** 83 456 ms → "1:23.4" (or "1:23" without tenths). */
export function formatClock(ms: number, tenths = true): string {
  const total = Math.max(0, ms) / 1000;
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  const whole = Math.floor(seconds);
  const base = `${minutes}:${String(whole).padStart(2, "0")}`;
  return tenths ? `${base}.${Math.floor((seconds - whole) * 10)}` : base;
}

/** "1:23.4", "0:05" or "83.4" → milliseconds; null if it is not a time. */
export function parseClock(text: string): number | null {
  const clean = text.trim();
  const parts = clean.split(":");
  if (!clean || parts.length > 3) return null;
  let seconds = 0;
  for (const part of parts) {
    if (!/^\d+(\.\d+)?$/.test(part)) return null;
    seconds = seconds * 60 + Number(part);
  }
  return Math.round(seconds * 1000);
}

export interface YouTubePlayerHandle {
  /** Put this on an empty element; the player's iframe goes inside it. */
  readonly containerRef: RefObject<HTMLDivElement | null>;
  /** Set once the player is ready to take commands. */
  readonly player: YouTubePlayer | null;
  /** One of PLAYER_STATE (or YouTube's other states). */
  readonly state: number;
  readonly error: string | null;
}

/** An embedded YouTube player for one video. */
export function useYouTubePlayer(youtubeId: string | null): YouTubePlayerHandle {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [player, setPlayer] = useState<YouTubePlayer | null>(null);
  const [state, setState] = useState<number>(PLAYER_STATE.unstarted);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !youtubeId) return;
    let cancelled = false;
    let created: YouTubePlayer | null = null;
    setPlayer(null);
    setError(null);
    setState(PLAYER_STATE.unstarted);
    // YouTube replaces the element it is given with an iframe. Give it a child
    // React does not manage, so React never trips over the swap.
    const mount = document.createElement("div");
    container.appendChild(mount);
    loadYouTubeApi().then(
      (YT) => {
        if (cancelled) return;
        created = new YT.Player(mount, {
          videoId: youtubeId,
          host: PLAYER_HOST,
          width: "100%",
          height: "100%",
          playerVars: { playsinline: 1, rel: 0, origin: window.location.origin },
          events: {
            onReady: (event) => !cancelled && setPlayer(event.target),
            onStateChange: (event) => !cancelled && setState(event.data),
            onError: (event) => !cancelled && setError(youtubeErrorMessage(event.data)),
          },
        });
      },
      (err: Error) => !cancelled && setError(err.message),
    );
    return () => {
      cancelled = true;
      created?.destroy();
      container.replaceChildren();
    };
  }, [youtubeId]);

  return { containerRef, player, state, error };
}

export interface SegmentPlayback {
  /** Where the video is, in ms, to the nearest 100 ms. Updates while it plays. */
  readonly nowMs: number;
  /** Play from `startMs`, and pause at `endMs` when it is given. */
  playRange: (startMs: number, endMs: number | null) => void;
  pause: () => void;
  /** The exact current time in ms, for marking where a sentence starts or ends. */
  currentMs: () => number;
}

const POLL_MS = 50;
/** Pause a little early: the poll can be up to POLL_MS late. */
const STOP_EARLY_MS = 30;
/** Jumping this far past the end means the viewer moved on: don't pause. */
const JUMPED_MS = 1500;

/** Play one stretch of a video and pause at its end ("Stop after each sentence"). */
export function useSegmentPlayback(player: YouTubePlayer | null): SegmentPlayback {
  const rangeRef = useRef<{ start: number; end: number; arrived: boolean } | null>(null);
  const [nowMs, setNowMs] = useState(0);

  useEffect(() => {
    if (!player) return;
    const timer = window.setInterval(() => {
      let t: number;
      try {
        t = player.getCurrentTime() * 1000;
      } catch {
        return; // the player is being destroyed
      }
      setNowMs(Math.floor(t / 100) * 100);
      const range = rangeRef.current;
      if (!range) return;
      // seekTo is not instant: until the player has reached the range, the old
      // position (maybe past the end) must not count as "the end".
      if (!range.arrived) {
        if (t >= range.start - 250 && t < range.end - STOP_EARLY_MS) range.arrived = true;
      } else if (t > range.end + JUMPED_MS) {
        rangeRef.current = null;
      } else if (t >= range.end - STOP_EARLY_MS) {
        rangeRef.current = null;
        player.pauseVideo();
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [player]);

  const playRange = useCallback(
    (startMs: number, endMs: number | null) => {
      if (!player) return;
      rangeRef.current = endMs === null ? null : { start: startMs, end: endMs, arrived: false };
      player.seekTo(startMs / 1000, true);
      player.playVideo();
    },
    [player],
  );

  const pause = useCallback(() => {
    rangeRef.current = null;
    player?.pauseVideo();
  }, [player]);

  const currentMs = useCallback(() => (player ? player.getCurrentTime() * 1000 : 0), [player]);

  return useMemo(
    () => ({ nowMs, playRange, pause, currentMs }),
    [nowMs, playRange, pause, currentMs],
  );
}
