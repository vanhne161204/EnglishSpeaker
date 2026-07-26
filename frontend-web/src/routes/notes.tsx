import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createNote, deleteNote, listNotes, listTopics, updateNote, type Note } from "@/lib/api";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/notes")({
  head: () => ({
    meta: [
      { title: "Sentence notes — EnglishTalker" },
      {
        name: "description",
        content:
          "Save useful sentences and AI-improved phrases, grouped by topic. Review them anytime to speak more naturally.",
      },
    ],
  }),
  component: NotesPage,
});

function NotesPage() {
  const qc = useQueryClient();
  const notesQ = useQuery({ queryKey: ["notes"], queryFn: () => listNotes() });
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notes"] });

  const createM = useMutation({ mutationFn: createNote, onSuccess: invalidate });
  const updateM = useMutation({
    mutationFn: (v: { id: string; improved_text: string; topic: string | null }) =>
      updateNote(v.id, { improved_text: v.improved_text, topic: v.topic }),
    onSuccess: invalidate,
  });
  const deleteM = useMutation({ mutationFn: deleteNote, onSuccess: invalidate });

  const topicTitles = (topicsQ.data ?? []).map((t) => t.title);

  // Group notes by topic for review (PRD §8.7 "group sentence notes by topic").
  const notes = notesQ.data ?? [];
  const groups = new Map<string, Note[]>();
  for (const n of notes) {
    const key = n.topic ?? "No topic";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(n);
  }

  return (
    <>
      <section className="container-page pt-16 pb-6 text-center">
        <span className="chip">Sentence notes</span>
        <h1 className="mt-5 text-5xl sm:text-6xl text-ink">
          Keep the sentences <span className="italic text-primary">worth remembering.</span>
        </h1>
        <p className="mt-5 max-w-2xl mx-auto text-muted-foreground leading-relaxed">
          Save a phrase you said, a better version from the AI coach, or a useful line from a
          partner. Review them by topic to speak more naturally next time.
        </p>
      </section>

      <section className="container-page py-8 grid lg:grid-cols-12 gap-8 items-start">
        {/* Add a note */}
        <div className="lg:col-span-5">
          <div className="sticky top-24">
            <AddNote
              topicTitles={topicTitles}
              pending={createM.isPending}
              onAdd={(v) => createM.mutate(v)}
            />
          </div>
        </div>

        {/* Note list */}
        <div className="lg:col-span-7">
          {notesQ.isLoading && (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-20 rounded-3xl border border-border bg-card animate-pulse"
                />
              ))}
            </div>
          )}
          {notesQ.isError && (
            <ErrorState
              message={(notesQ.error as Error)?.message ?? "Could not load notes"}
              onRetry={() => notesQ.refetch()}
            />
          )}
          {notesQ.isSuccess && notes.length === 0 && (
            <div className="rounded-4xl border border-dashed border-border bg-card p-10 text-center">
              <div className="text-4xl">📝</div>
              <h3 className="mt-3 text-xl text-ink">No notes yet</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Add one on the left, or save suggestions straight from the AI coach inside a room.
              </p>
              <Link
                to="/rooms"
                className="mt-4 inline-flex rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground"
              >
                Go to a room
              </Link>
            </div>
          )}
          {notes.length > 0 && (
            <div className="space-y-8">
              {[...groups.entries()].map(([topic, items]) => (
                <div key={topic}>
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-sm font-semibold text-foreground">{topic}</h3>
                    <span className="text-xs text-muted-foreground">({items.length})</span>
                  </div>
                  <div className="space-y-3">
                    {items.map((n) => (
                      <NoteRow
                        key={n.id}
                        note={n}
                        topicTitles={topicTitles}
                        onSave={(improved_text, t) =>
                          updateM.mutate({ id: n.id, improved_text, topic: t })
                        }
                        onDelete={() => deleteM.mutate(n.id)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function AddNote({
  topicTitles,
  pending,
  onAdd,
}: {
  topicTitles: string[];
  pending: boolean;
  onAdd: (v: {
    original_text: string | null;
    improved_text: string | null;
    topic: string | null;
    source: string;
  }) => void;
}) {
  const [original, setOriginal] = useState("");
  const [improved, setImproved] = useState("");
  const [topic, setTopic] = useState("");

  const canSave = original.trim() || improved.trim();

  return (
    <div className="rounded-4xl border border-border bg-card p-6">
      <h3 className="text-lg text-ink">Add a sentence note</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Fill in at least one field. Keep the original and the better version side by side.
      </p>
      <div className="mt-4 space-y-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Original (optional)
          </span>
          <textarea
            value={original}
            onChange={(e) => setOriginal(e.target.value)}
            rows={2}
            placeholder="e.g. I very like travel"
            className="mt-1 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Better sentence
          </span>
          <textarea
            value={improved}
            onChange={(e) => setImproved(e.target.value)}
            rows={2}
            placeholder="e.g. I really like traveling"
            className="mt-1 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Topic</span>
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="mt-1 w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary"
          >
            <option value="">No topic</option>
            {topicTitles.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        disabled={!canSave || pending}
        onClick={() => {
          onAdd({
            original_text: original.trim() || null,
            improved_text: improved.trim() || null,
            topic: topic || null,
            source: "self",
          });
          setOriginal("");
          setImproved("");
        }}
        className="mt-4 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving…" : "Save note"}
      </button>
    </div>
  );
}

function NoteRow({
  note,
  topicTitles,
  onSave,
  onDelete,
}: {
  note: Note;
  topicTitles: string[];
  onSave: (improved: string, topic: string | null) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [improved, setImproved] = useState(note.improved_text ?? "");
  const [topic, setTopic] = useState(note.topic ?? "");

  if (editing) {
    return (
      <div className="rounded-3xl border border-primary/40 bg-card p-4">
        <textarea
          value={improved}
          onChange={(e) => setImproved(e.target.value)}
          rows={2}
          className="w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs focus:outline-none focus:border-primary"
          >
            <option value="">No topic</option>
            {topicTitles.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => {
                onSave(improved.trim(), topic || null);
                setEditing(false);
              }}
              className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-3xl border border-border bg-card p-4">
      {note.original_text && (
        <p className="text-sm text-muted-foreground line-through decoration-muted-foreground/40">
          {note.original_text}
        </p>
      )}
      {note.improved_text && (
        <p className="mt-1 text-sm text-foreground font-medium">{note.improved_text}</p>
      )}
      <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="rounded-full bg-muted px-2 py-0.5 uppercase tracking-wider">
          {note.source}
        </span>
        <div className="ml-auto flex gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => setEditing(true)} className="hover:text-foreground">
            Edit
          </button>
          <button onClick={onDelete} className="hover:text-destructive">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
