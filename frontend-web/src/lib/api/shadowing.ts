// Shadowing endpoints (PRD §8.14, docs/08_API.md "Shadowing"). Kept in their own
// file so the resource's types and calls sit together; re-exported from index.ts.

import { API_BASE_URL, ApiError, apiRequest, authToken } from "./client";

export type ShadowingKind = "question" | "answer" | "term" | "example" | "segment";

/** Where a sentence comes from: a topic, or a video lesson (Phase 4). */
export type ShadowingSource = { topicId: string } | { videoId: string };

export type ShadowingItem = {
  /** "<kind>-<uuid>", stable for as long as the source row exists. */
  key: string;
  kind: ShadowingKind;
  text: string;
  translation: string | null;
  /** An admin-attached recording. When null, use `shadowingAudio`. */
  audio_url: string | null;
  best_score: number | null;
  attempts: number;
};

export type ShadowingItemList = {
  topic_id: string;
  topic_title: string;
  level: string | null;
  /** False when the server cannot make model voices: use the browser's voice. */
  voice_enabled: boolean;
  /** Phase 2: whether "Check pronunciation" works, and checks left today. */
  assess_enabled: boolean;
  assess_remaining: number;
  items: ShadowingItem[];
};

export type ShadowingWordStatus = "ok" | "close" | "wrong" | "missed";

export type ShadowingWord = {
  /** The word as written in the sentence. */
  word: string;
  /** What was heard in its place, or null when it was missed. */
  heard: string | null;
  status: ShadowingWordStatus;
  /** The ending left off ("-s", "-ed", "-ing", "-'s"), worked out from spelling. */
  hint?: string | null;
};

export type ShadowingAttemptCreate = {
  /** Exactly one of `topic_id` and `video_id`. */
  topic_id?: string;
  video_id?: string;
  item_key: string;
  heard_text: string;
  /** How long the learner spoke, first to last loud moment. */
  duration_ms: number | null;
  /** How long the model voice is at normal speed. */
  reference_ms: number | null;
  engine: "browser" | "server";
};

export type ShadowingResult = {
  /** Word match 0-100. NOT a pronunciation score. */
  score: number;
  words: ShadowingWord[];
  extra: string[];
  tempo_ratio: number | null;
  tempo: "slow" | "good" | "fast" | null;
  best_score: number;
  attempts: number;
};

export type PronunciationWord = {
  word: string;
  accuracy: number | null;
  /** Azure's terms: "None", "Mispronunciation", "Omission", "Insertion". */
  error: string;
  /** A name or non-English word: shown, but not counted in `accuracy`. */
  is_name: boolean;
};

export type PronunciationResult = {
  /** Mean word accuracy WITHOUT names (0-100). */
  accuracy: number | null;
  fluency: number | null;
  completeness: number | null;
  /** Null when the prosody add-on is off. */
  prosody: number | null;
  words: PronunciationWord[];
  heard: string;
  seconds: number;
  remaining_today: number;
};

/** The sentences to shadow in one topic, with my best score for each. */
export const shadowingItems = (topicId: string) =>
  apiRequest<ShadowingItemList>(`/shadowing/topics/${topicId}/items`);

/** Score one try and keep it. */
export const scoreShadowingAttempt = (body: ShadowingAttemptCreate) =>
  apiRequest<ShadowingResult>("/shadowing/attempts", { method: "POST", body });

function authHeaders(): Record<string, string> {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * The model voice for one sentence, as a WAV Blob.
 *
 * Binary, so it cannot go through `apiRequest` (JSON only); the bearer token is
 * attached the same way. Throws `ApiError`: a 503 means "no model voice — read
 * it with the browser's voice".
 */
export async function shadowingAudio(
  topicId: string,
  key: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch(
    `${API_BASE_URL}/shadowing/topics/${topicId}/items/${encodeURIComponent(key)}/audio`,
    { headers: authHeaders(), signal },
  );
  if (!res.ok) {
    throw new ApiError(`Audio unavailable (${res.status})`, res.status, "audio_unavailable");
  }
  return res.blob();
}

/**
 * Phase 2: a deep pronunciation check by Azure. `wav` must be 16 kHz mono
 * 16-bit (see `toWav16kMono`). Multipart, so it cannot go through `apiRequest`.
 */
export async function assessPronunciation(
  source: ShadowingSource,
  itemKey: string,
  wav: Blob,
): Promise<PronunciationResult> {
  const form = new FormData();
  if ("topicId" in source) form.append("topic_id", source.topicId);
  else form.append("video_id", source.videoId);
  form.append("item_key", itemKey);
  form.append("audio", wav, "take.wav");
  const res = await fetch(`${API_BASE_URL}/shadowing/assess`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const envelope = (data as { error?: { code?: string; message?: string } } | undefined)?.error;
    throw new ApiError(
      envelope?.message ?? `Pronunciation check failed (${res.status})`,
      res.status,
      envelope?.code ?? "http_error",
    );
  }
  return data as PronunciationResult;
}

// ----- Phase 4: video lessons -----

export type ShadowingVideoCard = {
  id: string;
  youtube_id: string;
  title: string;
  level: string | null;
  sentences: number;
  /** How many of its sentences I have tried at least once. */
  practised: number;
};

export type ShadowingSegmentItem = {
  /** "segment-<uuid>". */
  key: string;
  text: string;
  translation: string | null;
  start_ms: number;
  end_ms: number;
  best_score: number | null;
  attempts: number;
};

export type ShadowingVideoLesson = {
  id: string;
  youtube_id: string;
  title: string;
  level: string | null;
  /** Where the video comes from, shown under the player. */
  source_note: string;
  assess_enabled: boolean;
  assess_remaining: number;
  items: ShadowingSegmentItem[];
};

/** Published video lessons, newest first. */
export const shadowingVideos = () => apiRequest<ShadowingVideoCard[]>("/shadowing/videos");

/** One video lesson: its sentences and their times, with my best scores. */
export const shadowingVideoLesson = (videoId: string) =>
  apiRequest<ShadowingVideoLesson>(`/shadowing/videos/${videoId}/items`);

// ----- Phase 4: admin -----

export type VideoStatus = "draft" | "published" | "archived";

export type AdminShadowingVideo = {
  id: string;
  youtube_id: string;
  title: string;
  level: string | null;
  source_note: string;
  status: VideoStatus;
  sentences: number;
  created_at: string;
  updated_at: string;
};

export type AdminVideoSegment = {
  id: string;
  position: number;
  start_ms: number;
  end_ms: number;
  text: string;
  translation: string | null;
};

export type AdminShadowingVideoDetail = AdminShadowingVideo & { segments: AdminVideoSegment[] };

export type AdminVideoSegmentIn = {
  /** Keep it for an existing sentence, so learners' scores on it survive. */
  id?: string;
  start_ms: number;
  end_ms: number;
  text: string;
  translation?: string | null;
};

export type AdminShadowingVideoCreate = {
  /** A YouTube link or the 11-character video id. */
  youtube: string;
  title: string;
  level?: string | null;
  source_note?: string;
};

export type AdminShadowingVideoUpdate = {
  title?: string;
  level?: string | null;
  source_note?: string;
  status?: VideoStatus;
};

const ADMIN_VIDEOS = "/admin/shadowing/videos";

export const adminShadowingVideos = () => apiRequest<AdminShadowingVideo[]>(ADMIN_VIDEOS);
export const adminShadowingVideo = (id: string) =>
  apiRequest<AdminShadowingVideoDetail>(`${ADMIN_VIDEOS}/${id}`);
export const adminCreateShadowingVideo = (body: AdminShadowingVideoCreate) =>
  apiRequest<AdminShadowingVideoDetail>(ADMIN_VIDEOS, { method: "POST", body });
export const adminUpdateShadowingVideo = (id: string, body: AdminShadowingVideoUpdate) =>
  apiRequest<AdminShadowingVideoDetail>(`${ADMIN_VIDEOS}/${id}`, { method: "PATCH", body });
/** Replace the whole list of sentences: one left out is deleted. */
export const adminSaveVideoSegments = (id: string, segments: AdminVideoSegmentIn[]) =>
  apiRequest<AdminShadowingVideoDetail>(`${ADMIN_VIDEOS}/${id}/segments`, {
    method: "PUT",
    body: { segments },
  });
export const adminDeleteShadowingVideo = (id: string) =>
  apiRequest<void>(`${ADMIN_VIDEOS}/${id}`, { method: "DELETE" });
