import { apiClient } from "./client";
import type { ConversationMode, Room, RoomKind } from "../types";

export function fetchRooms(mode: ConversationMode, kind?: RoomKind): Promise<Room[]> {
  const params = new URLSearchParams({ mode });
  if (kind) params.set("kind", kind);
  return apiClient.get<Room[]>(`/rooms?${params.toString()}`);
}

export function fetchRoom(roomId: string): Promise<Room> {
  return apiClient.get<Room>(`/rooms/${roomId}`);
}

export function joinRoom(roomId: string, userId: string, displayName?: string): Promise<Room> {
  return apiClient.post<Room>(`/rooms/${roomId}/join`, {
    user_id: userId,
    display_name: displayName,
  });
}

export function leaveRoom(roomId: string, userId: string): Promise<Room> {
  return apiClient.post<Room>(`/rooms/${roomId}/leave`, { user_id: userId });
}
