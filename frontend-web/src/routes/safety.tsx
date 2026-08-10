import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/safety")({
  head: () => ({
    meta: [
      { title: "Safety & Privacy — EnglishTalker" },
      {
        name: "description",
        content:
          "How EnglishTalker keeps conversations safe — Incognito mode, reporting, transcript handling, and respectful matching.",
      },
      { property: "og:title", content: "Safety & Privacy — EnglishTalker" },
      {
        property: "og:description",
        content: "Incognito by design, kind by default. Here's how we keep practice safe.",
      },
      { property: "og:url", content: "/safety" },
    ],
    links: [{ rel: "canonical", href: "/safety" }],
  }),
  component: SafetyPage,
});

const PILLARS = [
  {
    icon: "🛡️",
    title: "Incognito mode",
    body: "Use a temporary display name; your real profile, level, and interests stay hidden. Incognito only matches with Incognito — always.",
  },
  {
    icon: "🔇",
    title: "Mute, leave, block",
    body: "Mute the room mic, leave any conversation instantly, and block users you don't want to be matched with again.",
  },
  {
    icon: "🚩",
    title: "Report in one tap",
    body: "Report a message, voice clip, or user. Reports go to moderators and reviewed quickly. Repeated offenses lead to bans.",
  },
  {
    icon: "🎙️",
    title: "Transcript privacy",
    body: "Live transcripts stay in the room and your private notes. In Incognito, we keep transcripts off your public profile end-to-end.",
  },
  {
    icon: "✨",
    title: "Kind AI by default",
    body: "The coach never shames you. Rewrites are gentle, suggestions are short, and feedback assumes good faith.",
  },
  {
    icon: "🧒",
    title: "Age-appropriate",
    body: "EnglishTalker is for ages 16+. We screen reported behavior and follow regional safeguarding rules.",
  },
];

const RULES = [
  "Be kind — assume your partner is nervous too.",
  "Speak about the topic; off-topic is fine, harassment is not.",
  "No hate speech, no harassment, no sexual content.",
  "Don't share personal contact info in Incognito rooms.",
  "Don't record partners without consent.",
  "If a partner asks to stop, stop.",
];

function SafetyPage() {
  return (
    <>
      <section className="container-page pt-16 pb-10 text-center">
        <span className="chip">Safety & Privacy</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Practice <span className="italic text-primary">without worry.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Speaking takes courage. We build EnglishTalker so the platform itself protects that
          courage — not just with rules, but with defaults.
        </p>
      </section>

      <section className="container-page py-10">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {PILLARS.map((p) => (
            <div key={p.title} className="rounded-3xl border border-border bg-card p-7">
              <div className="text-3xl">{p.icon}</div>
              <h3 className="mt-3 text-xl text-ink">{p.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="container-page py-16">
        <div className="rounded-4xl bg-cream border border-border p-10 lg:p-14 grid lg:grid-cols-2 gap-10">
          <div>
            <h2 className="text-4xl text-ink">Community rules</h2>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              A short list everyone agrees to. We enforce it.
            </p>
          </div>
          <ul className="space-y-3">
            {RULES.map((r) => (
              <li key={r} className="flex gap-3 text-sm text-foreground">
                <svg
                  className="mt-0.5 h-5 w-5 flex-none text-primary"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <path d="M5 13l4 4L19 7" />
                </svg>
                {r}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="container-page py-16">
        <div className="rounded-4xl border border-border bg-card p-10 lg:p-14 grid lg:grid-cols-12 gap-8">
          <div className="lg:col-span-5">
            <span className="chip">Data</span>
            <h2 className="mt-4 text-3xl text-ink">What we store, in plain words.</h2>
          </div>
          <dl className="lg:col-span-7 space-y-5 text-sm">
            {[
              [
                "Your account",
                "Email, display name, level, interests. You control all of it from Settings.",
              ],
              [
                "Messages & transcripts",
                "Stored so you can review and save sentence notes. You can delete a room from your history any time.",
              ],
              ["Sentence notes", "Yours. Edit, delete, export when you want."],
              [
                "Incognito sessions",
                "Linked only to a temporary display name; not shown on your public profile.",
              ],
              ["Analytics", "Aggregate counts only — no message contents are used for marketing."],
            ].map(([k, v]) => (
              <div key={k as string} className="border-l-2 border-primary pl-4">
                <dt className="font-semibold text-foreground">{k}</dt>
                <dd className="text-muted-foreground mt-1">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="container-page py-16 text-center">
        <h2 className="text-4xl text-ink">See something? Tell us.</h2>
        <p className="mt-3 text-muted-foreground">We read every report from real humans.</p>
        <Link
          to="/contact"
          className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground"
        >
          Contact moderation
        </Link>
      </section>
    </>
  );
}
