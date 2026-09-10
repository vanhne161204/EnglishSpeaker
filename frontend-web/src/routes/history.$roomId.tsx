// One past conversation (PRD §8.13): what was said, and the AI's feedback on
// the learner's own sentences.
//
// The two report cards are the same ones offered when leaving a room. They show
// a saved report for free, and let the learner ask for one now if they skipped
// it on the way out.

import { requireAuth } from "@/lib/require-auth";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { BandReport } from "@/components/room/band-report";
import { CoachReport } from "@/components/room/coach-report";
import { ApiError, createNote, getRoom, roomTranscript, type TranscriptSegment } from "@/lib/api";
import { useHydrated, useIdentity } from "@/lib/identity";
import { formatWhen, levelLabel, topicEmoji } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/history/$roomId")({
  beforeLoad: ({ location }) => requireAuth(location.pathname),
  head: () => ({
    meta: [
      { title: "Conversation — EnglishTalker" },
      { name: "description", content: "A past conversation and the AI feedback on it." },
    ],
  }),
  component: HistoryDetail,
});

/** The API's page limit. A full page means there may be more before it. */
const PAGE = 200;

function HistoryDetail() {
  const { roomId } = Route.useParams();
  const identity = useIdentity();
  const hydrated = useHydrated();
  const signedIn = hydrated && !!identity?.token;

  const roomQ = useQuery({ queryKey: ["room", roomId], queryFn: () => getRoom(roomId) });
  const scriptQ = useQuery({
    queryKey: ["history-script", roomId],
    queryFn: () => roomTranscript(roomId, { limit: PAGE }),
    enabled: signedIn,
  });

  // Earlier pages, loaded on demand and kept in front of the first page.
  const [older, setOlder] = useState<TranscriptSegment[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [noMore, setNoMore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const nextBefore = cursor ?? scriptQ.data?.next_before ?? null;
  const canLoadMore = (scriptQ.data?.segments.length ?? 0) === PAGE && !noMore && !!nextBefore;
  const segments = [...older, ...(scriptQ.data?.segments ?? [])];

  const loadEarlier = async () => {
    if (!nextBefore) return;
    setLoadingOlder(true);
    try {
      const page = await roomTranscript(roomId, { limit: PAGE, before: nextBefore });
      setOlder((prev) => [...page.segments, ...prev]);
      setCursor(page.next_before);
      setNoMore(page.segments.length < PAGE);
    } finally {
      setLoadingOlder(false);
    }
  };

  const saveNote = async (original: string, improved: string) => {
    try {
      await createNote({
        original_text: original,
        improved_text: improved,
        source: "ai",
        topic: roomQ.data?.topic ?? null,
      });
      setNotice("Saved to your notes ✓");
    } catch (e) {
      setNotice(`Couldn't save note: ${(e as Error).message}`);
    }
    window.setTimeout(() => setNotice(null), 2500);
  };

  if (roomQ.isError) {
    return (
      <section className="container-page py-20">
        <ErrorState
          message="This room no longer exists"
          hint="Its conversation was deleted with it. Any band report you had is still on your History page."
          onRetry={() => void roomQ.refetch()}
        />
        <BackLink />
      </section>
    );
  }

  // Knowing the room's link is not enough: you must have been in it.
  const notAMember = scriptQ.error instanceof ApiError && scriptQ.error.status === 403;
  if (notAMember) {
    return (
      <section className="container-page py-20">
        <ErrorState
          message="You were not in this room"
          hint="History only shows conversations you joined."
          onRetry={() => void scriptQ.refetch()}
        />
        <BackLink />
      </section>
    );
  }

  const room = roomQ.data;

  return (
    <section className="container-page py-6 lg:py-8">
      <BackLink />

      <header className="mt-3">
        <h1 className="flex items-center gap-2 text-2xl sm:text-3xl text-ink">
          <span>{topicEmoji(room?.topic ?? null)}</span>
          <span className="truncate">{room?.title ?? "…"}</span>
        </h1>
        {room && (
          <div className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted-foreground">
            {room.topic && <span>{room.topic}</span>}
            {room.level && <span>· {levelLabel(room.level)}</span>}
            {room.mode === "incognito" && <span>· Incognito — names are aliases</span>}
          </div>
        )}
      </header>

      <div className="mt-6 grid gap-5 lg:grid-cols-12">
        {/* The conversation. */}
        <div className="flex flex-col rounded-4xl border border-border bg-card lg:col-span-7">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <div className="text-sm font-semibold">📝 Conversation</div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {segments.length} line{segments.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="max-h-[70vh] space-y-3 overflow-y-auto p-5">
            {canLoadMore && (
              <button
                onClick={() => void loadEarlier()}
                disabled={loadingOlder}
                className="w-full rounded-full border border-border py-2 text-xs font-semibold text-muted-foreground hover:bg-muted disabled:opacity-50"
              >
                {loadingOlder ? "Loading…" : "Load earlier lines"}
              </button>
            )}

            {scriptQ.isLoading && <div className="h-40 animate-pulse rounded-2xl bg-muted/50" />}

            {scriptQ.isSuccess && segments.length === 0 && (
              // The script is only saved while someone has it switched on.
              <p className="py-10 text-center text-sm text-muted-foreground">
                No conversation was recorded here. The live script only saves when someone turns it
                on in the room.
              </p>
            )}

            {segments.map((seg) => {
              const mine = seg.user_id === identity?.id;
              return (
                <div
                  key={seg.id}
                  className={
                    mine ? "rounded-2xl border border-primary/20 bg-primary/5 px-3 py-2" : ""
                  }
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wider ${mine ? "text-primary" : "text-muted-foreground"}`}
                    >
                      {mine ? "You" : seg.speaker_name}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(seg.spoken_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  <p className="text-sm leading-snug text-foreground">{seg.text}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* The AI's feedback on the learner's own sentences. */}
        <div className="space-y-5 lg:col-span-5">
          <CoachReport
            roomId={roomId}
            signedIn={signedIn}
            onSave={(original, improved) => void saveNote(original, improved)}
          />
          <BandReport roomId={roomId} signedIn={signedIn} />
        </div>
      </div>

      {scriptQ.data && segments.length > 0 && (
        <p className="mt-4 text-xs text-muted-foreground">
          Last line {formatWhen(segments[segments.length - 1].spoken_at)}.
        </p>
      )}

      {notice && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background shadow-lg">
          {notice}
        </div>
      )}
    </section>
  );
}

function BackLink() {
  return (
    <Link to="/history" className="text-xs text-muted-foreground hover:text-foreground">
      ← All history
    </Link>
  );
}
