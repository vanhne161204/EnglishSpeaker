import { apiClient } from "./client";
import type { Topic } from "../types";

export function fetchTopics(): Promise<Topic[]> {
  return apiClient.get<Topic[]>("/topics");
}
