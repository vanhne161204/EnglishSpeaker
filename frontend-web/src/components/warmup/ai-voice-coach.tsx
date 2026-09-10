// The AI voice coach mode of Warm-up (PRD §8.12): a voice call with a Gemini
// Live coach that asks the topic's questions, with live captions for both sides.

import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { createNote, voiceCoachUsage, type Topic, type VoiceCoachUsage } from "@/lib/api";
import { useGeminiLive, type LiveLine, type LiveStatus } from "@/lib/voice/use-gemini-live";

const USAGE_KEY = ["voice-coach", "usage"] as const;

/** Below this many seconds the server refuses a new session. */
const MIN_SESSION_SECONDS = 30;

const STATUS_LABEL: Record<LiveStatus, string> = {
  idle: "Ready",
  connecting: "Connecting to your coach…",
  listening: "Your turn — speak any time",
  speaking: "Coach is speaking",
  ended: "Session ended",
  error: "Something went wrong",
};

function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function wholeMinutes(seconds: number): number {
  return Math.floor(seconds / 60);
}

function resetTime(usage: VoiceCoachUsage): string {
  return new Date(usage.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function AiVoiceCoach({ topic, onExit }: { topic: Topic | null; onExit: () => void }) {
  const queryClient = useQueryClient();
  const usageQ = useQuery({ queryKey: USAGE_KEY, queryFn: () => voiceCoachUsage() });
  const live = useGeminiLive();
  const [notice, setNotice] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const flash = useCallback((msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 2500);
  }, []);

  // Minutes change when a session starts (its time is held) and when it ends
  // (the unused time comes back).
  const sessionId = live.session?.id;
  const finished = live.status === "ended" || live.status === "error";
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: USAGE_KEY });
  }, [sessionId, finished, queryClient]);

  // Keep the newest line in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [live.lines, live.captions]);

  const saveLine = useCallback(
    async (text: string) => {
      try {
        await createNote({ improved_text: text, source: "self", topic: topic?.title ?? null });
        flash("Saved to your notes ✓");
      } catch (e) {
        flash(`Couldn't save note: ${(e as Error).message}`);
      }
    },
    [flash, topic?.title],
  );

  const usage = usageQ.data;
  const started = live.status !== "idle";
  const canStart = !!usage?.enabled && usage.remaining_seconds >= MIN_SESSION_SECONDS;
  const begin = () => void live.start(topic?.id ?? null);
  const leave = () => {
    live.stop();
    onExit();
  };
  const spokenLines = live.lines.filter((line) => line.role === "user").length;

  return (
    <section className="container-page py-6 lg:py-8">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <button onClick={leave} className="text-xs text-muted-foreground hover:text-foreground">
            ← Change topic
          </button>
          <h1 className="mt-1 text-2xl sm:text-3xl text-ink flex items-center gap-2">
            <span>🤖</span> AI voice coach
            <span className="text-base text-muted-foreground">· {topic?.title ?? "General"}</span>
          </h1>
        </div>
        <div className="text-sm text-muted-foreground whitespace-nowrap text-right">
          {live.secondsLeft !== null
            ? `⏱ ${clock(live.secondsLeft)} left`
            : usage?.enabled
              ? `${wholeMinutes(usage.remaining_seconds)} min left today`
              : null}
        </div>
      </div>

      {usageQ.isLoading && (
        <div className="mt-5 h-48 max-w-2xl rounded-4xl border border-border bg-card animate-pulse" />
      )}

      {usageQ.isError && !started && (
        <div className="mt-5 max-w-2xl rounded-4xl border border-border bg-card p-6">
          <p className="text-muted-foreground">Couldn't load your AI minutes.</p>
          <button
            onClick={() => void usageQ.refetch()}
            className="mt-3 rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
          >
            Try again
          </button>
        </div>
      )}

      {usage && !usage.enabled && !started && (
        <div className="mt-5 max-w-2xl rounded-4xl border border-border bg-card p-6 text-center">
          <div className="text-3xl">🔌</div>
          <h2 className="mt-2 text-xl text-ink">The AI voice coach isn't switched on yet</h2>
          <p className="mt-2 text-muted-foreground">
            You can still warm up with the classic mode: read each question and answer by voice.
          </p>
          <button
            onClick={onExit}
            className="mt-5 rounded-full bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold hover:opacity-90"
          >
            ← Use classic warm-up
          </button>
        </div>
      )}

      {usage?.enabled && !started && (
        <div className="mt-5 max-w-2xl rounded-4xl border border-border bg-card p-6">
          <h2 className="text-xl text-ink">Talk it through, out loud</h2>
          <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground list-disc pl-5">
            <li>
              The coach asks{" "}
              {topic ? `questions about “${topic.title}”` : "friendly everyday questions"}, one at a
              time.
            </li>
            <li>Just answer by speaking. You can interrupt the coach at any time.</li>
            <li>You'll see captions for both of you, and you can save your good sentences.</li>
            <li>
              One session lasts up to {wholeMinutes(usage.session_max_seconds)} minutes. It stops by
              itself after 2 minutes of silence.
            </li>
          </ul>
          <p className="mt-4 text-sm">
            <span className="font-semibold text-ink">
              {wholeMinutes(usage.remaining_seconds)} of {wholeMinutes(usage.daily_limit_seconds)}{" "}
              minutes
            </span>{" "}
            left today · resets at {resetTime(usage)}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Your voice is sent to Google Gemini to create the coach's replies. Don't share personal
            details.
          </p>
          <button
            onClick={begin}
            disabled={!canStart}
            className="mt-5 rounded-full bg-primary text-primary-foreground px-6 py-3 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            🎙️ Start talking
          </button>
          {!canStart && (
            <p className="mt-2 text-xs text-muted-foreground">
              You've used today's AI minutes. Try the classic warm-up, or come back after{" "}
              {resetTime(usage)}.
            </p>
          )}
        </div>
      )}

      {started && (
        <div className="mt-5 rounded-4xl border border-border bg-card flex flex-col min-h-[440px]">
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[52vh]">
            {live.lines.map((line) => (
              <CoachBubble
                key={line.id}
                line={line}
                onSave={line.role === "user" ? () => void saveLine(line.text) : undefined}
              />
            ))}
            {live.captions.user && (
              <CoachBubble
                line={{ id: "live-user", role: "user", text: live.captions.user }}
                pending
              />
            )}
            {live.captions.coach && (
              <CoachBubble
                line={{ id: "live-coach", role: "coach", text: live.captions.coach }}
                pending
              />
            )}
            {live.status === "connecting" && (
              <p className="py-10 text-center text-sm text-muted-foreground">
                Connecting to your coach… allow the microphone if your browser asks.
              </p>
            )}
          </div>

          <div className="border-t border-border p-3">
            {finished ? (
              <div className="py-1 text-center">
                <p className="text-sm text-muted-foreground">
                  {live.error ??
                    live.endReason ??
                    (spokenLines > 0
                      ? `Nice work — you answered ${spokenLines} time${spokenLines === 1 ? "" : "s"}.`
                      : "Session ended.")}
                </p>
                <div className="mt-3 flex flex-wrap items-center justify-center gap-3">
                  {canStart && (
                    <button
                      onClick={begin}
                      className="rounded-full bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold hover:opacity-90"
                    >
                      Talk again
                    </button>
                  )}
                  <Link
                    to="/rooms"
                    className="rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
                  >
                    Join a room
                  </Link>
                  <Link
                    to="/match"
                    className="rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
                  >
                    Find a partner
                  </Link>
                  <button
                    onClick={onExit}
                    className="rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-muted"
                  >
                    Classic warm-up
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <StatusDot status={live.status} muted={live.muted} />
                <span className="text-sm text-muted-foreground">
                  {live.muted ? "Mic is off" : STATUS_LABEL[live.status]}
                </span>
                <LevelMeter level={live.level} muted={live.muted} />
                <div className="ml-auto flex gap-2">
                  <button
                    onClick={live.toggleMute}
                    disabled={live.status === "connecting"}
                    className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"
                  >
                    {live.muted ? "🎙️ Unmute" : "🔇 Mute"}
                  </button>
                  <button
                    onClick={live.stop}
                    className="rounded-full bg-destructive text-destructive-foreground px-4 py-2 text-sm font-semibold hover:opacity-90"
                  >
                    End session
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {notice && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background shadow-lg">
          {notice}
        </div>
      )}
    </section>
  );
}

function CoachBubble({
  line,
  onSave,
  pending = false,
}: {
  line: LiveLine;
  onSave?: () => void;
  pending?: boolean;
}) {
  const isUser = line.role === "user";
  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        {!isUser && (
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 ml-3">
            AI coach
          </div>
        )}
        <div className={`flex items-center gap-1.5 ${isUser ? "flex-row-reverse" : ""}`}>
          <div
            className={`rounded-2xl px-4 py-2 text-sm leading-snug ${
              isUser
                ? "bg-primary text-primary-foreground rounded-br-md"
                : "bg-muted text-foreground rounded-bl-md"
            } ${pending ? "opacity-60" : ""}`}
          >
            {line.text}
            {pending ? " …" : ""}
          </div>
          {onSave && (
            <button
              onClick={onSave}
              title="Save to notes"
              aria-label="Save to notes"
              className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-muted-foreground hover:text-primary"
            >
              ＋
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusDot({ status, muted }: { status: LiveStatus; muted: boolean }) {
  const color = muted
    ? "bg-muted-foreground"
    : status === "speaking"
      ? "bg-primary animate-pulse"
      : status === "listening"
        ? "bg-emerald-500"
        : "bg-amber-500 animate-pulse";
  return <span className={`inline-block size-2.5 rounded-full ${color}`} aria-hidden="true" />;
}

function LevelMeter({ level, muted }: { level: number; muted: boolean }) {
  // Speech RMS sits around 0.02–0.25; scale it so normal talking fills the bar.
  const pct = muted ? 0 : Math.min(100, Math.round(level * 400));
  return (
    <div className="h-2 w-24 overflow-hidden rounded-full bg-muted" aria-hidden="true">
      <div
        className="h-full bg-primary transition-[width] duration-100"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
