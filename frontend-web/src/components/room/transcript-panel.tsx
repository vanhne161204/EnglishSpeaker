// The live script of a room (PRD §8.9).
//
// Shows what everyone SAID, grouped by speaker like a screenplay, with the
// sentence currently being spoken shown greyed until the engine finalises it.
//
// Two product rules this component exists to honour:
//
//  1. "Users should know when Speech-to-Text is active" (PRD §8.9). Hence the
//     red LIVE badge and an explicit on/off switch, never a silent background
//     recording.
//  2. "The transcript may have mistakes" (§14.7). Said once, plainly, so a
//     learner does not read a mis-heard word as their own error.

import { useEffect, useRef } from "react";

export interface TranscriptLine {
  /** Server id for a stored line; `${userId}:${seq}` for a live preview. */
  id: string;
  userId: string;
  speaker: string;
  text: string;
  mine: boolean;
  /** True while the engine is still refining this sentence. */
  interim?: boolean;
}

export interface TranscriptPanelProps {
  lines: TranscriptLine[];
  /** Whether this browser can capture speech at all. */
  supported: boolean;
  /** Whether MY microphone is currently feeding the transcript. */
  listening: boolean;
  error: string | null;
  onToggle: () => void;
  /** Lets the room stretch this panel to share the column's spare height. */
  className?: string;
}

export function TranscriptPanel({
  lines,
  supported,
  listening,
  error,
  onToggle,
  className = "",
}: TranscriptPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Follow the conversation. Speech arrives continuously, so a transcript that
  // does not scroll is a transcript nobody reads.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [lines]);

  return (
    <div className={`flex flex-col rounded-4xl border border-border bg-card ${className}`}>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">📝 Live script</span>
          {listening && (
            // PRD §8.9: users must know when speech-to-text is active.
            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-destructive" />
              LIVE
            </span>
          )}
        </div>

        {supported ? (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={listening}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              listening
                ? "bg-destructive text-destructive-foreground"
                : "border border-border hover:bg-muted"
            }`}
          >
            {listening ? "Turn off" : "Turn on"}
          </button>
        ) : (
          <span
            className="text-[10px] text-muted-foreground"
            title="The browser speech engine is only in Chrome, Edge and Safari."
          >
            Needs Chrome or Edge
          </span>
        )}
      </div>

      <div
        ref={scrollRef}
        className="max-h-[240px] flex-1 space-y-3 overflow-y-auto p-4 lg:max-h-none lg:min-h-0"
      >
        {error && <p className="text-sm text-destructive">{error}</p>}

        {lines.length === 0 && !error && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {listening
              ? "Listening… start speaking and your words appear here."
              : supported
                ? "Turn on the script to see what everyone says."
                : "Live script needs Chrome, Edge or Safari."}
          </p>
        )}

        {lines.map((line) => (
          <div key={line.id}>
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider ${
                line.mine ? "text-primary" : "text-muted-foreground"
              }`}
            >
              {line.mine ? "You" : line.speaker}
            </span>
            <p
              className={`text-sm leading-snug ${
                line.interim ? "italic text-muted-foreground" : ""
              }`}
            >
              {line.text}
            </p>
          </div>
        ))}
      </div>

      {lines.length > 0 && (
        // PRD §14.7 — a mis-heard word must not read as the learner's mistake.
        <p className="border-t border-border px-4 py-2 text-[10px] text-muted-foreground">
          Speech-to-text isn't perfect — some words may be wrong.
        </p>
      )}
    </div>
  );
}
