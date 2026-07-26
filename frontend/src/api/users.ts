import { apiClient } from "./client";
import type { User, UserInput } from "../types";

export function createUser(input: UserInput): Promise<User> {
  return apiClient.post<User>("/users", input);
}

export function fetchUser(userId: string): Promise<User> {
  return apiClient.get<User>(`/users/${userId}`);
}
