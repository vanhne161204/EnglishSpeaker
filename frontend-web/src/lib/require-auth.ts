// Route guard for pages that need an account (docs/11_Security.md §11.2).
//
// This is a **convenience, not a security boundary**. The real enforcement is on
// the API — every protected endpoint derives identity from the session token and
// returns 401 without one. The guard exists so a visitor gets a login screen
// instead of a page that renders and then fails every request.
//
// Never rely on it for protection: anyone can edit client-side state.

import { redirect } from "@tanstack/react-router";

import { currentUser } from "@/lib/identity";

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
  // render and re-check on the client rather than redirecting everyone to login.
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
  if (!user.is_admin) throw redirect({ to: "/" });
}
