import { requireAuth } from "@/lib/require-auth";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createRoom,
  listRooms,
  listTopics,
  type ConversationMode,
  type RoomCreate,
  type RoomKind,
} from "@/lib/api";
import { ensureUser } from "@/lib/identity";
import { levelLabel, modeLabel, sizeLabel, topicEmoji } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/rooms/")({
  // Requires an account (docs/11_Security.md §11.2). The API enforces this
  // too; the guard just avoids rendering a page that would 401 on every call.
  beforeLoad: ({ location }) => requireAuth(location.pathname),
  head: () => ({
    meta: [
      { title: "Speaking Rooms — EnglishTalker" },
      {
        name: "description",
        content:
          "Browse and join English speaking rooms. Group or 1-on-1, each tagged with a topic.",
      },
      { property: "og:title", content: "Speaking Rooms — EnglishTalker" },
      { property: "og:description", content: "One room model. Pick one and join." },
      { property: "og:url", content: "/rooms" },
    ],
    links: [{ rel: "canonical", href: "/rooms" }],
  }),
  component: RoomsIndex,
});

const SIZES: ("All" | RoomKind)[] = ["All", "group", "one_on_one"];
const LEVELS = ["All", "beginner", "intermediate", "advanced"] as const;
const MODES: ("All" | ConversationMode)[] = ["All", "normal", "incognito"];

function RoomsIndex() {
  const [kind, setKind] = useState<"All" | RoomKind>("All");
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("All");
  const [mode, setMode] = useState<"All" | ConversationMode>("All");
  const [topicTitle, setTopicTitle] = useState<string>("All");
  const [query, setQuery] = useState("");
  const [hideFull, setHideFull] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const roomsQ = useQuery({ queryKey: ["rooms"], queryFn: () => listRooms() });
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });

  const q = query.trim().toLowerCase();
  const filtered = (roomsQ.data ?? []).filter((r) => {
    if (kind !== "All" && r.kind !== kind) return false;
    if (level !== "All" && r.level !== level) return false;
    if (mode !== "All" && r.mode !== mode) return false;
    if (topicTitle !== "All" && r.topic !== topicTitle) return false;
    if (hideFull && r.participant_count >= r.capacity) return false;
    if (q && !r.title.toLowerCase().includes(q)) return false;
    return true;
  });

  const activeCount =
    (kind !== "All" ? 1 : 0) +
    (level !== "All" ? 1 : 0) +
    (mode !== "All" ? 1 : 0) +
    (topicTitle !== "All" ? 1 : 0) +
    (hideFull ? 1 : 0) +
    (q ? 1 : 0);

  const resetAll = () => {
    setKind("All");
    setLevel("All");
    setMode("All");
    setTopicTitle("All");
    setQuery("");
    setHideFull(false);
  };

  return (
    <>
      <section className="container-page pt-16 pb-8 text-center">
        <span className="chip">Speaking rooms</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Step in. <span className="italic text-primary">Start talking.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Every room carries a topic. Open a room to see its notes, the people inside, and start the
          conversation.
        </p>
      </section>

      <section className="container-page pb-4">
        <div className="rounded-3xl border border-border bg-card p-4 sm:p-5 space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
                🔍
              </span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by room title…"
                className="w-full rounded-full border border-border bg-background pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="rounded-full px-4 py-2.5 text-sm font-semibold bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap"
            >
              + Create room
            </button>
            <Link
              to="/match"
              className="rounded-full px-4 py-2.5 text-sm font-semibold bg-secondary text-secondary-foreground hover:opacity-90 whitespace-nowrap grid place-items-center"
            >
              + Find a match
            </Link>
          </div>

          <FilterRow
            label="Format"
            value={kind}
            options={SIZES}
            render={(v) => (v === "All" ? "All" : sizeLabel(v as RoomKind))}
            onChange={(v) => setKind(v as "All" | RoomKind)}
          />
          <FilterRow
            label="Level"
            value={level}
            options={LEVELS}
            render={(v) => (v === "All" ? "All" : levelLabel(v))}
            onChange={(v) => setLevel(v as (typeof LEVELS)[number])}
          />
          <FilterRow
            label="Mode"
            value={mode}
            options={MODES}
            render={(v) => (v === "All" ? "All" : modeLabel(v as ConversationMode))}
            onChange={(v) => setMode(v as "All" | ConversationMode)}
          />

          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Topic
            </div>
            <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
              <Chip active={topicTitle === "All"} onClick={() => setTopicTitle("All")}>
                All
              </Chip>
              {(topicsQ.data ?? []).map((t) => (
                <Chip
                  key={t.id}
                  active={topicTitle === t.title}
                  onClick={() => setTopicTitle(t.title)}
                >
                  {topicEmoji(t.slug)} {t.title}
                </Chip>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-border">
            <label className="inline-flex items-center gap-2 text-sm text-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={hideFull}
                onChange={(e) => setHideFull(e.target.checked)}
                className="accent-primary"
              />
              Hide full rooms
            </label>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>
                {filtered.length} {filtered.length === 1 ? "room" : "rooms"}
              </span>
              {activeCount > 0 && (
                <button onClick={resetAll} className="text-primary font-medium hover:underline">
                  Clear filters ({activeCount})
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="container-page py-10">
        {roomsQ.isLoading && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-60 rounded-3xl border border-border bg-card animate-pulse"
              />
            ))}
          </div>
        )}
        {roomsQ.isError && (
          <ErrorState message={(roomsQ.error as Error).message} onRetry={() => roomsQ.refetch()} />
        )}
        {!roomsQ.isLoading && !roomsQ.isError && filtered.length === 0 && (
          <p className="text-center text-muted-foreground">
            No rooms match your filters.{" "}
            <button onClick={resetAll} className="text-primary font-medium hover:underline">
              Clear filters
            </button>{" "}
            or{" "}
            <Link to="/match" className="text-primary font-medium hover:underline">
              start one via Match
            </Link>
            .
          </p>
        )}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((r) => {
            const full = r.participant_count >= r.capacity;
            return (
              <article
                key={r.id}
                className={`rounded-3xl border bg-card p-6 transition-all ${full ? "opacity-70" : "hover:-translate-y-0.5 hover:shadow-[var(--shadow-soft)]"} ${r.mode === "incognito" ? "border-secondary/40" : "border-border"}`}
              >
                <div className="flex items-center justify-between">
                  <div className="text-3xl">{topicEmoji(r.topic)}</div>
                  <div className="flex flex-wrap gap-1.5 justify-end">
                    <Pill tone={r.mode === "incognito" ? "ink" : "muted"}>{modeLabel(r.mode)}</Pill>
                    <Pill tone="muted">{sizeLabel(r.kind)}</Pill>
                  </div>
                </div>
                <h3 className="mt-3 text-xl text-ink">{r.title}</h3>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="uppercase tracking-wider">{levelLabel(r.level)}</span>
                  {r.topic && (
                    <>
                      <span>·</span>
                      <span>{r.topic}</span>
                    </>
                  )}
                </div>

                <div className="mt-5">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>People</span>
                    <span>
                      {r.participant_count}/{r.capacity}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary"
                      style={{
                        width: `${Math.min(100, (r.participant_count / r.capacity) * 100)}%`,
                      }}
                    />
                  </div>
                </div>

                <Link
                  to="/rooms/$roomId"
                  params={{ roomId: r.id }}
                  className={`mt-5 block text-center rounded-full px-4 py-2.5 text-sm font-semibold ${full ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground hover:opacity-90"}`}
                >
                  {full ? "Peek inside" : "Enter room"}
                </Link>
              </article>
            );
          })}
        </div>
      </section>

      <section className="container-page py-16 text-center">
        <h2 className="text-4xl text-ink">Prefer a partner over a crowd?</h2>
        <Link
          to="/match"
          className="mt-6 inline-flex rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground"
        >
          Find a 1-on-1 match
        </Link>
      </section>

      {showCreate && (
        <CreateRoomModal
          topicTitles={(topicsQ.data ?? []).map((t) => t.title)}
          onClose={() => setShowCreate(false)}
        />
      )}
    </>
  );
}

const CREATE_LEVELS = ["beginner", "intermediate", "advanced"] as const;

function CreateRoomModal({ topicTitles, onClose }: { topicTitles: string[]; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<ConversationMode>("normal");
  const [roomKind, setRoomKind] = useState<RoomKind>("group");
  const [topic, setTopic] = useState("");
  const [level, setLevel] = useState<(typeof CREATE_LEVELS)[number]>("intermediate");
  const [capacity, setCapacity] = useState(4);
  const [password, setPassword] = useState("");

  const createM = useMutation({
    mutationFn: (body: RoomCreate) => createRoom(body),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["rooms"] });
      navigate({ to: "/rooms/$roomId", params: { roomId: room.id } });
    },
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    // The creator becomes the owner/host who can moderate it (PRD §8.3). The
    // server takes that from the session token — sending `owner_id` here would
    // be ignored, and used to be a way to create a room owned by someone else.
    createM.mutate({
      title: title.trim(),
      mode,
      kind: roomKind,
      topic: topic || null,
      level,
      capacity: roomKind === "one_on_one" ? 2 : capacity,
      password: password.trim() || null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-4xl border border-border bg-card p-6 sm:p-8 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl text-ink">Create a room</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Open a space others can join. You'll go straight in.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-2 text-muted-foreground hover:bg-muted"
          >
            ✕
          </button>
        </div>

        <form onSubmit={(e) => void submit(e)} className="mt-6 space-y-5">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Room name
            </span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              maxLength={120}
              placeholder="e.g. Friday Travel Chat"
              className="mt-1 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <Field label="Format">
            <div className="grid grid-cols-2 gap-2">
              {(["group", "one_on_one"] as RoomKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setRoomKind(k)}
                  className={`rounded-2xl border px-4 py-2.5 text-sm font-medium ${roomKind === k ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                >
                  {sizeLabel(k)}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Mode">
            <div className="grid grid-cols-2 gap-2">
              {(["normal", "incognito"] as ConversationMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-2xl border px-4 py-2.5 text-sm font-medium ${mode === m ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                >
                  {modeLabel(m)}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Topic
              </span>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:border-primary"
              >
                <option value="">No topic</option>
                {topicTitles.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Level
              </span>
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value as (typeof CREATE_LEVELS)[number])}
                className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:border-primary"
              >
                {CREATE_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {levelLabel(l)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {roomKind === "group" && (
            <Field label={`Capacity — ${capacity} people`}>
              <input
                type="range"
                min={2}
                max={12}
                value={capacity}
                onChange={(e) => setCapacity(Number(e.target.value))}
                className="w-full accent-primary"
              />
            </Field>
          )}

          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Password (optional)
            </span>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="new-password"
              maxLength={72}
              placeholder="Leave blank for a public room"
              className="mt-1 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              If set, people must enter this password to join. 🔒
            </span>
          </label>

          {createM.isError && (
            <p className="text-sm text-destructive">{(createM.error as Error).message}</p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="submit"
              disabled={!title.trim() || createM.isPending}
              className="flex-1 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {createM.isPending ? "Creating…" : "Create & enter"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-border bg-background px-5 py-3 text-sm font-semibold text-foreground hover:bg-muted"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function FilterRow({
  label,
  value,
  options,
  onChange,
  render,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
  render: (v: string) => string;
}) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <Chip key={o} active={value === o} onClick={() => onChange(o)}>
            {render(o)}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function Chip({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-xs font-medium border transition-colors ${active ? "bg-primary text-primary-foreground border-primary" : "bg-card text-foreground border-border hover:bg-muted"}`}
    >
      {children}
    </button>
  );
}

function Pill({ children, tone }: { children: React.ReactNode; tone: "muted" | "ink" }) {
  const cls =
    tone === "ink" ? "bg-secondary text-secondary-foreground" : "bg-muted text-muted-foreground";
  return (
    <span className={`text-[10px] uppercase tracking-wider rounded-full px-2 py-1 ${cls}`}>
      {children}
    </span>
  );
}
