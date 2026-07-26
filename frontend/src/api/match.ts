import { apiClient } from "./client";
import type { MatchInput, Room } from "../types";

// A match resolves to a room to join.
export function matchOne(input: MatchInput): Promise<Room> {
  return apiClient.post<Room>("/match/one", input);
}

export function randomMatch(input: MatchInput): Promise<Room> {
  return apiClient.post<Room>("/match/random", input);
}
