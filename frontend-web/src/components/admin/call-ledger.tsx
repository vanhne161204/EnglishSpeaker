// The raw AI ledger: one row per call, newest first.
//
// The summary above it answers "how much". This answers "which call", which is
// the only way to find out why a figure looks wrong — a runaway loop, one
// enormous report, a provider quietly falling back on every request.
//
// Costs arrive as decimal STRINGS and are only ever parsed for display. A
// single rescue call costs about $0.000011, so the usual `toFixed(2)` would
// render most of this table as "$0.00".

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { adminAiCalls, type AiCall } from "@/lib/api";

const PAGE = 50;

const TASKS = ["", "rescue", "translation", "sentence_check", "ielts_report", "transcription"];

const TASK_LABELS: Record<string, string> = {
  "": "All tasks",
  rescue: "Rescue",
  translation: "Translation",
  sentence_check: "Sentence feedback",
  ielts_report: "IELTS report",
  transcription: "Speech-to-text",
};

/** Enough decimal places that a fraction of a cent is still a number. */
function exactMoney(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (n === 0) return "—";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(4)}`;
}

export function CallLedger() {
  const [task, setTask] = useState("");
  const [failedOnly, setFailedOnly] = useState(false);
  const [page, setPage] = useState(0);

  const params = {
    limit: PAGE,
    offset: page * PAGE,
    task: task || undefined,
    failed_only: failedOnly || undefined,
  };
  const q = useQuery({
    queryKey: ["admin", "ai-calls", params],
    queryFn: () => adminAiCalls(params),
  });

  const rows = q.data?.items ?? [];

  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Every call</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            One row per AI call, with what it cost. Newest first.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={task}
            onChange={(e) => {
              setTask(e.target.value);
              setPage(0);
            }}
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs"
          >
            {TASKS.map((t) => (
              <option key={t} value={t}>
                {TASK_LABELS[t]}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={failedOnly}
              onChange={(e) => {
                setFailedOnly(e.target.checked);
                setPage(0);
              }}
            />
            Failures only
          </label>
        </div>
      </div>

      {q.isLoading && <div className="mt-4 h-40 animate-pulse rounded-2xl bg-muted/50" />}

      {q.isSuccess && rows.length === 0 && (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No calls match. Nothing has cost you anything yet.
        </p>
      )}

      {rows.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="pb-2 font-medium">When</th>
                <th className="pb-2 font-medium">Task</th>
                <th className="pb-2 font-medium">Model</th>
                <th className="pb-2 font-medium text-right">Tokens</th>
                <th className="pb-2 font-medium text-right">Time</th>
                <th className="pb-2 font-medium text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <Row key={c.id} call={c} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between text-xs">
        <button
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          className="rounded-full border border-border px-3 py-1.5 disabled:opacity-40"
        >
          ← Newer
        </button>
        <span className="text-muted-foreground">Page {page + 1}</span>
        <button
          // No total is fetched: counting the whole table on every page view is
          // the expensive part, and "is there another page" is all this needs.
          disabled={rows.length < PAGE}
          onClick={() => setPage((p) => p + 1)}
          className="rounded-full border border-border px-3 py-1.5 disabled:opacity-40"
        >
          Older →
        </button>
      </div>
    </div>
  );
}

function Row({ call }: { call: AiCall }) {
  const when = new Date(call.created_at);
  return (
    <tr className={`border-t border-border/60 ${call.ok ? "" : "bg-destructive/5"}`}>
      <td className="py-2 text-xs text-muted-foreground whitespace-nowrap">
        {when.toLocaleDateString()} {when.toLocaleTimeString()}
      </td>
      <td className="py-2">
        <span className="text-foreground">{TASK_LABELS[call.task] ?? call.task}</span>
        {call.degraded && (
          <span
            className="ml-1.5 text-[10px] text-amber-700 dark:text-amber-500"
            title="A fallback answered instead of the first choice"
          >
            fell back
          </span>
        )}
        {!call.ok && <span className="ml-1.5 text-[10px] text-destructive">failed</span>}
      </td>
      <td className="py-2 text-xs text-muted-foreground">
        {call.model}
        <span className="ml-1 opacity-60">via {call.provider}</span>
      </td>
      <td className="py-2 text-right text-xs text-muted-foreground whitespace-nowrap">
        {call.input_tokens.toLocaleString()} in / {call.output_tokens.toLocaleString()} out
        {call.cached_tokens > 0 && (
          <span
            className="ml-1 text-emerald-700 dark:text-emerald-500"
            title="Cached input, billed at roughly a tenth of the normal rate"
          >
            ({call.cached_tokens.toLocaleString()} cached)
          </span>
        )}
      </td>
      <td className="py-2 text-right text-xs text-muted-foreground">
        {call.latency_ms > 0 ? `${(call.latency_ms / 1000).toFixed(1)}s` : "—"}
      </td>
      <td className="py-2 text-right font-medium whitespace-nowrap">{exactMoney(call.cost_usd)}</td>
    </tr>
  );
}
