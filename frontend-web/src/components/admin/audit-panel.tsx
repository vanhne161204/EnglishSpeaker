// Every privileged action, and who took it.
//
// Read-only by design. There is no edit or delete anywhere in this feature — the
// moment an audit log becomes editable it stops being evidence.

import { useQuery } from "@tanstack/react-query";

import { adminAudit, type AuditEntry } from "@/lib/api";

/** Plain-English labels. `user.update` means nothing to someone skimming. */
const ACTION_LABELS: Record<string, string> = {
  "user.update": "Changed an account",
  "user.delete": "Deleted an account",
  "report.review": "Decided a report",
  "ban.lift": "Lifted a ban",
};

export function AuditPanel() {
  const q = useQuery({ queryKey: ["admin", "audit"], queryFn: () => adminAudit() });

  if (q.isLoading) {
    return <div className="h-48 animate-pulse rounded-4xl border border-border bg-card" />;
  }
  if (q.isError) {
    return (
      <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
        {(q.error as Error).message}
      </p>
    );
  }

  const entries = q.data ?? [];
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground leading-relaxed">
        Boring until the first time it matters. Every promotion, suspension, deletion and report
        decision is recorded here, permanently.
      </p>

      {entries.length === 0 ? (
        <p className="rounded-4xl border border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
          Nothing yet. Admin actions will appear here as they happen.
        </p>
      ) : (
        <ol className="space-y-2">
          {entries.map((e) => (
            <Row key={e.id} entry={e} />
          ))}
        </ol>
      )}
    </div>
  );
}

function Row({ entry }: { entry: AuditEntry }) {
  return (
    <li className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm">
          <span className="font-semibold text-foreground">{entry.actor_name}</span>{" "}
          <span className="text-muted-foreground">
            {ACTION_LABELS[entry.action] ?? entry.action}
          </span>
          {entry.target_name && <span className="text-foreground"> · {entry.target_name}</span>}
        </span>
        <span className="flex-none text-xs text-muted-foreground">
          {new Date(entry.created_at).toLocaleString()}
        </span>
      </div>
      {entry.detail && <p className="mt-1 text-xs text-muted-foreground">{entry.detail}</p>}
    </li>
  );
}
