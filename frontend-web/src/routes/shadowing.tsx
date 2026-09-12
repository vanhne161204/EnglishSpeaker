import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ShadowingSession } from "@/components/shadowing/shadowing-session";
import { listTopics, type Topic } from "@/lib/api";
import { levelLabel, topicEmoji } from "@/lib/presentation";
import { requireAuth } from "@/lib/require-auth";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/shadowing")({
  // Requires an account (docs/11_Security.md §11.2): attempts are per learner.
  beforeLoad: ({ location }) => requireAuth(location.pathname),
  head: () => ({
    meta: [
      { title: "Shadowing — EnglishTalker" },
      {
        name: "description",
        content: "Hear a short sentence, say it straight back, and see which words came through.",
      },
    ],
  }),
  component: ShadowingPage,
});

function ShadowingPage() {
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const [topic, setTopic] = useState<Topic | null>(null);

  if (topic) return <ShadowingSession topic={topic} onExit={() => setTopic(null)} />;

  return (
    <section className="container-page py-8 lg:py-10">
      <div className="max-w-2xl">
        <h1 className="text-3xl sm:text-4xl text-ink flex items-center gap-3">
          <span>🎧</span> Shadowing
        </h1>
        <p className="mt-2 text-muted-foreground">
          Hear a short sentence, then say it straight back. Copy the words, the rhythm and the tune
          — one sentence at a time. Your recording stays on your device.
        </p>
      </div>

      {topicsQ.isError && (
        <div className="mt-6 max-w-2xl">
          <ErrorState
            message={(topicsQ.error as Error)?.message ?? "Couldn't load topics"}
            onRetry={() => void topicsQ.refetch()}
          />
        </div>
      )}

      <div className="mt-6">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          Choose a topic
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(topicsQ.data ?? []).map((t) => (
            <button
              key={t.id}
              onClick={() => setTopic(t)}
              className="text-left rounded-3xl border border-border bg-card p-4 transition-colors hover:bg-muted"
            >
              <div className="flex items-center gap-2">
                <span className="text-2xl">{topicEmoji(t.slug)}</span>
                <div className="min-w-0">
                  <div className="font-semibold text-ink truncate">{t.title}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {levelLabel(t.level)}
                  </div>
                </div>
              </div>
            </button>
          ))}
          {topicsQ.isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded-3xl bg-card border border-border animate-pulse"
              />
            ))}
        </div>
      </div>
    </section>
  );
}
