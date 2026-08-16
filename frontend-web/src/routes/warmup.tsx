import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createNote,
  listQuestions,
  listTopics,
  type AnswerTemplate,
  type Topic,
  type TopicQuestion,
} from "@/lib/api";
import { resolveWarmupQuestions } from "@/lib/warmup";
import { useMicTranscribe } from "@/lib/voice/use-mic-transcribe";
import { levelLabel, topicEmoji } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/warmup")({
  head: () => ({
    meta: [
      { title: "Warm-up — EnglishTalker" },
      {
        name: "description",
        content:
          "Warm up your speaking alone: pick a topic and answer its questions by voice, one at a time.",
      },
    ],
  }),
  component: WarmupPage,
});

/** A line in the warm-up chat: a system question, or the user's transcribed answer. */
interface WarmupLine {
  readonly id: string;
  readonly role: "system" | "user";
  readonly text: string;
  /** Answer templates for a question line, revealed on demand as a hint (PRD §8.12). */
  readonly hints?: readonly AnswerTemplate[];
}

/** Short, encouraging acknowledgements shown before the next question (PRD §8.8 tone). */
const ACKS: readonly string[] = ["Nice — got it.", "Good answer!", "Well said.", "Great, thanks!"];

function WarmupPage() {
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  // One flat fetch covers every topic, so switching topics needs no extra request.
  const questionsQ = useQuery({ queryKey: ["questions"], queryFn: () => listQuestions() });
  const [topic, setTopic] = useState<Topic | null>(null);
  const [started, setStarted] = useState(false);

  if (started) {
    return (
      <WarmupSession
        topic={topic}
        allQuestions={questionsQ.data ?? []}
        onExit={() => setStarted(false)}
      />
    );
  }

  return (
    <section className="container-page py-8 lg:py-10">
      <div className="max-w-2xl">
        <h1 className="text-3xl sm:text-4xl text-ink flex items-center gap-3">
          <span>🔥</span> Warm-up
        </h1>
        <p className="mt-2 text-muted-foreground">
          Practice alone before you talk with people. Pick a topic, then answer its questions by
          voice — one at a time. You'll see the transcript of everything you say.
        </p>
      </div>

      {(topicsQ.isError || questionsQ.isError) && (
        <div className="mt-6 max-w-2xl">
          <ErrorState
            message={
              ((topicsQ.error ?? questionsQ.error) as Error)?.message ??
              "Couldn't load warm-up content"
            }
            onRetry={() => {
              void topicsQ.refetch();
              void questionsQ.refetch();
            }}
          />
        </div>
      )}

      <div className="mt-6">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          Choose a topic
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <TopicChoice
            selected={topic === null}
            onClick={() => setTopic(null)}
            emoji="✨"
            title="General warm-up"
            subtitle="A friendly mix of everyday questions"
          />
          {(topicsQ.data ?? []).map((t) => {
            // Only topics whose published doc actually has questions can run a
            // warm-up, so the rest are shown as unavailable rather than as a dead end.
            const count = (questionsQ.data ?? []).filter((q) => q.topic_id === t.id).length;
            return (
              <TopicChoice
                key={t.id}
                selected={topic?.id === t.id}
                disabled={count === 0}
                onClick={() => setTopic(t)}
                emoji={topicEmoji(t.slug)}
                title={t.title}
                subtitle={
                  count === 0
                    ? "No questions yet"
                    : `${levelLabel(t.level)} · ${count} question${count === 1 ? "" : "s"}`
                }
              />
            );
          })}
          {(topicsQ.isLoading || questionsQ.isLoading) &&
            Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded-3xl bg-card border border-border animate-pulse"
              />
            ))}
        </div>
      </div>

      <div className="mt-8">
        <button
          onClick={() => setStarted(true)}
          className="rounded-full bg-primary text-primary-foreground px-6 py-3 text-sm font-semibold hover:opacity-90"
        >
          Start warm-up →
        </button>
      </div>
    </section>
  );
}

function TopicChoice({
  selected,
  onClick,
  emoji,
  title,
  subtitle,
  disabled = false,
}: {
  selected: boolean;
  onClick: () => void;
  emoji: string;
  title: string;
  subtitle: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={`text-left rounded-3xl border p-4 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
        selected
          ? "border-primary bg-primary/5 ring-1 ring-primary"
          : "border-border bg-card hover:bg-muted disabled:hover:bg-card"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-2xl">{emoji}</span>
        <div className="min-w-0">
          <div className="font-semibold text-ink truncate">{title}</div>
          <div className="text-xs text-muted-foreground truncate">{subtitle}</div>
        </div>
      </div>
    </button>
  );
}

/* ---------- The guided session ---------- */

function WarmupSession({
  topic,
  allQuestions,
  onExit,
}: {
  topic: Topic | null;
  allQuestions: readonly TopicQuestion[];
  onExit: () => void;
}) {
  const questions = useMemo(
    () => resolveWarmupQuestions(topic, allQuestions),
    [topic, allQuestions],
  );
  const [lines, setLines] = useState<WarmupLine[]>([]);
  const [step, setStep] = useState(0); // number of questions answered
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const flash = useCallback((msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 2500);
  }, []);

  const pushLine = useCallback(
    (role: WarmupLine["role"], text: string, hints?: readonly AnswerTemplate[]) => {
      setLines((prev) => [
        ...prev,
        { id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2)}`, role, text, hints },
      ]);
    },
    [],
  );

  // Ask the first question when the session opens. Guarded so React StrictMode's
  // double-invoked mount effect asks it once, not twice.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current) return;
    seededRef.current = true;
    const first = questions[0];
    if (first) pushLine("system", first.text, first.answer_templates);
    // Intentionally run once per session; `questions` is stable for a chosen topic.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finished = step >= questions.length;

  const submitAnswer = useCallback(
    (raw: string) => {
      const answer = raw.trim();
      if (!answer || finished) return;
      pushLine("user", answer);
      setDraft("");

      const nextStep = step + 1;
      setStep(nextStep);

      // The system's turn: acknowledge, then ask the next question — or wrap up.
      const ack = ACKS[nextStep % ACKS.length]!;
      window.setTimeout(() => {
        const next = questions[nextStep];
        if (next) {
          pushLine("system", `${ack} ${next.text}`, next.answer_templates);
        } else {
          pushLine(
            "system",
            `${ack} That's the warm-up done — you answered ${questions.length} questions. ` +
              "Ready to practice with people?",
          );
        }
      }, 350);
    },
    [finished, pushLine, questions, step],
  );

  const stt = useMicTranscribe(submitAnswer, "en");

  // Surface speech errors in the toast.
  useEffect(() => {
    if (stt.error) flash(stt.error);
  }, [stt.error, flash]);

  // Keep the newest line in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  const saveAnswer = useCallback(
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

  // A topic can exist without any admin-authored questions yet (PRD §8.1). Rather
  // than an empty chat, tell the user and send them back to pick another topic.
  if (questions.length === 0) {
    return (
      <section className="container-page py-10">
        <div className="max-w-2xl rounded-4xl border border-border bg-card p-6 text-center">
          <div className="text-3xl">🕰️</div>
          <h1 className="mt-2 text-2xl text-ink">No warm-up questions yet</h1>
          <p className="mt-2 text-muted-foreground">
            {topic
              ? `“${topic.title}” doesn't have any questions yet. Try another topic.`
              : "There are no topics with questions yet. Please check back soon."}
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

  return (
    <section className="container-page py-6 lg:py-8">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <button onClick={onExit} className="text-xs text-muted-foreground hover:text-foreground">
            ← Change topic
          </button>
          <h1 className="mt-1 text-2xl sm:text-3xl text-ink flex items-center gap-2">
            <span>🔥</span> Warm-up
            <span className="text-base text-muted-foreground">· {topic?.title ?? "General"}</span>
          </h1>
        </div>
        <div className="text-sm text-muted-foreground whitespace-nowrap">
          {Math.min(step + (finished ? 0 : 1), questions.length)} / {questions.length}
        </div>
      </div>

      <div className="mt-5 rounded-4xl border border-border bg-card flex flex-col min-h-[440px]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[52vh]">
          {lines.map((line) => (
            <WarmupBubble
              key={line.id}
              line={line}
              onSave={line.role === "user" ? () => void saveAnswer(line.text) : undefined}
            />
          ))}
        </div>

        <div className="border-t border-border p-3">
          {finished ? (
            <div className="flex flex-wrap items-center justify-center gap-3 py-1">
              <Link
                to="/rooms"
                className="rounded-full bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold hover:opacity-90"
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
                New warm-up
              </button>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitAnswer(draft);
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={stt.listening ? stt.stop : stt.start}
                title={
                  stt.supported
                    ? stt.listening
                      ? "Stop and use what I heard"
                      : "Answer by voice"
                    : "Speech isn't available here — type your answer"
                }
                aria-label="Answer by voice"
                disabled={!stt.supported || stt.busy}
                className={`flex-none rounded-full px-3 py-2 text-sm font-semibold disabled:opacity-40 ${
                  stt.listening
                    ? "bg-destructive text-destructive-foreground animate-pulse"
                    : "border border-border hover:bg-muted"
                }`}
              >
                {stt.busy ? "…" : stt.listening ? "■ Stop" : "🎙️"}
              </button>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  stt.listening
                    ? "Listening… speak your answer"
                    : "Speak with the mic, or type your answer…"
                }
                className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:border-primary"
              />
              <button
                type="submit"
                disabled={!draft.trim()}
                className="rounded-full bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          )}
        </div>
      </div>

      {!stt.supported && (
        <p className="mt-3 text-xs text-muted-foreground">
          Voice answers need Chrome or Edge. You can still do the full warm-up by typing your
          answers.
        </p>
      )}

      {notice && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background shadow-lg">
          {notice}
        </div>
      )}
    </section>
  );
}

function WarmupBubble({ line, onSave }: { line: WarmupLine; onSave?: () => void }) {
  const isUser = line.role === "user";
  const [showHint, setShowHint] = useState(false);
  const hints = line.hints ?? [];

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        {!isUser && (
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 ml-3">
            Warm-up coach
          </div>
        )}
        <div className={`flex items-center gap-1.5 ${isUser ? "flex-row-reverse" : ""}`}>
          <div
            className={`rounded-2xl px-4 py-2 text-sm leading-snug ${
              isUser
                ? "bg-primary text-primary-foreground rounded-br-md"
                : "bg-muted text-foreground rounded-bl-md"
            }`}
          >
            {line.text}
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

        {/* Answer templates give the learner a sentence shape to copy (PRD §8.2). */}
        {hints.length > 0 && (
          <div className="mt-1.5 ml-3">
            {showHint ? (
              <div className="rounded-2xl border border-dashed border-border bg-background p-3 space-y-2">
                {hints.map((hint) => (
                  <div key={hint.id}>
                    <div className="text-sm font-medium text-foreground">{hint.template}</div>
                    {hint.example && (
                      <div className="text-xs text-muted-foreground mt-0.5">
                        e.g. {hint.example}
                      </div>
                    )}
                  </div>
                ))}
                <button
                  onClick={() => setShowHint(false)}
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                >
                  Hide hint
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowHint(true)}
                className="text-[11px] font-semibold text-primary hover:underline"
              >
                💡 Need a sentence to start with?
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
