// Warm-up question resolution (PRD §8.12 "Warm-up Practice").
//
// Questions come entirely from the database: each topic's published documentation
// carries them in its `questions` sections (PRD §8.2), served flat by
// `GET /questions`. There is no hardcoded question content here — this module only
// decides WHICH database questions to show.

import type { Topic, TopicQuestion } from "@/lib/api";

/** How many questions a "General warm-up" pulls across all topics. */
const GENERAL_QUESTION_LIMIT = 5;

/**
 * Resolve the ordered warm-up questions for a session, using only database data.
 *
 * - A chosen topic uses that topic's own questions.
 * - The "General warm-up" (no topic) takes the first question from each topic, so
 *   it stays varied while remaining fully database-driven.
 *
 * @param topic - The chosen topic, or `null` for a general warm-up.
 * @param allQuestions - The flat question feed from `GET /questions`, already
 *   ordered by topic and then by the admin's section/question order.
 * @returns The questions to ask one at a time (may be empty if none are authored).
 */
export function resolveWarmupQuestions(
  topic: Topic | null,
  allQuestions: readonly TopicQuestion[],
): readonly TopicQuestion[] {
  if (topic) return allQuestions.filter((q) => q.topic_id === topic.id);

  const picked: TopicQuestion[] = [];
  const seenTopics = new Set<string>();
  for (const question of allQuestions) {
    if (seenTopics.has(question.topic_id)) continue;
    seenTopics.add(question.topic_id);
    picked.push(question);
    if (picked.length === GENERAL_QUESTION_LIMIT) break;
  }
  return picked;
}
