import Constants from "expo-constants";
import { Platform } from "react-native";

// Android emulators reach the host machine via 10.0.2.2; iOS simulators use localhost.
const defaultHost = Platform.OS === "android" ? "10.0.2.2" : "localhost";

// Only honour a real string override; ignore null/{}/undefined so a malformed
// app.json `extra` can never turn the base URL into "[object Object]".
const raw = (Constants.expoConfig?.extra as { apiBaseUrl?: unknown } | undefined)?.apiBaseUrl;
const configured = typeof raw === "string" && raw.length > 0 ? raw : undefined;

const apiBaseUrl = configured ?? `http://${defaultHost}:8000/api/v1`;

export const env = {
  apiBaseUrl,
  // Same host/prefix as the REST API, but ws:// (or wss:// when served over TLS).
  wsBaseUrl: apiBaseUrl.replace(/^http/, "ws"),
};
