import Constants from "expo-constants";

// STUN lets peers discover their public address (free, public servers). TURN is a
// relay for restrictive/symmetric NATs — supply one in app.json `extra` for
// production reliability; without it, peer-to-peer still works on most networks.
interface IceServer {
  urls: string | string[];
  username?: string;
  credential?: string;
}

const extra = (Constants.expoConfig?.extra ?? {}) as {
  turnUrl?: unknown;
  turnUsername?: unknown;
  turnCredential?: unknown;
};

// Only accept real string values (a malformed app.json `extra` may hold {}).
const asString = (value: unknown): string | undefined =>
  typeof value === "string" && value.length > 0 ? value : undefined;

const iceServers: IceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];

const turnUrl = asString(extra.turnUrl);
if (turnUrl) {
  iceServers.push({
    urls: turnUrl,
    username: asString(extra.turnUsername),
    credential: asString(extra.turnCredential),
  });
}

export const rtcConfig = { iceServers };
