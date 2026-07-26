import { apiClient } from "./client";
import type { AssistInput, AssistResult } from "../types";

// In-room AI coach: improve a sentence or suggest a reply (PRD §8.8).
export function assist(input: AssistInput): Promise<AssistResult> {
  return apiClient.post<AssistResult>("/assist", input);
}
