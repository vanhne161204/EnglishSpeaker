// Route guards for pages that need an account (docs/11_Security.md §11.2).
//
// These are a **convenience, not a security boundary**. The real enforcement is
// on the API — every protected endpoint derives identity from the session token
// and returns 401 without one. The guards exist so a visitor gets a login screen
// instead of a page that renders and then fails every request.
//
// Never rely on them for protection: anyone can edit client-side state.
//
// There are two halves, and both are needed:
//
//  1. `requireAuth` in a route's `beforeLoad`. Covers client-side navigation
//     (clicking a link), which is the common case.
//  2. `<AuthWatcher>` in the root layout. Covers what `beforeLoad` cannot: a
//     hard page load. `beforeLoad` runs on the SERVER during SSR, where
//     localStorage does not exist, so it has to let the render through — and it
//     is not re-run on the client after hydration. Without the watcher, opening
//     `/rooms` in a fresh tab shows the page to a signed-out visitor until the
//     first API call 401s. The watcher also handles logging out while sitting on
//     a protected page.

import { redirect } from "@tanstack/react-router";

import { currentUser } from "@/lib/identity";

/** Path prefixes that need a signed-in account. Keep in sync with the routes
 *  that call `requireAuth` — `<AuthWatcher>` reads this list. */
const PROTECTED_PREFIXES = ["/rooms", "/warmup", "/match", "/notes", "/profile", "/admin"];

/** Path prefixes that additionally need the `admin` role. */
const ADMIN_PREFIXES = ["/admin"];

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Whether this path needs an account. */
export function isProtectedPath(pathname: string): boolean {
  return matches(pathname, PROTECTED_PREFIXES);
}

/** Whether this path needs an admin account. */
export function isAdminPath(pathname: string): boolean {
  return matches(pathname, ADMIN_PREFIXES);
}

/**
 * Send anonymous visitors to `/login`, remembering where they were headed.
 *
 * The `next` parameter matters more than it looks: someone who follows a shared
 * room link and is dumped on an unexplained home page usually does not come
 * back. After signing in they should land in the room they were invited to.
 *
 * @param pathname - Where the visitor was going, e.g. `/rooms/abc`.
 */
export function requireAuth(pathname: string): void {
  // During SSR there is no localStorage, so identity is unknowable. Let the page
  // render; `<AuthWatcher>` re-checks on the client once hydration finishes.
  if (typeof window === "undefined") return;

  const user = currentUser();
  if (user?.token) return;

  throw redirect({ to: "/login", search: { next: pathname } });
}

/** Guard for admin-only pages. Same caveat: the API is what actually enforces it. */
export function requireAdmin(pathname: string): void {
  if (typeof window === "undefined") return;

  const user = currentUser();
  if (!user?.token) throw redirect({ to: "/login", search: { next: pathname } });
  // Not an error page: an ordinary user reaching /admin has simply gone
  // somewhere that does not concern them.
  if (user.role !== "admin") throw redirect({ to: "/" });
}
