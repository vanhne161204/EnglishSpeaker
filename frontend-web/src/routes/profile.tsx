import { requireAuth } from "@/lib/require-auth";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import type { ConversationMode } from "@/lib/api";
import { currentUser, logout, randomGuestName, saveProfile } from "@/lib/identity";
import { INTERESTS, LEVELS, levelLabel, modeLabel, parseInterests } from "@/lib/presentation";

export const Route = createFileRoute("/profile")({
  // Requires an account (docs/11_Security.md §11.2). The API enforces this
  // too; the guard just avoids rendering a page that would 401 on every call.
  beforeLoad: ({ location }) => requireAuth(location.pathname),
  head: () => ({
    meta: [
      { title: "Your profile — EnglishTalker" },
      {
        name: "description",
        content:
          "Set your display name, English level, interests, and practice mode. No sign-up — your profile lives on this device.",
      },
    ],
  }),
  component: ProfilePage,
});

const MODES: ConversationMode[] = ["normal", "incognito"];

function ProfilePage() {
  const [name, setName] = useState("");
  const [level, setLevel] = useState<string>("intermediate");
  const [interests, setInterests] = useState<string[]>([]);
  const [mode, setMode] = useState<ConversationMode>("normal");
  const [username, setUsername] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Hydrate from the device profile (client-only — avoids SSR mismatch).
  useEffect(() => {
    const u = currentUser();
    if (u) {
      setName(u.display_name);
      if (u.level) setLevel(u.level);
      setInterests(parseInterests(u.interests));
      if (u.mode) setMode(u.mode);
      setUsername(u.username);
    } else {
      setName(randomGuestName());
    }
    setLoaded(true);
  }, []);

  const toggleInterest = (i: string) =>
    setInterests((prev) => (prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i]));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setErr(null);
    setSaved(false);
    try {
      await saveProfile({
        display_name: name.trim(),
        level,
        interests: interests.join(", ") || null,
        mode,
      });
      setSaved(true);
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="container-page pt-16 pb-6 text-center">
        <span className="chip">Your profile</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Tell us how you <span className="italic text-primary">like to practice.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          No sign-up needed. Your profile is saved on this device and used to find better partners
          and topics. You can change it anytime.
        </p>
      </section>

      <section className="container-page py-8 max-w-2xl mx-auto">
        <form onSubmit={submit} className="rounded-4xl border border-border bg-card p-8 space-y-7">
          {/* Login status */}
          {loaded &&
            (username ? (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                <span className="text-sm text-emerald-800">
                  Logged in as <span className="font-medium">@{username}</span> — your profile is
                  saved to this account.
                </span>
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    setUsername(null);
                    setName(randomGuestName());
                  }}
                  className="flex-none rounded-full border border-emerald-600/40 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-500/10"
                >
                  Log out
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-muted/40 px-4 py-3">
                <span className="text-sm text-muted-foreground">
                  You're a guest. Log in to keep this profile across devices.
                </span>
                <Link
                  to="/login"
                  className="flex-none rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                >
                  Log in
                </Link>
              </div>
            ))}

          {/* Display name */}
          <Field title="Display name" hint="Other learners see this in rooms.">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              placeholder="e.g. QuietPanda42"
              className="w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => setName(randomGuestName())}
              className="mt-2 text-xs text-primary hover:underline"
            >
              🎲 Give me a random name
            </button>
          </Field>

          {/* Level */}
          <Field title="English level" hint="We try to pair you with a similar level.">
            <div className="flex flex-wrap gap-2">
              {LEVELS.map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLevel(l)}
                  className={`rounded-full px-4 py-2 text-sm border ${level === l ? "bg-primary text-primary-foreground border-primary" : "bg-background text-foreground border-border hover:bg-muted"}`}
                >
                  {levelLabel(l)}
                </button>
              ))}
            </div>
          </Field>

          {/* Interests */}
          <Field title="Interests" hint="Used to improve match quality. Pick any.">
            <div className="flex flex-wrap gap-2">
              {INTERESTS.map((i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => toggleInterest(i)}
                  className={`rounded-full px-4 py-2 text-sm border ${interests.includes(i) ? "bg-secondary text-secondary-foreground border-secondary" : "bg-background text-foreground border-border hover:bg-muted"}`}
                >
                  {i}
                </button>
              ))}
            </div>
          </Field>

          {/* Mode */}
          <Field
            title="Default mode"
            hint="Normal users match Normal. Incognito match Incognito. Always."
          >
            <div className="grid grid-cols-2 gap-2">
              {MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-2xl border px-4 py-3 text-sm font-medium ${mode === m ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                >
                  {modeLabel(m)}
                  <span className="mt-0.5 block text-[11px] font-normal text-muted-foreground">
                    {m === "incognito" ? "Private temporary name" : "Show your display name"}
                  </span>
                </button>
              ))}
            </div>
          </Field>

          {err && <p className="text-sm text-destructive">{err}</p>}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={saving || !name.trim() || !loaded}
              className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save profile"}
            </button>
            <Link
              to="/rooms"
              className="rounded-full border border-border bg-background px-6 py-3 text-sm font-semibold text-foreground hover:bg-muted"
            >
              Skip to rooms
            </Link>
            {saved && (
              <span className="text-sm text-emerald-600 font-medium">✓ Saved on this device</span>
            )}
          </div>
        </form>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          Ready to talk?{" "}
          <Link to="/match" className="text-primary hover:underline">
            Find a 1-on-1 match
          </Link>{" "}
          or{" "}
          <Link to="/rooms" className="text-primary hover:underline">
            browse rooms
          </Link>
          .
        </p>
      </section>
    </>
  );
}

function Field({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {hint && <span className="text-xs text-muted-foreground text-right">{hint}</span>}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}
