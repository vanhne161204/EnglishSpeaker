// The safety queue: abuse reports and room bans (docs/11_Security.md §11.9).
//
// This product puts strangers in a voice call together. Until now there was no
// way to report what happened in one, and no way to lift a ban issued by
// mistake. Both of those are obligations rather than features.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  adminListBans,
  adminListReports,
  adminLiftBan,
  adminReviewReport,
  type AbuseReport,
  type ReportStatus,
  type RoomBan,
} from "@/lib/api";

const STATUSES: ReportStatus[] = ["open", "resolved", "dismissed"];

export function SafetyPanel() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<ReportStatus>("open");

  const reportsQ = useQuery({
    queryKey: ["admin", "reports", status],
    queryFn: () => adminListReports(status),
  });
  const bansQ = useQuery({ queryKey: ["admin", "bans"], queryFn: () => adminListBans() });

  const refresh = () => void qc.invalidateQueries({ queryKey: ["admin"] });

  const reviewM = useMutation({
    mutationFn: (v: { id: string; body: Parameters<typeof adminReviewReport>[1] }) =>
      adminReviewReport(v.id, v.body),
    onSuccess: refresh,
  });
  const liftM = useMutation({ mutationFn: adminLiftBan, onSuccess: refresh });

  return (
    <div className="space-y-8">
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg text-ink">Reports</h3>
          <div className="inline-flex rounded-full border border-border bg-card p-1">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`rounded-full px-4 py-1.5 text-xs font-semibold capitalize ${
                  status === s
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {reviewM.isError && (
          <p className="mt-3 rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {(reviewM.error as Error).message}
          </p>
        )}

        <div className="mt-4 space-y-3">
          {reportsQ.isLoading && (
            <div className="h-28 animate-pulse rounded-4xl border border-border bg-card" />
          )}
          {reportsQ.isSuccess && reportsQ.data.length === 0 && (
            <p className="rounded-4xl border border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
              {status === "open"
                ? "Nothing waiting. That is the state you want this page in."
                : `No ${status} reports.`}
            </p>
          )}
          {(reportsQ.data ?? []).map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              busy={reviewM.isPending}
              onReview={(body) => reviewM.mutate({ id: r.id, body })}
            />
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-lg text-ink">Active bans</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          A kick is a time-out from one room, not a life sentence. These expire on their own;
          lifting one here ends it early.
        </p>

        <div className="mt-4 space-y-2">
          {bansQ.isSuccess && bansQ.data.length === 0 && (
            <p className="rounded-4xl border border-border bg-card px-6 py-8 text-center text-sm text-muted-foreground">
              Nobody is banned from any room.
            </p>
          )}
          {(bansQ.data ?? []).map((b) => (
            <BanRow key={b.id} ban={b} busy={liftM.isPending} onLift={() => liftM.mutate(b.id)} />
          ))}
        </div>
      </section>
    </div>
  );
}

function ReportCard({
  report,
  busy,
  onReview,
}: {
  report: AbuseReport;
  busy: boolean;
  onReview: (body: Parameters<typeof adminReviewReport>[1]) => void;
}) {
  const [note, setNote] = useState("");
  const open = report.status === "open";

  return (
    <div className="rounded-4xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm">
            <span className="font-semibold text-foreground">{report.reporter_name}</span>
            <span className="text-muted-foreground"> reported </span>
            <span className="font-semibold text-foreground">{report.target_name}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-full bg-muted px-2 py-0.5 capitalize">{report.reason}</span>
            <span>{new Date(report.created_at).toLocaleString()}</span>
          </div>
        </div>
        {!open && (
          <span
            className={`rounded-full px-3 py-1 text-[11px] font-semibold capitalize ${
              report.status === "resolved"
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {report.status}
          </span>
        )}
      </div>

      {report.detail && (
        <p className="mt-3 text-sm text-foreground leading-relaxed">{report.detail}</p>
      )}
      {report.quoted_text && (
        // Snapshotted at report time, so it survives deletion of the original.
        <blockquote className="mt-3 border-l-2 border-border pl-3 text-sm italic text-muted-foreground">
          “{report.quoted_text}”
        </blockquote>
      )}
      {report.review_note && (
        <p className="mt-3 rounded-2xl bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          Decision: {report.review_note}
        </p>
      )}

      {open && (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What did you decide, and why?"
            className="w-full rounded-2xl border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
          />
          <div className="flex flex-wrap gap-2">
            <button
              disabled={busy}
              onClick={() => onReview({ status: "dismissed", note: note || null })}
              className="rounded-full border border-border px-4 py-2 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              Dismiss
            </button>
            <button
              disabled={busy}
              onClick={() => onReview({ status: "resolved", note: note || null })}
              className="rounded-full border border-border px-4 py-2 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              Resolve, no action
            </button>
            {/* Deciding and acting are one motion for a moderator, so they are
                one request — two calls can half-fail. */}
            <button
              disabled={busy}
              onClick={() =>
                onReview({
                  status: "resolved",
                  note: note || null,
                  suspend_target: true,
                  suspend_reason: note || "Reported for abuse",
                })
              }
              className="rounded-full bg-destructive px-4 py-2 text-xs font-semibold text-destructive-foreground hover:opacity-90 disabled:opacity-50"
            >
              Resolve &amp; suspend {report.target_name}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function BanRow({ ban, busy, onLift }: { ban: RoomBan; busy: boolean; onLift: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3">
      <div className="min-w-0 text-sm">
        <span className="font-medium text-foreground">{ban.user_name ?? "(deleted account)"}</span>
        <span className="text-muted-foreground"> · {ban.room_title ?? "(deleted room)"}</span>
        <div className="text-xs text-muted-foreground">
          {ban.reason ?? "No reason given"} ·{" "}
          {ban.expires_at ? `expires ${new Date(ban.expires_at).toLocaleString()}` : "permanent"}
        </div>
      </div>
      <button
        disabled={busy}
        onClick={onLift}
        className="flex-none rounded-full border border-border px-4 py-1.5 text-xs font-semibold hover:bg-muted disabled:opacity-50"
      >
        Lift ban
      </button>
    </div>
  );
}
