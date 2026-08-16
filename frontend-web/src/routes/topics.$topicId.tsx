import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError, getTopic, getTopicDoc, listRooms, type Doc, type DocSection } from "@/lib/api";
import { levelLabel, modeLabel, sizeLabel, topicEmoji } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/topics/$topicId")({
  head: () => ({
    meta: [
      { title: "Topic — EnglishTalker" },
      {
        name: "description",
        content:
          "A conversation topic for English speaking practice — see its learning notes and active rooms.",
      },
    ],
  }),
  component: TopicPage,
});

function TopicPage() {
  const { topicId } = Route.useParams();

  const topicQ = useQuery({ queryKey: ["topic", topicId], queryFn: () => getTopic(topicId) });
  // A topic without documentation is normal, not an error — the endpoint 404s and
  // we render the empty state instead of retrying.
  const docQ = useQuery({
    queryKey: ["topic-doc", topicId],
    queryFn: () => getTopicDoc(topicId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  const roomsQ = useQuery({ queryKey: ["rooms"], queryFn: () => listRooms() });

  if (topicQ.isLoading) {
    return (
      <section className="container-page py-20">
        <div className="h-40 rounded-4xl bg-card border border-border animate-pulse" />
      </section>
    );
  }
  if (topicQ.isError || !topicQ.data) {
    return (
      <section className="container-page py-20">
        <ErrorState
          message={(topicQ.error as Error)?.message ?? "Topic not found"}
          onRetry={() => topicQ.refetch()}
        />
        <div className="mt-6 text-center">
          <Link to="/topics" className="text-primary hover:underline">
            ← All topics
          </Link>
        </div>
      </section>
    );
  }

  const topic = topicQ.data;
  const doc = docQ.data ?? null;
  // Backend rooms carry a single topic *title*; match on that.
  const rooms = (roomsQ.data ?? []).filter((r) => r.topic === topic.title);

  return (
    <>
      <section className="container-page pt-12">
        <Link to="/topics" className="text-sm text-muted-foreground hover:text-foreground">
          ← All topics
        </Link>
        <div className="mt-4 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-5xl text-ink flex items-center gap-3">
              <span className="text-5xl">{topicEmoji(topic.slug)}</span>
              {topic.title}
            </h1>
            <p className="mt-3 max-w-2xl text-muted-foreground leading-relaxed">
              {topic.description ?? "Practice speaking on this topic."}
            </p>
            <div className="mt-3 flex gap-2">
              <span className="chip">{levelLabel(topic.level)}</span>
              <span className="chip">
                {rooms.length} active room{rooms.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>
          <Link
            to="/match"
            className="rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground"
          >
            Match 1-on-1 on this topic
          </Link>
        </div>
      </section>

      <section className="container-page py-10 grid lg:grid-cols-12 gap-5">
        <div className="lg:col-span-7 rounded-4xl bg-cream border border-border p-7">
          <h2 className="text-2xl text-ink">{doc?.title ?? "Learning notes"}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {doc?.intro ?? "Trusted material for this topic. The in-room AI coach uses it too."}
          </p>
          {docQ.isLoading ? (
            <div className="mt-5 h-24 rounded-2xl bg-card border border-border animate-pulse" />
          ) : !doc || doc.sections.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              No notes for this topic yet — jump into a room and ask the AI coach.
            </div>
          ) : (
            <DocBody doc={doc} />
          )}
        </div>

        <div className="lg:col-span-5">
          <h2 className="text-2xl text-ink">Rooms using this topic</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Open a room to start talking — or match for a private 1-on-1.
          </p>
          {roomsQ.isLoading ? (
            <div className="mt-5 h-24 rounded-3xl bg-card border border-border animate-pulse" />
          ) : rooms.length === 0 ? (
            <div className="mt-5 rounded-3xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No active rooms yet. Try{" "}
              <Link to="/match" className="text-primary font-semibold">
                Random Match
              </Link>{" "}
              to start one.
            </div>
          ) : (
            <div className="mt-5 space-y-3">
              {rooms.map((r) => (
                <Link
                  key={r.id}
                  to="/rooms/$roomId"
                  params={{ roomId: r.id }}
                  className="block rounded-3xl border border-border bg-card p-5 hover:border-primary hover:shadow-[var(--shadow-soft)] transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xl text-ink flex items-center gap-2">
                        <span>{topicEmoji(topic.slug)}</span>
                        {r.title}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {modeLabel(r.mode)} · {sizeLabel(r.kind)} · {levelLabel(r.level)}
                      </div>
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      <div>
                        {r.participant_count}/{r.capacity}
                      </div>
                      <div className="mt-2 rounded-full bg-primary text-primary-foreground px-3 py-1 font-semibold">
                        Enter →
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}

/* ---------- Documentation renderer (PRD §8.2) ---------- */

/** Heading shown above a section when the admin left the title blank. */
const SECTION_FALLBACK_TITLE: Record<DocSection["type"], string> = {
  vocabulary: "Vocabulary",
  phrases: "Useful phrases",
  questions: "Conversation questions",
  tips: "Speaking tips",
  text: "Notes",
};

function DocBody({ doc }: { doc: Doc }) {
  return (
    <div className="mt-5 space-y-5">
      {doc.sections.map((section) => (
        <section key={section.id}>
          <h3 className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {section.title ?? SECTION_FALLBACK_TITLE[section.type]}
          </h3>
          <div className="mt-2">
            <SectionBody section={section} />
          </div>
        </section>
      ))}
    </div>
  );
}

function SectionBody({ section }: { section: DocSection }) {
  // A section's `type` decides where its content lives: vocabulary/phrases keep
  // it in `items`, questions in `questions`, and tips/text in `body`.
  if (section.type === "vocabulary" || section.type === "phrases") {
    return (
      <ul className="grid sm:grid-cols-2 gap-2.5">
        {section.items.map((item) => (
          <li key={item.id} className="rounded-2xl border border-border bg-card px-4 py-3">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-sm font-semibold text-foreground">{item.term}</span>
              {item.phonetic && (
                <span className="text-xs text-muted-foreground">{item.phonetic}</span>
              )}
            </div>
            {item.meaning && <p className="mt-1 text-sm text-muted-foreground">{item.meaning}</p>}
            {item.translation && (
              <p className="mt-0.5 text-sm text-muted-foreground italic">{item.translation}</p>
            )}
            {item.example && (
              <p className="mt-1.5 text-xs text-muted-foreground">“{item.example}”</p>
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (section.type === "questions") {
    return (
      <ul className="space-y-2.5">
        {section.questions.map((question) => (
          <li key={question.id} className="rounded-2xl border border-border bg-card px-4 py-3">
            <p className="text-sm font-semibold text-foreground">{question.text}</p>
            {question.translation && (
              <p className="mt-0.5 text-xs text-muted-foreground italic">{question.translation}</p>
            )}
            {/* Answer templates hand the learner a sentence shape to copy. */}
            {question.answer_templates.map((tpl) => (
              <div
                key={tpl.id}
                className="mt-2 rounded-xl border border-dashed border-border bg-background px-3 py-2"
              >
                <p className="text-sm text-foreground">{tpl.template}</p>
                {tpl.example && (
                  <p className="mt-0.5 text-xs text-muted-foreground">e.g. {tpl.example}</p>
                )}
              </div>
            ))}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <p className="rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
      {section.body}
    </p>
  );
}
