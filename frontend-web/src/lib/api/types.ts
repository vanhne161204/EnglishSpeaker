// Wire types for the EnglishTalker backend (FastAPI). These mirror the Pydantic
// response/request schemas in backend/app/schemas. Keep them in sync with the
// API; the source of truth is the OpenAPI doc at `${API_BASE_URL}/openapi.json`.

export type ConversationMode = "normal" | "incognito";
export type RoomKind = "group" | "one_on_one";
/** What kind of help the learner is asking for (docs/10_AI_Design.md §10.2).
 *  `improve`/`reply` are the original two; the rest are the "I'm stuck" modes —
 *  `say_this` turns the learner's own idea (often Vietnamese) into English. */
export type AssistKind = "improve" | "reply" | "answer" | "ask" | "say_this";
export type PlanTier = "free" | "premium";
/** Publication state of admin-authored content (PRD §8.1/§8.2). */
export type ContentStatus = "draft" | "published" | "archived";
/** What a doc section holds, and therefore how it renders (PRD §8.2). */
export type DocSectionType = "vocabulary" | "phrases" | "questions" | "tips" | "text";

// ----- Categories (topic grouping, PRD §8.1) -----
export type Category = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  icon_url: string | null;
  sort_order: number;
  created_at: string;
};

export type CategoryCreate = {
  name: string;
  slug: string;
  description?: string | null;
  icon_url?: string | null;
  sort_order?: number;
};

export type CategoryUpdate = {
  name?: string;
  description?: string | null;
  icon_url?: string | null;
  sort_order?: number;
};

// ----- Topics -----
export type Topic = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  level: string | null;
  status: string;
  /** Grouping category, or `null` for an ungrouped topic (shown under "Other"). */
  category_id: string | null;
  cover_image_url: string | null;
  sort_order: number;
  created_at: string;
};

export type TopicCreate = {
  slug: string;
  title: string;
  description?: string | null;
  level?: string | null;
  category_id?: string | null;
  cover_image_url?: string | null;
  sort_order?: number;
};

export type TopicUpdate = {
  title?: string;
  description?: string | null;
  level?: string | null;
  status?: string;
  category_id?: string | null;
  cover_image_url?: string | null;
  sort_order?: number;
};

// ----- Topic documentation (PRD §8.2) -----
//
// A topic has one doc. A doc is an ordered list of sections, and a section's
// `type` decides where its content lives:
//   vocabulary | phrases -> `items`
//   questions            -> `questions` (each with `answer_templates`)
//   tips | text          -> `body`

/** A fill-in-the-blank answer the learner can lean on. */
export type AnswerTemplate = {
  id: string;
  question_id: string;
  /** The shape, e.g. "My favourite food is ___." */
  template: string;
  /** The same sentence filled in, e.g. "My favourite food is pizza." */
  example: string | null;
  translation: string | null;
  audio_url: string | null;
  sort_order: number;
};

export type AnswerTemplateCreate = {
  template: string;
  example?: string | null;
  translation?: string | null;
  audio_url?: string | null;
  sort_order?: number;
};

export type AnswerTemplateUpdate = Partial<AnswerTemplateCreate>;

export type Question = {
  id: string;
  section_id: string;
  text: string;
  translation: string | null;
  audio_url: string | null;
  sort_order: number;
  answer_templates: AnswerTemplate[];
};

/** A question flattened with its topic — the shape `GET /questions` returns. */
export type TopicQuestion = Question & {
  topic_id: string;
  topic_title: string;
};

// ----- Simple question-and-answer editing (PRD §8.1) -----
//
// Authoring through the tree takes four calls (doc → section → question →
// answer template). Admins think in plain question/answer pairs, so these back a
// single call that does all four steps. Same storage, flatter door.

/** One question with its sample answer, as an admin types it. */
export type QAPair = {
  text: string;
  /** Blank means "no sample answer yet" — the question is still saved. */
  answer?: string | null;
};

export type QAPairRead = QAPair & {
  id: string;
  sort_order: number;
};

export type QuestionCreate = {
  section_id: string;
  text: string;
  translation?: string | null;
  audio_url?: string | null;
  sort_order?: number;
};

export type QuestionUpdate = Omit<Partial<QuestionCreate>, "section_id">;

/** One word or phrase. Vocabulary and phrases share this shape. */
export type DocItem = {
  id: string;
  section_id: string;
  term: string;
  /** IPA spelling, e.g. "/ˈbrekfəst/". */
  phonetic: string | null;
  meaning: string | null;
  translation: string | null;
  example: string | null;
  audio_url: string | null;
  sort_order: number;
};

export type DocItemCreate = {
  term: string;
  phonetic?: string | null;
  meaning?: string | null;
  translation?: string | null;
  example?: string | null;
  audio_url?: string | null;
  sort_order?: number;
};

export type DocItemUpdate = Partial<DocItemCreate>;

export type DocSection = {
  id: string;
  doc_id: string;
  type: DocSectionType;
  title: string | null;
  /** Used by `tips` and `text` sections; empty for the others. */
  body: string | null;
  sort_order: number;
  items: DocItem[];
  questions: Question[];
};

export type DocSectionCreate = {
  type: DocSectionType;
  title?: string | null;
  body?: string | null;
  sort_order?: number;
};

/** `type` is not editable — changing it would orphan the section's children. */
export type DocSectionUpdate = Omit<Partial<DocSectionCreate>, "type">;

/** A doc without its tree, as returned by list and write endpoints. */
export type DocSummary = {
  id: string;
  topic_id: string;
  title: string | null;
  intro: string | null;
  level: string | null;
  status: ContentStatus;
  created_at: string;
  updated_at: string;
};

export type Doc = DocSummary & {
  sections: DocSection[];
};

export type DocCreate = {
  topic_id: string;
  title?: string | null;
  intro?: string | null;
  level?: string | null;
  status?: ContentStatus;
};

export type DocUpdate = Omit<Partial<DocCreate>, "topic_id">;

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
  /** Optional join password. Omit/empty for a public room. */
  password?: string | null;
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
  /** True if a password is required to join (the password itself is never sent). */
  has_password: boolean;
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
  /** The learner's own text. Required for `improve` and `say_this`. */
  text?: string;
  /** Recent room speech. Used by `reply`, `answer` and `ask`. */
  context?: string | null;
  topic_id?: string | null;
  /** Learner CEFR level (e.g. "A2") so a suggestion is never too hard to say. */
  level?: string | null;
};

export type AssistResult = {
  suggestion: string;
  kind: AssistKind;
  /** Which engine answered: "openai", "anthropic", "stub", or "limit". */
  provider: string;
  /** True when a fallback answered, or a spend cap was hit. Lets the UI soften
   *  instead of presenting a backup as if it were the best available. */
  degraded?: boolean;
};

// ----- Coach Report layer 1 (docs/10_AI_Design.md §10.3) -----
//
// What the AI found in ONE sentence the learner SPOKE. Generated from
// `transcript_segments`, and disposable — the learner keeps what matters by
// saving it to their notes.

export type GrammarError = {
  /** The exact wrong words, quoted from what they said. */
  wrong: string;
  right: string;
  /** e.g. "verb tense", "article", "preposition" — grouped in the summary. */
  kind: string;
  why: string;
};

export type VocabUpgrade = {
  basic: string;
  better: string;
  example: string;
};

export type SentenceFeedback = {
  id: string;
  room_id: string | null;
  segment_id: string | null;
  original_text: string;
  is_correct: boolean;
  /** Null when the sentence was already correct. */
  corrected: string | null;
  natural: string;
  paraphrase: string;
  errors: GrammarError[];
  vocab: VocabUpgrade[];
  cefr: string | null;
  score: number;
  model: string;
  created_at: string;
};

export type MistakeCount = { kind: string; count: number };

/** The "what do I keep getting wrong" view — pure SQL server-side, no AI call. */
export type FeedbackSummary = {
  sentences_checked: number;
  with_errors: number;
  average_score: number;
  top_mistakes: MistakeCount[];
};

// ----- Coach Report layer 2: IELTS bands (docs §10.3.7) -----

export type ReportMode = "conversation" | "ielts_part1" | "ielts_part2" | "ielts_part3";
export type BandCriterion = "fluency" | "lexical" | "grammar" | "pronunciation";

export type CriterionScore = {
  /** Quotes from the LEARNER's own lines — partner quotes are stripped server-side. */
  evidence: string[];
  what_worked: string;
  what_held_back: string;
  descriptor: string;
  band: number;
};

export type Blocker = {
  title: string;
  /** Their own words. */
  example: string;
  /** The same idea, said better. */
  fix: string;
  criterion: BandCriterion;
};

export type Drill = { title: string; how: string; minutes: number };

export type SessionReport = {
  id: string;
  room_id: string | null;
  mode: ReportMode;

  band_fluency: number;
  band_lexical: number;
  band_grammar: number;
  /** Always null for now: no model accepts audio, so it cannot be scored. */
  band_pronunciation: number | null;
  band_overall: number;

  pronunciation_assessed: boolean;
  /** True while `band_overall` averages only three criteria. The UI MUST label
   *  the number when this is set — it is an estimate, not a band. */
  overall_is_estimate: boolean;

  summary: string;
  next_band: number;
  criteria: Record<string, CriterionScore>;
  blockers: Blocker[];
  drills: Drill[];
  metrics: Record<string, number | boolean>;
  model: string;
  quotes_removed: number;
  created_at: string;
};

export type BandPoint = { created_at: string; band_overall: number; mode: ReportMode };

// ----- Matchmaking -----
export type MatchRequest = {
  mode?: ConversationMode;
  topic?: string | null;
  level?: string | null;
  interest?: string | null;
};

// ----- Sentence notes -----
//
// One shape covers both kinds of note (PRD §8.7):
//   correction  — `original_text` (what you said) + `improved_text` (the better version)
//   translation — `original_text` in `source_lang` + `translated_text` in `target_lang`,
//                 saved from the in-room translator as an English/Vietnamese wordbook
// The language codes are what tell them apart.
export type Note = {
  id: string;
  original_text: string | null;
  improved_text: string | null;
  translated_text: string | null;
  source_lang: string | null;
  target_lang: string | null;
  source: string;
  topic: string | null;
  created_at: string;
};

export type NoteCreate = {
  original_text?: string | null;
  improved_text?: string | null;
  translated_text?: string | null;
  source_lang?: string | null;
  target_lang?: string | null;
  source?: string;
  topic?: string | null;
};

export type NoteUpdate = NoteCreate;

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
