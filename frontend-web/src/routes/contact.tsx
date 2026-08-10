import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Contact — EnglishTalker" },
      {
        name: "description",
        content:
          "Get in touch with the EnglishTalker team. We'd love to hear from learners, teachers, and partners.",
      },
      { property: "og:title", content: "Contact — EnglishTalker" },
      {
        property: "og:description",
        content: "Reach out with feedback, partnership ideas, or questions.",
      },
      { property: "og:url", content: "/contact" },
    ],
    links: [{ rel: "canonical", href: "/contact" }],
  }),
  component: ContactPage,
});

function ContactPage() {
  const [sent, setSent] = useState(false);
  return (
    <section className="container-page py-16 grid lg:grid-cols-2 gap-12 max-w-5xl">
      <div>
        <span className="chip">Contact</span>
        <h1 className="mt-5 text-5xl text-ink">
          Let's <span className="italic text-primary">talk.</span>
        </h1>
        <p className="mt-5 text-muted-foreground leading-relaxed">
          Tell us how you learn English, what you wish existed, or how we can help. We read every
          message.
        </p>
        <dl className="mt-8 space-y-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="text-foreground font-medium">hello@englishtalker.app</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Support hours</dt>
            <dd className="text-foreground font-medium">Mon–Fri, 9–18 (UTC+7)</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">For partnerships</dt>
            <dd className="text-foreground font-medium">partners@englishtalker.app</dd>
          </div>
        </dl>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSent(true);
        }}
        className="rounded-4xl border border-border bg-card p-8 space-y-4"
      >
        {sent ? (
          <div className="text-center py-12">
            <div className="text-4xl">✉️</div>
            <h2 className="mt-4 text-2xl text-ink">Thanks!</h2>
            <p className="mt-2 text-muted-foreground">We'll get back to you within a few days.</p>
          </div>
        ) : (
          <>
            <Field label="Your name">
              <input required className="input" placeholder="Maya" />
            </Field>
            <Field label="Email">
              <input required type="email" className="input" placeholder="you@example.com" />
            </Field>
            <Field label="I am a…">
              <select className="input">
                <option>Learner</option>
                <option>Teacher</option>
                <option>School / Company</option>
                <option>Press</option>
                <option>Other</option>
              </select>
            </Field>
            <Field label="Message">
              <textarea
                required
                rows={5}
                className="input resize-none"
                placeholder="Tell us anything…"
              />
            </Field>
            <button className="w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90">
              Send message
            </button>
            <style>{`.input{width:100%;border:1px solid var(--color-border);background:var(--color-background);border-radius:0.875rem;padding:0.75rem 1rem;font-size:0.95rem;outline:none;}.input:focus{border-color:var(--color-primary);box-shadow:0 0 0 3px color-mix(in oklab, var(--color-primary) 20%, transparent);}`}</style>
          </>
        )}
      </form>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-foreground mb-1.5">{label}</span>
      {children}
    </label>
  );
}
