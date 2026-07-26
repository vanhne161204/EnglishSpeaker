import { apiClient } from "./client";
import type { Message } from "../types";

// Message history for a room. Live messages arrive over the WebSocket (see socket.ts).
export function fetchMessages(roomId: string): Promise<Message[]> {
  return apiClient.get<Message[]>(`/rooms/${roomId}/messages`);
}
