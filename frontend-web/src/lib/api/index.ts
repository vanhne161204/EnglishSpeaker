// Typed endpoint functions for the EnglishTalker backend. One function per REST
// operation, grouped by resource. UI code should import from here rather than
// calling `apiRequest` directly, so endpoint paths live in a single place.
//
// See backend docs/08_API.md for the full contract.

import { API_BASE_URL, apiRequest, WS_BASE_URL } from "./client";
import type {
  AssistRequest,
  AssistResult,
  AuthResult,
  ConversationMode,
  DocumentCreate,
  DocumentUpdate,
  Message,
  ModerateResult,
  ModerationAction,
  Note,
  NoteCreate,
  NoteUpdate,
  PlanTier,
  Room,
  RoomCreate,
  RoomKind,
  Subscription,
  Topic,
  TopicCreate,
  TopicDocument,
  TopicUpdate,
  TranscriptionResult,
  TranslateRequest,
  TranslateResult,
  User,
  UserCreate,
  UserUpdate,
} from "./types";

export { ApiError, API_BASE_URL, WS_BASE_URL } from "./client";
export type * from "./types";

// ----- System -----
export const getHealth = () =>
  apiRequest<{ status: string; service: string; environment: string }>("/health");

// ----- Auth (optional username/password login) -----
export const register = (username: string, password: string, display_name?: string) =>
  apiRequest<AuthResult>("/auth/register", {
    method: "POST",
    body: { username, password, display_name },
  });
export const login = (username: string, password: string) =>
  apiRequest<AuthResult>("/auth/login", { method: "POST", body: { username, password } });
export const logoutApi = () => apiRequest<{ ok: boolean }>("/auth/logout", { method: "POST" });

// ----- Topics -----
export const listTopics = () => apiRequest<Topic[]>("/topics");
export const getTopic = (id: string) => apiRequest<Topic>(`/topics/${id}`);
// Admin (PRD §9.2) — no auth gate yet, like the rest of the demo API.
export const createTopic = (body: TopicCreate) =>
  apiRequest<Topic>("/topics", { method: "POST", body });
export const updateTopic = (id: string, body: TopicUpdate) =>
  apiRequest<Topic>(`/topics/${id}`, { method: "PATCH", body });
export const deleteTopic = (id: string) => apiRequest<void>(`/topics/${id}`, { method: "DELETE" });

// ----- Documents (topic learning content) -----
export const listDocuments = (topicId?: string) =>
  apiRequest<TopicDocument[]>("/documents", { query: { topic_id: topicId } });
export const createDocument = (body: DocumentCreate) =>
  apiRequest<TopicDocument>("/documents", { method: "POST", body });
export const updateDocument = (id: string, body: DocumentUpdate) =>
  apiRequest<TopicDocument>(`/documents/${id}`, { method: "PATCH", body });
export const deleteDocument = (id: string) =>
  apiRequest<void>(`/documents/${id}`, { method: "DELETE" });

// ----- Users (lightweight profiles) -----
export const createUser = (body: UserCreate) =>
  apiRequest<User>("/users", { method: "POST", body });
export const getUser = (id: string) => apiRequest<User>(`/users/${id}`);
export const updateUser = (id: string, body: UserUpdate) =>
  apiRequest<User>(`/users/${id}`, { method: "PATCH", body });
export const getSubscription = (userId: string) =>
  apiRequest<Subscription>(`/users/${userId}/subscription`);
export const setSubscription = (userId: string, plan: PlanTier) =>
  apiRequest<Subscription>(`/users/${userId}/subscription`, {
    method: "PUT",
    body: { plan },
  });

// ----- Rooms -----
export const listRooms = (filters?: { mode?: ConversationMode; kind?: RoomKind }) =>
  apiRequest<Room[]>("/rooms", { query: filters });
export const getRoom = (id: string) => apiRequest<Room>(`/rooms/${id}`);
export const createRoom = (body: RoomCreate) =>
  apiRequest<Room>("/rooms", { method: "POST", body });

export const joinRoom = (roomId: string, body: { user_id: string; display_name?: string }) =>
  apiRequest<Room>(`/rooms/${roomId}/join`, { method: "POST", body });
export const leaveRoom = (roomId: string, body: { user_id: string }) =>
  apiRequest<Room>(`/rooms/${roomId}/leave`, { method: "POST", body });

/** Owner-only: mute, unmute, or kick a member (PRD §8.3). */
export const moderateRoom = (
  roomId: string,
  body: { owner_id: string; target_user_id: string; action: ModerationAction },
) => apiRequest<ModerateResult>(`/rooms/${roomId}/moderate`, { method: "POST", body });

export const listMessages = (roomId: string) => apiRequest<Message[]>(`/rooms/${roomId}/messages`);
export const sendMessage = (roomId: string, body: { user_id: string; text: string }) =>
  apiRequest<Message>(`/rooms/${roomId}/messages`, { method: "POST", body });

// ----- Matchmaking (both resolve to a Room to join) -----
export const matchOne = (body: {
  mode?: ConversationMode;
  topic?: string;
  level?: string;
  interest?: string;
}) => apiRequest<Room>("/match/one", { method: "POST", body });
export const matchRandom = (body: {
  mode?: ConversationMode;
  topic?: string;
  level?: string;
  interest?: string;
}) => apiRequest<Room>("/match/random", { method: "POST", body });

// ----- Translation -----
export const translate = (body: TranslateRequest) =>
  apiRequest<TranslateResult>("/translate", { method: "POST", body });

// ----- AI conversation help -----
export const assist = (body: AssistRequest) =>
  apiRequest<AssistResult>("/assist", { method: "POST", body });

// ----- Sentence notes -----
export const listNotes = () => apiRequest<Note[]>("/notes");
export const createNote = (body: NoteCreate) =>
  apiRequest<Note>("/notes", { method: "POST", body });
export const updateNote = (id: string, body: NoteUpdate) =>
  apiRequest<Note>(`/notes/${id}`, { method: "PATCH", body });
export const deleteNote = (id: string) => apiRequest<void>(`/notes/${id}`, { method: "DELETE" });

/** Build the live-chat WebSocket URL for a room (`POST /rooms/{id}/join` first). */
export const roomSocketUrl = (roomId: string, userId: string, name: string) =>
  `${WS_BASE_URL}/ws/rooms/${roomId}?user_id=${encodeURIComponent(userId)}&name=${encodeURIComponent(name)}`;

/** Build the WebRTC voice-signaling WebSocket URL for a room (PRD §8.3 voice calls). */
export const voiceSocketUrl = (roomId: string, userId: string, name: string) =>
  `${WS_BASE_URL}/ws/voice/${roomId}?user_id=${encodeURIComponent(userId)}&name=${encodeURIComponent(name)}`;

/** Transcribe recorded audio (multipart). Powered by faster-whisper, else a stub. */
export async function transcribe(audio: Blob, language?: string): Promise<TranscriptionResult> {
  const form = new FormData();
  form.append("audio", audio, "clip.webm");
  if (language) form.append("language", language);
  const res = await fetch(`${API_BASE_URL}/transcribe`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Transcription failed (${res.status})`);
  return (await res.json()) as TranscriptionResult;
}
