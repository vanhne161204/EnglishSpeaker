// Reporting someone you met in a room (docs/11_Security.md §11.9).
//
// This is the other half of the admin safety queue. Without it the queue can
// never receive anything, and a product that puts strangers in a voice call has
// no way to hear that one of them went wrong.
//
// Deliberately quiet: no confirmation shouting, no "are you sure". Someone
// filing this has usually just had an unpleasant few minutes, and the kindest
// interface is a short one.

import { useState } from "react";

import { reportUser, type ReportReason } from "@/lib/api";

const REASONS: { id: ReportReason; label: string }[] = [
  { id: "harassment", label: "Harassment or bullying" },
  { id: "inappropriate", label: "Inappropriate content" },
  { id: "hate", label: "Hate speech" },
  { id: "spam", label: "Spam or advertising" },
  { id: "other", label: "Something else" },
];

export function ReportDialog({
  targetUserId,
  targetName,
  roomId,
  onClose,
}: {
  targetUserId: string;
  targetName: string;
  roomId: string;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<ReportReason>("harassment");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await reportUser({
        target_user_id: targetUserId,
        room_id: roomId,
        reason,
        detail: detail.trim() || null,
      });
      setSent(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-3xl border border-border bg-card p-6 shadow-2xl">
        {sent ? (
          <>
            <h2 className="text-xl text-ink">Thank you</h2>
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              A moderator will read this. You will not hear back on every report, but every one is
              read.
            </p>
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              If you would rather not talk to {targetName} again, you can leave the room — the host
              can also remove them.
            </p>
            <button
              onClick={onClose}
              className="mt-5 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90"
            >
              Close
            </button>
          </>
        ) : (
          <>
            <h2 className="text-xl text-ink">Report {targetName}</h2>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
              Tell us what happened. They are not told that you reported them.
            </p>

            <div className="mt-5 space-y-2">
              {REASONS.map((r) => (
                <label
                  key={r.id}
                  className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-2.5 text-sm ${
                    reason === r.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted"
                  }`}
                >
                  <input
                    type="radio"
                    name="reason"
                    checked={reason === r.id}
                    onChange={() => setReason(r.id)}
                    className="accent-[var(--primary)]"
                  />
                  {r.label}
                </label>
              ))}
            </div>

            <label className="mt-4 block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                What happened? (optional)
              </span>
              <textarea
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Anything that helps a moderator understand…"
                className="mt-1 w-full resize-none rounded-2xl border border-border bg-background p-3 text-sm focus:border-primary focus:outline-none"
              />
            </label>

            {err && <p className="mt-3 text-sm text-destructive">{err}</p>}

            <div className="mt-5 flex gap-2">
              <button
                onClick={onClose}
                className="flex-1 rounded-full border border-border px-4 py-2.5 text-sm font-semibold hover:bg-muted"
              >
                Cancel
              </button>
              <button
                disabled={busy}
                onClick={() => void submit()}
                className="flex-1 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Sending…" : "Send report"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
