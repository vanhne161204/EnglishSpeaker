// Coach Report layer 2 — the IELTS band report (docs §10.3.7, §10.3.14).
//
// Layer 1 is a proofreader. This is the teacher, and it answers the question a
// learner actually has: *what band am I, why, and what do I do this week?*
//
// Four honesty rules this component exists to keep:
//
//  1. **Say "estimated" when it is an estimate.** Pronunciation cannot be scored
//     from a transcript (§10.3.11), so the overall averages three criteria, and
//     the number must be labelled whenever `overall_is_estimate` is set.
//  2. **Show pronunciation as not assessed, with a reason.** Hiding the row
//     would imply it was included.
//  3. **The band is the headline; the space belongs to the blockers.** A score
//     with no next step is a scoreboard, not teaching.
//  4. **Never let it read as an official IELTS result.** The disclaimer is not
//     optional, and free conversation is labelled as weaker evidence than a
//     cue-card task (§10.3.12).

import { useCallback, useEffect, useState } from "react";

import { bandReport, buildBandReport } from "@/lib/api";
import type { CriterionScore, SessionReport } from "@/lib/api/types";

export interface BandReportProps {
  roomId: string;
  signedIn: boolean;
}

const CRITERIA: ReadonlyArray<{ key: string; label: string }> = [
  { key: "fluency", label: "Fluency & coherence" },
  { key: "lexical", label: "Vocabulary" },
  { key: "grammar", label: "Grammar" },
];

/** Bands arrive as numbers; IELTS always writes them to one decimal. */
const band = (value: number) => value.toFixed(1);

export function BandReport({ roomId, signedIn }: BandReportProps) {
  const [report, setReport] = useState<SessionReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load an existing report without re-running it — a plain DB read, no AI call.
  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    bandReport(roomId)
      .then((existing) => {
        if (!cancelled && existing) setReport(existing);
      })
      .catch(() => {
        // None yet, or unreachable. The button still works.
      });
    return () => {
      cancelled = true;
    };
  }, [roomId, signedIn]);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await buildBandReport(roomId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [roomId]);

  return (
    <div className="rounded-4xl border border-border bg-card p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-2xl bg-secondary/40">
            🎯
          </span>
          <div>
            <div className="text-sm font-semibold">IELTS estimate</div>
            <div className="text-[11px] text-muted-foreground">
              Your speaking, scored the way an examiner would
            </div>
          </div>
        </div>

        {signedIn && (
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="flex-none rounded-full bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Marking…" : report ? "Mark again" : "Get my band"}
          </button>
        )}
      </div>

      {!signedIn && (
        <p className="mt-4 text-sm text-muted-foreground">
          Sign in to get a band estimate for your speaking.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      {!report && signedIn && !busy && !error && (
        <p className="mt-4 text-sm text-muted-foreground">
          Talk for a minute or two, then get an estimated band with the three things holding you
          back.
        </p>
      )}

      {report && (
        <>
          {/* The headline. Labelled honestly when it averages three criteria. */}
          <div className="mt-4 rounded-2xl border border-border bg-background/60 p-4">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-semibold leading-none">
                {band(report.band_overall)}
              </span>
              <span className="text-xs text-muted-foreground">
                {report.overall_is_estimate ? "estimated band" : "band"}
                {report.mode === "conversation" && " · free conversation"}
              </span>
            </div>

            <div className="mt-3 space-y-1.5">
              {CRITERIA.map(({ key, label }) => (
                <CriterionRow
                  key={key}
                  label={label}
                  score={report.criteria[key] as CriterionScore | undefined}
                />
              ))}
              {/* Shown, not hidden: omitting the row would imply it was scored. */}
              <div className="flex items-center gap-3 text-sm">
                <span className="w-10 flex-none text-muted-foreground">—</span>
                <span className="flex-1 text-muted-foreground">Pronunciation</span>
                <span
                  className="text-[10px] text-muted-foreground"
                  title="Scoring pronunciation needs the audio itself, which the app doesn't send to the AI."
                >
                  not assessed
                </span>
              </div>
            </div>

            {report.summary && (
              <p className="mt-3 border-t border-border pt-3 text-sm leading-snug">
                {report.summary}
              </p>
            )}
          </div>

          {report.blockers.length > 0 && (
            <div className="mt-4">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                To reach {band(report.next_band)}, fix these
              </h4>
              <ol className="mt-2 space-y-2">
                {report.blockers.map((blocker, i) => (
                  <li key={i} className="rounded-2xl border border-border p-3">
                    <div className="text-sm font-medium">
                      {i + 1}. {blocker.title}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      You said: <span className="italic">“{blocker.example}”</span>
                    </p>
                    <p className="mt-0.5 text-xs">
                      Try: <span className="font-medium">“{blocker.fix}”</span>
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {report.drills.length > 0 && (
            <div className="mt-4">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                This week
              </h4>
              <ul className="mt-2 space-y-1.5">
                {report.drills.map((drill, i) => (
                  <li key={i} className="text-xs">
                    <span className="font-medium">
                      ☐ {drill.title} ({drill.minutes} min)
                    </span>
                    <span className="block text-muted-foreground">{drill.how}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Required on every report (§10.3.14). Not optional, not small print
              we can drop when the layout gets tight. */}
          <p className="mt-4 border-t border-border pt-3 text-[10px] text-muted-foreground">
            This is practice feedback from AI, not an official IELTS score. Only a certified
            examiner can give you a real band.
            {report.mode === "conversation" &&
              " A free conversation is also weaker evidence than a real exam task."}
          </p>
        </>
      )}
    </div>
  );
}

function CriterionRow({ label, score }: { label: string; score?: CriterionScore }) {
  if (!score) return null;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-10 flex-none font-semibold">{band(score.band)}</span>
      <span className="flex-1">{label}</span>
      <span
        className="max-w-[55%] truncate text-[11px] text-muted-foreground"
        title={`${score.what_worked} ${score.what_held_back}`}
      >
        {score.what_held_back}
      </span>
    </div>
  );
}
