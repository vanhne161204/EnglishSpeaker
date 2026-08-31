import { requireAdmin } from "@/lib/require-auth";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useIdentity } from "@/lib/identity";
import {
  ApiError,
  createAnswerTemplate,
  createCategory,
  createDoc,
  createDocItem,
  createQuestion,
  createSection,
  createTopic,
  deleteAnswerTemplate,
  deleteCategory,
  deleteDoc,
  deleteDocItem,
  deleteQuestion,
  deleteSection,
  deleteTopic,
  getTopicDoc,
  listCategories,
  listTopicQA,
  listTopics,
  saveTopicQA,
  updateCategory,
  updateDoc,
  updateSection,
  updateTopic,
  type Category,
  type ContentStatus,
  type Doc,
  type DocSection,
  type DocSectionType,
  type Question,
  type Topic,
} from "@/lib/api";
import { levelLabel, LEVELS } from "@/lib/presentation";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/admin")({
  // Requires an account (docs/11_Security.md §11.2). The API enforces this
  // too; the guard just avoids rendering a page that would 401 on every call.
  beforeLoad: ({ location }) => requireAdmin(location.pathname),
  head: () => ({
    meta: [
      { title: "Admin — EnglishTalker" },
      { name: "description", content: "Manage categories, topics, and learning content." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AdminPage,
});

const TABS = ["categories", "topics", "content"] as const;
type Tab = (typeof TABS)[number];

/** Tab labels. "content" leads with the job admins actually do most: questions. */
const TAB_LABELS: Record<Tab, string> = {
  categories: "Categories",
  topics: "Topics",
  content: "Questions & answers",
};

/** Section types, with a plain-English hint about what each one holds (PRD §8.2). */
const SECTION_TYPES: { readonly type: DocSectionType; readonly hint: string }[] = [
  { type: "vocabulary", hint: "Single words, with meaning and example" },
  { type: "phrases", hint: "Ready-made phrases the learner can copy" },
  { type: "questions", hint: "Conversation questions, each with sample answers" },
  { type: "tips", hint: "Free-text speaking advice" },
  { type: "text", hint: "Anything else — explanations, common mistakes" },
];

const STATUSES: readonly ContentStatus[] = ["draft", "published", "archived"];

function AdminPage() {
  const identity = useIdentity();
  const [tab, setTab] = useState<Tab>("topics");

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
          Group topics into categories, create the topics learners practice, then give each topic a
          few questions with a sample answer. Those questions show up in the room and in Warm-up,
          and the AI coach uses them to ground its suggestions (PRD §8.1, §8.2).
        </p>
        <div className="mt-6 inline-flex rounded-full border border-border bg-card p-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-full px-5 py-2 text-sm font-medium ${tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>
      </section>

      <section className="container-page py-6">
        {tab === "categories" && <CategoriesManager />}
        {tab === "topics" && <TopicsManager />}
        {tab === "content" && <ContentManager />}
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

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/* ---------------- Categories ---------------- */

function CategoriesManager() {
  const qc = useQueryClient();
  const categoriesQ = useQuery({ queryKey: ["categories"], queryFn: () => listCategories() });
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["categories"] });
    // Topics carry `category_id`, so their cached copies can go stale too.
    void qc.invalidateQueries({ queryKey: ["topics"] });
  };

  const createM = useMutation({ mutationFn: createCategory, onSuccess: invalidate });
  const deleteM = useMutation({ mutationFn: deleteCategory, onSuccess: invalidate });
  const updateM = useMutation({
    mutationFn: (v: { id: string; name: string; description: string | null; sort_order: number }) =>
      updateCategory(v.id, {
        name: v.name,
        description: v.description,
        sort_order: v.sort_order,
      }),
    onSuccess: invalidate,
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  return (
    <div className="grid lg:grid-cols-12 gap-8 items-start">
      <div className="lg:col-span-5">
        <div className="sticky top-24 rounded-4xl border border-border bg-card p-6">
          <h3 className="text-lg text-ink">New category</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            A shelf for topics, like “Daily Life” or “Work”.
          </p>
          <div className="mt-4 space-y-3">
            <LabeledInput label="Name" value={name} onChange={setName} placeholder="Daily Life" />
            <SlugPreview title={name} />
            <LabeledTextarea
              label="Description"
              value={description}
              onChange={setDescription}
              rows={3}
              placeholder="What kind of topics live here…"
            />
          </div>
          {createM.isError && (
            <p className="mt-3 text-sm text-destructive">{(createM.error as Error).message}</p>
          )}
          <button
            disabled={!name.trim() || createM.isPending}
            onClick={() =>
              createM.mutate(
                {
                  slug: slugify(name),
                  name: name.trim(),
                  description: description.trim() || null,
                  sort_order: categoriesQ.data?.length ?? 0,
                },
                {
                  onSuccess: () => {
                    setName("");
                    setDescription("");
                  },
                },
              )
            }
            className="mt-4 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {createM.isPending ? "Creating…" : "Create category"}
          </button>
        </div>
      </div>

      <div className="lg:col-span-7 space-y-3">
        {categoriesQ.isLoading && <SkeletonRow />}
        {categoriesQ.isError && (
          <ErrorState
            message={(categoriesQ.error as Error)?.message ?? "Could not load categories"}
            onRetry={() => void categoriesQ.refetch()}
          />
        )}
        {categoriesQ.isSuccess && (categoriesQ.data ?? []).length === 0 && (
          <EmptyCard>No categories yet. Topics without one show under “Other”.</EmptyCard>
        )}
        {(categoriesQ.data ?? []).map((c) => (
          <CategoryRow
            key={c.id}
            category={c}
            onSave={(v) => updateM.mutate({ id: c.id, ...v })}
            onDelete={() => deleteM.mutate(c.id)}
          />
        ))}
      </div>
    </div>
  );
}

function CategoryRow({
  category,
  onSave,
  onDelete,
}: {
  category: Category;
  onSave: (v: { name: string; description: string | null; sort_order: number }) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);
  const [description, setDescription] = useState(category.description ?? "");
  const [sortOrder, setSortOrder] = useState(String(category.sort_order));

  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      {editing ? (
        <div className="space-y-2">
          <LabeledInput label="Name" value={name} onChange={setName} />
          <LabeledTextarea
            label="Description"
            value={description}
            onChange={setDescription}
            rows={2}
          />
          <LabeledInput label="Sort order" value={sortOrder} onChange={setSortOrder} />
          <EditActions
            onSave={() => {
              onSave({
                name: name.trim(),
                description: description.trim() || null,
                sort_order: Number(sortOrder) || 0,
              });
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-base text-ink font-medium truncate">{category.name}</h4>
              <Pill>#{category.sort_order}</Pill>
            </div>
            <p className="mt-1 text-xs text-muted-foreground font-mono">/{category.slug}</p>
            {category.description && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                {category.description}
              </p>
            )}
          </div>
          <RowActions
            onEdit={() => setEditing(true)}
            onDelete={onDelete}
            deleteHint="Topics in it are kept — they just lose their grouping."
          />
        </div>
      )}
    </div>
  );
}

/* ---------------- Topics ---------------- */

function TopicsManager() {
  const qc = useQueryClient();
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const categoriesQ = useQuery({ queryKey: ["categories"], queryFn: () => listCategories() });
  const categories = categoriesQ.data ?? [];
  const invalidate = () => void qc.invalidateQueries({ queryKey: ["topics"] });

  const createM = useMutation({ mutationFn: createTopic, onSuccess: invalidate });
  const deleteM = useMutation({ mutationFn: deleteTopic, onSuccess: invalidate });
  const updateM = useMutation({
    mutationFn: (v: { id: string } & TopicFields) => updateTopic(v.id, v),
    onSuccess: invalidate,
  });

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [level, setLevel] = useState<string>("beginner");
  const [categoryId, setCategoryId] = useState<string>("");
  const [coverImageUrl, setCoverImageUrl] = useState("");

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
            <SlugPreview title={title} />
            <LabeledTextarea
              label="Description"
              value={description}
              onChange={setDescription}
              rows={3}
              placeholder="What this topic is about…"
            />
            <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
            <LevelPicker value={level} onChange={setLevel} />
            <LabeledInput
              label="Cover image URL"
              value={coverImageUrl}
              onChange={setCoverImageUrl}
              placeholder="https://… (optional)"
            />
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
                  category_id: categoryId || null,
                  cover_image_url: coverImageUrl.trim() || null,
                  sort_order: topicsQ.data?.length ?? 0,
                },
                {
                  onSuccess: () => {
                    setTitle("");
                    setDescription("");
                    setCoverImageUrl("");
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
        {topicsQ.isLoading && <SkeletonRow />}
        {topicsQ.isError && (
          <ErrorState
            message={(topicsQ.error as Error)?.message ?? "Could not load topics"}
            onRetry={() => void topicsQ.refetch()}
          />
        )}
        {(topicsQ.data ?? []).map((t) => (
          <TopicRow
            key={t.id}
            topic={t}
            categories={categories}
            onSave={(fields) => updateM.mutate({ id: t.id, ...fields })}
            onDelete={() => deleteM.mutate(t.id)}
          />
        ))}
      </div>
    </div>
  );
}

/** The editable slice of a topic — shared by the row's form and its save handler. */
interface TopicFields {
  title: string;
  description: string | null;
  level: string | null;
  category_id: string | null;
  cover_image_url: string | null;
  sort_order: number;
}

function TopicRow({
  topic,
  categories,
  onSave,
  onDelete,
}: {
  topic: Topic;
  categories: readonly Category[];
  onSave: (fields: TopicFields) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(topic.title);
  const [description, setDescription] = useState(topic.description ?? "");
  const [level, setLevel] = useState(topic.level ?? "beginner");
  const [categoryId, setCategoryId] = useState(topic.category_id ?? "");
  const [coverImageUrl, setCoverImageUrl] = useState(topic.cover_image_url ?? "");
  const [sortOrder, setSortOrder] = useState(String(topic.sort_order));
  const categoryName = categories.find((c) => c.id === topic.category_id)?.name;

  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      {editing ? (
        <div className="space-y-2">
          <LabeledInput label="Title" value={title} onChange={setTitle} />
          <LabeledTextarea
            label="Description"
            value={description}
            onChange={setDescription}
            rows={2}
          />
          <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
          <LevelPicker value={level} onChange={setLevel} />
          <LabeledInput label="Cover image URL" value={coverImageUrl} onChange={setCoverImageUrl} />
          <LabeledInput label="Sort order" value={sortOrder} onChange={setSortOrder} />
          <EditActions
            onSave={() => {
              onSave({
                title: title.trim(),
                description: description.trim() || null,
                level,
                category_id: categoryId || null,
                cover_image_url: coverImageUrl.trim() || null,
                sort_order: Number(sortOrder) || 0,
              });
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-base text-ink font-medium truncate">{topic.title}</h4>
              <Pill>{levelLabel(topic.level)}</Pill>
              {categoryName && <Pill>{categoryName}</Pill>}
              <Pill>#{topic.sort_order}</Pill>
            </div>
            <p className="mt-1 text-xs text-muted-foreground font-mono">/{topic.slug}</p>
            {topic.description && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{topic.description}</p>
            )}
          </div>
          <RowActions
            onEdit={() => setEditing(true)}
            onDelete={onDelete}
            deleteHint="Its documentation is deleted too."
          />
        </div>
      )}
    </div>
  );
}

/* ---------------- Questions & answers (PRD §8.1) ---------------- */

function ContentManager() {
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });
  const topics = topicsQ.data ?? [];
  const [topicId, setTopicId] = useState<string>("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const activeTopicId = topicId || topics[0]?.id || "";
  const activeTopic = topics.find((t) => t.id === activeTopicId) ?? null;

  if (topicsQ.isLoading) return <SkeletonRow />;
  if (topics.length === 0) {
    return (
      <EmptyCard icon="📚" title="Create a topic first">
        Questions belong to a topic. Add one on the Topics tab, then come back.
      </EmptyCard>
    );
  }

  return (
    <div className="space-y-6">
      <label className="block max-w-md">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Topic</span>
        <select
          value={activeTopicId}
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

      {activeTopic && <QAEditor key={activeTopic.id} topic={activeTopic} />}

      {/* The full section editor is still here for vocabulary, phrases, and tips —
          just folded away, so the common job (questions) is the whole screen. */}
      <div className="pt-2">
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-sm font-semibold text-muted-foreground hover:text-foreground"
        >
          {showAdvanced ? "▾" : "▸"} Advanced — vocabulary, phrases, and tips
        </button>
        {showAdvanced && activeTopic && (
          <div className="mt-4">
            <DocEditor key={`adv-${activeTopic.id}`} topic={activeTopic} />
          </div>
        )}
      </div>
    </div>
  );
}

/** How many blank rows to show, so an admin always sees room for a full set. */
const DEFAULT_QA_ROWS = 5;

interface QARow {
  /** Stable React key. Server rows reuse their id; new rows get a generated one. */
  readonly key: string;
  text: string;
  answer: string;
}

function blankRow(): QARow {
  return { key: `new-${Math.random().toString(36).slice(2)}`, text: "", answer: "" };
}

/** Pad to `DEFAULT_QA_ROWS` so the form never looks empty or cramped. */
function padRows(rows: QARow[]): QARow[] {
  const padded = [...rows];
  while (padded.length < DEFAULT_QA_ROWS) padded.push(blankRow());
  return padded;
}

/**
 * The simple editor: a numbered list of question/answer pairs, one Save button.
 *
 * It hides the doc tree entirely. `PUT /topics/{id}/questions` creates the doc and
 * the questions section on the server, so an admin types pairs and nothing else.
 */
function QAEditor({ topic }: { topic: Topic }) {
  const qc = useQueryClient();
  const qaQ = useQuery({ queryKey: ["topic-qa", topic.id], queryFn: () => listTopicQA(topic.id) });
  const [rows, setRows] = useState<QARow[]>(() => padRows([]));
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Reload the form whenever the server copy changes — on first load, and again
  // after a save, so what's on screen is always what's stored.
  useEffect(() => {
    if (!qaQ.data) return;
    setRows(padRows(qaQ.data.map((p) => ({ key: p.id, text: p.text, answer: p.answer ?? "" }))));
  }, [qaQ.data]);

  const saveM = useMutation({
    mutationFn: () =>
      saveTopicQA(
        topic.id,
        // Blank rows are just unused slots, not content — drop them.
        rows
          .filter((r) => r.text.trim())
          .map((r) => ({ text: r.text.trim(), answer: r.answer.trim() || null })),
      ),
    onSuccess: () => {
      setSavedAt(Date.now());
      void qc.invalidateQueries({ queryKey: ["topic-qa", topic.id] });
      // The room panel and Warm-up both read the published question feed.
      void qc.invalidateQueries({ queryKey: ["questions"] });
      void qc.invalidateQueries({ queryKey: ["topic-doc", topic.id] });
    },
  });

  const update = (index: number, patch: Partial<QARow>) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  const removeRow = (index: number) =>
    setRows((prev) => padRows(prev.filter((_, i) => i !== index)));

  const filled = rows.filter((r) => r.text.trim()).length;

  if (qaQ.isLoading) return <SkeletonRow />;
  if (qaQ.isError) {
    return <ErrorState message={(qaQ.error as Error).message} onRetry={() => void qaQ.refetch()} />;
  }

  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-xl text-ink">Questions &amp; answers</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Write a question and one sample answer a learner can copy. These show in the room and in
            Warm-up. Saving publishes them right away.
          </p>
        </div>
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {filled} question{filled === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-5 space-y-3">
        {rows.map((row, index) => (
          <div
            key={row.key}
            className="rounded-3xl border border-border bg-background p-4 flex gap-3"
          >
            <div className="flex-none h-7 w-7 rounded-full bg-primary/10 text-primary inline-flex items-center justify-center text-xs font-semibold">
              {index + 1}
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <input
                value={row.text}
                onChange={(e) => update(index, { text: e.target.value })}
                placeholder="Question — e.g. What is your favourite food?"
                className="w-full rounded-2xl border border-border bg-card px-3 py-2 text-sm font-medium focus:outline-none focus:border-primary"
              />
              <input
                value={row.answer}
                onChange={(e) => update(index, { answer: e.target.value })}
                placeholder="Sample answer — e.g. My favourite food is pizza."
                className="w-full rounded-2xl border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:border-primary"
              />
            </div>
            <button
              onClick={() => removeRow(index)}
              title="Remove this question"
              aria-label={`Remove question ${index + 1}`}
              className="flex-none self-start rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-destructive hover:border-destructive/40"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-3 flex-wrap">
        <button
          onClick={() => setRows((prev) => [...prev, blankRow()])}
          className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted"
        >
          + Add another
        </button>
        <button
          disabled={saveM.isPending}
          onClick={() => saveM.mutate()}
          className="rounded-full bg-primary px-6 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {saveM.isPending ? "Saving…" : "Save questions"}
        </button>
        {savedAt && !saveM.isPending && !saveM.isError && (
          <span className="text-sm text-muted-foreground">Saved ✓</span>
        )}
      </div>

      {saveM.isError && (
        <p className="mt-3 text-sm text-destructive">{(saveM.error as Error).message}</p>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Saving replaces the whole list — a question you clear here is removed for learners too.
      </p>
    </div>
  );
}

function DocEditor({ topic }: { topic: Topic }) {
  const qc = useQueryClient();
  // A topic with no doc yet is the normal starting state, so a 404 is data, not
  // an error — don't retry it.
  const docQ = useQuery({
    queryKey: ["topic-doc", topic.id],
    queryFn: () => getTopicDoc(topic.id),
    retry: (count, error) => !isNotFound(error) && count < 2,
  });
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["topic-doc", topic.id] });
    // Warm-up reads questions from published docs, so its feed can go stale.
    void qc.invalidateQueries({ queryKey: ["questions"] });
  };

  const createDocM = useMutation({ mutationFn: createDoc, onSuccess: invalidate });
  const deleteDocM = useMutation({ mutationFn: deleteDoc, onSuccess: invalidate });

  if (docQ.isLoading) return <SkeletonRow />;
  if (docQ.isError && !isNotFound(docQ.error)) {
    return (
      <ErrorState message={(docQ.error as Error).message} onRetry={() => void docQ.refetch()} />
    );
  }

  const doc = docQ.data ?? null;
  if (!doc) {
    return (
      <EmptyCard icon="📝" title={`“${topic.title}” has no documentation yet`}>
        <p>
          Start it to add vocabulary, phrases, conversation questions, and sample answers. It stays
          a draft — hidden from learners — until you publish it.
        </p>
        {createDocM.isError && (
          <p className="mt-3 text-sm text-destructive">{(createDocM.error as Error).message}</p>
        )}
        <button
          disabled={createDocM.isPending}
          onClick={() => createDocM.mutate({ topic_id: topic.id, title: topic.title })}
          className="mt-5 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {createDocM.isPending ? "Starting…" : "Start documentation"}
        </button>
      </EmptyCard>
    );
  }

  return (
    <div className="space-y-4">
      <DocHeader doc={doc} onChanged={invalidate} onDelete={() => deleteDocM.mutate(doc.id)} />
      {doc.sections.map((section) => (
        <SectionCard key={section.id} section={section} onChanged={invalidate} />
      ))}
      <AddSectionForm docId={doc.id} nextOrder={doc.sections.length} onChanged={invalidate} />
    </div>
  );
}

function DocHeader({
  doc,
  onChanged,
  onDelete,
}: {
  doc: Doc;
  onChanged: () => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(doc.title ?? "");
  const [intro, setIntro] = useState(doc.intro ?? "");
  const updateM = useMutation({
    mutationFn: (v: Parameters<typeof updateDoc>[1]) => updateDoc(doc.id, v),
    onSuccess: onChanged,
  });

  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      {editing ? (
        <div className="space-y-2">
          <LabeledInput label="Title" value={title} onChange={setTitle} />
          <LabeledTextarea
            label="Intro"
            value={intro}
            onChange={setIntro}
            rows={2}
            placeholder="How to use this page…"
          />
          <EditActions
            onSave={() => {
              updateM.mutate({ title: title.trim() || null, intro: intro.trim() || null });
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : (
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <h3 className="text-xl text-ink">{doc.title ?? "Untitled documentation"}</h3>
            {doc.intro && <p className="mt-1 text-sm text-muted-foreground">{doc.intro}</p>}
            <p className="mt-2 text-xs text-muted-foreground">
              {doc.sections.length} section{doc.sections.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Only a published doc reaches learners and Warm-up (PRD §8.2). */}
            <select
              value={doc.status}
              onChange={(e) => updateM.mutate({ status: e.target.value as ContentStatus })}
              className="rounded-full border border-border bg-background px-3 py-1.5 text-xs capitalize focus:outline-none focus:border-primary"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <RowActions
              onEdit={() => setEditing(true)}
              onDelete={onDelete}
              deleteHint="Every section, item, and question goes with it."
            />
          </div>
        </div>
      )}
      {updateM.isError && (
        <p className="mt-3 text-sm text-destructive">{(updateM.error as Error).message}</p>
      )}
    </div>
  );
}

function AddSectionForm({
  docId,
  nextOrder,
  onChanged,
}: {
  docId: string;
  nextOrder: number;
  onChanged: () => void;
}) {
  const [type, setType] = useState<DocSectionType>("questions");
  const [title, setTitle] = useState("");
  const createM = useMutation({
    mutationFn: () =>
      createSection(docId, { type, title: title.trim() || null, sort_order: nextOrder }),
    onSuccess: () => {
      setTitle("");
      onChanged();
    },
  });
  const hint = SECTION_TYPES.find((s) => s.type === type)?.hint;

  return (
    <div className="rounded-4xl border border-dashed border-border bg-card p-6">
      <h4 className="text-base text-ink">Add a section</h4>
      <div className="mt-3 grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as DocSectionType)}
            className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm capitalize focus:outline-none focus:border-primary"
          >
            {SECTION_TYPES.map((s) => (
              <option key={s.type} value={s.type}>
                {s.type}
              </option>
            ))}
          </select>
        </label>
        <LabeledInput
          label="Heading"
          value={title}
          onChange={setTitle}
          placeholder="Useful travel words (optional)"
        />
      </div>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
      {createM.isError && (
        <p className="mt-3 text-sm text-destructive">{(createM.error as Error).message}</p>
      )}
      <button
        disabled={createM.isPending}
        onClick={() => createM.mutate()}
        className="mt-4 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        {createM.isPending ? "Adding…" : "Add section"}
      </button>
    </div>
  );
}

function SectionCard({ section, onChanged }: { section: DocSection; onChanged: () => void }) {
  const deleteM = useMutation({
    mutationFn: () => deleteSection(section.id),
    onSuccess: onChanged,
  });
  const holdsItems = section.type === "vocabulary" || section.type === "phrases";

  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Pill>{section.type}</Pill>
            <h4 className="text-base text-ink font-medium truncate">
              {section.title ?? "Untitled section"}
            </h4>
          </div>
        </div>
        <ConfirmDelete
          onDelete={() => deleteM.mutate()}
          hint="Everything inside this section is deleted too."
        />
      </div>

      <div className="mt-4">
        {holdsItems && <ItemsEditor section={section} onChanged={onChanged} />}
        {section.type === "questions" && (
          <QuestionsEditor section={section} onChanged={onChanged} />
        )}
        {(section.type === "tips" || section.type === "text") && (
          <BodyEditor section={section} onChanged={onChanged} />
        )}
      </div>
    </div>
  );
}

/** Free-text body for `tips` and `text` sections. */
function BodyEditor({ section, onChanged }: { section: DocSection; onChanged: () => void }) {
  const [body, setBody] = useState(section.body ?? "");
  const updateM = useMutation({
    mutationFn: () => updateSection(section.id, { body: body.trim() || null }),
    onSuccess: onChanged,
  });
  const dirty = body !== (section.body ?? "");

  return (
    <div>
      <LabeledTextarea
        label="Body"
        value={body}
        onChange={setBody}
        rows={4}
        placeholder="Write the advice or explanation…"
      />
      {updateM.isError && (
        <p className="mt-2 text-sm text-destructive">{(updateM.error as Error).message}</p>
      )}
      <button
        disabled={!dirty || updateM.isPending}
        onClick={() => updateM.mutate()}
        className="mt-2 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
      >
        {updateM.isPending ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

/** Vocabulary and phrase items. */
function ItemsEditor({ section, onChanged }: { section: DocSection; onChanged: () => void }) {
  const [term, setTerm] = useState("");
  const [phonetic, setPhonetic] = useState("");
  const [meaning, setMeaning] = useState("");
  const [example, setExample] = useState("");

  const createM = useMutation({
    mutationFn: () =>
      createDocItem(section.id, {
        term: term.trim(),
        phonetic: phonetic.trim() || null,
        meaning: meaning.trim() || null,
        example: example.trim() || null,
        sort_order: section.items.length,
      }),
    onSuccess: () => {
      setTerm("");
      setPhonetic("");
      setMeaning("");
      setExample("");
      onChanged();
    },
  });
  const deleteM = useMutation({ mutationFn: deleteDocItem, onSuccess: onChanged });

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {section.items.map((item) => (
          <li
            key={item.id}
            className="flex items-start justify-between gap-3 rounded-2xl border border-border bg-background px-4 py-3"
          >
            <div className="min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-sm font-semibold">{item.term}</span>
                {item.phonetic && (
                  <span className="text-xs text-muted-foreground">{item.phonetic}</span>
                )}
              </div>
              {item.meaning && (
                <p className="mt-0.5 text-xs text-muted-foreground">{item.meaning}</p>
              )}
              {item.example && (
                <p className="mt-0.5 text-xs text-muted-foreground">“{item.example}”</p>
              )}
            </div>
            <ConfirmDelete onDelete={() => deleteM.mutate(item.id)} />
          </li>
        ))}
      </ul>

      <div className="rounded-2xl border border-dashed border-border p-4 space-y-2">
        <div className="grid sm:grid-cols-2 gap-2">
          <LabeledInput label="Term" value={term} onChange={setTerm} placeholder="breakfast" />
          <LabeledInput
            label="Phonetic"
            value={phonetic}
            onChange={setPhonetic}
            placeholder="/ˈbrekfəst/"
          />
        </div>
        <LabeledInput
          label="Meaning"
          value={meaning}
          onChange={setMeaning}
          placeholder="the first meal of the day"
        />
        <LabeledInput
          label="Example"
          value={example}
          onChange={setExample}
          placeholder="I have breakfast at seven."
        />
        {createM.isError && (
          <p className="text-sm text-destructive">{(createM.error as Error).message}</p>
        )}
        <button
          disabled={!term.trim() || createM.isPending}
          onClick={() => createM.mutate()}
          className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
        >
          {createM.isPending ? "Adding…" : "Add item"}
        </button>
      </div>
    </div>
  );
}

/** Questions, each with its own answer templates. */
function QuestionsEditor({ section, onChanged }: { section: DocSection; onChanged: () => void }) {
  const [text, setText] = useState("");
  const createM = useMutation({
    mutationFn: () =>
      createQuestion({
        section_id: section.id,
        text: text.trim(),
        sort_order: section.questions.length,
      }),
    onSuccess: () => {
      setText("");
      onChanged();
    },
  });
  const deleteM = useMutation({ mutationFn: deleteQuestion, onSuccess: onChanged });

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {section.questions.map((question) => (
          <li key={question.id} className="rounded-2xl border border-border bg-background p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold">{question.text}</p>
              <ConfirmDelete
                onDelete={() => deleteM.mutate(question.id)}
                hint="Its answer templates go too."
              />
            </div>
            <AnswerTemplatesEditor question={question} onChanged={onChanged} />
          </li>
        ))}
      </ul>

      <div className="rounded-2xl border border-dashed border-border p-4 space-y-2">
        <LabeledInput
          label="Question"
          value={text}
          onChange={setText}
          placeholder="What is your favourite food?"
        />
        {createM.isError && (
          <p className="text-sm text-destructive">{(createM.error as Error).message}</p>
        )}
        <button
          disabled={!text.trim() || createM.isPending}
          onClick={() => createM.mutate()}
          className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
        >
          {createM.isPending ? "Adding…" : "Add question"}
        </button>
      </div>
    </div>
  );
}

function AnswerTemplatesEditor({
  question,
  onChanged,
}: {
  question: Question;
  onChanged: () => void;
}) {
  const [template, setTemplate] = useState("");
  const [example, setExample] = useState("");
  const [open, setOpen] = useState(false);

  const createM = useMutation({
    mutationFn: () =>
      createAnswerTemplate(question.id, {
        template: template.trim(),
        example: example.trim() || null,
        sort_order: question.answer_templates.length,
      }),
    onSuccess: () => {
      setTemplate("");
      setExample("");
      onChanged();
    },
  });
  const deleteM = useMutation({ mutationFn: deleteAnswerTemplate, onSuccess: onChanged });

  return (
    <div className="mt-2 pl-3 border-l-2 border-border">
      {question.answer_templates.map((tpl) => (
        <div key={tpl.id} className="flex items-start justify-between gap-2 py-1">
          <div className="min-w-0">
            <p className="text-sm">{tpl.template}</p>
            {tpl.example && <p className="text-xs text-muted-foreground">e.g. {tpl.example}</p>}
          </div>
          <ConfirmDelete onDelete={() => deleteM.mutate(tpl.id)} />
        </div>
      ))}

      {open ? (
        <div className="mt-2 space-y-2">
          <LabeledInput
            label="Template"
            value={template}
            onChange={setTemplate}
            placeholder="My favourite food is ___."
          />
          <LabeledInput
            label="Filled example"
            value={example}
            onChange={setExample}
            placeholder="My favourite food is pizza."
          />
          {createM.isError && (
            <p className="text-sm text-destructive">{(createM.error as Error).message}</p>
          )}
          <div className="flex gap-2">
            <button
              disabled={!template.trim() || createM.isPending}
              onClick={() => createM.mutate()}
              className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
            >
              {createM.isPending ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => setOpen(false)}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="mt-1 text-xs font-semibold text-primary hover:underline"
        >
          + Sample answer
        </button>
      )}
    </div>
  );
}

/* ---------------- shared ---------------- */

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

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

function LabeledTextarea({
  label,
  value,
  onChange,
  rows,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows: number;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        placeholder={placeholder}
        className="mt-1 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
      />
    </label>
  );
}

function SlugPreview({ title }: { title: string }) {
  return (
    <div>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Slug</span>
      <p className="mt-1 rounded-2xl border border-dashed border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
        {title ? slugify(title) : "auto-generated-from-title"}
      </p>
    </div>
  );
}

function CategorySelect({
  categories,
  value,
  onChange,
}: {
  categories: readonly Category[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Category</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary"
      >
        <option value="">No category (shows under “Other”)</option>
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function LevelPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Level</span>
      <div className="mt-1 flex flex-wrap gap-2">
        {LEVELS.map((l) => (
          <button
            key={l}
            type="button"
            onClick={() => onChange(l)}
            className={`rounded-full px-3 py-1.5 text-xs border ${value === l ? "bg-primary text-primary-foreground border-primary" : "bg-background text-foreground border-border hover:bg-muted"}`}
          >
            {levelLabel(l)}
          </button>
        ))}
      </div>
    </div>
  );
}

function EditActions({ onSave, onCancel }: { onSave: () => void; onCancel: () => void }) {
  return (
    <div className="flex justify-end gap-2 pt-1">
      <button
        onClick={onSave}
        className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground"
      >
        Save
      </button>
      <button
        onClick={onCancel}
        className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold"
      >
        Cancel
      </button>
    </div>
  );
}

function RowActions({
  onEdit,
  onDelete,
  deleteHint,
}: {
  onEdit: () => void;
  onDelete: () => void;
  deleteHint?: string;
}) {
  return (
    <div className="flex flex-none gap-2">
      <button
        onClick={onEdit}
        className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold hover:bg-muted"
      >
        Edit
      </button>
      <ConfirmDelete onDelete={onDelete} hint={deleteHint} />
    </div>
  );
}

/** Two-step delete: the first click arms it, the second confirms (blur disarms). */
function ConfirmDelete({ onDelete, hint }: { onDelete: () => void; hint?: string }) {
  const [armed, setArmed] = useState(false);
  if (armed) {
    return (
      <button
        onClick={onDelete}
        onBlur={() => setArmed(false)}
        title={hint}
        className="flex-none rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
      >
        Confirm
      </button>
    );
  }
  return (
    <button
      onClick={() => setArmed(true)}
      title={hint}
      className="flex-none rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10"
    >
      Delete
    </button>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
      {children}
    </span>
  );
}

function SkeletonRow() {
  return <div className="h-24 rounded-3xl bg-card border border-border animate-pulse" />;
}

function EmptyCard({
  icon,
  title,
  children,
}: {
  icon?: string;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-4xl border border-dashed border-border bg-card p-10 text-center">
      {icon && <div className="text-4xl">{icon}</div>}
      {title && <h3 className="mt-3 text-xl text-ink">{title}</h3>}
      <div className="mt-2 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}
