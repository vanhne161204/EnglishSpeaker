// Coach Report layer 1 — what the AI found in what you SAID (docs §10.3).
//
// Runs on demand, after the conversation. Never during: correcting someone
// while they are still speaking destroys the confidence the whole product
// exists to build (PRD §14.7).
//
// Three things this component is careful about:
//
//  1. It reports on YOUR speech only. The server scopes every row to the
//     authenticated user (§10.3.0), and the copy says so, because "is my
//     partner being graded too?" is the first thing people wonder.
//  2. A correct sentence is celebrated, not padded with a fake correction.
//     False positives are the failure mode that loses trust (§10.8).
//  3. Every suggestion is one tap from the learner's notes, because a report
//     nobody keeps anything from is a report nobody comes back to.

import { useCallback, useEffect, useState } from "react";

import { assessRoom, roomReport } from "@/lib/api";
import type { SentenceFeedback } from "@/lib/api/types";

export interface CoachReportProps {
  roomId: string;
  /** True once the learner has signed in — the report needs an account. */
  signedIn: boolean;
  /** Save one sentence to the learner's notes. */
  onSave: (original: string, improved: string) => void;
}

export function CoachReport({ roomId, signedIn, onSave }: CoachReportProps) {
  const [rows, setRows] = useState<SentenceFeedback[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setRows(await assessRoom(roomId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [roomId]);

  // Show an existing report without re-running it. Coming back to a room you
  // already checked should not cost a second assessment — this is a plain DB
  // read, no AI call.
  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    roomReport(roomId)
      .then((existing) => {
        if (!cancelled && existing.length > 0) setRows(existing);
      })
      .catch(() => {
        // No report yet, or not reachable. The button still works.
      });
    return () => {
      cancelled = true;
    };
  }, [roomId, signedIn]);

  const withErrors = rows?.filter((r) => !r.is_correct).length ?? 0;
  const averageScore = rows?.length
    ? Math.round(rows.reduce((sum, r) => sum + r.score, 0) / rows.length)
    : 0;

  return (
    <div className="rounded-4xl border border-border bg-card p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-2xl bg-secondary/40">
            🎓
          </span>
          <div>
            <div className="text-sm font-semibold">Coach report</div>
            <div className="text-[11px] text-muted-foreground">
              Checks what <span className="font-medium">you</span> said — never your partner
            </div>
          </div>
        </div>

        {signedIn && (
          <button
            type="button"
            onClick={check}
            disabled={busy}
            className="flex-none rounded-full bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Checking…" : rows ? "Check again" : "Check my English"}
          </button>
        )}
      </div>

      {!signedIn && (
        <p className="mt-4 text-sm text-muted-foreground">
          Sign in to get a report on your speaking.
        </p>
      )}

      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

      {rows && rows.length > 0 && (
        <>
          <div className="mt-4 flex gap-4 rounded-2xl border border-border bg-background/60 px-4 py-3">
            <Stat label="Sentences" value={String(rows.length)} />
            <Stat label="To fix" value={String(withErrors)} />
            <Stat label="Score" value={`${averageScore}`} />
          </div>

          <div className="mt-4 space-y-3">
            {rows.map((row) => (
              <SentenceCard key={row.id} row={row} onSave={onSave} />
            ))}
          </div>

          {/* PRD §14.7 — a mis-heard word must not read as the learner's mistake. */}
          <p className="mt-4 text-[10px] text-muted-foreground">
            Based on speech-to-text, which isn't perfect. If a word was heard wrong, ignore that
            line.
          </p>
        </>
      )}

      {rows && rows.length === 0 && !error && (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing to check yet — speak a few full sentences first.
        </p>
      )}

      {!rows && signedIn && !busy && !error && (
        <p className="mt-4 text-sm text-muted-foreground">
          Finished talking? Get grammar, vocabulary and a more natural version of every sentence you
          said.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-lg font-semibold leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function SentenceCard({
  row,
  onSave,
}: {
  row: SentenceFeedback;
  onSave: (original: string, improved: string) => void;
}) {
  // A correct sentence gets a short, genuinely positive card. Padding it with a
  // manufactured "improvement" is exactly the false positive §10.8 warns about.
  const good = row.is_correct;

  return (
    <div
      className={`rounded-2xl border p-4 ${
        good ? "border-border bg-background/40" : "border-destructive/30 bg-destructive/5"
      }`}
    >
      <div className="flex items-start gap-2">
        <span className="text-sm">{good ? "✅" : "✏️"}</span>
        <p className="flex-1 text-sm leading-snug">
          <span className={good ? "" : "line-through opacity-60"}>{row.original_text}</span>
        </p>
      </div>

      {row.corrected && (
        <p className="mt-2 pl-6 text-sm font-medium text-foreground">{row.corrected}</p>
      )}

      {row.errors.length > 0 && (
        <ul className="mt-2 space-y-1 pl-6">
          {row.errors.map((error, i) => (
            <li key={i} className="text-xs text-muted-foreground">
              <span className="font-semibold text-destructive">{error.kind}</span>{" "}
              <span className="line-through">{error.wrong}</span> → {error.right}
              <span className="block text-[11px] opacity-80">{error.why}</span>
            </li>
          ))}
        </ul>
      )}

      {row.vocab.length > 0 && (
        <ul className="mt-2 space-y-1 pl-6">
          {row.vocab.map((up, i) => (
            <li key={i} className="text-xs text-muted-foreground">
              <span className="font-semibold text-primary">better word</span> {up.basic} →{" "}
              <span className="font-medium text-foreground">{up.better}</span>
            </li>
          ))}
        </ul>
      )}

      {/* The natural version is the most useful line for a learner who is already
          grammatically correct, so show it whenever it adds something. */}
      {row.natural && row.natural !== row.corrected && row.natural !== row.original_text && (
        <p className="mt-2 pl-6 text-xs text-muted-foreground">
          <span className="font-semibold">natural</span> {row.natural}
        </p>
      )}

      <div className="mt-3 flex gap-2 pl-6">
        <button
          type="button"
          onClick={() => onSave(row.original_text, row.corrected ?? row.natural)}
          className="rounded-full border border-border px-3 py-1 text-[11px] font-semibold hover:bg-muted"
        >
          ＋ Save to notes
        </button>
        {row.cefr && (
          <span className="self-center text-[10px] uppercase tracking-wider text-muted-foreground">
            {row.cefr}
          </span>
        )}
      </div>
    </div>
  );
}
