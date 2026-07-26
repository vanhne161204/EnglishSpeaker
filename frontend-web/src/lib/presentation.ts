// Purely-cosmetic presentation helpers for backend data. These add no data —
// they just map backend fields (slugs, enum values) to display strings/emoji so
// the UI stays friendly. The source of truth is always the API.

import type { ConversationMode, RoomKind } from "@/lib/api";

// Emoji per topic slug. Falls back to a generic chat bubble for unknown slugs,
// so new backend topics still render without a code change.
const TOPIC_EMOJI: Record<string, string> = {
  "daily-life": "☕",
  travel: "✈️",
  food: "🍜",
  work: "💼",
  school: "🎓",
  "job-interview": "🤝",
  hobbies: "🎨",
  technology: "💻",
  culture: "🌏",
  movies: "🎬",
  debate: "⚖️",
  future: "🌱",
};

/** Emoji for a topic, keyed by slug (preferred) or title. */
export function topicEmoji(slugOrTitle: string | null | undefined): string {
  if (!slugOrTitle) return "💬";
  const key = slugOrTitle.toLowerCase().replace(/\s+/g, "-");
  return TOPIC_EMOJI[key] ?? "💬";
}

/** Title-case a backend level (`"upper-intermediate"` → `"Upper intermediate"`). */
export function levelLabel(level: string | null | undefined): string {
  if (!level) return "Any level";
  return level
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Friendly room-format label from the backend `kind`. */
export function sizeLabel(kind: RoomKind): string {
  return kind === "one_on_one" ? "1-on-1" : "Group";
}

/** Friendly mode label from the backend `mode`. */
export function modeLabel(mode: ConversationMode): string {
  return mode === "incognito" ? "Incognito" : "Normal";
}

/** English levels offered in profile setup and matching (PRD §8.6). */
export const LEVELS = [
  "beginner",
  "elementary",
  "intermediate",
  "upper-intermediate",
  "advanced",
] as const;

/** Interests offered in profile setup and matching (PRD §8.6). */
export const INTERESTS = [
  "Movies",
  "Music",
  "Travel",
  "Business",
  "Games",
  "Sports",
  "Study",
  "Technology",
] as const;

/** Parse a stored comma-separated interests string into a clean list. */
export function parseInterests(raw: string | null | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}
