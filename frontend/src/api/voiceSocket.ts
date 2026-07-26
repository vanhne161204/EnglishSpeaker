import { env } from "../config/env";

export interface PeerInfo {
  id: string;
  name: string;
}

// Frames the signaling server sends down. `data` carries SDP / ICE payloads,
// which are opaque here and handed straight to the WebRTC APIs.
export type SignalingMessage =
  | { type: "peers"; peers: PeerInfo[] }
  | { type: "peer-joined"; peer: PeerInfo }
  | { type: "peer-left"; peer: { id: string } }
  | { type: "offer"; from: string; data: unknown }
  | { type: "answer"; from: string; data: unknown }
  | { type: "ice-candidate"; from: string; data: unknown };

// Frames we send up — always targeted at one peer.
export interface OutgoingSignal {
  type: "offer" | "answer" | "ice-candidate";
  to: string;
  data: unknown;
}

/** WebSocket client for a room's WebRTC signaling channel. */
export class VoiceSocket {
  private ws: WebSocket | null = null;

  constructor(
    private readonly roomId: string,
    private readonly userId: string,
    private readonly name: string,
    private readonly onMessage: (message: SignalingMessage) => void,
    private readonly onClose?: () => void,
  ) {}

  connect(): void {
    const params = new URLSearchParams({ user_id: this.userId, name: this.name });
    this.ws = new WebSocket(`${env.wsBaseUrl}/ws/voice/${this.roomId}?${params.toString()}`);
    this.ws.onclose = () => this.onClose?.();
    this.ws.onmessage = (e) => {
      try {
        this.onMessage(JSON.parse(e.data as string) as SignalingMessage);
      } catch {
        // Ignore malformed frames rather than tearing down the call.
      }
    };
  }

  send(signal: OutgoingSignal): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(signal));
    }
  }

  close(): void {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
