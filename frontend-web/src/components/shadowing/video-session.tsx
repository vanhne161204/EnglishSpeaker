// One Shadowing video lesson (PRD §8.14 Phase 4): real speech from a YouTube
// video, one sentence at a time. The video plays in YouTube's own player, always
// visible (YouTube's Developer Policies); this page only seeks, pauses, and sets
// the speed. The word score is a WORD MATCH, never "pronunciation".

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  assessPronunciation,
  scoreShadowingAttempt,
  shadowingVideoLesson,
  type PronunciationResult,
  type ShadowingResult,
  type ShadowingVideoCard,
  type ShadowingVideoLesson,
} from "@/lib/api";
import { levelLabel } from "@/lib/presentation";
import { useShadowRecorder, type ShadowTake } from "@/lib/voice/use-shadow-recorder";
import { toWav16kMono } from "@/lib/voice/wav16k";
import { formatClock, PLAYER_STATE, useSegmentPlayback, useYouTubePlayer } from "@/lib/youtube";

import { LevelMeter, PronunciationCheck, WordMatchCard } from "./result-parts";

type Speed = 1 | 0.75;
/** stop = pause at the end of each sentence; on = keep playing, the list follows. */
type Mode = "stop" | "on";

export function VideoSession({ video, onExit }: { video: ShadowingVideoCard; onExit: () => void }) {
  const queryClient = useQueryClient();
  const lessonKey = ["shadowing-video", video.id] as const;
  const lessonQ = useQuery({
    queryKey: lessonKey,
    queryFn: () => shadowingVideoLesson(video.id),
  });
  const recorder = useShadowRecorder();
  const cancelRecording = recorder.cancel;
  const yt = useYouTubePlayer(video.youtube_id);
  const playback = useSegmentPlayback(yt.player);

  const [index, setIndex] = useState(0);
  const [speed, setSpeed] = useState<Speed>(1);
  const [mode, setMode] = useState<Mode>("stop");
  const [showText, setShowText] = useState(true);
  const [showMeaning, setShowMeaning] = useState(false);
  const [take, setTake] = useState<ShadowTake | null>(null);
  const [takeUrl, setTakeUrl] = useState<string | null>(null);
  const [result, setResult] = useState<ShadowingResult | null>(null);
  const [scoring, setScoring] = useState(false);
  const [check, setCheck] = useState<PronunciationResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const takeRef = useRef<HTMLAudioElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const activeRowRef = useRef<HTMLButtonElement | null>(null);

  const lesson = lessonQ.data;
  // Stable between renders, so the "Play on" effect below does not run for nothing.
  const items = useMemo(() => lesson?.items ?? [], [lesson]);
  const item = items[index];
  const itemKey = item?.key;
  const assessEnabled = lesson?.assess_enabled ?? false;
  const checksLeft = lesson?.assess_remaining ?? 0;
  const playing = yt.state === PLAYER_STATE.playing;

  // A fresh start for every sentence.
  useEffect(() => {
    cancelRecording();
    setTake(null);
    setResult(null);
    setCheck(null);
    setNotice(null);
  }, [itemKey, cancelRecording]);

  // The learner's own try, playable next to the sentence in the video.
  useEffect(() => {
    if (!take) {
      setTakeUrl(null);
      return;
    }
    const url = URL.createObjectURL(take.blob);
    setTakeUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [take]);

  // The speed is the YouTube player's own setting.
  useEffect(() => {
    yt.player?.setPlaybackRate(speed);
  }, [yt.player, speed]);

  // "Play on": the current sentence follows the video.
  useEffect(() => {
    if (mode !== "on" || !playing) return;
    let current = -1;
    for (let i = 0; i < items.length; i++) {
      if (items[i].start_ms > playback.nowMs + 50) break;
      current = i;
    }
    if (current >= 0 && current !== index) setIndex(current);
  }, [mode, playing, playback.nowMs, items, index]);

  // Keep the current sentence in view inside the list (never scroll the page).
  useEffect(() => {
    const list = listRef.current;
    const row = activeRowRef.current;
    if (!list || !row) return;
    const top = row.offsetTop;
    if (top < list.scrollTop || top + row.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
    }
  }, [index]);

  const playSentence = (at: number = index) => {
    const target = items[at];
    if (!target || !yt.player) return;
    takeRef.current?.pause();
    if (at !== index) setIndex(at);
    playback.playRange(target.start_ms, mode === "stop" ? target.end_ms : null);
  };

  const playTake = () => {
    playback.pause();
    const audio = takeRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    void audio.play().catch(() => undefined);
  };

  const startTake = async () => {
    // The video would leak into the microphone.
    playback.pause();
    takeRef.current?.pause();
    setResult(null);
    setCheck(null);
    setTake(null);
    setNotice(null);
    await recorder.start();
  };

  const finishTake = async () => {
    const got = await recorder.stop();
    if (!got || !item) return;
    setTake(got);
    if (!got.heardText) {
      setNotice("No words came through. Try again a little louder, closer to the mic.");
      return;
    }
    setScoring(true);
    try {
      const scored = await scoreShadowingAttempt({
        video_id: video.id,
        item_key: item.key,
        heard_text: got.heardText,
        duration_ms: got.speechMs,
        reference_ms: item.end_ms - item.start_ms,
        engine: got.engine,
      });
      setResult(scored);
      queryClient.setQueryData<ShadowingVideoLesson>(lessonKey, (old) =>
        old
          ? {
              ...old,
              items: old.items.map((entry) =>
                entry.key === item.key
                  ? { ...entry, best_score: scored.best_score, attempts: scored.attempts }
                  : entry,
              ),
            }
          : old,
      );
      // The video list shows how many sentences were practised.
      void queryClient.invalidateQueries({ queryKey: ["shadowing-videos"] });
    } catch (err) {
      setNotice(`Couldn't score this try: ${(err as Error).message}`);
    } finally {
      setScoring(false);
    }
  };

  // Phase 2: send this try to Azure for a real pronunciation score.
  const runCheck = async () => {
    if (!take || !item) return;
    setChecking(true);
    setNotice(null);
    try {
      const wav = await toWav16kMono(take.blob);
      const checked = await assessPronunciation({ videoId: video.id }, item.key, wav);
      setCheck(checked);
      queryClient.setQueryData<ShadowingVideoLesson>(lessonKey, (old) =>
        old ? { ...old, assess_remaining: checked.remaining_today } : old,
      );
    } catch (err) {
      setNotice(`Pronunciation check failed: ${(err as Error).message}`);
    } finally {
      setChecking(false);
    }
  };

  const go = (next: number) => {
    if (next < 0 || next >= items.length) return;
    playback.pause();
    setIndex(next);
  };

  return (
    <section className="container-page py-6 lg:py-8">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <button onClick={onExit} className="text-xs text-muted-foreground hover:text-foreground">
            ← All videos
          </button>
          <h1 className="mt-1 flex min-w-0 items-center gap-2 text-2xl text-ink sm:text-3xl">
            <span>🎬</span>
            <span className="truncate">{video.title}</span>
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">{levelLabel(video.level)}</p>
        </div>
        {items.length > 0 && (
          <div className="whitespace-nowrap text-sm text-muted-foreground">
            {index + 1} / {items.length}
          </div>
        )}
      </div>

      <div className="mt-5 grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-7">
          {/* YouTube's own player, always visible: the page never covers or hides it. */}
          <div className="relative aspect-video w-full max-w-full overflow-hidden rounded-3xl bg-black">
            <div ref={yt.containerRef} className="absolute inset-0" />
          </div>
          {yt.error && <p className="text-sm text-destructive">{yt.error}</p>}
          {lesson?.source_note && (
            <p className="text-[11px] text-muted-foreground">Source: {lesson.source_note}</p>
          )}

          {lessonQ.isLoading && (
            <div className="h-48 animate-pulse rounded-4xl border border-border bg-card" />
          )}
          {lessonQ.isError && (
            <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {(lessonQ.error as Error).message}
            </p>
          )}

          {item && (
            <div className="rounded-4xl border border-border bg-card p-5 sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="tabular-nums">
                  {formatClock(item.start_ms)} – {formatClock(item.end_ms)}
                </span>
                {item.best_score !== null && (
                  <span>
                    Best {item.best_score}% · {item.attempts}{" "}
                    {item.attempts === 1 ? "try" : "tries"}
                  </span>
                )}
              </div>

              <p
                className={`mt-3 text-xl leading-snug text-ink transition sm:text-2xl ${
                  showText ? "" : "select-none blur-md"
                }`}
                aria-hidden={!showText}
              >
                {item.text}
              </p>
              {showMeaning && item.translation && (
                <p className="mt-2 text-sm text-muted-foreground">{item.translation}</p>
              )}

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => playSentence()}
                  disabled={!yt.player || recorder.recording}
                  className="rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {yt.player ? "▶ Play sentence" : "Loading video…"}
                </button>
                <button
                  onClick={() => setSpeed(speed === 1 ? 0.75 : 1)}
                  className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
                  title="Playback speed"
                >
                  {speed === 1 ? "1×" : "0.75×"}
                </button>
                <button
                  onClick={() => setMode(mode === "stop" ? "on" : "stop")}
                  className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
                  title="Switch between stopping after each sentence and playing on"
                >
                  {mode === "stop" ? "⏸ Stop after each sentence" : "⏵ Play on"}
                </button>
                <button
                  onClick={() => setShowText(!showText)}
                  className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
                >
                  {showText ? "Hide text" : "Show text"}
                </button>
                {item.translation && (
                  <button
                    onClick={() => setShowMeaning(!showMeaning)}
                    className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
                  >
                    {showMeaning ? "Hide meaning" : "Meaning"}
                  </button>
                )}
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-5">
                {recorder.recording ? (
                  <button
                    onClick={() => void finishTake()}
                    className="animate-pulse rounded-full bg-destructive px-6 py-3 text-sm font-semibold text-destructive-foreground"
                  >
                    ■ Stop
                  </button>
                ) : (
                  <button
                    onClick={() => void startTake()}
                    disabled={recorder.busy || scoring || checking}
                    className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    {recorder.busy || scoring ? "Checking…" : take ? "🎙️ Try again" : "🎙️ Say it"}
                  </button>
                )}
                {recorder.recording && <LevelMeter level={recorder.level} />}
                {take && !recorder.recording && (
                  <>
                    <button
                      onClick={() => playSentence()}
                      disabled={!yt.player}
                      className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"
                    >
                      ▶ Video
                    </button>
                    <button
                      onClick={playTake}
                      className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
                    >
                      ▶ You
                    </button>
                  </>
                )}
              </div>

              {(notice ?? recorder.error) && (
                <p className="mt-3 text-sm text-destructive">{notice ?? recorder.error}</p>
              )}

              {result && (
                <WordMatchCard result={result}>
                  {assessEnabled && take && (
                    <PronunciationCheck
                      check={check}
                      checking={checking}
                      checksLeft={checksLeft}
                      onRun={() => void runCheck()}
                    />
                  )}
                </WordMatchCard>
              )}

              <div className="mt-6 flex items-center justify-between gap-3">
                <button
                  onClick={() => go(index - 1)}
                  disabled={index === 0 || recorder.recording}
                  className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-40"
                >
                  ← Previous
                </button>
                <button
                  onClick={() => go(index + 1)}
                  disabled={index + 1 >= items.length || recorder.recording}
                  className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-5">
          <div className="rounded-4xl border border-border bg-card p-3">
            <div className="px-2 pb-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              Sentences
            </div>
            <div ref={listRef} className="relative max-h-[60vh] space-y-1 overflow-y-auto">
              {items.map((entry, i) => (
                <button
                  key={entry.key}
                  ref={i === index ? activeRowRef : undefined}
                  onClick={() => playSentence(i)}
                  disabled={recorder.recording}
                  className={`flex w-full items-start gap-3 rounded-2xl px-3 py-2 text-left disabled:opacity-60 ${
                    i === index ? "bg-primary/10" : "hover:bg-muted"
                  }`}
                >
                  <span className="w-10 flex-none pt-0.5 text-[11px] tabular-nums text-muted-foreground">
                    {formatClock(entry.start_ms, false)}
                  </span>
                  <span
                    className={`min-w-0 flex-1 text-sm ${showText ? "" : "select-none blur-sm"}`}
                  >
                    {entry.text}
                  </span>
                  {entry.best_score !== null && (
                    <span className="flex-none text-[11px] font-semibold text-emerald-700">
                      {entry.best_score}%
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {takeUrl && <audio ref={takeRef} src={takeUrl} preload="auto" className="hidden" />}
    </section>
  );
}
