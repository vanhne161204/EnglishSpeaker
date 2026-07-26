import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { listTopics, matchOne, matchRandom, type ConversationMode, type Room } from "@/lib/api";
import { currentUser } from "@/lib/identity";
import { INTERESTS, levelLabel, modeLabel, parseInterests, sizeLabel } from "@/lib/presentation";

export const Route = createFileRoute("/match")({
  head: () => ({
    meta: [
      { title: "1-on-1 Match — EnglishTalker" },
      {
        name: "description",
        content:
          "Get paired with one English-speaking partner at your level and topic. Match One or Random Match.",
      },
      { property: "og:title", content: "1-on-1 Match — EnglishTalker" },
      {
        property: "og:description",
        content: "Private 1-on-1 English practice. Paired by mode, level, and topic.",
      },
      { property: "og:url", content: "/match" },
    ],
    links: [{ rel: "canonical", href: "/match" }],
  }),
  component: MatchPage,
});

const MODES: ConversationMode[] = ["normal", "incognito"];
const LEVELS = ["beginner", "intermediate", "advanced"] as const;

type MatchPrefs = { mode: ConversationMode; level: string; topic: string; interest: string };

/** Explain how close the result is to what the user asked for (PRD §8.5). */
function matchQuality(prefs: MatchPrefs, room: Room): { exact: boolean; text: string } {
  const sameTopic = !!prefs.topic && room.topic?.toLowerCase() === prefs.topic.toLowerCase();
  const sameInterest =
    !!prefs.interest && room.topic?.toLowerCase() === prefs.interest.toLowerCase();
  const sameLevel = !!prefs.level && room.level?.toLowerCase() === prefs.level.toLowerCase();

  if (prefs.topic && sameTopic && sameLevel)
    return { exact: true, text: `Perfect match — same topic (${room.topic}) and level.` };
  if (prefs.topic && sameTopic) return { exact: true, text: `Matched your topic: ${room.topic}.` };
  if (sameInterest)
    return {
      exact: false,
      text: `No room for "${prefs.topic || "your topic"}", but we found one about your interest: ${room.topic}.`,
    };
  if (prefs.topic && sameLevel)
    return {
      exact: false,
      text: `We couldn't find "${prefs.topic}", but matched your level (${levelLabel(room.level)}).`,
    };
  if (sameLevel) return { exact: false, text: `Matched your level (${levelLabel(room.level)}).` };
  return {
    exact: false,
    text: "No exact match right now — we put you in the closest open room. Others can join you here.",
  };
}

function MatchPage() {
  const navigate = useNavigate();
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });

  const [mode, setMode] = useState<ConversationMode>("normal");
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("intermediate");
  const [topic, setTopic] = useState<string>("");
  const [interest, setInterest] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "searching" | "matched" | "error">("idle");
  const [matched, setMatched] = useState<Room | null>(null);
  const [prefs, setPrefs] = useState<MatchPrefs | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Pre-fill from the device profile (mode + first interest) for a faster start.
  useEffect(() => {
    const u = currentUser();
    if (!u) return;
    if (u.mode) setMode(u.mode);
    const first = parseInterests(u.interests)[0];
    if (first) setInterest(first);
  }, []);

  const start = async (kind: "one" | "random") => {
    setStatus("searching");
    setErr(null);
    setMatched(null);
    const used: MatchPrefs = { mode, level, topic, interest };
    setPrefs(used);
    try {
      const body = {
        mode,
        topic: topic || undefined,
        level,
        interest: interest || undefined,
      };
      const room = kind === "one" ? await matchOne(body) : await matchRandom(body);
      setMatched(room);
      setStatus("matched");
    } catch (e) {
      setErr((e as Error).message);
      setStatus("error");
    }
  };

  return (
    <>
      <section className="container-page pt-16 pb-8 text-center">
        <span className="chip">1-on-1 Match</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          One partner. <span className="italic text-primary">One real conversation.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          We pair you by mode, English level, and topic. Choose Match One for a focused pick, or
          Random Match to just go. Either way you land in a real room.
        </p>
      </section>

      <section className="container-page py-10 grid lg:grid-cols-12 gap-8">
        {/* Form */}
        <div className="lg:col-span-7 rounded-4xl border border-border bg-card p-8 lg:p-10 space-y-6">
          <Group title="Mode" hint="Normal users match Normal. Incognito match Incognito. Always.">
            <div className="grid grid-cols-2 gap-2">
              {MODES.map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`rounded-2xl border px-4 py-3 text-sm font-medium ${mode === m ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                >
                  {modeLabel(m)}
                </button>
              ))}
            </div>
          </Group>

          <Group title="English level" hint="Used by Match One to prefer a similar level.">
            <div className="grid grid-cols-3 gap-2">
              {LEVELS.map((l) => (
                <button
                  key={l}
                  onClick={() => setLevel(l)}
                  className={`rounded-2xl border px-3 py-3 text-sm font-medium ${level === l ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                >
                  {levelLabel(l)}
                </button>
              ))}
            </div>
          </Group>

          <Group title="Topic" hint="Optional — Match One prefers this topic when it can.">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setTopic("")}
                className={`rounded-full px-3.5 py-1.5 text-sm border ${topic === "" ? "bg-primary text-primary-foreground border-primary" : "bg-background text-foreground border-border hover:bg-muted"}`}
              >
                Any
              </button>
              {(topicsQ.data ?? []).map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTopic(t.title)}
                  className={`rounded-full px-3.5 py-1.5 text-sm border ${topic === t.title ? "bg-primary text-primary-foreground border-primary" : "bg-background text-foreground border-border hover:bg-muted"}`}
                >
                  {t.title}
                </button>
              ))}
            </div>
          </Group>

          <Group title="Interest" hint="Improves match quality when the exact topic isn't free.">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setInterest("")}
                className={`rounded-full px-3.5 py-1.5 text-sm border ${interest === "" ? "bg-secondary text-secondary-foreground border-secondary" : "bg-background text-foreground border-border hover:bg-muted"}`}
              >
                Any
              </button>
              {INTERESTS.map((i) => (
                <button
                  key={i}
                  onClick={() => setInterest(i)}
                  className={`rounded-full px-3.5 py-1.5 text-sm border ${interest === i ? "bg-secondary text-secondary-foreground border-secondary" : "bg-background text-foreground border-border hover:bg-muted"}`}
                >
                  {i}
                </button>
              ))}
            </div>
          </Group>

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              onClick={() => start("one")}
              disabled={status === "searching"}
              className="rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              Match One
            </button>
            <button
              onClick={() => start("random")}
              disabled={status === "searching"}
              className="rounded-full border border-border bg-background px-6 py-3.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
            >
              ⚡ Random Match
            </button>
          </div>
        </div>

        {/* Status panel */}
        <div className="lg:col-span-5">
          <div className="sticky top-24 rounded-4xl bg-cream border border-border p-8 min-h-[420px] flex flex-col">
            <span className="chip">Live preview</span>
            {status === "idle" && (
              <div className="mt-6 flex-1 flex flex-col items-center justify-center text-center">
                <div className="text-5xl">🎯</div>
                <h3 className="mt-4 text-2xl text-ink">Ready when you are.</h3>
                <p className="mt-2 text-sm text-muted-foreground max-w-xs">
                  Pick your preferences and tap Match One. We'll find or open a room and drop you
                  in.
                </p>
              </div>
            )}
            {status === "searching" && (
              <div className="mt-6 flex-1 flex flex-col items-center justify-center text-center">
                <div className="relative h-20 w-20">
                  <span className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
                  <span className="absolute inset-2 rounded-full bg-primary/30" />
                  <span className="absolute inset-6 rounded-full bg-primary" />
                </div>
                <h3 className="mt-6 text-2xl text-ink">Finding a room…</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {modeLabel(mode)} · {levelLabel(level)}
                  {topic ? ` · ${topic}` : ""}
                </p>
              </div>
            )}
            {status === "error" && (
              <div className="mt-6 flex-1 flex flex-col items-center justify-center text-center">
                <div className="text-4xl">⚠️</div>
                <h3 className="mt-3 text-xl text-ink">Couldn't match</h3>
                <p className="mt-2 text-sm text-muted-foreground">{err}</p>
                <p className="mt-1 text-xs text-muted-foreground">Is the backend running?</p>
                <button
                  onClick={() => setStatus("idle")}
                  className="mt-4 rounded-full border border-border bg-background px-4 py-2 text-sm font-semibold"
                >
                  Try again
                </button>
              </div>
            )}
            {status === "matched" && matched && (
              <div className="mt-6 flex-1 flex flex-col">
                <div className="flex items-center gap-3">
                  <div className="h-12 w-12 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center font-display text-lg">
                    {matched.title.charAt(0)}
                  </div>
                  <div>
                    <div className="text-lg text-ink font-semibold">{matched.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {modeLabel(matched.mode)} · {sizeLabel(matched.kind)} ·{" "}
                      {levelLabel(matched.level)}
                    </div>
                  </div>
                </div>
                {prefs &&
                  (() => {
                    const q = matchQuality(prefs, matched);
                    return (
                      <div
                        className={`mt-4 rounded-2xl border p-3 text-sm ${q.exact ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700" : "border-amber-500/40 bg-amber-500/10 text-amber-800"}`}
                      >
                        <span className="mr-1">{q.exact ? "✓" : "ℹ"}</span>
                        {q.text}
                      </div>
                    );
                  })()}
                <div className="mt-4 rounded-2xl border border-border bg-card p-4 text-sm">
                  <div className="text-[11px] uppercase tracking-wider text-primary font-semibold">
                    Your room
                  </div>
                  <ul className="mt-2 space-y-1.5 text-foreground">
                    <li>· Mode: {modeLabel(matched.mode)}</li>
                    <li>· Topic: {matched.topic ?? "Open"}</li>
                    <li>· Level: {levelLabel(matched.level)}</li>
                    <li>
                      · People: {matched.participant_count}/{matched.capacity}
                    </li>
                  </ul>
                </div>
                <div className="mt-5 flex gap-2">
                  <button
                    onClick={() =>
                      navigate({ to: "/rooms/$roomId", params: { roomId: matched.id } })
                    }
                    className="flex-1 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
                  >
                    Enter room
                  </button>
                  <button
                    onClick={() => setStatus("idle")}
                    className="rounded-full border border-border bg-background px-4 py-2.5 text-sm font-semibold"
                  >
                    Skip
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="container-page py-16">
        <div className="rounded-4xl bg-secondary text-secondary-foreground p-10 lg:p-14 grid lg:grid-cols-2 gap-8 items-center">
          <div>
            <h2 className="text-4xl">Match One vs Random Match</h2>
            <p className="mt-3 text-secondary-foreground/80 leading-relaxed">
              Both drop you into a 1-on-1 / open room. The difference is how picky we are before
              pairing.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-3xl bg-secondary-foreground/10 p-6">
              <div className="text-2xl">🎯</div>
              <h3 className="mt-2 text-xl">Match One</h3>
              <p className="mt-1 text-sm text-secondary-foreground/85">
                Prefers your mode, level, and topic. Falls back gracefully if there's no exact room.
              </p>
            </div>
            <div className="rounded-3xl bg-secondary-foreground/10 p-6">
              <div className="text-2xl">⚡</div>
              <h3 className="mt-2 text-xl">Random Match</h3>
              <p className="mt-1 text-sm text-secondary-foreground/85">
                Same mode, any open room. The fastest way into a conversation.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="container-page py-16 text-center">
        <h2 className="text-4xl text-ink">Or join a group room instead.</h2>
        <Link
          to="/rooms"
          className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground"
        >
          Browse rooms
        </Link>
      </section>
    </>
  );
}

function Group({
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
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {hint && (
          <span className="text-xs text-muted-foreground hidden sm:block max-w-xs text-right">
            {hint}
          </span>
        )}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}
