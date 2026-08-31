// The "before you go" moment — offered on leaving a room, not during it.
//
// Assessment belongs here rather than beside the live conversation, for two
// reasons that come straight out of docs/10_AI_Design.md §10.3.2:
//
//  1. **Never during.** Correcting someone while they are still speaking
//     destroys the confidence the product exists to build (PRD §14.7). A card
//     sitting under a live room invites exactly that.
//  2. **Leaving is when the session is complete.** Only then is the transcript
//     the whole conversation, which is what both layers grade.
//
// It is always a choice. A report costs real money and takes ~10 seconds, and
// a learner who just wanted to say hello should not be made to sit through one
// — so "Just leave" is always one tap away, and is the default-looking action.

import { useState } from "react";

import { BandReport } from "@/components/room/band-report";
import { CoachReport } from "@/components/room/coach-report";

export interface LeaveDialogProps {
  open: boolean;
  roomId: string;
  /** Reports need a live session; an expired token skips straight to leaving. */
  signedIn: boolean;
  /** Save a corrected sentence to the learner's notes. */
  onSave: (original: string, improved: string) => void;
  /** Actually leave the room. */
  onLeave: () => void;
  /** Dismiss and stay — a mis-tapped Leave should be recoverable. */
  onCancel: () => void;
}

export function LeaveDialog({
  open,
  roomId,
  signedIn,
  onSave,
  onLeave,
  onCancel,
}: LeaveDialogProps) {
  const [showReports, setShowReports] = useState(false);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-foreground/40 p-4 backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Before you leave"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div className="my-auto w-full max-w-2xl rounded-4xl border border-border bg-card p-5 shadow-2xl sm:p-6">
        {!showReports ? (
          <>
            <h2 className="text-lg font-semibold">Before you go</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {signedIn
                ? "Want feedback on what you said? It takes about ten seconds, and only looks at your own speaking — never your partner's."
                : "Sign in next time and you'll get feedback on your speaking after each room."}
            </p>

            <div className="mt-5 flex flex-col gap-2 sm:flex-row-reverse">
              {signedIn && (
                <button
                  type="button"
                  onClick={() => setShowReports(true)}
                  className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
                >
                  Yes, check my English
                </button>
              )}
              <button
                type="button"
                onClick={onLeave}
                className="rounded-full border border-border px-5 py-2.5 text-sm font-semibold hover:bg-muted"
              >
                Just leave
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="rounded-full px-5 py-2.5 text-sm text-muted-foreground hover:text-foreground sm:mr-auto"
              >
                Stay in the room
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-semibold">Your session</h2>
              <button
                type="button"
                onClick={onLeave}
                className="flex-none rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
              >
                Done — leave room
              </button>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Save anything useful to your notes before you go — you can always read this again from
              your profile.
            </p>

            {/* Both reports run on demand from inside their own cards, so a
                learner who only wants one does not pay for both. */}
            <div className="mt-4 space-y-4">
              <BandReport roomId={roomId} signedIn={signedIn} />
              <CoachReport roomId={roomId} signedIn={signedIn} onSave={onSave} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
