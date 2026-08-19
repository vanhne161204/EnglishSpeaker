// ICE servers for room voice (WebRTC NAT traversal).
//
// STUN only tells a peer its own public address. It is enough when both peers
// can reach each other directly — two browsers on one laptop, or two PCs on a
// friendly home network. It is NOT enough for most real cross-device calls:
// mobile carriers (CGNAT), corporate networks and many routers use symmetric
// NAT, where the direct path never opens. Those calls need a TURN relay, which
// forwards the audio through a server both sides can reach.
//
// Symptom when TURN is missing: voice works between two browsers on the same
// machine, and fails between two devices. See docs/DEPLOYMENT.md §10.
//
// Configure via `.env.local` (dev) or the Cloudflare Pages env vars (prod):
//   VITE_TURN_URL=turn:turn.englishspeaker.me:3478
//   VITE_TURN_USERNAME=etturn
//   VITE_TURN_CREDENTIAL=<password>
//
// `VITE_TURN_URL` accepts a comma-separated list so one deployment can offer
// UDP, TCP and TLS transports — networks that block UDP 3478 usually still
// allow TURN over TLS on 443/5349:
//   VITE_TURN_URL=turn:host:3478,turn:host:3478?transport=tcp,turns:host:5349

const asString = (value: unknown): string | undefined =>
  typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;

/** Split the comma-separated `VITE_TURN_URL` into individual TURN URLs. */
function turnUrls(): string[] {
  const raw = asString(import.meta.env.VITE_TURN_URL);
  if (!raw) return [];
  return raw
    .split(",")
    .map((url) => url.trim())
    .filter((url) => url.length > 0);
}

/** ICE server list passed to every `RTCPeerConnection` in a room voice call. */
export function buildIceServers(): RTCIceServer[] {
  // Several public STUN servers: if one is unreachable the others still let the
  // peer discover its public address, so a direct path is tried before relaying.
  const servers: RTCIceServer[] = [
    { urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] },
  ];

  const urls = turnUrls();
  if (urls.length > 0) {
    servers.push({
      // One entry with every transport — the browser tries them in order and
      // keeps whichever the network allows.
      urls,
      username: asString(import.meta.env.VITE_TURN_USERNAME),
      credential: asString(import.meta.env.VITE_TURN_CREDENTIAL),
    });
  }

  return servers;
}

/** True when a TURN relay is configured (needed for reliable cross-device voice). */
export function hasTurnConfigured(): boolean {
  return turnUrls().length > 0;
}
