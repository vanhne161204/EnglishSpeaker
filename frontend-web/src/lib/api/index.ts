// Typed endpoint functions for the EnglishTalker backend. One function per REST
// operation, grouped by resource. UI code should import from here rather than
// calling `apiRequest` directly, so endpoint paths live in a single place.
//
// See backend docs/08_API.md for the full contract.

import { API_BASE_URL, apiRequest, authToken, WS_BASE_URL } from "./client";
import type {
  AbuseReport,
  AdminOverview,
  AdminUser,
  AdminUserPage,
  AdminUserUpdate,
  AiCallPage,
  AiSpendSummary,
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
  AuditEntry,
  ReportCreate,
  ReportMode,
  ReportReview,
  ReportStatus,
  RoomBan,
  UserRole,
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

export { ApiError, API_BASE_URL, WS_BASE_URL, setUnauthenticatedHandler } from "./client";
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
export const getMe = () => apiRequest<User>("/users/me");
export const updateMe = (body: UserUpdate) =>
  apiRequest<User>("/users/me", { method: "PATCH", body });
export const getMySubscription = () => apiRequest<Subscription>("/users/me/subscription");
export const setMySubscription = (plan: PlanTier) =>
  apiRequest<Subscription>("/users/me/subscription", { method: "PUT", body: { plan } });

// ----- Rooms -----
export const listRooms = (filters?: { mode?: ConversationMode; kind?: RoomKind }) =>
  apiRequest<Room[]>("/rooms", { query: filters });
export const getRoom = (id: string) => apiRequest<Room>(`/rooms/${id}`);
export const createRoom = (body: RoomCreate) =>
  apiRequest<Room>("/rooms", { method: "POST", body });

export const joinRoom = (roomId: string, body: { display_name?: string; password?: string } = {}) =>
  apiRequest<Room>(`/rooms/${roomId}/join`, { method: "POST", body });
export const leaveRoom = (roomId: string) =>
  apiRequest<Room>(`/rooms/${roomId}/leave`, { method: "POST" });

/** Owner-only: mute, unmute, or kick a member (PRD §8.3). */
export const moderateRoom = (
  roomId: string,
  body: { target_user_id: string; action: ModerationAction },
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
export const roomSocketUrl = (roomId: string) =>
  `${WS_BASE_URL}/ws/rooms/${roomId}?token=${encodeURIComponent(authToken() ?? "")}`;

/** Build the WebRTC voice-signaling WebSocket URL for a room (PRD §8.3 voice calls). */
export const voiceSocketUrl = (roomId: string, alias?: string) =>
  `${WS_BASE_URL}/ws/voice/${roomId}?token=${encodeURIComponent(authToken() ?? "")}` +
  (alias ? `&name=${encodeURIComponent(alias)}` : "");

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

// ----- Admin panel (docs/11_Security.md 11.9) -----
//
// Every call here is admin-only on the server. The client guard in
// `require-auth.ts` is convenience; these 403 without an admin token.

export const adminOverview = () => apiRequest<AdminOverview>("/admin/overview");

export const adminListUsers = (
  params: {
    q?: string;
    role?: UserRole;
    plan?: string;
    suspended?: boolean;
    limit?: number;
    offset?: number;
  } = {},
) => apiRequest<AdminUserPage>("/admin/users", { query: params });

export const adminUpdateUser = (userId: string, body: AdminUserUpdate) =>
  apiRequest<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body });

export const adminDeleteUser = (userId: string) =>
  apiRequest<void>(`/admin/users/${userId}`, { method: "DELETE" });

export const adminAiSpend = (days = 30, top = 10) =>
  apiRequest<AiSpendSummary>("/admin/ai-spend", { query: { days, top } });

/** The raw ledger behind the summary: one row per AI call, newest first. */
export const adminAiCalls = (
  params: {
    limit?: number;
    offset?: number;
    task?: string;
    user_id?: string;
    failed_only?: boolean;
  } = {},
) => apiRequest<AiCallPage>("/admin/ai-calls", { query: params });

export const adminListReports = (status: ReportStatus | null = "open", limit = 50) =>
  apiRequest<AbuseReport[]>("/admin/reports", { query: { status, limit } });

export const adminReviewReport = (reportId: string, body: ReportReview) =>
  apiRequest<AbuseReport>(`/admin/reports/${reportId}`, { method: "PATCH", body });

export const adminListBans = (limit = 100) =>
  apiRequest<RoomBan[]>("/admin/bans", { query: { limit } });

export const adminLiftBan = (banId: string) =>
  apiRequest<void>(`/admin/bans/${banId}`, { method: "DELETE" });

export const adminAudit = (limit = 100) =>
  apiRequest<AuditEntry[]>("/admin/audit", { query: { limit } });

/** File a report about another learner. Any signed-in user, not just admins. */
export const reportUser = (body: ReportCreate) =>
  apiRequest<AbuseReport>("/moderation/reports", { method: "POST", body });
