// Shadowing video lessons, admin side (PRD §8.14 Phase 4).
//
// An admin pastes a YouTube link and the transcript, then marks where each
// sentence starts and ends while the video plays. Nothing is downloaded: the video
// stays on YouTube, and only its id, the sentences and their times are saved.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import {
  adminCreateShadowingVideo,
  adminDeleteShadowingVideo,
  adminSaveVideoSegments,
  adminShadowingVideo,
  adminShadowingVideos,
  adminUpdateShadowingVideo,
  type AdminShadowingVideoDetail,
  type AdminShadowingVideoUpdate,
  type VideoStatus,
} from "@/lib/api";
import { levelLabel, LEVELS } from "@/lib/presentation";
import {
  formatClock,
  parseClock,
  PLAYER_STATE,
  useSegmentPlayback,
  useYouTubePlayer,
  youtubeThumbnail,
} from "@/lib/youtube";

const STATUSES: readonly VideoStatus[] = ["draft", "published", "archived"];

// The server's rules (app/services/shadowing_video.py), checked here first so a
// problem shows on its row instead of as one error after Save.
const MIN_MS = 300;
const MAX_MS = 30_000;
const MAX_WORDS = 40;
const MAX_ROWS = 300;
const NUDGE_MS = 100;

const INPUT =
  "w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:border-primary";

/** One sentence being edited. `id` is null until it has been saved. */
interface Row {
  readonly key: string;
  id: string | null;
  text: string;
  translation: string;
  start: number | null;
  end: number | null;
}

let rowCounter = 0;
const newRowKey = () => `row-${rowCounter++}`;

function rowsFrom(detail: AdminShadowingVideoDetail): Row[] {
  return detail.segments.map((segment) => ({
    key: segment.id,
    id: segment.id,
    text: segment.text,
    translation: segment.translation ?? "",
    start: segment.start_ms,
    end: segment.end_ms,
  }));
}

/** "3:21.2 - 3:22.4 | sentence | meaning" (PRD §8.14 Phase 4). The meaning is optional. */
const TIMED_LINE = /^(\d[\d:.]*)\s*[-–—]\s*(\d[\d:.]*)\s*\|\s*(.+?)\s*(?:\|\s*(.*))?$/;

/** One pasted line: a bare sentence, "sentence | meaning", or the timed form above. */
function parseLine(line: string): Pick<Row, "text" | "translation" | "start" | "end"> {
  const timed = TIMED_LINE.exec(line);
  if (timed) {
    const start = parseClock(timed[1]);
    const end = parseClock(timed[2]);
    if (start !== null && end !== null) {
      return { text: timed[3], translation: (timed[4] ?? "").trim(), start, end };
    }
  }
  const [text, translation = ""] = line.split("|").map((part) => part.trim());
  return { text, translation, start: null, end: null };
}

function rowProblem(row: Row): string | null {
  const words = row.text.trim().split(/\s+/).filter(Boolean).length;
  if (words === 0) return "Type the sentence.";
  if (words > MAX_WORDS) return "At most 40 words.";
  if (row.start === null || row.end === null) return "Mark where it starts and ends.";
  if (row.end - row.start < MIN_MS) return "The end must be at least 0.3 s after the start.";
  if (row.end - row.start > MAX_MS) return "At most 30 seconds.";
  return null;
}

/** No usable start yet: never marked, or stamped with an end that is not after it. */
function needsStart(row: Row): boolean {
  return row.start === null || (row.end !== null && row.end <= row.start);
}

export function ShadowingVideosManager() {
  const [openId, setOpenId] = useState<string | null>(null);
  if (openId) return <VideoEditor key={openId} videoId={openId} onBack={() => setOpenId(null)} />;
  return <VideoList onOpen={setOpenId} />;
}

/* ---------------- the list, and a new lesson ---------------- */

function VideoList({ onOpen }: { onOpen: (id: string) => void }) {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ["admin", "shadowing-videos"],
    queryFn: () => adminShadowingVideos(),
  });
  const [youtube, setYoutube] = useState("");
  const [title, setTitle] = useState("");
  const [level, setLevel] = useState<string>("beginner");
  const [sourceNote, setSourceNote] = useState("");

  const createM = useMutation({
    mutationFn: () =>
      adminCreateShadowingVideo({
        youtube: youtube.trim(),
        title: title.trim(),
        level,
        source_note: sourceNote.trim(),
      }),
    onSuccess: (video) => {
      void qc.invalidateQueries({ queryKey: ["admin", "shadowing-videos"] });
      onOpen(video.id);
    },
  });

  return (
    <div className="grid items-start gap-8 lg:grid-cols-12">
      <div className="lg:col-span-5">
        <div className="sticky top-24 rounded-4xl border border-border bg-card p-6">
          <h3 className="text-lg text-ink">New video lesson</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Real speech for Shadowing. The video stays on YouTube: only its link, your sentences and
            their times are saved.
          </p>
          <div className="mt-4 space-y-3">
            <Field label="YouTube link">
              <input
                value={youtube}
                onChange={(e) => setYoutube(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
                className={INPUT}
              />
            </Field>
            <Field label="Title">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ordering coffee"
                className={INPUT}
              />
            </Field>
            <LevelPicker value={level} onChange={setLevel} />
            <Field label="Source and permission">
              <textarea
                value={sourceNote}
                onChange={(e) => setSourceNote(e.target.value)}
                rows={3}
                placeholder="e.g. Creative Commons BY, channel X — or: our own channel"
                className={`${INPUT} resize-none`}
              />
            </Field>
            <p className="text-xs text-muted-foreground">
              Needed before publishing. Use only videos we may use, and whose owner allows playing
              them on other sites.
            </p>
          </div>
          {createM.isError && (
            <p className="mt-3 text-sm text-destructive">{(createM.error as Error).message}</p>
          )}
          <button
            disabled={!youtube.trim() || !title.trim() || createM.isPending}
            onClick={() => createM.mutate()}
            className="mt-4 w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {createM.isPending ? "Adding…" : "Add and open the editor"}
          </button>
        </div>
      </div>

      <div className="space-y-3 lg:col-span-7">
        {listQ.isLoading && (
          <div className="h-24 animate-pulse rounded-3xl border border-border bg-card" />
        )}
        {listQ.isError && (
          <p className="text-sm text-destructive">{(listQ.error as Error).message}</p>
        )}
        {listQ.isSuccess && listQ.data.length === 0 && (
          <div className="rounded-4xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
            No video lessons yet.
          </div>
        )}
        {(listQ.data ?? []).map((video) => (
          <button
            key={video.id}
            onClick={() => onOpen(video.id)}
            className="flex w-full items-center gap-4 rounded-3xl border border-border bg-card p-3 text-left hover:bg-muted"
          >
            <img
              src={youtubeThumbnail(video.youtube_id)}
              alt=""
              loading="lazy"
              className="aspect-video w-28 flex-none rounded-xl bg-muted object-cover"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium text-ink">{video.title}</div>
              <div className="mt-1 flex flex-wrap gap-2">
                <Pill>{video.status}</Pill>
                <Pill>{levelLabel(video.level)}</Pill>
                <Pill>{video.sentences} sentences</Pill>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------------- the editor ---------------- */

function VideoEditor({ videoId, onBack }: { videoId: string; onBack: () => void }) {
  const qc = useQueryClient();
  const detailKey = ["admin", "shadowing-video", videoId] as const;
  const detailQ = useQuery({ queryKey: detailKey, queryFn: () => adminShadowingVideo(videoId) });
  const detail = detailQ.data;
  const yt = useYouTubePlayer(detail?.youtube_id ?? null);
  const playback = useSegmentPlayback(yt.player);
  const playing = yt.state === PLAYER_STATE.playing;

  const [loaded, setLoaded] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [cursor, setCursor] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [markHint, setMarkHint] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [title, setTitle] = useState("");
  const [level, setLevel] = useState<string>("");
  const [sourceNote, setSourceNote] = useState("");

  // Fill the form once. Later saves hand back their own copy (below), so a status
  // change never wipes sentences that are being edited.
  useEffect(() => {
    if (!detail || loaded) return;
    setRows(rowsFrom(detail));
    setTitle(detail.title);
    setLevel(detail.level ?? "");
    setSourceNote(detail.source_note);
    setLoaded(true);
  }, [detail, loaded]);

  const refreshList = () => void qc.invalidateQueries({ queryKey: ["admin", "shadowing-videos"] });

  const metaM = useMutation({
    mutationFn: (body: AdminShadowingVideoUpdate) => adminUpdateShadowingVideo(videoId, body),
    onSuccess: (saved) => {
      qc.setQueryData(detailKey, saved);
      refreshList();
    },
  });
  const saveM = useMutation({
    mutationFn: () =>
      adminSaveVideoSegments(
        videoId,
        rows.map((row) => ({
          id: row.id ?? undefined,
          start_ms: row.start ?? 0,
          end_ms: row.end ?? 0,
          text: row.text.trim(),
          translation: row.translation.trim() || null,
        })),
      ),
    onSuccess: (saved) => {
      qc.setQueryData(detailKey, saved);
      setRows(rowsFrom(saved));
      setCursor((c) => Math.min(c, Math.max(0, saved.segments.length - 1)));
      setDirty(false);
      refreshList();
    },
  });
  const deleteM = useMutation({
    mutationFn: () => adminDeleteShadowingVideo(videoId),
    onSuccess: () => {
      refreshList();
      onBack();
    },
  });

  const edit = (index: number, patch: Partial<Row>) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setDirty(true);
  };

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
    setCursor((c) => Math.max(0, c > index ? c - 1 : c));
    setDirty(true);
  };

  const addLines = () => {
    const lines = transcript
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length === 0) return;
    setRows((prev) =>
      [...prev, ...lines.map((line) => ({ key: newRowKey(), id: null, ...parseLine(line) }))].slice(
        0,
        MAX_ROWS,
      ),
    );
    setTranscript("");
    setDirty(true);
  };

  const nowMs = () => Math.round(playback.currentMs());

  const clearTimes = () => {
    if (!window.confirm("Clear the start and end of every sentence?")) return;
    setRows((prev) => prev.map((row) => ({ ...row, start: null, end: null })));
    setCursor(0);
    setMarkHint(null);
    setDirty(true);
  };

  // One key per boundary: the first press starts the sentence, the next ends it
  // and starts the one after, so a single pass through the video times them all.
  const mark = useCallback(() => {
    const row = rows[cursor];
    if (!yt.player || !row) return;
    const t = Math.round(playback.currentMs());
    // Before the video has played the player reports 0:00.0, and a press would
    // stamp the sentence with the very start of the video.
    if (!playing && t < 100) {
      setMarkHint("Play the video first, then press M when the sentence starts.");
      return;
    }
    setMarkHint(null);
    const next = rows.map((r) => ({ ...r }));
    if (needsStart(row)) {
      next[cursor].start = t;
      next[cursor].end = null;
    } else {
      next[cursor].end = t;
      const following = next[cursor + 1];
      // The next sentence starts here, unless it was already marked later on.
      if (following && (following.start === null || following.start < t)) {
        following.start = t;
        if (following.end !== null && following.end <= t) following.end = null;
      }
      if (cursor + 1 < rows.length) setCursor(cursor + 1);
    }
    setRows(next);
    setDirty(true);
  }, [rows, cursor, yt.player, playback, playing]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "m" && event.key !== "M") return;
      const target = event.target as HTMLElement | null;
      if (
        target?.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "")
      ) {
        return;
      }
      event.preventDefault();
      mark();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mark]);

  const leave = () => {
    if (dirty && !window.confirm("Leave without saving the sentences?")) return;
    onBack();
  };

  if (detailQ.isLoading) {
    return <div className="h-64 animate-pulse rounded-4xl border border-border bg-card" />;
  }
  if (detailQ.isError || !detail) {
    return (
      <div className="space-y-3">
        <button onClick={onBack} className="text-sm text-muted-foreground hover:text-foreground">
          ← All videos
        </button>
        <p className="text-sm text-destructive">
          {(detailQ.error as Error | null)?.message ?? "Video not found"}
        </p>
      </div>
    );
  }

  const problems = rows.filter((row) => rowProblem(row) !== null).length;
  const current = rows[cursor];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <button onClick={leave} className="text-sm text-muted-foreground hover:text-foreground">
            ← All videos
          </button>
          <h3 className="mt-1 truncate text-2xl text-ink">{detail.title}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Only a published lesson reaches learners (PRD §8.14 Phase 4). */}
          <select
            value={detail.status}
            onChange={(e) => metaM.mutate({ status: e.target.value as VideoStatus })}
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs capitalize focus:outline-none focus:border-primary"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <ConfirmDelete
            onDelete={() => deleteM.mutate()}
            hint="Every learner's tries at it go too."
          />
        </div>
      </div>
      {metaM.isError && (
        <p className="text-sm text-destructive">{(metaM.error as Error).message}</p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-3 lg:col-span-7">
          <div className="relative aspect-video w-full max-w-full overflow-hidden rounded-3xl bg-black">
            <div ref={yt.containerRef} className="absolute inset-0" />
          </div>
          {yt.error && <p className="text-sm text-destructive">{yt.error}</p>}

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={mark}
              disabled={!yt.player || !current}
              className="rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              ⏺ Mark (M)
            </button>
            <button
              onClick={() => (playing ? playback.pause() : yt.player?.playVideo())}
              disabled={!yt.player}
              className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"
            >
              {playing ? "Pause" : "Play"}
            </button>
            <button
              onClick={() => yt.player?.seekTo(Math.max(0, nowMs() - 2000) / 1000, true)}
              disabled={!yt.player}
              className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"
            >
              −2 s
            </button>
            <button
              onClick={clearTimes}
              disabled={rows.length === 0}
              className="rounded-full border border-border px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-muted disabled:opacity-50"
            >
              Clear times
            </button>
            <span className="ml-1 text-sm tabular-nums text-muted-foreground">
              {formatClock(playback.nowMs)}
            </span>
          </div>
          {markHint && <p className="text-xs font-medium text-destructive">{markHint}</p>}
          <p className="text-xs text-muted-foreground">
            {current
              ? `Marking sentence ${cursor + 1}: press Mark at its ${
                  needsStart(current) ? "start" : "end"
                }. `
              : "Add the transcript first. "}
            Pressing at the end of a sentence also starts the next one. Click outside the video
            before pressing M: keys typed into the player go to YouTube.
          </p>
        </div>

        <div className="space-y-4 lg:col-span-5">
          <div className="rounded-4xl border border-border bg-card p-5 space-y-3">
            <Field label="Title">
              <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
            </Field>
            <LevelPicker value={level} onChange={setLevel} />
            <Field label="Source and permission">
              <textarea
                value={sourceNote}
                onChange={(e) => setSourceNote(e.target.value)}
                rows={2}
                className={`${INPUT} resize-none`}
              />
            </Field>
            <button
              disabled={!title.trim() || metaM.isPending}
              onClick={() =>
                metaM.mutate({
                  title: title.trim(),
                  level: level || null,
                  source_note: sourceNote.trim(),
                })
              }
              className="rounded-full border border-border px-4 py-2 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              {metaM.isPending ? "Saving…" : "Save details"}
            </button>
          </div>

          <div className="rounded-4xl border border-border bg-card p-5">
            <Field label="Transcript — one sentence per line">
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                rows={5}
                placeholder={"Hi, can I get a latte, please?\nSure. What size?"}
                className={`${INPUT} resize-y`}
              />
            </Field>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Already timed? Paste <code>start - end | sentence | meaning</code>, e.g.{" "}
              <code>3:21.0 - 3:22.5 | Hi! Are you Anna? | Chào! Bạn là Anna phải không?</code>
            </p>
            <button
              disabled={!transcript.trim()}
              onClick={addLines}
              className="mt-2 rounded-full border border-border px-4 py-2 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              Add as sentences
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {rows.map((row, index) => {
          const problem = rowProblem(row);
          return (
            <div
              key={row.key}
              className={`rounded-3xl border p-3 ${
                index === cursor ? "border-primary bg-primary/5" : "border-border bg-card"
              }`}
            >
              <div className="flex items-start gap-3">
                <button
                  onClick={() => setCursor(index)}
                  title="Mark this sentence next"
                  className="inline-flex h-7 w-7 flex-none items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary"
                >
                  {index + 1}
                </button>
                <div className="min-w-0 flex-1 space-y-2">
                  <input
                    value={row.text}
                    onChange={(e) => edit(index, { text: e.target.value })}
                    className={`${INPUT} font-medium`}
                  />
                  <input
                    value={row.translation}
                    onChange={(e) => edit(index, { translation: e.target.value })}
                    placeholder="Meaning in Vietnamese (optional)"
                    className={`${INPUT} text-xs`}
                  />
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <TimeField
                      label="Start"
                      value={row.start}
                      onChange={(ms) => edit(index, { start: ms })}
                      onNow={() => edit(index, { start: nowMs() })}
                      canNow={!!yt.player}
                    />
                    <TimeField
                      label="End"
                      value={row.end}
                      onChange={(ms) => edit(index, { end: ms })}
                      onNow={() => edit(index, { end: nowMs() })}
                      canNow={!!yt.player}
                    />
                    <button
                      onClick={() => row.start !== null && playback.playRange(row.start, row.end)}
                      disabled={row.start === null || !yt.player}
                      className="rounded-full border border-border px-3 py-1 text-xs font-semibold hover:bg-muted disabled:opacity-50"
                    >
                      ▶ Preview
                    </button>
                    {problem && <span className="text-xs text-destructive">{problem}</span>}
                  </div>
                </div>
                <button
                  onClick={() => removeRow(index)}
                  title="Remove this sentence"
                  aria-label={`Remove sentence ${index + 1}`}
                  className="flex-none rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:border-destructive/40 hover:text-destructive"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
        {rows.length === 0 && (
          <div className="rounded-4xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No sentences yet. Paste the transcript above.
          </div>
        )}
      </div>

      <div className="sticky bottom-4 flex flex-wrap items-center gap-3 rounded-3xl border border-border bg-card p-3 shadow-sm">
        <button
          disabled={!dirty || problems > 0 || saveM.isPending}
          onClick={() => saveM.mutate()}
          className="rounded-full bg-primary px-6 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {saveM.isPending ? "Saving…" : "Save sentences"}
        </button>
        <span className="text-sm text-muted-foreground">
          {rows.length} sentence{rows.length === 1 ? "" : "s"}
          {problems > 0 ? ` · ${problems} to fix` : ""}
          {dirty ? " · unsaved changes" : ""}
        </span>
        {saveM.isError && (
          <span className="text-sm text-destructive">{(saveM.error as Error).message}</span>
        )}
      </div>
    </div>
  );
}

/* ---------------- small parts ---------------- */

/** A time as "m:ss.s": type it, take it from the player, or nudge it by 0.1 s. */
function TimeField({
  label,
  value,
  onChange,
  onNow,
  canNow,
}: {
  label: string;
  value: number | null;
  onChange: (ms: number | null) => void;
  onNow: () => void;
  canNow: boolean;
}) {
  const shown = value === null ? "" : formatClock(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);

  const commit = () => {
    if (!text.trim()) {
      onChange(null);
      return;
    }
    const ms = parseClock(text);
    if (ms === null) setText(shown);
    else onChange(ms);
  };

  return (
    <div className="flex items-center gap-1">
      <span className="w-9 text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        placeholder="0:00.0"
        className="w-20 rounded-xl border border-border bg-background px-2 py-1 text-xs tabular-nums focus:outline-none focus:border-primary"
      />
      <SmallButton title="Take the time from the player" onClick={onNow} disabled={!canNow}>
        ⤓
      </SmallButton>
      <SmallButton
        title="0.1 s earlier"
        onClick={() => value !== null && onChange(Math.max(0, value - NUDGE_MS))}
        disabled={value === null}
      >
        −
      </SmallButton>
      <SmallButton
        title="0.1 s later"
        onClick={() => value !== null && onChange(value + NUDGE_MS)}
        disabled={value === null}
      >
        +
      </SmallButton>
    </div>
  );
}

function SmallButton({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className="h-6 w-6 rounded-full border border-border text-xs hover:bg-muted disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="mt-1">{children}</div>
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
            className={`rounded-full border px-3 py-1.5 text-xs ${
              value === l
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-foreground hover:bg-muted"
            }`}
          >
            {levelLabel(l)}
          </button>
        ))}
      </div>
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
      {children}
    </span>
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
        className="rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground"
      >
        Confirm delete
      </button>
    );
  }
  return (
    <button
      onClick={() => setArmed(true)}
      title={hint}
      className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10"
    >
      Delete
    </button>
  );
}
