// Pieces of a Shadowing result, shared by topic sentences and video lessons
// (PRD §8.14). The word score is a WORD MATCH, never "pronunciation"
// (docs/10_AI_Design.md §10.3.11). Real pronunciation scores come only from the
// Phase 2 check, which Azure makes from the recording.

import type { ReactNode } from "react";

import type {
  PronunciationResult,
  PronunciationWord,
  ShadowingResult,
  ShadowingWord,
} from "@/lib/api";

const TEMPO_TEXT = {
  slow: "A bit slow — try to keep up with the voice.",
  good: "Good pace.",
  fast: "A bit fast — slow down and copy the rhythm.",
} as const;

const STATUS_CLASS: Record<ShadowingWord["status"], string> = {
  ok: "bg-emerald-500/15 text-emerald-700",
  close: "bg-amber-500/15 text-amber-700",
  wrong: "bg-rose-500/15 text-rose-700",
  missed: "bg-rose-500/10 text-rose-600/80 line-through",
};

/** Colour for a 0-100 pronunciation score. */
function scoreClass(value: number | null): string {
  if (value === null) return "text-muted-foreground";
  if (value >= 80) return "text-emerald-700";
  if (value >= 60) return "text-amber-700";
  return "text-rose-700";
}

function wordClass(word: PronunciationWord): string {
  if (word.is_name) return "bg-muted text-muted-foreground";
  if (word.error === "Omission") return STATUS_CLASS.missed;
  const accuracy = word.accuracy ?? 0;
  if (word.error === "Mispronunciation" || accuracy < 60) return STATUS_CLASS.wrong;
  if (accuracy < 80) return STATUS_CLASS.close;
  return STATUS_CLASS.ok;
}

function wordTitle(word: PronunciationWord): string {
  if (word.is_name) return "Name — not scored";
  if (word.error === "Omission") return "Not said";
  const accuracy = word.accuracy === null ? "—" : Math.round(word.accuracy);
  return word.error === "None" ? `Accuracy ${accuracy}` : `Accuracy ${accuracy} · ${word.error}`;
}

function matchTitle(word: ShadowingWord): string {
  if (word.status === "ok") return "Heard";
  if (!word.heard) return "Not heard";
  return word.hint
    ? `Heard “${word.heard}” — say the ${word.hint} ending`
    : `Heard “${word.heard}”`;
}

/** The word-match result of one try. `children` go at the bottom (the Azure check). */
export function WordMatchCard({
  result,
  children,
}: {
  result: ShadowingResult;
  children?: ReactNode;
}) {
  // Vietnamese words never end in a consonant cluster, so dropped English
  // endings are the commonest slip: name them.
  const endings = result.words.filter((word) => word.hint);
  return (
    <div className="mt-5 rounded-3xl border border-border bg-background p-4">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-3xl font-semibold text-ink">{result.score}%</span>
        <span className="text-sm text-muted-foreground">
          word match · best {result.best_score}%
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {result.words.map((word, i) => (
          <span
            key={`${i}-${word.word}`}
            title={matchTitle(word)}
            className={`rounded-lg px-2 py-1 text-sm font-medium ${STATUS_CLASS[word.status]}`}
          >
            {word.word}
          </span>
        ))}
      </div>
      {endings.length > 0 && (
        <p className="mt-2 text-sm text-amber-800">
          Say the endings: {endings.map((word) => `${word.word} (${word.hint})`).join(", ")}
        </p>
      )}
      {result.extra.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Extra words heard: {result.extra.join(", ")}
        </p>
      )}
      {result.tempo && <p className="mt-2 text-sm">{TEMPO_TEXT[result.tempo]}</p>}
      <p className="mt-3 text-[11px] text-muted-foreground">
        Word match shows the words the app heard. It is not a pronunciation or accent score.
      </p>
      {children}
    </div>
  );
}

/** Phase 2: the button that sends a try to Azure, then its result. */
export function PronunciationCheck({
  check,
  checking,
  checksLeft,
  onRun,
}: {
  check: PronunciationResult | null;
  checking: boolean;
  checksLeft: number;
  onRun: () => void;
}) {
  return (
    <div className="mt-4 border-t border-border pt-4">
      {check ? (
        <PronunciationPanel check={check} />
      ) : (
        <>
          <button
            onClick={onRun}
            disabled={checking || checksLeft <= 0}
            className="rounded-full border border-primary px-4 py-2 text-sm font-semibold text-primary hover:bg-primary/5 disabled:opacity-50"
          >
            {checking
              ? "Checking pronunciation…"
              : checksLeft > 0
                ? `🔬 Check pronunciation · ${checksLeft} left today`
                : "No pronunciation checks left today"}
          </button>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Sends this recording to Microsoft Azure to be scored. It is not stored.
          </p>
        </>
      )}
    </div>
  );
}

function PronunciationPanel({ check }: { check: PronunciationResult }) {
  const scores: [string, number | null][] = [
    ["Accuracy", check.accuracy],
    ["Fluency", check.fluency],
    ["Completeness", check.completeness],
    ["Prosody", check.prosody],
  ];
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Pronunciation
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {scores
          .filter(([, value]) => value !== null)
          .map(([label, value]) => (
            <div key={label} className="rounded-2xl bg-muted/60 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {label}
              </div>
              <div className={`text-xl font-semibold ${scoreClass(value)}`}>
                {Math.round(value ?? 0)}
              </div>
            </div>
          ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {check.words
          .filter((word) => word.error !== "Insertion")
          .map((word, i) => (
            <span
              key={`${i}-${word.word}`}
              title={wordTitle(word)}
              className={`rounded-lg px-2 py-1 text-sm font-medium ${wordClass(word)}`}
            >
              {word.word}
            </span>
          ))}
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Scored by Microsoft Azure from your recording. Names and non-English words are grey and not
        counted. Hover a word for its score.
      </p>
    </div>
  );
}

export function LevelMeter({ level }: { level: number }) {
  // Speech RMS sits around 0.02–0.25; scale it so normal talking fills the bar.
  const pct = Math.min(100, Math.round(level * 400));
  return (
    <div className="h-2 w-24 overflow-hidden rounded-full bg-muted" aria-hidden="true">
      <div
        className="h-full bg-primary transition-[width] duration-100"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
