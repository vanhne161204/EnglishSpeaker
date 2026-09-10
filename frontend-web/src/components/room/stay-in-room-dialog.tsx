// Shown when someone tries to leave a room by accident — a header link, the
// browser's back button, a logo click.
//
// "Stay" is the primary button on purpose. The person did not ask to leave;
// they clicked something else. The safe answer should be the easy one.

export function StayInRoomDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        role="alertdialog"
        aria-labelledby="stay-title"
        className="w-full max-w-md rounded-3xl border border-border bg-card p-6 shadow-2xl"
      >
        <h2 id="stay-title" className="text-xl text-ink">
          Leave this room?
        </h2>
        <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
          You are still in the conversation. If you go now, you drop out of the call and the live
          script, and your seat is given up.
        </p>
        <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
          Want your practice report? Stay, then use the <strong>Leave</strong> button in the room.
        </p>

        <div className="mt-5 flex gap-2">
          <button
            onClick={onLeave}
            className="flex-1 rounded-full border border-border px-4 py-2.5 text-sm font-semibold hover:bg-muted"
          >
            Leave anyway
          </button>
          <button
            onClick={onStay}
            autoFocus
            className="flex-1 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
          >
            Stay in room
          </button>
        </div>
      </div>
    </div>
  );
}
