// Wire types for the EnglishTalker backend (FastAPI). These mirror the Pydantic
// response/request schemas in backend/app/schemas. Keep them in sync with the
// API; the source of truth is the OpenAPI doc at `${API_BASE_URL}/openapi.json`.

export type ConversationMode = "normal" | "incognito";
export type RoomKind = "group" | "one_on_one";
export type AssistKind = "improve" | "reply";
export type PlanTier = "free" | "premium";
export type DocumentKind =
  | "explanation"
  | "example"
  | "vocabulary"
  | "mistake"
  | "tip"
  | "sample_answer";

// ----- Topics -----
export type Topic = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  level: string | null;
  status: string;
  /** Admin-authored Warm-up questions (PRD §8.1); empty if none added. */
  sample_questions: string[];
  created_at: string;
};

export type TopicCreate = {
  slug: string;
  title: string;
  description?: string | null;
  level?: string | null;
  sample_questions?: string[];
};

export type TopicUpdate = {
  slug?: string;
  title?: string;
  description?: string | null;
  level?: string | null;
  status?: string;
  sample_questions?: string[];
};

// ----- Documents (topic learning content) -----
export type TopicDocument = {
  id: string;
  topic_id: string;
  kind: DocumentKind;
  title: string;
  content: string;
  created_at: string;
};

export type DocumentCreate = {
  topic_id: string;
  kind?: DocumentKind;
  title: string;
  content: string;
};

export type DocumentUpdate = {
  kind?: DocumentKind;
  title?: string;
  content?: string;
};

// ----- Rooms -----
export type RoomCreate = {
  title: string;
  mode?: ConversationMode;
  kind?: RoomKind;
  topic?: string | null;
  level?: string | null;
  capacity?: number | null;
  /** The creator's user id; makes them the room owner/host (PRD §8.3). */
  owner_id?: string | null;
};

export type Room = {
  id: string;
  title: string;
  mode: ConversationMode;
  kind: RoomKind;
  topic: string | null;
  level: string | null;
  status: string;
  capacity: number;
  participant_count: number;
  owner_id: string | null;
  created_at: string;
};

// ----- Room owner moderation (PRD §8.3) -----
export type ModerationAction = "mute" | "unmute" | "kick";

export type ModerateResult = {
  ok: boolean;
  action: ModerationAction;
  target_user_id: string;
};

// ----- Users (lightweight profiles) -----
export type User = {
  id: string;
  display_name: string;
  username: string | null;
  is_admin: boolean;
  phone: string | null;
  level: string | null;
  interests: string | null;
  plan: string;
  created_at: string;
};

// ----- Auth (optional username/password login) -----
export type AuthResult = {
  user: User;
  token: string;
};

export type UserCreate = {
  display_name: string;
  level?: string | null;
  interests?: string | null;
};

export type UserUpdate = {
  display_name?: string;
  level?: string | null;
  interests?: string | null;
};

// ----- Messages -----
export type Message = {
  id: string;
  room_id: string;
  user_id: string;
  sender_name: string;
  text: string;
  created_at: string;
};

// ----- Translation -----
export type TranslateRequest = {
  text: string;
  target_lang?: string;
  source_lang?: string | null;
};

export type TranslateResult = {
  translated_text: string;
  target_lang: string;
  provider: string;
};

// ----- AI conversation help -----
export type AssistRequest = {
  kind: AssistKind;
  text?: string;
  context?: string | null;
  topic_id?: string | null;
};

export type AssistResult = {
  suggestion: string;
  kind: AssistKind;
  provider: string;
};

// ----- Matchmaking -----
export type MatchRequest = {
  mode?: ConversationMode;
  topic?: string | null;
  level?: string | null;
  interest?: string | null;
};

// ----- Sentence notes -----
export type Note = {
  id: string;
  original_text: string | null;
  improved_text: string | null;
  source: string;
  topic: string | null;
  created_at: string;
};

export type NoteCreate = {
  original_text?: string | null;
  improved_text?: string | null;
  source?: string;
  topic?: string | null;
};

export type NoteUpdate = {
  original_text?: string | null;
  improved_text?: string | null;
  source?: string;
  topic?: string | null;
};

// ----- Subscription -----
export type PlanLimits = {
  ai_suggestions_per_day: number | null;
  max_saved_notes: number | null;
  max_topics: number | null;
};

export type Subscription = {
  plan: PlanTier;
  limits: PlanLimits;
};

// ----- Speech-to-Text -----
export type TranscriptionResult = {
  text: string;
  language: string | null;
  provider: string;
};
