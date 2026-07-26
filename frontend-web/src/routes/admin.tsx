import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useIdentity } from "@/lib/identity";
import {
  createDocument,
  createTopic,
  deleteDocument,
  deleteTopic,
  listDocuments,
  listTopics,
  updateDocument,
  updateTopic,
  type DocumentKind,
  type Topic,
  type TopicDocument,
} from "@/lib/api";
import { levelLabel, LEVELS } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/admin")({
  head: () => ({
    meta: [
      { title: "Admin — EnglishTalker" },
      { name: "description", content: "Manage topics and learning content." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AdminPage,
});

const DOC_KINDS: DocumentKind[] = [
  "explanation",
  "example",
  "vocabulary",
  "mistake",
  "tip",
  "sample_answer",
];

function AdminPage() {
  const identity = useIdentity();
  const [tab, setTab] = useState<"topics" | "documents">("topics");

  // Authorization gate: only admins may manage content. The backend also
  // enforces this (require_admin), so this is the friendly first line, not the
  // only one. `identity` is null during SSR/first paint — treat as not-admin.
  if (!identity?.is_admin) {
    return <AdminForbidden loggedIn={!!identity?.username} />;
  }

  return (
    <>
      <section className="container-page pt-12 pb-4">
        <span className="chip">Admin</span>
        <h1 className="mt-4 text-4xl sm:text-5xl text-ink">Content management</h1>
        <p className="mt-3 max-w-2xl text-muted-foreground">
          Create the topics learners practice, and add trusted learning content the AI coach uses to
          ground its suggestions (PRD §8.1, §8.2).
        </p>
        <div className="mt-6 inline-flex rounded-full border border-border bg-card p-1">
          {(["topics", "documents"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-full px-5 py-2 text-sm font-medium capitalize ${tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      <section className="container-page py-6">
        {tab === "topics" ? <TopicsManager /> : <DocumentsManager />}
      </section>
    </>
  );
}

/** Shown when a non-admin (guest or ordinary user) opens the admin page. */
function AdminForbidden({ loggedIn }: { loggedIn: boolean }) {
  return (
    <section className="container-page py-24 max-w-md mx-auto text-center">
      <span className="chip">Admin only</span>
      <h1 className="mt-5 text-4xl text-ink">You don't have access</h1>
      <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
        {loggedIn
          ? "This area is for admins only. Ask an administrator to grant your account access."
          : "Please log in with an admin account to manage topics and learning content."}
      </p>
      {!loggedIn && (
        <Link
          to="/login"
          className="mt-6 inline-block rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90"
        >
          Log in
        </Link>
      )}
    </section>
  );
}

/* ---------------- Topics ---------------- */

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function TopicsManager() {
  const qc = useQueryClient();
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["topics"] });

  const createM = useMutation({ mutationFn: createTopic, onSuccess: invalidate });
  const deleteM = useMutation({ mutationFn: deleteTopic, onSuccess: invalidate });
  const updateM = useMutation({
    mutationFn: (v: {
      id: string;
      title: string;
      description: string | null;
      level: string | null;
    }) => updateTopic(v.id, { title: v.title, description: v.description, level: v.level }),
    onSuccess: invalidate,
  });

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [level, setLevel] = useState<string>("beginner");

  return (
    <div className="grid lg:grid-cols-12 gap-8 items-start">
      <div className="lg:col-span-5">
        <div className="sticky top-24 rounded-4xl border border-border bg-card p-6">
          <h3 className="text-lg text-ink">New topic</h3>
          <div className="mt-4 space-y-3">
            <LabeledInput
              label="Title"
              value={title}
              onChange={setTitle}
              placeholder="Job Interview"
            />
            <div>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Slug
              </span>
              <p className="mt-1 rounded-2xl border border-dashed border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                {title ? slugify(title) : "auto-generated-from-title"}
              </p>
            </div>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Description
              </span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="What this topic is about…"
                className="mt-1 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
              />
            </label>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Level
              </span>
              <div className="mt-1 flex flex-wrap gap-2">
                {LEVELS.map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLevel(l)}
                    className={`rounded-full px-3 py-1.5 text-xs border ${level === l ? "bg-primary text-primary-foreground border-primary" : "bg-background text-foreground border-border hover:bg-muted"}`}
                  >
                    {levelLabel(l)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {createM.isError && (
            <p className="mt-3 text-sm text-destructive">{(createM.error as Error).message}</p>
          )}
          <button
            disabled={!title.trim() || createM.isPending}
            onClick={() =>
              createM.mutate(
                {
                  slug: slugify(title),
                  title: title.trim(),
                  description: description.trim() || null,
                  level,
                },
                {
                  onSuccess: () => {
                    setTitle("");
                    setDescription("");
                  },
                },
              )
            }
            className="mt-4 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {createM.isPending ? "Creating…" : "Create topic"}
          </button>
        </div>
      </div>

      <div className="lg:col-span-7 space-y-3">
        {topicsQ.isLoading && (
          <div className="h-24 rounded-3xl bg-card border border-border animate-pulse" />
        )}
        {topicsQ.isError && (
          <ErrorState
            message={(topicsQ.error as Error)?.message ?? "Could not load topics"}
            onRetry={() => topicsQ.refetch()}
          />
        )}
        {(topicsQ.data ?? []).map((t) => (
          <TopicRow
            key={t.id}
            topic={t}
            onSave={(title2, description2, level2) =>
              updateM.mutate({ id: t.id, title: title2, description: description2, level: level2 })
            }
            onDelete={() => deleteM.mutate(t.id)}
          />
        ))}
      </div>
    </div>
  );
}

function TopicRow({
  topic,
  onSave,
  onDelete,
}: {
  topic: Topic;
  onSave: (title: string, description: string | null, level: string | null) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(topic.title);
  const [description, setDescription] = useState(topic.description ?? "");
  const [level, setLevel] = useState(topic.level ?? "beginner");
  const [confirm, setConfirm] = useState(false);

  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      {editing ? (
        <div className="space-y-2">
          <LabeledInput label="Title" value={title} onChange={setTitle} />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
          />
          <div className="flex flex-wrap gap-2">
            {LEVELS.map((l) => (
              <button
                key={l}
                onClick={() => setLevel(l)}
                className={`rounded-full px-3 py-1 text-xs border ${level === l ? "bg-primary text-primary-foreground border-primary" : "bg-background border-border"}`}
              >
                {levelLabel(l)}
              </button>
            ))}
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={() => {
                onSave(title.trim(), description.trim() || null, level);
                setEditing(false);
              }}
              className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-base text-ink font-medium truncate">{topic.title}</h4>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                {levelLabel(topic.level)}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground font-mono">/{topic.slug}</p>
            {topic.description && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{topic.description}</p>
            )}
          </div>
          <div className="flex flex-none gap-2">
            <button
              onClick={() => setEditing(true)}
              className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold hover:bg-muted"
            >
              Edit
            </button>
            {confirm ? (
              <button
                onClick={onDelete}
                className="rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
              >
                Confirm
              </button>
            ) : (
              <button
                onClick={() => setConfirm(true)}
                onBlur={() => setConfirm(false)}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Documents ---------------- */

function DocumentsManager() {
  const qc = useQueryClient();
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const topics = topicsQ.data ?? [];
  const [topicId, setTopicId] = useState<string>("");
  const activeTopic = topicId || topics[0]?.id || "";

  const docsQ = useQuery({
    queryKey: ["documents", activeTopic],
    queryFn: () => listDocuments(activeTopic),
    enabled: !!activeTopic,
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["documents", activeTopic] });

  const createM = useMutation({ mutationFn: createDocument, onSuccess: invalidate });
  const deleteM = useMutation({ mutationFn: deleteDocument, onSuccess: invalidate });
  const updateM = useMutation({
    mutationFn: (v: { id: string; title: string; content: string; kind: DocumentKind }) =>
      updateDocument(v.id, { title: v.title, content: v.content, kind: v.kind }),
    onSuccess: invalidate,
  });

  const [kind, setKind] = useState<DocumentKind>("explanation");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  if (topics.length === 0) {
    return (
      <div className="rounded-4xl border border-dashed border-border bg-card p-10 text-center">
        <div className="text-4xl">📚</div>
        <h3 className="mt-3 text-xl text-ink">Create a topic first</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Documents attach to a topic. Add a topic on the Topics tab, then come back.
        </p>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-12 gap-8 items-start">
      <div className="lg:col-span-5">
        <div className="sticky top-24 rounded-4xl border border-border bg-card p-6">
          <h3 className="text-lg text-ink">New document</h3>
          <div className="mt-4 space-y-3">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Topic
              </span>
              <select
                value={activeTopic}
                onChange={(e) => setTopicId(e.target.value)}
                className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary"
              >
                {topics.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Kind
              </span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as DocumentKind)}
                className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary capitalize"
              >
                {DOC_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <LabeledInput
              label="Title"
              value={title}
              onChange={setTitle}
              placeholder="Useful phrases"
            />
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Content
              </span>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={5}
                placeholder="Example sentences, vocabulary, tips…"
                className="mt-1 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
              />
            </label>
          </div>
          {createM.isError && (
            <p className="mt-3 text-sm text-destructive">{(createM.error as Error).message}</p>
          )}
          <button
            disabled={!title.trim() || !content.trim() || createM.isPending}
            onClick={() =>
              createM.mutate(
                { topic_id: activeTopic, kind, title: title.trim(), content: content.trim() },
                {
                  onSuccess: () => {
                    setTitle("");
                    setContent("");
                  },
                },
              )
            }
            className="mt-4 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {createM.isPending ? "Adding…" : "Add document"}
          </button>
        </div>
      </div>

      <div className="lg:col-span-7 space-y-3">
        {docsQ.isLoading && (
          <div className="h-24 rounded-3xl bg-card border border-border animate-pulse" />
        )}
        {docsQ.isError && (
          <ErrorState
            message={(docsQ.error as Error)?.message ?? "Could not load documents"}
            onRetry={() => docsQ.refetch()}
          />
        )}
        {docsQ.isSuccess && (docsQ.data ?? []).length === 0 && (
          <div className="rounded-3xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No documents on this topic yet. Add the first one on the left.
          </div>
        )}
        {(docsQ.data ?? []).map((d) => (
          <DocumentRow
            key={d.id}
            doc={d}
            onSave={(title2, content2, kind2) =>
              updateM.mutate({ id: d.id, title: title2, content: content2, kind: kind2 })
            }
            onDelete={() => deleteM.mutate(d.id)}
          />
        ))}
      </div>
    </div>
  );
}

function DocumentRow({
  doc,
  onSave,
  onDelete,
}: {
  doc: TopicDocument;
  onSave: (title: string, content: string, kind: DocumentKind) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(doc.title);
  const [content, setContent] = useState(doc.content);
  const [kind, setKind] = useState<DocumentKind>(doc.kind);
  const [confirm, setConfirm] = useState(false);

  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      {editing ? (
        <div className="space-y-2">
          <LabeledInput label="Title" value={title} onChange={setTitle} />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={4}
            className="w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as DocumentKind)}
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs capitalize"
          >
            {DOC_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.replace("_", " ")}
              </option>
            ))}
          </select>
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={() => {
                onSave(title.trim(), content.trim(), kind);
                setEditing(false);
              }}
              className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-base text-ink font-medium truncate">{doc.title}</h4>
              <span className="rounded-full bg-secondary/30 px-2 py-0.5 text-[10px] uppercase tracking-wider text-secondary-foreground">
                {doc.kind.replace("_", " ")}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground line-clamp-3 whitespace-pre-wrap">
              {doc.content}
            </p>
          </div>
          <div className="flex flex-none gap-2">
            <button
              onClick={() => setEditing(true)}
              className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold hover:bg-muted"
            >
              Edit
            </button>
            {confirm ? (
              <button
                onClick={onDelete}
                className="rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
              >
                Confirm
              </button>
            ) : (
              <button
                onClick={() => setConfirm(true)}
                onBlur={() => setConfirm(false)}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- shared ---------------- */

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary"
      />
    </label>
  );
}
