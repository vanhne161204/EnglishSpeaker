import { createFileRoute, Link } from "@tanstack/react-router";
import heroImg from "@/assets/hero-conversation.jpg";
import bubblesImg from "@/assets/pattern-bubbles.jpg";
import { PracticeLink } from "@/components/practice-link";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "EnglishTalker — Practice speaking English, every day" },
      {
        name: "description",
        content:
          "Speaking rooms, 1-on-1 matches, and an AI coach that helps you sound natural. Practice English without the fear.",
      },
      { property: "og:title", content: "EnglishTalker — Practice speaking English, every day" },
      {
        property: "og:description",
        content: "Speaking rooms, real partners, and an AI coach that helps you sound natural.",
      },
      { property: "og:url", content: "/" },
    ],
    links: [{ rel: "canonical", href: "/" }],
  }),
  component: Home,
});

function Home() {
  return (
    <>
      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-cream via-background to-background" />
        <div className="container-page pt-16 pb-20 lg:pt-24 lg:pb-28 grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-7">
            <span className="chip">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Speak more. Fear less.
            </span>
            <h1 className="mt-5 text-5xl sm:text-6xl lg:text-7xl text-ink leading-[1.02]">
              Practice English
              <br />
              <span className="italic text-primary">by actually speaking it.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-muted-foreground leading-relaxed">
              Join a room, match 1-on-1, or get a random partner at your level. A gentle in-room AI
              coach helps you sound natural — and you save every great sentence for later.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <PracticeLink className="rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-[var(--shadow-glow)] hover:opacity-90">
                Start practicing free
              </PracticeLink>
              <Link
                to="/how-it-works"
                className="rounded-full border border-border bg-card px-6 py-3.5 text-sm font-semibold text-foreground hover:bg-muted"
              >
                See how it works
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-2">
                <Dot />
                Normal & Incognito modes
              </span>
              <span className="flex items-center gap-2">
                <Dot />
                Real-time translator
              </span>
              <span className="flex items-center gap-2">
                <Dot />
                Voice & text rooms
              </span>
            </div>
          </div>
          <div className="lg:col-span-5">
            <div className="relative">
              <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-accent/30 blur-2xl" />
              <img
                src={heroImg}
                alt="Two friends practicing English on a video call"
                width={1536}
                height={1280}
                className="rounded-3xl shadow-[var(--shadow-glow)] border border-border"
              />
              <FloatingCard className="absolute -left-4 top-8 hidden sm:flex" />
              <CoachCard className="absolute -right-4 bottom-6 hidden sm:flex" />
            </div>
          </div>
        </div>
      </section>

      {/* MODES */}
      <section className="container-page py-20">
        <div className="grid md:grid-cols-2 gap-6">
          <ModeCard
            tag="Normal mode"
            title="Show up as you."
            body="Share your name, level, and interests. Join open rooms and meet learners ready to practice openly."
            tone="primary"
          />
          <ModeCard
            tag="Incognito mode"
            title="Practice privately."
            body="Use a temporary display name and match only with other incognito learners. A safer space to begin."
            tone="ink"
          />
        </div>
        <p className="mt-6 text-sm text-muted-foreground text-center">
          Normal users match with Normal. Incognito with Incognito. Always.
        </p>
      </section>

      {/* FEATURE GRID */}
      <section className="container-page py-10">
        <SectionHeading
          eyebrow="Everything you need"
          title="A complete speaking toolkit"
          subtitle="Rooms, matches, AI help, and sentence notes — built around the one thing that matters: opening your mouth."
        />
        <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <FeatureCard key={f.title} {...f} />
          ))}
        </div>
      </section>

      {/* AI COACH PREVIEW */}
      <section className="container-page py-20">
        <div className="rounded-4xl border border-border bg-card overflow-hidden grid lg:grid-cols-2">
          <div className="p-10 lg:p-14">
            <span className="chip">AI Coach</span>
            <h2 className="mt-4 text-4xl text-ink">A kind nudge, mid-conversation.</h2>
            <p className="mt-4 text-muted-foreground leading-relaxed">
              Type a sentence and the coach rewrites it to sound more natural — gently, never
              embarrassingly. Stuck for a reply? Tap <em>Idea</em> for a short, friendly suggestion
              based on the last message.
            </p>
            <ul className="mt-6 space-y-3 text-sm">
              <li className="flex gap-3">
                <Check /> Improve my sentence
              </li>
              <li className="flex gap-3">
                <Check /> Suggest what to say next
              </li>
              <li className="flex gap-3">
                <Check /> Save any line to Sentence Notes
              </li>
              <li className="flex gap-3">
                <Check /> Grounded in trusted topic content
              </li>
            </ul>
          </div>
          <div className="relative bg-cream p-10 lg:p-14 border-t lg:border-t-0 lg:border-l border-border">
            <ChatPreview />
          </div>
        </div>
      </section>

      {/* TOPICS */}
      <section className="container-page py-20">
        <SectionHeading
          eyebrow="Conversation topics"
          title="Know what to talk about."
          subtitle="Pick a topic, see sample questions, and start. Topics are tagged by level so you don't bite off more than you can chew."
        />
        <div className="mt-10 flex flex-wrap justify-center gap-2.5">
          {TOPICS.map((t) => (
            <span key={t.name} className="chip text-sm">
              {t.emoji} {t.name}
              <span className="ml-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                {t.level}
              </span>
            </span>
          ))}
        </div>
      </section>

      {/* HOW IT FLOWS */}
      <section className="relative py-20">
        <img
          src={bubblesImg}
          alt=""
          aria-hidden
          width={1280}
          height={800}
          loading="lazy"
          className="absolute inset-0 -z-10 h-full w-full object-cover opacity-30"
        />
        <div className="container-page">
          <SectionHeading
            eyebrow="The flow"
            title="Open. Match. Speak."
            subtitle="Most users go from app icon to first sentence in under 60 seconds."
          />
          <ol className="mt-12 grid md:grid-cols-3 gap-5">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-3xl bg-card border border-border p-7">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground font-display text-base">
                    {i + 1}
                  </span>
                  <h3 className="text-xl text-ink">{s.title}</h3>
                </div>
                <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* CTA */}
      <section className="container-page py-20">
        <div className="rounded-4xl bg-secondary text-secondary-foreground p-12 lg:p-16 text-center relative overflow-hidden">
          <div className="absolute -top-20 -right-20 h-64 w-64 rounded-full bg-primary/30 blur-3xl" />
          <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-accent/30 blur-3xl" />
          <h2 className="text-4xl sm:text-5xl">Your first conversation is one tap away.</h2>
          <p className="mt-4 max-w-xl mx-auto text-secondary-foreground/80">
            Free forever for daily practice. Upgrade when you want more AI help and unlimited
            matches.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <PracticeLink className="rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground hover:opacity-90">
              Start practicing
            </PracticeLink>
            <Link
              to="/features"
              className="rounded-full border border-secondary-foreground/30 px-6 py-3.5 text-sm font-semibold hover:bg-secondary-foreground/10"
            >
              Explore features
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}

/* ---------- bits ---------- */

function Dot() {
  return <span className="h-1.5 w-1.5 rounded-full bg-primary" />;
}
function Check() {
  return (
    <svg
      className="mt-0.5 h-5 w-5 flex-none text-primary"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
    >
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}

function SectionHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="text-center max-w-2xl mx-auto">
      <span className="chip">{eyebrow}</span>
      <h2 className="mt-4 text-4xl sm:text-5xl text-ink">{title}</h2>
      {subtitle && <p className="mt-4 text-muted-foreground leading-relaxed">{subtitle}</p>}
    </div>
  );
}

function ModeCard({
  tag,
  title,
  body,
  tone,
}: {
  tag: string;
  title: string;
  body: string;
  tone: "primary" | "ink";
}) {
  const isPrimary = tone === "primary";
  return (
    <div
      className={`rounded-3xl p-8 lg:p-10 border ${isPrimary ? "bg-primary text-primary-foreground border-primary" : "bg-secondary text-secondary-foreground border-secondary"}`}
    >
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${isPrimary ? "bg-white/15" : "bg-white/10"}`}
      >
        {tag}
      </span>
      <h3 className="mt-5 text-3xl font-display">{title}</h3>
      <p
        className={`mt-3 leading-relaxed ${isPrimary ? "text-primary-foreground/90" : "text-secondary-foreground/85"}`}
      >
        {body}
      </p>
    </div>
  );
}

function FeatureCard({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div className="group rounded-3xl border border-border bg-card p-7 hover:shadow-[var(--shadow-soft)] hover:-translate-y-0.5 transition-all">
      <div className="text-3xl">{icon}</div>
      <h3 className="mt-4 text-xl text-ink">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{body}</p>
    </div>
  );
}

function FloatingCard({ className = "" }: { className?: string }) {
  return (
    <div
      className={`rounded-2xl bg-card border border-border shadow-[var(--shadow-soft)] px-4 py-3 max-w-[220px] ${className}`}
    >
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        Live transcript
      </div>
      <div className="mt-1 text-sm text-foreground">"I really enjoy traveling solo."</div>
    </div>
  );
}

function CoachCard({ className = "" }: { className?: string }) {
  return (
    <div
      className={`rounded-2xl bg-card border border-border shadow-[var(--shadow-soft)] px-4 py-3 max-w-[240px] ${className}`}
    >
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-primary">
        ✨ Coach
      </div>
      <div className="mt-1 text-sm text-foreground">
        Try: <span className="italic">"Where do you usually travel to?"</span>
      </div>
    </div>
  );
}

function ChatPreview() {
  return (
    <div className="space-y-3 max-w-md mx-auto">
      <Bubble side="them" name="Maya">
        Hi! What do you do on weekend?
      </Bubble>
      <Bubble side="me" name="You">
        I very like go hiking with friend.
      </Bubble>
      <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
        <div className="text-[11px] uppercase tracking-wider text-primary font-semibold">
          Coach · Improve my sentence
        </div>
        <div className="mt-1 text-sm">I really enjoy going hiking with friends.</div>
        <div className="mt-3 flex gap-2">
          <button className="rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground">
            Use this
          </button>
          <button className="rounded-full border border-border px-3 py-1 text-xs">
            Save to notes
          </button>
        </div>
      </div>
      <Bubble side="them" name="Maya">
        Nice! Where do you usually hike?
      </Bubble>
    </div>
  );
}
function Bubble({
  side,
  name,
  children,
}: {
  side: "me" | "them";
  name: string;
  children: React.ReactNode;
}) {
  const me = side === "me";
  return (
    <div className={`flex ${me ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${me ? "bg-secondary text-secondary-foreground" : "bg-card border border-border"}`}
      >
        <div
          className={`text-[10px] uppercase tracking-wider mb-0.5 ${me ? "text-secondary-foreground/60" : "text-muted-foreground"}`}
        >
          {name}
        </div>
        {children}
      </div>
    </div>
  );
}

const FEATURES = [
  {
    icon: "🎙️",
    title: "Speaking rooms",
    body: "Group or 1-on-1 rooms with the same powerful features. Text chat plus peer-to-peer voice calls.",
  },
  {
    icon: "🎯",
    title: "Match One",
    body: "Get paired with one learner at your level, topic, and interests for a focused conversation.",
  },
  {
    icon: "⚡",
    title: "Random Match",
    body: "Tap and go. We find the closest match by mode, level, and topic — and tell you if it's not exact.",
  },
  {
    icon: "✨",
    title: "AI Coach",
    body: "Improve your sentence or get a 'what to say next' idea, grounded in trusted topic content.",
  },
  {
    icon: "📝",
    title: "Sentence Notes",
    body: "Save useful lines from yourself, your partner, or the coach. Group them by topic for review.",
  },
  {
    icon: "🌐",
    title: "In-room translator",
    body: "Type a word, see the meaning instantly. Swap direction with one tap. Never leave the room.",
  },
  {
    icon: "🗣️",
    title: "Speech-to-Text",
    body: "See your spoken words as text. Review the transcript and save the best sentences.",
  },
  {
    icon: "🛡️",
    title: "Incognito mode",
    body: "Practice with a temporary display name. Incognito only matches with incognito.",
  },
  {
    icon: "📚",
    title: "Curated topics",
    body: "Daily life, travel, food, interviews and more — each with sample questions and a suggested level.",
  },
];

const TOPICS = [
  { name: "Daily life", emoji: "☕", level: "Beginner" },
  { name: "Travel", emoji: "✈️", level: "Beginner" },
  { name: "Food", emoji: "🍜", level: "Beginner" },
  { name: "Work", emoji: "💼", level: "Intermediate" },
  { name: "School", emoji: "🎓", level: "Beginner" },
  { name: "Job interview", emoji: "🤝", level: "Advanced" },
  { name: "Hobbies", emoji: "🎨", level: "Beginner" },
  { name: "Technology", emoji: "💻", level: "Intermediate" },
  { name: "Culture", emoji: "🌏", level: "Intermediate" },
];

const STEPS = [
  {
    title: "Pick a topic",
    body: "Browse topics tagged by level and see sample questions for each one.",
  },
  {
    title: "Choose your mode",
    body: "Normal to show up as you, or Incognito for a private warm-up.",
  },
  {
    title: "Match and speak",
    body: "Join a room, match 1-on-1, or hit Random Match — your coach is right there.",
  },
];
