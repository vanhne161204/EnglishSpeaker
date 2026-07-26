import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/how-it-works")({
  head: () => ({
    meta: [
      { title: "How it works — EnglishTalker" },
      { name: "description", content: "From picking a topic to your first sentence, here's how a session on EnglishTalker actually flows." },
      { property: "og:title", content: "How it works — EnglishTalker" },
      { property: "og:description", content: "A 5-step walkthrough of a typical EnglishTalker session." },
      { property: "og:url", content: "/how-it-works" },
    ],
    links: [{ rel: "canonical", href: "/how-it-works" }],
  }),
  component: HowPage,
});

const STEPS = [
  {
    n: "01",
    title: "Pick a mode",
    body: "Choose Normal to show up as yourself, or Incognito to practice with a temporary display name. Matching always respects your choice.",
  },
  {
    n: "02",
    title: "Choose a topic",
    body: "Browse admin-curated topics tagged by level. Read the sample questions to warm up your thinking before the call.",
  },
  {
    n: "03",
    title: "Find your partner",
    body: "Join an open room, use Match One for a focused 1-on-1, or tap Random Match. You'll be paired by mode, level, topic, and interests.",
  },
  {
    n: "04",
    title: "Speak — with help nearby",
    body: "Chat by text or join the voice call. When you're stuck, ask the coach to improve your sentence or suggest what to say next. Translate a word without leaving the room.",
  },
  {
    n: "05",
    title: "Save and review",
    body: "Save the best sentences — yours, your partner's, or the coach's — to your Sentence Notes. Review them anytime, grouped by topic.",
  },
];

function HowPage() {
  return (
    <>
      <section className="container-page pt-16 pb-10 text-center">
        <span className="chip">How it works</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">From app icon to first sentence in <span className="italic text-primary">60 seconds.</span></h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">A typical session is five short steps. Here's exactly what happens.</p>
      </section>

      <section className="container-page py-12">
        <ol className="space-y-5">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-4xl border border-border bg-card p-8 lg:p-10 grid lg:grid-cols-12 gap-6 items-start">
              <div className="lg:col-span-3">
                <div className="font-display text-6xl text-primary leading-none">{s.n}</div>
              </div>
              <div className="lg:col-span-9">
                <h2 className="text-3xl text-ink">{s.title}</h2>
                <p className="mt-3 text-muted-foreground leading-relaxed">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="container-page py-16">
        <div className="rounded-4xl bg-secondary text-secondary-foreground p-12 text-center">
          <h2 className="text-4xl">That's it. Now go talk.</h2>
          <p className="mt-3 text-secondary-foreground/80">Free forever. No card required to start.</p>
          <Link to="/pricing" className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground">Start free</Link>
        </div>
      </section>
    </>
  );
}
