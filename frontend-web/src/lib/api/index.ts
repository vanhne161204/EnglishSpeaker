// Typed endpoint functions for the EnglishTalker backend. One function per REST
// operation, grouped by resource. UI code should import from here rather than
// calling `apiRequest` directly, so endpoint paths live in a single place.
//
// See backend docs/08_API.md for the full contract.

import { API_BASE_URL, apiRequest, WS_BASE_URL } from "./client";
import type {
  AnswerTemplate,
  AnswerTemplateCreate,
  AnswerTemplateUpdate,
  AssistRequest,
  AssistResult,
  AuthResult,
  Category,
  CategoryCreate,
  CategoryUpdate,
  ConversationMode,
  Doc,
  DocCreate,
  DocItem,
  DocItemCreate,
  DocItemUpdate,
  DocSection,
  DocSectionCreate,
  DocSectionUpdate,
  DocSummary,
  BandPoint,
  DocUpdate,
  FeedbackSummary,
  Message,
  ModerateResult,
  ModerationAction,
  Note,
  NoteCreate,
  NoteUpdate,
  PlanTier,
  QAPair,
  QAPairRead,
  Question,
  QuestionCreate,
  QuestionUpdate,
  Room,
  RoomCreate,
  ReportMode,
  RoomKind,
  SentenceFeedback,
  SessionReport,
  Subscription,
  Topic,
  TopicCreate,
  TopicQuestion,
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

// ----- Categories (topic grouping, PRD §8.1) -----
export const listCategories = () => apiRequest<Category[]>("/categories");
export const createCategory = (body: CategoryCreate) =>
  apiRequest<Category>("/categories", { method: "POST", body });
export const updateCategory = (id: string, body: CategoryUpdate) =>
  apiRequest<Category>(`/categories/${id}`, { method: "PATCH", body });
export const deleteCategory = (id: string) =>
  apiRequest<void>(`/categories/${id}`, { method: "DELETE" });

// ----- Topics -----
export const listTopics = (categoryId?: string) =>
  apiRequest<Topic[]>("/topics", { query: { category_id: categoryId } });
export const getTopic = (id: string) => apiRequest<Topic>(`/topics/${id}`);
/** A topic's documentation with its full tree. Throws a 404 `ApiError` if it has none. */
export const getTopicDoc = (topicId: string) => apiRequest<Doc>(`/topics/${topicId}/doc`);
// Admin-only writes (PRD §9.2); the bearer token is attached by the client.
export const createTopic = (body: TopicCreate) =>
  apiRequest<Topic>("/topics", { method: "POST", body });
export const updateTopic = (id: string, body: TopicUpdate) =>
  apiRequest<Topic>(`/topics/${id}`, { method: "PATCH", body });
export const deleteTopic = (id: string) => apiRequest<void>(`/topics/${id}`, { method: "DELETE" });

// ----- Simple question-and-answer editing (PRD §8.1) -----
//
// `GET` includes questions from a draft doc, so the admin editor loads what is
// really stored. `PUT` replaces the whole list and builds any missing doc or
// section itself — one call instead of four.
export const listTopicQA = (topicId: string) =>
  apiRequest<QAPairRead[]>(`/topics/${topicId}/questions`);
export const saveTopicQA = (topicId: string, items: QAPair[]) =>
  apiRequest<QAPairRead[]>(`/topics/${topicId}/questions`, { method: "PUT", body: { items } });

// ----- Topic documentation (PRD §8.2) -----
export const listDocs = (topicId?: string) =>
  apiRequest<DocSummary[]>("/docs", { query: { topic_id: topicId } });
export const getDoc = (id: string) => apiRequest<Doc>(`/docs/${id}`);
export const createDoc = (body: DocCreate) =>
  apiRequest<DocSummary>("/docs", { method: "POST", body });
export const updateDoc = (id: string, body: DocUpdate) =>
  apiRequest<DocSummary>(`/docs/${id}`, { method: "PATCH", body });
export const deleteDoc = (id: string) => apiRequest<void>(`/docs/${id}`, { method: "DELETE" });

export const createSection = (docId: string, body: DocSectionCreate) =>
  apiRequest<DocSection>(`/docs/${docId}/sections`, { method: "POST", body });
export const updateSection = (id: string, body: DocSectionUpdate) =>
  apiRequest<DocSection>(`/docs/sections/${id}`, { method: "PATCH", body });
export const deleteSection = (id: string) =>
  apiRequest<void>(`/docs/sections/${id}`, { method: "DELETE" });

/** Vocabulary / phrase items. Rejected with a 400 on a non-item section. */
export const createDocItem = (sectionId: string, body: DocItemCreate) =>
  apiRequest<DocItem>(`/docs/sections/${sectionId}/items`, { method: "POST", body });
export const updateDocItem = (id: string, body: DocItemUpdate) =>
  apiRequest<DocItem>(`/docs/items/${id}`, { method: "PATCH", body });
export const deleteDocItem = (id: string) =>
  apiRequest<void>(`/docs/items/${id}`, { method: "DELETE" });

// ----- Questions + answer templates (PRD §8.2, §8.12) -----
/** Questions from *published* docs, flattened with their topic. Powers Warm-up. */
export const listQuestions = (topicId?: string) =>
  apiRequest<TopicQuestion[]>("/questions", { query: { topic_id: topicId } });
export const createQuestion = (body: QuestionCreate) =>
  apiRequest<Question>("/questions", { method: "POST", body });
export const updateQuestion = (id: string, body: QuestionUpdate) =>
  apiRequest<Question>(`/questions/${id}`, { method: "PATCH", body });
export const deleteQuestion = (id: string) =>
  apiRequest<void>(`/questions/${id}`, { method: "DELETE" });

export const createAnswerTemplate = (questionId: string, body: AnswerTemplateCreate) =>
  apiRequest<AnswerTemplate>(`/questions/${questionId}/answers`, { method: "POST", body });
export const updateAnswerTemplate = (id: string, body: AnswerTemplateUpdate) =>
  apiRequest<AnswerTemplate>(`/questions/answers/${id}`, { method: "PATCH", body });
export const deleteAnswerTemplate = (id: string) =>
  apiRequest<void>(`/questions/answers/${id}`, { method: "DELETE" });

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

export const joinRoom = (
  roomId: string,
  body: { user_id: string; display_name?: string; password?: string },
) => apiRequest<Room>(`/rooms/${roomId}/join`, { method: "POST", body });
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
// ----- Coach Report layer 1 (docs/10_AI_Design.md §10.3) -----

/** Grade my own speech from one session. Costs money and takes a few seconds,
 *  so it is triggered by the learner, never automatically. Repeat calls are
 *  free: the server reuses anything it has already graded. */
export const assessRoom = (roomId: string) =>
  apiRequest<SentenceFeedback[]>(`/feedback/rooms/${roomId}`, { method: "POST" });

/** My already-generated report for one session (no AI call). */
export const roomReport = (roomId: string) =>
  apiRequest<SentenceFeedback[]>(`/feedback/rooms/${roomId}`);

export const myFeedback = (limit = 50) =>
  apiRequest<SentenceFeedback[]>("/feedback/me", { query: { limit } });

export const myFeedbackSummary = () => apiRequest<FeedbackSummary>("/feedback/me/summary");

// ----- Coach Report layer 2: IELTS bands (docs §10.3.7) -----

/** Band my speaking in one session. Costs money and takes ~10s. */
export const buildBandReport = (roomId: string, mode: ReportMode = "conversation") =>
  apiRequest<SessionReport>(`/reports/rooms/${roomId}`, { method: "POST", query: { mode } });

/** My stored report for a session, or null. No AI call — free to load on mount. */
export const bandReport = (roomId: string) =>
  apiRequest<SessionReport | null>(`/reports/rooms/${roomId}`);

/** Band over time, oldest first, ready to plot. */
export const bandHistory = (limit = 30) =>
  apiRequest<BandPoint[]>("/reports/me/history", { query: { limit } });

export async function transcribe(audio: Blob, language?: string): Promise<TranscriptionResult> {
  const form = new FormData();
  form.append("audio", audio, "clip.webm");
  if (language) form.append("language", language);
  const res = await fetch(`${API_BASE_URL}/transcribe`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Transcription failed (${res.status})`);
  return (await res.json()) as TranscriptionResult;
}
