import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listCategories, listTopics, type Category, type Topic } from "@/lib/api";
import { levelLabel, topicEmoji } from "@/lib/presentation";

export const Route = createFileRoute("/topics/")({
  head: () => ({
    meta: [
      { title: "Conversation topics — EnglishTalker" },
      {
        name: "description",
        content:
          "Browse curated English speaking topics by level. Each topic is used by one or more live rooms.",
      },
      { property: "og:title", content: "Conversation topics — EnglishTalker" },
      {
        property: "og:description",
        content: "Curated topics with sample questions. Open a topic to see rooms using it.",
      },
      { property: "og:url", content: "/topics" },
    ],
    links: [{ rel: "canonical", href: "/topics" }],
  }),
  component: TopicsIndex,
});

const LEVELS = ["All", "beginner", "intermediate", "advanced"] as const;

function TopicsIndex() {
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("All");
  const {
    data: topics,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["topics"],
    queryFn: () => listTopics(),
  });
  const categoriesQ = useQuery({ queryKey: ["categories"], queryFn: () => listCategories() });

  const filtered: Topic[] = !topics
    ? []
    : level === "All"
      ? topics
      : topics.filter((t) => t.level === level);

  // Group into the admin's categories (PRD §8.1), keeping their sort order.
  // Ungrouped topics fall into a trailing "Other" group rather than disappearing.
  const groups = groupByCategory(filtered, categoriesQ.data ?? []);

  return (
    <>
      <section className="container-page pt-16 pb-8 text-center">
        <span className="chip">Topics</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Always know <span className="italic text-primary">what to talk about.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Topics live in rooms — open one to see active rooms that use it and the learning notes to
          warm up.
        </p>
      </section>

      <section className="container-page pb-4">
        <div className="flex flex-wrap justify-center gap-2">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={`rounded-full px-4 py-2 text-sm font-medium border transition-colors ${level === l ? "bg-primary text-primary-foreground border-primary" : "bg-card text-foreground border-border hover:bg-muted"}`}
            >
              {l === "All" ? "All" : levelLabel(l)}
            </button>
          ))}
        </div>
      </section>

      <section className="container-page py-10">
        {isLoading && <LoadingGrid />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {!isLoading && !isError && filtered.length === 0 && (
          <p className="text-center text-muted-foreground">No topics at this level yet.</p>
        )}
        <div className="space-y-12">
          {groups.map((group) => (
            <div key={group.key}>
              <div className="flex items-baseline gap-3">
                <h2 className="text-2xl text-ink">{group.name}</h2>
                <span className="text-xs text-muted-foreground">
                  {group.topics.length} topic{group.topics.length === 1 ? "" : "s"}
                </span>
              </div>
              {group.description && (
                <p className="mt-1 text-sm text-muted-foreground">{group.description}</p>
              )}
              <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {group.topics.map((t) => (
                  <TopicCard key={t.id} topic={t} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

/** A category with the topics that belong to it, ready to render. */
interface TopicGroup {
  readonly key: string;
  readonly name: string;
  readonly description: string | null;
  readonly topics: readonly Topic[];
}

function groupByCategory(
  topics: readonly Topic[],
  categories: readonly Category[],
): readonly TopicGroup[] {
  const groups: TopicGroup[] = categories
    .map((c) => ({
      key: c.id,
      name: c.name,
      description: c.description,
      topics: topics.filter((t) => t.category_id === c.id),
    }))
    .filter((g) => g.topics.length > 0);

  const known = new Set(categories.map((c) => c.id));
  const ungrouped = topics.filter((t) => t.category_id === null || !known.has(t.category_id));
  if (ungrouped.length > 0) {
    // "All topics" reads better than "Other" when no category exists at all.
    groups.push({
      key: "__ungrouped__",
      name: groups.length === 0 ? "All topics" : "Other",
      description: null,
      topics: ungrouped,
    });
  }
  return groups;
}

function TopicCard({ topic }: { topic: Topic }) {
  return (
    <Link
      to="/topics/$topicId"
      params={{ topicId: topic.id }}
      className="rounded-3xl border border-border bg-card overflow-hidden hover:shadow-[var(--shadow-soft)] hover:-translate-y-0.5 transition-all"
    >
      {topic.cover_image_url && (
        <img
          src={topic.cover_image_url}
          alt=""
          loading="lazy"
          className="h-32 w-full object-cover"
        />
      )}
      <div className="p-7">
        <div className="flex items-center justify-between">
          <div className="text-3xl">{topicEmoji(topic.slug)}</div>
          <span className="text-[10px] uppercase tracking-wider rounded-full px-2 py-1 bg-muted text-muted-foreground">
            {levelLabel(topic.level)}
          </span>
        </div>
        <h3 className="mt-3 text-xl text-ink">{topic.title}</h3>
        <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
          {topic.description ?? "Practice speaking on this topic."}
        </p>
        <div className="mt-4 text-xs font-semibold text-primary">Open topic →</div>
      </div>
    </Link>
  );
}

function LoadingGrid() {
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-44 rounded-3xl border border-border bg-card animate-pulse" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-3xl border border-dashed border-destructive/40 bg-destructive/5 p-8 text-center">
      <div className="text-3xl">⚠️</div>
      <p className="mt-2 text-sm text-foreground">{message}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Is the backend running? Check VITE_API_BASE_URL.
      </p>
      <button
        onClick={onRetry}
        className="mt-4 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"
      >
        Retry
      </button>
    </div>
  );
}
