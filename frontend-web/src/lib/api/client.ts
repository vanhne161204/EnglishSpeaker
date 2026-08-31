// Thin typed fetch wrapper around the EnglishTalker FastAPI backend.
//
// Responsibilities:
//   - resolve the REST/WebSocket base URLs from env (with a sensible dev default),
//   - serialize JSON bodies and query params,
//   - translate the backend's error envelope `{ "error": { code, message } }`
//     into a typed `ApiError` so callers get a useful `.message` and `.status`.

const DEFAULT_API_BASE = "http://127.0.0.1:8000/api/v1";

/** REST base, e.g. `http://127.0.0.1:8000/api/v1`. Override with `VITE_API_BASE_URL`. */
export const API_BASE_URL: string = normalizeBase(
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE,
);

/** WebSocket base derived from the REST base (`http`→`ws`, `https`→`wss`). */
export const WS_BASE_URL: string = API_BASE_URL.replace(/^http/, "ws");

function normalizeBase(url: string): string {
  // Drop a trailing slash so we can join paths with a single leading slash.
  return url.replace(/\/+$/, "");
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type QueryValue = string | number | boolean | null | undefined;

export type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** JSON-serializable body. Omit for GET/DELETE. */
  body?: unknown;
  /** Query-string params; `null`/`undefined` values are skipped. */
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
};

// The session JWT is persisted by `identity.ts` under this localStorage key.
// We read it directly (rather than importing identity) to avoid a circular
// import, and send it as a Bearer token so the backend can authenticate the
// user and authorize admin-only endpoints. Guests have no token → no header.
const IDENTITY_STORAGE_KEY = "et_user";

/** The stored session JWT, or null. Exported because WebSocket URLs must carry
 *  it as a query parameter — a browser cannot set headers on a WS handshake. */
export function authToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(IDENTITY_STORAGE_KEY);
    return raw ? ((JSON.parse(raw) as { token?: string }).token ?? null) : null;
  } catch {
    return null;
  }
}

// Called when the server rejects a token we actually sent. `identity.ts`
// registers `logout` here so an expired session clears itself instead of
// leaving the user staring at a page where every action fails. Registration is
// inverted (identity → client, not client → identity) to avoid a circular
// import: identity already imports from this module.
let onUnauthenticated: (() => void) | null = null;

export function setUnauthenticatedHandler(handler: () => void): void {
  onUnauthenticated = handler;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/**
 * Perform a JSON request against the API. Resolves to the parsed body (typed as
 * `T`), or `undefined` for `204 No Content`. Throws `ApiError` on non-2xx.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const token = authToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const init: RequestInit = { method, signal, headers };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), init);
  } catch (cause) {
    // Network failure / backend unreachable — surface a clear, typed error.
    throw new ApiError(
      "Could not reach the EnglishTalker API. Is the backend running?",
      0,
      "network_error",
    );
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? safeJsonParse(text) : undefined;

  if (!response.ok) {
    // 401 with a token attached means the session is dead — expired, or the
    // account is gone. Drop it so the app falls back to the signed-out state
    // and `<AuthWatcher>` moves the user to /login. A 401 with no token is just
    // an anonymous call to a protected endpoint: nothing to clear.
    //
    // Deliberately not 403: that is "signed in, but not allowed here", which
    // must not log anybody out.
    if (response.status === 401 && token) onUnauthenticated?.();

    const envelope = (data as { error?: { code?: string; message?: string } } | undefined)?.error;
    throw new ApiError(
      envelope?.message ??
        extractValidationMessage(data) ??
        response.statusText ??
        "Request failed",
      response.status,
      envelope?.code ?? (response.status === 422 ? "validation_error" : "http_error"),
    );
  }

  return data as T;
}

/**
 * Pull a readable message out of FastAPI's validation-error body, which uses a
 * different shape than our `{ error: { message } }` envelope:
 *   { "detail": [ { "loc": ["body", "password"], "msg": "String should have…" } ] }
 * `detail` can also be a plain string (from a raw HTTPException). Returns
 * `undefined` if the body isn't a recognizable FastAPI error.
 */
function extractValidationMessage(data: unknown): string | undefined {
  const detail = (data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail) || detail.length === 0) return undefined;
  return detail
    .map((item) => {
      const msg = (item as { msg?: string }).msg ?? "Invalid value";
      // Last path segment is the offending field (skip the "body" prefix).
      const loc = (item as { loc?: (string | number)[] }).loc ?? [];
      const field = loc.filter((p) => p !== "body").pop();
      return field ? `${field}: ${msg}` : msg;
    })
    .join("; ");
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
