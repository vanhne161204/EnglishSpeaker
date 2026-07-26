import { env } from "../config/env";
import type { Message } from "../types";

// Frames the server pushes over the room socket.
export type RoomEvent =
  | { type: "message"; message: Message }
  | { type: "presence"; event: "join" | "leave"; name: string }
  | { type: "error"; message: string };

export interface RoomSocketHandlers {
  onEvent: (event: RoomEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

/**
 * Thin wrapper over the native WebSocket for one room. Sending and receiving
 * both go through here so screens never touch the raw socket.
 */
export class RoomSocket {
  private ws: WebSocket | null = null;

  constructor(
    private readonly roomId: string,
    private readonly userId: string,
    private readonly name: string,
    private readonly handlers: RoomSocketHandlers,
  ) {}

  connect(): void {
    const params = new URLSearchParams({ user_id: this.userId, name: this.name });
    this.ws = new WebSocket(`${env.wsBaseUrl}/ws/rooms/${this.roomId}?${params.toString()}`);

    this.ws.onopen = () => this.handlers.onOpen?.();
    this.ws.onclose = () => this.handlers.onClose?.();
    this.ws.onmessage = (e) => {
      try {
        this.handlers.onEvent(JSON.parse(e.data as string) as RoomEvent);
      } catch {
        // Ignore malformed frames rather than crashing the chat.
      }
    };
  }

  send(text: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ text }));
    }
  }

  close(): void {
    // Drop handlers first so a normal teardown doesn't fire onClose into a gone screen.
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
