// Lightweight client identity. The backend has no mandatory auth — a "profile" is
// just a `user_id` created via `POST /users` (see backend docs/08_API.md). We
// create one on first need and persist it in localStorage so the same browser
// keeps the same identity across rooms, joins, and messages.
//
// Username/password login is optional on top of this: registering or logging in
// binds a username to a persistent profile (so it can be restored), and logging
// out clears the device identity. Guests keep full function without ever logging in.

import { useSyncExternalStore } from "react";
import {
  createUser,
  getUser,
  updateUser,
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
  // Session JWT from register/login. Absent for guests (they have no account).
  // Sent as the Bearer token by the API client; kept out of API request bodies.
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
 * Return the existing profile, or create one. Verifies a stored id still exists
 * on the backend (the dev DB may have been reset) and re-creates it if not.
 */
export async function ensureUser(defaults?: {
  display_name?: string;
  level?: string;
  interests?: string;
}): Promise<StoredUser> {
  const stored = readStored();
  if (stored) {
    try {
      await getUser(stored.id);
      return stored;
    } catch {
      // Stored id is stale (e.g. DB reset) — fall through and create a new one.
    }
  }

  const created = await createUser({
    display_name: defaults?.display_name ?? randomGuestName(),
    level: defaults?.level ?? null,
    interests: defaults?.interests ?? null,
  });
  const next: StoredUser = {
    id: created.id,
    display_name: created.display_name,
    username: created.username,
    is_admin: created.is_admin,
    level: created.level,
    interests: created.interests,
    mode: stored?.mode,
  };
  writeStored(next);
  return next;
}

/**
 * Save the user's profile. Creates the backend profile on first run, otherwise
 * PATCHes it. `mode` is stored locally only. Returns the updated stored profile.
 */
export async function saveProfile(input: {
  display_name: string;
  level?: string | null;
  interests?: string | null;
  mode?: ConversationMode;
}): Promise<StoredUser> {
  const existing = await ensureUser();
  const updated = await updateUser(existing.id, {
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

/** Clear the device identity. The next action creates a fresh guest profile. */
export function logout(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  notify();
}

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
