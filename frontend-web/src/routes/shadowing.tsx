import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ShadowingSession } from "@/components/shadowing/shadowing-session";
import { VideoSession } from "@/components/shadowing/video-session";
import { listTopics, shadowingVideos, type ShadowingVideoCard, type Topic } from "@/lib/api";
import { levelLabel, topicEmoji } from "@/lib/presentation";
import { requireAuth } from "@/lib/require-auth";
import { youtubeThumbnail } from "@/lib/youtube";
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

type Tab = "topics" | "videos";

const TAB_LABELS: Record<Tab, string> = { topics: "Topics", videos: "Videos" };

function ShadowingPage() {
  const [tab, setTab] = useState<Tab>("topics");
  const [topic, setTopic] = useState<Topic | null>(null);
  const [video, setVideo] = useState<ShadowingVideoCard | null>(null);
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const videosQ = useQuery({
    queryKey: ["shadowing-videos"],
    queryFn: () => shadowingVideos(),
    enabled: tab === "videos",
  });

  if (topic) return <ShadowingSession topic={topic} onExit={() => setTopic(null)} />;
  if (video) return <VideoSession video={video} onExit={() => setVideo(null)} />;

  const failed = tab === "topics" ? topicsQ : videosQ;

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

      <div className="mt-6 inline-flex gap-1 rounded-3xl border border-border bg-card p-1">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-2 text-sm font-medium ${
              tab === t
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {failed.isError && (
        <div className="mt-6 max-w-2xl">
          <ErrorState
            message={(failed.error as Error)?.message ?? "Couldn't load this list"}
            onRetry={() => void failed.refetch()}
          />
        </div>
      )}

      {tab === "topics" ? (
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
            {topicsQ.isLoading && <SkeletonCards />}
          </div>
        </div>
      ) : (
        <div className="mt-6">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Real speech, one sentence at a time
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(videosQ.data ?? []).map((v) => (
              <button
                key={v.id}
                onClick={() => setVideo(v)}
                className="overflow-hidden text-left rounded-3xl border border-border bg-card transition-colors hover:bg-muted"
              >
                <img
                  src={youtubeThumbnail(v.youtube_id)}
                  alt=""
                  loading="lazy"
                  className="aspect-video w-full max-w-full bg-muted object-cover"
                />
                <div className="p-4">
                  <div className="font-semibold text-ink line-clamp-2">{v.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {levelLabel(v.level)} · {v.sentences} sentences
                    {v.practised > 0 ? ` · ${v.practised} practised` : ""}
                  </div>
                </div>
              </button>
            ))}
            {videosQ.isLoading && <SkeletonCards />}
          </div>
          {videosQ.isSuccess && videosQ.data.length === 0 && (
            <p className="mt-3 max-w-2xl rounded-3xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
              No video lessons yet. Practise with the topics for now.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SkeletonCards() {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-20 rounded-3xl bg-card border border-border animate-pulse" />
      ))}
    </>
  );
}
