export type ConversationMode = "normal" | "incognito";

// A 1-on-1 is just a room that seats two — group and 1-on-1 share one model.
export type RoomKind = "group" | "one_on_one";

export interface Topic {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  level: string | null;
  status: string;
}

export interface Room {
  id: string;
  title: string;
  mode: ConversationMode;
  kind: RoomKind;
  topic: string | null;
  level: string | null;
  status: string;
  capacity: number;
  participant_count: number;
  created_at: string;
}

export interface SentenceNote {
  id: string;
  original_text: string | null;
  improved_text: string | null;
  source: string;
  topic: string | null;
  created_at: string;
}

export interface NoteInput {
  original_text?: string;
  improved_text?: string;
  source?: string;
  topic?: string;
}

export interface User {
  id: string;
  display_name: string;
  level: string | null;
  interests: string | null;
  created_at: string;
}

export interface UserInput {
  display_name: string;
  level?: string;
  interests?: string;
}

export interface Message {
  id: string;
  room_id: string;
  user_id: string;
  sender_name: string;
  text: string;
  created_at: string;
}

export interface MatchInput {
  mode: ConversationMode;
  topic?: string;
  level?: string;
}

export type AssistKind = "improve" | "reply";

export interface AssistInput {
  kind: AssistKind;
  text?: string;
  context?: string;
}

export interface AssistResult {
  suggestion: string;
  kind: AssistKind;
  provider: string;
}

export interface TranslateInput {
  text: string;
  target_lang: string;
  source_lang?: string;
}

export interface TranslateResult {
  translated_text: string;
  target_lang: string;
  provider: string;
}
