import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — EnglishTalker" },
      {
        name: "description",
        content:
          "Free forever for daily practice. Premium unlocks more AI suggestions, more matches, and more topics.",
      },
      { property: "og:title", content: "Pricing — EnglishTalker" },
      {
        property: "og:description",
        content: "Simple Free and Premium plans for English speaking practice.",
      },
      { property: "og:url", content: "/pricing" },
    ],
    links: [{ rel: "canonical", href: "/pricing" }],
  }),
  component: PricingPage,
});

const FREE = [
  "No sign-up — just start",
  "Set level and interests",
  "Join basic rooms",
  "Match One — with daily limits",
  "Random Match — with daily limits",
  "Save sentence notes (limited)",
  "Limited AI suggestions per day",
];

const PREMIUM = [
  "More daily AI suggestions",
  "Unlimited sentence notes",
  "Access to all topics",
  "Better AI feedback after conversations",
  "More Match One sessions",
  "Access to premium rooms (when available)",
  "Detailed progress information",
];

function PricingPage() {
  return (
    <>
      <section className="container-page pt-16 pb-8 text-center">
        <span className="chip">Pricing</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Simple plans. <span className="italic text-primary">No surprises.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Start free and practice every day. Upgrade when you want more AI help and more matches.
          Cancel anytime.
        </p>
      </section>

      <section className="container-page py-12 grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
        <PlanCard
          name="Free"
          price="$0"
          tagline="For new and casual learners."
          features={FREE}
          cta="Start practicing"
          ctaTo="/rooms"
          tone="card"
        />
        <PlanCard
          name="Premium"
          price="$9"
          period="/ month"
          tagline="For learners who want to go further."
          features={PREMIUM}
          cta="Upgrade to Premium"
          tone="primary"
          highlight
        />
      </section>

      <section className="container-page py-16 max-w-3xl mx-auto">
        <h2 className="text-3xl text-ink text-center">Promises that come with every plan</h2>
        <ul className="mt-8 grid sm:grid-cols-2 gap-4">
          {[
            "You'll always know what's free and what's paid.",
            "We'll never cut you off mid-conversation.",
            "Limits are explained in simple words.",
            "You can see your current plan anytime.",
            "Upgrade when you want, cancel when you want.",
            "Your privacy is respected — especially in Incognito.",
          ].map((p) => (
            <li
              key={p}
              className="flex gap-3 text-sm text-foreground rounded-2xl border border-border bg-card p-4"
            >
              <svg
                className="mt-0.5 h-5 w-5 flex-none text-primary"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path d="M5 13l4 4L19 7" />
              </svg>
              {p}
            </li>
          ))}
        </ul>
      </section>

      <section className="container-page py-16 max-w-3xl mx-auto">
        <h2 className="text-3xl text-ink text-center">Common questions</h2>
        <div className="mt-8 space-y-3">
          {FAQS.map((f) => (
            <details key={f.q} className="group rounded-2xl border border-border bg-card p-5">
              <summary className="cursor-pointer list-none flex justify-between items-center font-medium text-foreground">
                {f.q}
                <span className="text-primary group-open:rotate-45 transition-transform text-xl leading-none">
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{f.a}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

function PlanCard({
  name,
  price,
  period,
  tagline,
  features,
  cta,
  ctaTo = "/contact",
  tone,
  highlight,
}: {
  name: string;
  price: string;
  period?: string;
  tagline: string;
  features: string[];
  cta: string;
  ctaTo?: string;
  tone: "card" | "primary";
  highlight?: boolean;
}) {
  const isPrimary = tone === "primary";
  return (
    <div
      className={`rounded-4xl p-8 border ${isPrimary ? "bg-secondary text-secondary-foreground border-secondary" : "bg-card border-border"} ${highlight ? "shadow-[var(--shadow-glow)]" : ""} relative`}
    >
      {highlight && (
        <span className="absolute -top-3 left-8 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
          Most useful
        </span>
      )}
      <h3 className="text-2xl font-display">{name}</h3>
      <div className="mt-4 flex items-baseline gap-1">
        <span className="text-5xl font-display">{price}</span>
        {period && (
          <span className={isPrimary ? "text-secondary-foreground/70" : "text-muted-foreground"}>
            {period}
          </span>
        )}
      </div>
      <p
        className={`mt-2 text-sm ${isPrimary ? "text-secondary-foreground/80" : "text-muted-foreground"}`}
      >
        {tagline}
      </p>
      <ul className="mt-6 space-y-2.5 text-sm">
        {features.map((f) => (
          <li key={f} className="flex gap-2.5">
            <svg
              className={`mt-0.5 h-4 w-4 flex-none ${isPrimary ? "text-primary" : "text-primary"}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            >
              <path d="M5 13l4 4L19 7" />
            </svg>
            {f}
          </li>
        ))}
      </ul>
      <Link
        to={ctaTo}
        className={`mt-7 block rounded-full px-5 py-3 text-center text-sm font-semibold ${isPrimary ? "bg-primary text-primary-foreground" : "bg-foreground text-background"} hover:opacity-90`}
      >
        {cta}
      </Link>
    </div>
  );
}

const FAQS = [
  {
    q: "Is there really a free plan?",
    a: "Yes. The free plan needs no sign-up — just start. Join rooms, use Match One and Random Match, and get AI suggestions every day.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Anytime. You'll keep Premium until the end of your current billing period and then move to Free.",
  },
  {
    q: "Will the app interrupt me to ask for payment?",
    a: "No. We never cut you off in the middle of a conversation. If you hit a free limit, we explain it kindly before your next session.",
  },
  {
    q: "Do voice calls work in the web preview?",
    a: "Voice uses peer-to-peer audio that needs a real native build. The web app supports rooms, text chat, transcripts, AI coach, and translator.",
  },
  {
    q: "What happens in Incognito mode?",
    a: "You get a temporary display name and only match with other incognito users. Transcripts and notes are handled with extra privacy care.",
  },
];
