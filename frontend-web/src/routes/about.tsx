import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About — EnglishTalker" },
      { name: "description", content: "EnglishTalker exists to help English learners speak more, with less fear, and with better support." },
      { property: "og:title", content: "About — EnglishTalker" },
      { property: "og:description", content: "Our mission: make English speaking practice feel safe, simple, and daily." },
      { property: "og:url", content: "/about" },
    ],
    links: [{ rel: "canonical", href: "/about" }],
  }),
  component: AboutPage,
});

function AboutPage() {
  return (
    <>
      <section className="container-page pt-16 pb-10">
        <span className="chip">About</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink max-w-3xl">A safe place to <span className="italic text-primary">open your mouth</span> in English.</h1>
        <p className="mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">Many learners know the grammar and the vocabulary — but rarely speak. EnglishTalker fixes that with rooms, partners, topics, notes, and a kind AI coach.</p>
      </section>

      <section className="container-page py-10 grid md:grid-cols-3 gap-5">
        {WHO.map((w) => (
          <div key={w.title} className="rounded-3xl border border-border bg-card p-7">
            <div className="text-3xl">{w.icon}</div>
            <h3 className="mt-3 text-xl text-ink">{w.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{w.body}</p>
          </div>
        ))}
      </section>

      <section className="container-page py-16">
        <div className="rounded-4xl bg-cream border border-border p-10 lg:p-14 grid lg:grid-cols-2 gap-10">
          <div>
            <h2 className="text-4xl text-ink">Our principles</h2>
            <p className="mt-3 text-muted-foreground">A short list we don't compromise on.</p>
          </div>
          <ul className="space-y-4 text-foreground">
            {PRINCIPLES.map((p) => (
              <li key={p.t} className="border-l-2 border-primary pl-4">
                <div className="font-semibold">{p.t}</div>
                <div className="text-sm text-muted-foreground mt-1">{p.d}</div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="container-page py-16 text-center">
        <h2 className="text-4xl text-ink">Speak more. Fear less.</h2>
        <Link to="/pricing" className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground">Start free</Link>
      </section>
    </>
  );
}

const WHO = [
  { icon: "🎓", title: "Students", body: "Practice speaking outside the classroom with real partners at your level." },
  { icon: "💼", title: "Workers", body: "Build confidence for meetings, calls, and emails in a low-pressure space." },
  { icon: "🤝", title: "Job seekers", body: "Rehearse interview answers with topics and coaches tuned for it." },
  { icon: "🌱", title: "Beginners", body: "Use Incognito mode and simple topics to ease into speaking without fear." },
  { icon: "🚀", title: "Intermediates", body: "Push toward natural fluency with sentence-level AI feedback." },
  { icon: "🤫", title: "Shy learners", body: "Practice privately with a temporary name, then graduate to Normal when ready." },
];

const PRINCIPLES = [
  { t: "Speaking first, always.", d: "Every feature must lower the barrier between a thought and a spoken sentence." },
  { t: "Kindness over correction.", d: "The coach is gentle. We explain mistakes politely and encourage attempts." },
  { t: "Privacy is a setting, not an afterthought.", d: "Incognito mode is a first-class citizen and is respected end-to-end." },
  { t: "Real people, real practice.", d: "AI helps — but the human partner across the room is the point." },
];
