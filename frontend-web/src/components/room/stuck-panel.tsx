// "I'm stuck" — the in-room rescue coach (docs/10_AI_Design.md §10.2).
//
// Sits next to the chat input because that is where a learner actually freezes.
// Three modes, because being stuck has three different shapes:
//
//   answer    someone asked me something and my mind went blank
//   ask       the conversation died and I need something to ask
//   say_this  I know what I mean in Vietnamese, I just can't build the English
//
// `say_this` matters most for a Vietnamese learner: the block is usually not
// "I have no idea", it is "I know what I want to say but not how to say it".
//
// Three rules from §10.2 that this component exists to enforce:
//
//  1. PRIVATE. The suggestion lives in local state and never touches the room
//     WebSocket. If everyone could see it, nobody would use it — the whole point
//     is to not look stupid in front of the other learners.
//  2. NEVER AUTO-SEND. Tapping a suggestion fills the draft box. The learner
//     still has to read it and press send, so they practise the sentence instead
//     of letting the AI talk for them.
//  3. NEVER BLOCK. Any failure closes with a message; the room keeps working.

import { useEffect, useRef, useState } from "react";

import { assist } from "@/lib/api";
import type { AssistKind } from "@/lib/api/types";

/** How many recent lines of room talk to send as context. */
const CONTEXT_LINES = 8;
/** Backend caps `context` at 2000 chars; stay clear of it. */
const CONTEXT_MAX_CHARS = 1500;

type StuckMode = Extract<AssistKind, "answer" | "ask" | "say_this">;

const MODES: ReadonlyArray<{
  kind: StuckMode;
  label: string;
  hint: string;
  needsText: boolean;
}> = [
  {
    kind: "answer",
    label: "How do I answer?",
    hint: "Someone asked me something",
    needsText: false,
  },
  {
    kind: "ask",
    label: "What do I ask?",
    hint: "The conversation went quiet",
    needsText: false,
  },
  {
    kind: "say_this",
    label: "Say it in English",
    hint: "I know what I mean, in Vietnamese",
    needsText: true,
  },
];

export interface StuckPanelProps {
  /** Recent room speech, oldest first, already formatted as "Name: text". */
  contextLines: string[];
  topicId: string | null;
  /** Learner CEFR level, so a suggestion is never harder than they can say. */
  level?: string | null;
  /** Called when the learner picks a suggestion — fills their draft box. */
  onUse: (text: string) => void;
}

export function StuckPanel({ contextLines, topicId, level, onUse }: StuckPanelProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<StuckMode | null>(null);
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [degraded, setDegraded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idea, setIdea] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  // Close when clicking away or pressing Escape — a panel that traps the learner
  // in the middle of a live call is worse than no panel.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const request = async (mode: StuckMode) => {
    if (mode === "say_this" && !idea.trim()) return;
    setBusy(mode);
    setError(null);
    setSuggestion(null);
    try {
      // Only the last few lines: enough for the model to see what was just
      // asked, small enough to stay fast and cheap (§10.2).
      const context = contextLines.slice(-CONTEXT_LINES).join("\n").slice(-CONTEXT_MAX_CHARS);

      const result = await assist({
        kind: mode,
        text: mode === "say_this" ? idea.trim() : "",
        context: mode === "say_this" ? null : context || null,
        topic_id: topicId,
        level: level ?? null,
      });
      setSuggestion(result.suggestion);
      // True when a fallback model answered, or the AI was unavailable and this
      // is the demo stub. Worth showing rather than pretending it is the best
      // the app can do.
      setDegraded(result.degraded ?? result.provider === "stub");
    } catch (e) {
      setError((e as Error).message || "Couldn't get a suggestion — try again.");
    } finally {
      setBusy(null);
    }
  };

  const use = () => {
    if (!suggestion) return;
    onUse(suggestion);
    setOpen(false);
    setSuggestion(null);
    setIdea("");
  };

  return (
    <div ref={rootRef} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Stuck? Get something to say"
        aria-label="I'm stuck — get a suggestion"
        aria-expanded={open}
        className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
          open ? "bg-primary text-primary-foreground" : "border border-border hover:bg-muted"
        }`}
      >
        🆘
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-2 w-[300px] rounded-2xl border border-border bg-card p-4 shadow-lg">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-semibold">Stuck? Pick one</span>
            {/* Reassurance, not decoration: people only use this if it is private. */}
            <span className="text-[10px] text-muted-foreground">Only you see this</span>
          </div>

          <div className="mt-3 space-y-1.5">
            {MODES.map((mode) => (
              <div key={mode.kind}>
                {mode.needsText && (
                  <input
                    value={idea}
                    onChange={(e) => setIdea(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && request(mode.kind)}
                    placeholder="e.g. tôi muốn nói về gia đình tôi"
                    className="mb-1.5 w-full rounded-xl border border-border bg-background px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
                  />
                )}
                <button
                  type="button"
                  onClick={() => request(mode.kind)}
                  disabled={busy !== null || (mode.needsText && !idea.trim())}
                  className="w-full rounded-xl border border-border px-3 py-2 text-left hover:bg-muted disabled:opacity-50"
                >
                  <span className="block text-sm font-medium">
                    {busy === mode.kind ? "Thinking…" : mode.label}
                  </span>
                  <span className="block text-[11px] text-muted-foreground">{mode.hint}</span>
                </button>
              </div>
            ))}
          </div>

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

          {suggestion && (
            <div className="mt-3 rounded-xl border border-border bg-background/60 p-3">
              <p className="text-sm leading-snug">{suggestion}</p>
              {degraded && (
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Backup suggestion — the main coach was unavailable.
                </p>
              )}
              <button
                type="button"
                onClick={use}
                className="mt-2 w-full rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90"
              >
                Use this
              </button>
              {/* The learner still presses Send themselves — that is the practice. */}
              <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
                Goes to your message box — say it out loud too
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
