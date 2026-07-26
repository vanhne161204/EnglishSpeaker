// Warm-up question resolution (PRD §8.12 "Warm-up Practice").
//
// Questions come entirely from the database now: each topic carries admin-authored
// `sample_questions` (PRD §8.1), served by the topics API. There is no hardcoded
// question content here — this module only decides WHICH DB questions to show.

import type { Topic } from "@/lib/api";

/** How many questions a "General warm-up" pulls across all topics. */
const GENERAL_QUESTION_LIMIT = 5;

/**
 * Resolve the ordered warm-up questions for a session, using only DB data.
 *
 * - A chosen topic uses its own `sample_questions`.
 * - The "General warm-up" (no topic) takes one question from each available topic,
 *   so it stays varied while remaining fully database-driven.
 *
 * @param topic - The chosen topic, or `null` for a general warm-up.
 * @param allTopics - All topics loaded from the API (used for the general case).
 * @returns The questions to ask one at a time (may be empty if none are authored).
 */
export function resolveWarmupQuestions(
  topic: Topic | null,
  allTopics: readonly Topic[],
): readonly string[] {
  if (topic) return topic.sample_questions ?? [];
  return allTopics
    .flatMap((t) => (t.sample_questions ?? []).slice(0, 1))
    .slice(0, GENERAL_QUESTION_LIMIT);
}
