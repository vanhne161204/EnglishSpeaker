import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/features")({
  head: () => ({
    meta: [
      { title: "Features — EnglishTalker" },
      {
        name: "description",
        content:
          "Rooms, matches, AI coach, sentence notes, in-room translator, speech-to-text, incognito mode — everything EnglishTalker offers.",
      },
      { property: "og:title", content: "Features — EnglishTalker" },
      {
        property: "og:description",
        content: "The full toolkit for daily English speaking practice.",
      },
      { property: "og:url", content: "/features" },
    ],
    links: [{ rel: "canonical", href: "/features" }],
  }),
  component: FeaturesPage,
});

const SECTIONS = [
  {
    id: "rooms",
    eyebrow: "Rooms",
    title: "One room model. Group or 1-on-1.",
    body: "A room is where conversation happens. Group rooms and 1-on-1 rooms share the same model and features — just a different number of seats. Every room has a topic, a suggested level, and a single mode (Normal or Incognito).",
    bullets: [
      "Real-time text chat with message history",
      "Peer-to-peer voice calls (mute, unmute, leave)",
      "Filter rooms by All, Group, or 1-on-1",
      "Incognito rooms show temporary display names",
    ],
  },
  {
    id: "match-one",
    eyebrow: "Match One",
    title: "Find one partner at your level.",
    body: "Match One creates a private 1-on-1 room. We pair you by mode, topic, interests, and English level — so the conversation actually flows.",
    bullets: [
      "Same mode (Normal ↔ Normal, Incognito ↔ Incognito)",
      "Same or similar topic",
      "Similar interests when possible",
      "Close English level for comfort",
    ],
  },
  {
    id: "random-match",
    eyebrow: "Random Match",
    title: "Tap and go.",
    body: "When you don't want to think, hit Random Match. We follow the same matching rules and tell you honestly if the match isn't a perfect fit.",
    bullets: [
      "Always same mode",
      "Prefers same topic and interests",
      "Falls back to the closest level",
      "Tells you when a match is approximate",
    ],
  },
  {
    id: "ai-coach",
    eyebrow: "AI Coach",
    title: "Help while you speak.",
    body: "A small coach sits next to the conversation with two quick actions: improve my sentence, and suggest what to say next. It uses admin-curated content so suggestions stay on-topic.",
    bullets: [
      "Improve my sentence — natural, gentle rewrites",
      "Idea — a short reply based on the last message",
      "Tap to fill your message box, or save to notes",
      "Grounded in trusted topic content (RAG)",
    ],
  },
  {
    id: "notes",
    eyebrow: "Sentence Notes",
    title: "Save the lines worth remembering.",
    body: "Long-press any message, or save a coach suggestion, and it lands in your notes. Group by topic and review anytime.",
    bullets: [
      "Save your own sentences, partner sentences, or AI rewrites",
      "Edit, delete, organize by topic",
      "Review later to lock in fluency",
    ],
  },
  {
    id: "translator",
    eyebrow: "In-Room Translator",
    title: "Never leave the conversation.",
    body: "Type a word or short phrase and the translation appears instantly. Swap direction with one tap when you want to go from your language back to English.",
    bullets: [
      "Lives next to the conversation — no app switching",
      "Instant, types-as-you-go translation",
      "Google Translate by default; offline Argos Translate available",
      "Clear demo fallback if the engine is unavailable",
    ],
  },
  {
    id: "stt",
    eyebrow: "Speech-to-Text",
    title: "See what you said.",
    body: "Every voice conversation can be transcribed in real time. Review the transcript, save best lines, and let the coach give you better feedback.",
    bullets: [
      "Live transcript while you speak",
      "Save useful sentences straight to notes",
      "Used by the AI for richer feedback",
      "Clear privacy handling, especially in incognito",
    ],
  },
  {
    id: "modes",
    eyebrow: "Modes",
    title: "Normal or Incognito — your choice.",
    body: "Show up as yourself, or practice behind a temporary display name. Matching always respects mode so everyone feels safe.",
    bullets: [
      "Normal: real profile name, level, interests visible",
      "Incognito: temporary name, no identity exposed",
      "Normal only matches Normal. Incognito only matches Incognito.",
    ],
  },
  {
    id: "topics",
    eyebrow: "Topics",
    title: "Always know what to talk about.",
    body: "Admin-curated topics give you a subject, a suggested level, and sample questions. Pick one, join a room, and start.",
    bullets: [
      "Beginner, intermediate, and advanced topics",
      "Sample questions for every topic",
      "Trusted topic content powers the coach",
    ],
  },
];

function FeaturesPage() {
  return (
    <>
      <section className="container-page pt-16 pb-10 text-center">
        <span className="chip">Features</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Everything that helps you <span className="italic text-primary">actually speak.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          A full toolkit built around one idea: lower the fear, raise the practice. Here's every
          feature in EnglishTalker.
        </p>
      </section>

      <section className="container-page pb-10">
        <div className="flex flex-wrap justify-center gap-2">
          {SECTIONS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="chip hover:bg-muted">
              {s.eyebrow}
            </a>
          ))}
        </div>
      </section>

      <section className="container-page py-10 space-y-6">
        {SECTIONS.map((s, i) => (
          <article
            key={s.id}
            id={s.id}
            className={`rounded-4xl border border-border p-8 lg:p-12 grid lg:grid-cols-12 gap-8 ${i % 2 === 0 ? "bg-card" : "bg-cream"}`}
          >
            <div className="lg:col-span-5">
              <span className="chip">{s.eyebrow}</span>
              <h2 className="mt-4 text-4xl text-ink">{s.title}</h2>
            </div>
            <div className="lg:col-span-7">
              <p className="text-muted-foreground leading-relaxed">{s.body}</p>
              <ul className="mt-6 space-y-3">
                {s.bullets.map((b) => (
                  <li key={b} className="flex gap-3 text-sm">
                    <svg
                      className="mt-0.5 h-5 w-5 flex-none text-primary"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                    >
                      <path d="M5 13l4 4L19 7" />
                    </svg>
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </section>

      <section className="container-page py-16 text-center">
        <h2 className="text-4xl text-ink">Ready to try it?</h2>
        <Link
          to="/pricing"
          className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
        >
          Start free
        </Link>
      </section>
    </>
  );
}
