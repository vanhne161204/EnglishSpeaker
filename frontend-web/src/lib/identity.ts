// Client-side session state.
//
// Identity comes from **logging in**. There is no guest profile: practising
// (rooms, warm-up, matching) requires an account, because a session produces
// durable data — transcripts, feedback, band reports — that is worthless without
// an owner, and every AI call has to be attributable to cap its cost
// (docs/11_Security.md §11.2).
//
// What is stored here is a cache of the profile plus the session JWT. The server
// never trusts any of it: the token is the only thing that proves who you are,
// and every id in it is re-derived server-side.

import { useEffect, useState, useSyncExternalStore } from "react";
import {
  getMe,
  setUnauthenticatedHandler,
  updateMe,
  type AuthResult,
  type ConversationMode,
  type User,
} from "@/lib/api";

const STORAGE_KEY = "et_user";

// `mode` (normal / incognito) is a client-side preference — the backend User has
// no mode column — so we keep it alongside the cached profile fields. `username`
// is set once the user registers or logs in.
type StoredUser = Pick<
  User,
  "id" | "display_name" | "level" | "interests" | "username" | "is_admin"
> & {
  mode?: ConversationMode;
  // Session JWT from register/login. The API client sends it as a Bearer token,
  // and WebSocket URLs carry it as a query parameter. It is never put in a
  // request body — the server derives identity from it, not from what we claim.
  token?: string;
};

// --- reactive store (so the header reflects login/logout immediately) ---
const listeners = new Set<() => void>();
function notify(): void {
  listeners.forEach((l) => l());
}

function readStored(): StoredUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    return null;
  }
}

// Cached snapshot for `useSyncExternalStore`: it requires a STABLE reference
// between renders (returning a fresh object each call triggers an infinite loop).
// We re-parse only when the underlying localStorage string actually changes.
let snapshotRaw: string | null = null;
let snapshotUser: StoredUser | null = null;

function getSnapshot(): StoredUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === snapshotRaw) return snapshotUser;
  snapshotRaw = raw;
  try {
    snapshotUser = raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    snapshotUser = null;
  }
  return snapshotUser;
}

function writeStored(user: StoredUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  notify();
}

/** The current profile, if one has been created in this browser. */
export function currentUser(): StoredUser | null {
  return readStored();
}

/** Whether the user has logged in with a username/password account. */
export function isLoggedIn(): boolean {
  return !!readStored()?.username;
}

/** Whether the current user is an admin (may manage topics/content). */
export function isAdmin(): boolean {
  return !!readStored()?.is_admin;
}

/** Subscribe to identity changes (login / logout / profile save). */
export function useIdentity(): StoredUser | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getSnapshot,
    () => null, // server snapshot — no identity during SSR
  );
}

/**
 * `false` while rendering on the server and on the very first client paint,
 * `true` once React has hydrated.
 *
 * Identity lives in localStorage, which the server cannot see, so the first
 * paint of any auth-dependent UI would be the signed-out version — a signed-in
 * user would watch "Log in" flash and then swap to their name. Components use
 * this to render a neutral placeholder for that one frame instead of the wrong
 * answer.
 */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}

/**
 * The signed-in profile, refreshed from the server, or `null`.
 *
 * Previously this CREATED an anonymous account when none existed. It no longer
 * can: accounts come from `POST /auth/register`, which requires a password. A
 * caller that gets `null` should send the visitor to `/login`.
 */
export async function ensureUser(): Promise<StoredUser | null> {
  const stored = readStored();
  if (!stored?.token) return null;
  try {
    // Confirms the token is still valid and picks up any server-side change
    // (a plan upgrade, admin being granted or revoked).
    const fresh = await getMe();
    const next: StoredUser = { ...stored, ...fresh };
    writeStored(next);
    return next;
  } catch {
    // Expired, revoked, or the account is gone. Treat it as signed out rather
    // than leaving a stale identity that will fail on every request.
    logout();
    return null;
  }
}

/**
 * Save the signed-in user's profile. `mode` is stored locally only.
 *
 * Throws when nobody is signed in — there is no profile to update, and silently
 * creating one is exactly the guest path this change removed.
 */
export async function saveProfile(input: {
  display_name: string;
  level?: string | null;
  interests?: string | null;
  mode?: ConversationMode;
}): Promise<StoredUser> {
  const existing = await ensureUser();
  if (!existing) throw new Error("Sign in to save your profile.");
  const updated = await updateMe({
    display_name: input.display_name,
    level: input.level ?? null,
    interests: input.interests ?? null,
  });
  const next: StoredUser = {
    id: updated.id,
    display_name: updated.display_name,
    username: updated.username,
    is_admin: updated.is_admin,
    level: updated.level,
    interests: updated.interests,
    mode: input.mode ?? existing.mode,
    // Profile updates don't return a token — keep the existing session JWT.
    token: existing.token,
  };
  writeStored(next);
  return next;
}

/** Adopt the identity returned by register/login as the active profile. */
export function loginWithAuth(result: AuthResult): StoredUser {
  const prev = readStored();
  const next: StoredUser = {
    id: result.user.id,
    display_name: result.user.display_name,
    username: result.user.username,
    is_admin: result.user.is_admin,
    level: result.user.level,
    interests: result.user.interests,
    mode: prev?.mode,
    token: result.token,
  };
  writeStored(next);
  return next;
}

/** Sign out. Clears the cached profile and token from this browser.
 *
 *  NOTE: the token stays valid on the server until it expires — the session is
 *  stateless, so there is nothing to revoke (docs/11_Security.md §11.6). */
export function logout(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  notify();
}

// An expired or revoked token should sign the user out on its own, rather than
// leaving a session where every request 401s. See `setUnauthenticatedHandler`.
setUnauthenticatedHandler(logout);

/** Persist updated profile fields locally (after an API update, or for aliases). */
export function setStoredUser(user: StoredUser): void {
  writeStored(user);
}

const ADJ = ["Quiet", "Sunny", "Brave", "Calm", "Witty", "Lucky", "Swift", "Cozy"];
const NOUN = ["Panda", "Otter", "Falcon", "Tiger", "Koala", "Fox", "Whale", "Cat"];

/** A friendly random guest name, e.g. `QuietPanda42`. */
export function randomGuestName(): string {
  const a = ADJ[Math.floor(Math.random() * ADJ.length)];
  const n = NOUN[Math.floor(Math.random() * NOUN.length)];
  return `${a}${n}${Math.floor(Math.random() * 90) + 10}`;
}
