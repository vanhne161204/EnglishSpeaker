// One Shadowing session (PRD §8.14): hear a sentence, say it straight back, and
// see which words came through. The word score is a WORD MATCH, never
// "pronunciation" (docs/10_AI_Design.md §10.3.11). Real pronunciation scores come
// only from the Phase 2 check, which Azure makes from the recording.

import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  assessPronunciation,
  scoreShadowingAttempt,
  shadowingAudio,
  shadowingItems,
  type PronunciationResult,
  type ShadowingItemList,
  type ShadowingKind,
  type ShadowingResult,
  type Topic,
} from "@/lib/api";
import { useShadowRecorder, type ShadowTake } from "@/lib/voice/use-shadow-recorder";
import { toWav16kMono } from "@/lib/voice/wav16k";

import { LevelMeter, PronunciationCheck, WordMatchCard } from "./result-parts";

type Speed = 1 | 0.75;

/** Where the model voice for the current sentence comes from. */
type VoiceSource = { kind: "loading" } | { kind: "clip"; url: string } | { kind: "browser" };

const KIND_LABEL: Record<ShadowingKind, string> = {
  question: "Question",
  answer: "Sample answer",
  term: "Phrase",
  example: "Example",
  segment: "Video sentence",
};

export function ShadowingSession({ topic, onExit }: { topic: Topic; onExit: () => void }) {
  const queryClient = useQueryClient();
  const itemsKey = ["shadowing", topic.id] as const;
  const itemsQ = useQuery({ queryKey: itemsKey, queryFn: () => shadowingItems(topic.id) });
  const recorder = useShadowRecorder();
  const cancelRecording = recorder.cancel;

  const [index, setIndex] = useState(0);
  const [finished, setFinished] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [showText, setShowText] = useState(true);
  const [showMeaning, setShowMeaning] = useState(false);
  const [voice, setVoice] = useState<VoiceSource>({ kind: "loading" });
  const [referenceMs, setReferenceMs] = useState<number | null>(null);
  const [take, setTake] = useState<ShadowTake | null>(null);
  const [takeUrl, setTakeUrl] = useState<string | null>(null);
  const [result, setResult] = useState<ShadowingResult | null>(null);
  const [scoring, setScoring] = useState(false);
  const [check, setCheck] = useState<PronunciationResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const modelRef = useRef<HTMLAudioElement | null>(null);
  const takeRef = useRef<HTMLAudioElement | null>(null);

  const items = itemsQ.data?.items ?? [];
  const item = items[index];
  const itemKey = item?.key;
  const itemAudioUrl = item?.audio_url ?? null;
  const voiceEnabled = itemsQ.data?.voice_enabled ?? false;
  const assessEnabled = itemsQ.data?.assess_enabled ?? false;
  const checksLeft = itemsQ.data?.assess_remaining ?? 0;

  // A fresh start for every sentence.
  useEffect(() => {
    cancelRecording();
    setTake(null);
    setResult(null);
    setCheck(null);
    setNotice(null);
  }, [itemKey, cancelRecording]);

  // Find the model voice: an admin recording, our stored TTS clip, or the browser.
  useEffect(() => {
    if (!itemKey) return;
    setReferenceMs(null);
    if (itemAudioUrl) {
      setVoice({ kind: "clip", url: itemAudioUrl });
      return;
    }
    if (!voiceEnabled) {
      setVoice({ kind: "browser" });
      return;
    }
    setVoice({ kind: "loading" });
    const controller = new AbortController();
    let url: string | null = null;
    shadowingAudio(topic.id, itemKey, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setVoice({ kind: "clip", url });
      })
      .catch(() => {
        if (!controller.signal.aborted) setVoice({ kind: "browser" });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [itemKey, itemAudioUrl, voiceEnabled, topic.id]);

  // The learner's own try, playable next to the model voice.
  useEffect(() => {
    if (!take) {
      setTakeUrl(null);
      return;
    }
    const url = URL.createObjectURL(take.blob);
    setTakeUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [take]);

  const stopPlayback = () => {
    modelRef.current?.pause();
    takeRef.current?.pause();
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
  };

  const playModel = () => {
    if (!item) return;
    stopPlayback();
    if (voice.kind === "clip" && modelRef.current) {
      const audio = modelRef.current;
      audio.currentTime = 0;
      audio.playbackRate = speed;
      audio.preservesPitch = true;
      void audio.play().catch(() => setNotice("Couldn't play the model voice."));
    } else if (voice.kind === "browser" && "speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(item.text);
      utterance.lang = "en-US";
      utterance.rate = speed === 1 ? 0.95 : 0.7;
      window.speechSynthesis.speak(utterance);
    }
  };

  const playTake = () => {
    stopPlayback();
    const audio = takeRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    void audio.play().catch(() => undefined);
  };

  const startTake = async () => {
    stopPlayback();
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
        topic_id: topic.id,
        item_key: item.key,
        heard_text: got.heardText,
        duration_ms: got.speechMs,
        reference_ms: referenceMs === null ? null : Math.round(referenceMs),
        engine: got.engine,
      });
      setResult(scored);
      // Update the best score in place instead of refetching the whole list.
      queryClient.setQueryData<ShadowingItemList>(itemsKey, (old) =>
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
      const checked = await assessPronunciation({ topicId: topic.id }, item.key, wav);
      setCheck(checked);
      queryClient.setQueryData<ShadowingItemList>(itemsKey, (old) =>
        old ? { ...old, assess_remaining: checked.remaining_today } : old,
      );
    } catch (err) {
      setNotice(`Pronunciation check failed: ${(err as Error).message}`);
    } finally {
      setChecking(false);
    }
  };

  const go = (next: number) => {
    stopPlayback();
    if (next >= items.length) {
      setFinished(true);
      return;
    }
    setIndex(Math.max(0, next));
  };

  const header = (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <button onClick={onExit} className="text-xs text-muted-foreground hover:text-foreground">
          ← Change topic
        </button>
        <h1 className="mt-1 text-2xl sm:text-3xl text-ink flex items-center gap-2">
          <span>🎧</span> Shadowing
          <span className="text-base text-muted-foreground">· {topic.title}</span>
        </h1>
      </div>
      {items.length > 0 && !finished && (
        <div className="text-sm text-muted-foreground whitespace-nowrap">
          {index + 1} / {items.length}
        </div>
      )}
    </div>
  );

  if (itemsQ.isLoading) {
    return (
      <section className="container-page py-6 lg:py-8">
        {header}
        <div className="mt-5 h-72 max-w-3xl rounded-4xl border border-border bg-card animate-pulse" />
      </section>
    );
  }

  if (itemsQ.isError || items.length === 0) {
    return (
      <section className="container-page py-6 lg:py-8">
        {header}
        <div className="mt-5 max-w-2xl rounded-4xl border border-border bg-card p-6 text-center">
          <div className="text-3xl">🕰️</div>
          <h2 className="mt-2 text-xl text-ink">
            {itemsQ.isError ? "Couldn't load the sentences" : "No sentences to shadow yet"}
          </h2>
          <p className="mt-2 text-muted-foreground">
            {itemsQ.isError
              ? ((itemsQ.error as Error)?.message ?? "Please try again.")
              : `“${topic.title}” has no published sentences yet. Try another topic.`}
          </p>
          <button
            onClick={onExit}
            className="mt-5 rounded-full bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold hover:opacity-90"
          >
            ← Choose a topic
          </button>
        </div>
      </section>
    );
  }

  if (finished) {
    const practised = items.filter((entry) => entry.best_score !== null);
    const average = practised.length
      ? Math.round(
          practised.reduce((sum, entry) => sum + (entry.best_score ?? 0), 0) / practised.length,
        )
      : null;
    return (
      <section className="container-page py-6 lg:py-8">
        {header}
        <div className="mt-5 max-w-2xl rounded-4xl border border-border bg-card p-6 text-center">
          <div className="text-3xl">🎉</div>
          <h2 className="mt-2 text-xl text-ink">Round finished</h2>
          <p className="mt-2 text-muted-foreground">
            You practised {practised.length} of {items.length} sentences
            {average !== null ? ` · average best word match ${average}%` : ""}.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <button
              onClick={() => {
                setFinished(false);
                setIndex(0);
              }}
              className="rounded-full bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold hover:opacity-90"
            >
              Go again
            </button>
            <Link
              to="/rooms"
              className="rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
            >
              Join a room
            </Link>
            <button
              onClick={onExit}
              className="rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
            >
              Another topic
            </button>
          </div>
        </div>
      </section>
    );
  }

  if (!item) return null;
  const progress = Math.round(((index + 1) / items.length) * 100);

  return (
    <section className="container-page py-6 lg:py-8">
      {header}
      <div className="mt-3 h-1.5 max-w-3xl overflow-hidden rounded-full bg-muted">
        <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
      </div>

      <div className="mt-5 max-w-3xl rounded-4xl border border-border bg-card p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {KIND_LABEL[item.kind]}
          </span>
          {item.best_score !== null && (
            <span className="text-xs text-muted-foreground">
              Best {item.best_score}% · {item.attempts} {item.attempts === 1 ? "try" : "tries"}
            </span>
          )}
        </div>

        <p
          className={`mt-4 text-xl sm:text-2xl leading-snug text-ink transition ${
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
            onClick={playModel}
            disabled={voice.kind === "loading" || recorder.recording}
            className="rounded-full bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {voice.kind === "loading" ? "Loading voice…" : "▶ Listen"}
          </button>
          <button
            onClick={() => setSpeed(speed === 1 ? 0.75 : 1)}
            className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
            title="Playback speed"
          >
            {speed === 1 ? "1×" : "0.75×"}
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
        {voice.kind === "browser" && (
          <p className="mt-2 text-xs text-muted-foreground">
            Using your browser's voice for this sentence.
          </p>
        )}

        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-5">
          {recorder.recording ? (
            <button
              onClick={() => void finishTake()}
              className="rounded-full bg-destructive text-destructive-foreground px-6 py-3 text-sm font-semibold animate-pulse"
            >
              ■ Stop
            </button>
          ) : (
            <button
              onClick={() => void startTake()}
              disabled={recorder.busy || scoring || checking}
              className="rounded-full bg-primary text-primary-foreground px-6 py-3 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
            >
              {recorder.busy || scoring ? "Checking…" : take ? "🎙️ Try again" : "🎙️ Say it"}
            </button>
          )}
          {recorder.recording && <LevelMeter level={recorder.level} />}
          {take && !recorder.recording && (
            <>
              <button
                onClick={playModel}
                disabled={voice.kind === "loading"}
                className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"
              >
                ▶ Model
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
            disabled={recorder.recording}
            className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-40"
          >
            {index + 1 === items.length ? "Finish" : "Next →"}
          </button>
        </div>
      </div>

      {voice.kind === "clip" && (
        <audio
          ref={modelRef}
          src={voice.url}
          preload="auto"
          className="hidden"
          onLoadedMetadata={(event) => {
            const seconds = event.currentTarget.duration;
            if (Number.isFinite(seconds)) setReferenceMs(seconds * 1000);
          }}
        />
      )}
      {takeUrl && <audio ref={takeRef} src={takeUrl} preload="auto" className="hidden" />}
    </section>
  );
}
