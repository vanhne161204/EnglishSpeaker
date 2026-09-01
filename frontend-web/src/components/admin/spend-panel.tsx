// What the AI cost, and where it went (docs §18.8).
//
// A vendor dashboard gives one total. It cannot say which feature ate the budget
// or what a single user costs, and those two answers are what set the price of
// the product. Before this page, the only way to see any of it was to SSH in and
// write SQL.
//
// Money arrives as a decimal STRING and is never parsed into a JS number for
// arithmetic — 0.1 + 0.2 is not 0.3, and this is a bill.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { adminAiSpend } from "@/lib/api";

/** Display only: a fixed number of places, and a hint when it rounds to zero. */
function money(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (n === 0) return "$0.00";
  if (n < 0.01) return `<$0.01`;
  return `$${n.toFixed(2)}`;
}

const WINDOWS = [7, 30, 90] as const;

export function SpendPanel() {
  const [days, setDays] = useState<number>(30);
  const spendQ = useQuery({
    queryKey: ["admin", "spend", days],
    queryFn: () => adminAiSpend(days),
  });

  if (spendQ.isLoading) {
    return <div className="h-64 animate-pulse rounded-4xl border border-border bg-card" />;
  }
  if (spendQ.isError) {
    return (
      <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
        {(spendQ.error as Error).message}
      </p>
    );
  }

  const s = spendQ.data!;
  const taskTotal = s.by_task.reduce((sum, t) => sum + Number(t.cost_usd), 0);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Last 24 hours" value={money(s.today_usd)} />
        <Stat label="Last 7 days" value={money(s.week_usd)} />
        <Stat label="Last 30 days" value={money(s.month_usd)} />
      </div>

      {/* A failed call is a user who saw an error, not just a line in a log. */}
      {s.failed_24h > 0 && (
        <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {s.failed_24h} AI call{s.failed_24h === 1 ? "" : "s"} failed outright in the last 24
          hours. Every one of those was a learner who got an error.
        </p>
      )}

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Breakdown over</span>
        {WINDOWS.map((w) => (
          <button
            key={w}
            onClick={() => setDays(w)}
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              days === w
                ? "bg-primary text-primary-foreground"
                : "border border-border text-muted-foreground hover:bg-muted"
            }`}
          >
            {w} days
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Which feature ate the budget">
          {s.by_task.length === 0 ? (
            <Empty>No AI calls in this window.</Empty>
          ) : (
            <ul className="space-y-3">
              {s.by_task.map((t) => {
                const share = taskTotal > 0 ? (Number(t.cost_usd) / taskTotal) * 100 : 0;
                return (
                  <li key={t.task}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="font-medium text-foreground">{t.task}</span>
                      <span className="text-muted-foreground">
                        {money(t.cost_usd)} · {t.calls} call{t.calls === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full bg-primary" style={{ width: `${share}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="What one user costs">
          {s.by_user.length === 0 ? (
            <Empty>No attributed spend yet.</Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {s.by_user.map((u) => (
                <li key={u.user_id} className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate">
                    <span className="font-medium text-foreground">{u.display_name}</span>
                    {u.username && (
                      <span className="ml-1.5 text-xs text-muted-foreground">@{u.username}</span>
                    )}
                  </span>
                  <span className="flex-none text-muted-foreground">{money(u.cost_usd)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-muted-foreground leading-relaxed">
            This is your cost of goods per learner. Everything about pricing follows from it.
          </p>
        </Card>
      </div>

      <Card title="Provider health, last 24 hours">
        {s.health.length === 0 ? (
          <Empty>No calls in the last 24 hours.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="pb-2 font-medium">Model</th>
                  <th className="pb-2 font-medium text-right">Calls</th>
                  <th className="pb-2 font-medium text-right">Fell back</th>
                  <th className="pb-2 font-medium text-right">Failed</th>
                </tr>
              </thead>
              <tbody>
                {s.health.map((h) => (
                  <tr key={h.model} className="border-t border-border/60">
                    <td className="py-2 font-medium text-foreground">{h.model}</td>
                    <td className="py-2 text-right text-muted-foreground">{h.calls}</td>
                    <td
                      className={`py-2 text-right ${h.degraded > 0 ? "text-amber-700 dark:text-amber-500" : "text-muted-foreground"}`}
                    >
                      {h.degraded}
                    </td>
                    <td
                      className={`py-2 text-right ${h.failed > 0 ? "text-destructive" : "text-muted-foreground"}`}
                    >
                      {h.failed}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-4 text-xs text-muted-foreground leading-relaxed">
          A rising “fell back” count means the first-choice provider is struggling — an outage you
          can see before the bill shows it.
        </p>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-4xl border border-border bg-card p-5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 font-display text-3xl text-ink">{value}</div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{children}</p>;
}
