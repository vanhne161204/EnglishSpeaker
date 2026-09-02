// Confirming a room deletion.
//
// This is not an "are you sure?" — it is the only place the person is told what
// they are about to destroy. Deleting a room takes its chat and its transcript
// with it, for everyone who was in it, and there is no undo.
//
// Coach reports survive, because they are the learner's own record of their
// practice and losing those to somebody else's tidy-up would be wrong. Saying so
// here matters: without it, a host has to guess.

import { useState } from "react";

import { deleteRoom } from "@/lib/api";

export function DeleteRoomDialog({
  roomId,
  roomTitle,
  participants,
  /** True when the person can only delete this because they are an admin. */
  asAdmin = false,
  onDeleted,
  onCancel,
}: {
  roomId: string;
  roomTitle: string;
  participants: number;
  asAdmin?: boolean;
  onDeleted: () => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setErr(null);
    try {
      await deleteRoom(roomId);
      onDeleted();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-3xl border border-border bg-card p-6 shadow-2xl">
        <h2 className="text-xl text-ink">Delete “{roomTitle}”?</h2>

        <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
          This removes the room and everything said in it — the chat and the live script — for
          everyone who was there. It cannot be undone.
        </p>

        {/* Ejecting people mid-conversation is the part worth pausing over. */}
        {participants > 0 && (
          <p className="mt-3 rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {participants === 1 ? "1 person is" : `${participants} people are`} still in this room.
            They will be sent back to the room list straight away.
          </p>
        )}

        {asAdmin && (
          <p className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
            This is not your room. Deleting it is recorded in the admin audit log.
          </p>
        )}

        <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
          Coach reports and saved notes are kept — those belong to each learner, not to the room.
        </p>

        {err && <p className="mt-3 text-sm text-destructive">{err}</p>}

        <div className="mt-5 flex gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-full border border-border px-4 py-2.5 text-sm font-semibold hover:bg-muted disabled:opacity-50"
          >
            Keep it
          </button>
          <button
            onClick={() => void confirm()}
            disabled={busy}
            className="flex-1 rounded-full bg-destructive px-4 py-2.5 text-sm font-semibold text-destructive-foreground hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Deleting…" : "Delete room"}
          </button>
        </div>
      </div>
    </div>
  );
}
