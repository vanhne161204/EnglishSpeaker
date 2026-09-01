// The numbers worth putting above the tabs.
//
// Two of these are calls to action rather than statistics: an open report queue
// and a topic with no questions are both things that look fine until someone
// looks. Everything else is context.

import { useQuery } from "@tanstack/react-query";

import { adminOverview } from "@/lib/api";

function money(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (n === 0) return "$0.00";
  return n < 0.01 ? "<$0.01" : `$${n.toFixed(2)}`;
}

export function OverviewStrip({ onOpenSafety }: { onOpenSafety: () => void }) {
  const q = useQuery({ queryKey: ["admin", "overview"], queryFn: adminOverview });

  if (q.isLoading) {
    return <div className="h-24 animate-pulse rounded-4xl border border-border bg-card" />;
  }
  // A broken headline strip should not hide the tabs underneath it.
  if (q.isError || !q.data) return null;

  const o = q.data;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Accounts" value={String(o.total_users)} hint={`${o.admins} admin`} />
        <Stat label="New this week" value={String(o.new_users_7d)} />
        <Stat
          label="AI, last 24h"
          value={money(o.spend_today_usd)}
          hint={`${money(o.spend_month_usd)} this month`}
        />
        <Stat
          label="Suspended"
          value={String(o.suspended)}
          hint={
            o.active_bans > 0
              ? `${o.active_bans} room ban${o.active_bans === 1 ? "" : "s"}`
              : undefined
          }
        />
      </div>

      {o.open_reports > 0 && (
        <button
          onClick={onOpenSafety}
          className="w-full rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-left text-sm text-destructive hover:bg-destructive/10"
        >
          <strong>
            {o.open_reports} report{o.open_reports === 1 ? "" : "s"} waiting.
          </strong>{" "}
          Someone told you something went wrong in a room — open the safety queue.
        </button>
      )}

      {o.topics_without_questions > 0 && (
        <p className="rounded-2xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <strong>{o.topics_without_questions}</strong> topic
          {o.topics_without_questions === 1 ? " has" : "s have"} no questions. They look fine in the
          topic list and are empty in the room.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-4xl border border-border bg-card px-5 py-4">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-display text-2xl text-ink">{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}
