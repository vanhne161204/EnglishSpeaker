// Practice history (PRD §8.13): every conversation the learner joined.
//
// Free to open. It shows saved results only; the AI runs when the learner asks
// for feedback on a room's own page.

import { requireAuth } from "@/lib/require-auth";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { myHistory, type HistoryItem } from "@/lib/api";
import { formatWhen, levelLabel, topicEmoji } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/history/")({
  // Requires an account (docs/11_Security.md §11.2). The API enforces this
  // too; the guard just avoids rendering a page that would 401 on every call.
  beforeLoad: ({ location }) => requireAuth(location.pathname),
  head: () => ({
    meta: [
      { title: "History — EnglishTalker" },
      {
        name: "description",
        content: "Look back at the conversations you joined and the AI feedback on your English.",
      },
    ],
  }),
  component: HistoryPage,
});

function HistoryPage() {
  const historyQ = useQuery({ queryKey: ["history"], queryFn: () => myHistory() });
  const items = historyQ.data ?? [];

  return (
    <>
      <section className="container-page pt-16 pb-6 text-center">
        <span className="chip">History</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Every conversation, <span className="italic text-primary">and what you learned.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Open a room you joined to read the conversation again and see the AI's feedback on your
          own sentences. Missed the report when you left? You can ask for it here.
        </p>
      </section>

      <section className="container-page py-8 max-w-4xl mx-auto">
        {historyQ.isLoading && (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-3xl border border-border bg-card"
              />
            ))}
          </div>
        )}

        {historyQ.isError && (
          <ErrorState
            message={(historyQ.error as Error)?.message ?? "Could not load your history"}
            onRetry={() => void historyQ.refetch()}
          />
        )}

        {historyQ.isSuccess && items.length === 0 && (
          <div className="rounded-4xl border border-border bg-card px-6 py-14 text-center">
            <p className="text-lg text-ink">No conversations yet.</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Rooms you join will appear here, with the AI's feedback on what you said.
            </p>
            <Link
              to="/rooms"
              className="mt-6 inline-flex rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90"
            >
              Find a room
            </Link>
          </div>
        )}

        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.room_id ?? item.report_id ?? item.last_seen_at}>
              <HistoryCard item={item} />
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function HistoryCard({ item }: { item: HistoryItem }) {
  const body = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{item.room_exists ? topicEmoji(item.topic) : "🗑"}</span>
          <h2 className="truncate text-lg text-ink">
            {item.room_exists ? item.room_title : "Room deleted"}
          </h2>
          {item.mode === "incognito" && (
            <span className="rounded-full bg-secondary/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider">
              Incognito
            </span>
          )}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          {item.room_exists ? (
            <>
              {item.topic && <span>{item.topic}</span>}
              {item.level && <span>· {levelLabel(item.level)}</span>}
              <span>· Last here {formatWhen(item.last_seen_at)}</span>
              {item.visits !== null && item.visits > 1 && <span>· joined {item.visits} times</span>}
            </>
          ) : (
            // The conversation went with the room; the report is the learner's own.
            <span>
              Report from {formatWhen(item.last_seen_at)}. The conversation was deleted with the
              room.
            </span>
          )}
        </div>

        {item.room_exists ? (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Stat>
              {item.lines_spoken} line{item.lines_spoken === 1 ? "" : "s"} spoken
            </Stat>
            {item.sentences_checked > 0 ? (
              <Stat>
                {item.sentences_checked} checked ·{" "}
                <span className={item.sentences_with_mistakes ? "text-destructive" : ""}>
                  {item.sentences_with_mistakes} with mistakes
                </span>
              </Stat>
            ) : (
              <Stat muted>No feedback yet</Stat>
            )}
          </div>
        ) : (
          item.report_summary && (
            <p className="mt-3 text-sm text-foreground leading-relaxed">{item.report_summary}</p>
          )
        )}
      </div>

      {item.band_overall !== null && (
        <div className="flex-none rounded-2xl border border-border bg-background px-4 py-2 text-center">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            IELTS {item.band_is_estimate ? "est." : ""}
          </div>
          <div className="font-display text-2xl text-ink">{item.band_overall.toFixed(1)}</div>
        </div>
      )}
    </div>
  );

  // A deleted room has no page to open: its conversation is gone.
  if (!item.room_exists || !item.room_id) {
    return <div className="rounded-3xl border border-border bg-card/60 p-5">{body}</div>;
  }
  return (
    <Link
      to="/history/$roomId"
      params={{ roomId: item.room_id }}
      className="block rounded-3xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-soft)]"
    >
      {body}
    </Link>
  );
}

function Stat({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <span
      className={`rounded-full border border-border px-2.5 py-1 ${muted ? "text-muted-foreground" : "text-foreground"}`}
    >
      {children}
    </span>
  );
}
