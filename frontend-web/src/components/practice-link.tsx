// A call-to-action that leads into the app, for use on public marketing pages.
//
// Practising needs an account, so "Start practicing" cannot simply point at
// /rooms: a visitor who clicks it is bounced to /login and loses the thread.
// This sends visitors to the login screen with `next` set, so signing in drops
// them exactly where the button promised.
//
// Signed-in users get the direct link — no detour through a login form they
// don't need.

import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useHydrated, useIdentity } from "@/lib/identity";

export function PracticeLink({
  to = "/rooms",
  className,
  children,
}: {
  /** Where the visitor actually wants to end up. */
  to?: "/rooms" | "/warmup" | "/match";
  className?: string;
  children: ReactNode;
}) {
  const identity = useIdentity();
  const hydrated = useHydrated();

  // Before hydration we don't know who this is, so aim at /login. That is the
  // safe guess in both directions: /login now redirects an already-signed-in
  // visitor straight to `next`, so a member who clicks in that first frame
  // still lands in the right place.
  if (hydrated && identity?.token) {
    return (
      <Link to={to} className={className}>
        {children}
      </Link>
    );
  }

  return (
    <Link to="/login" search={{ next: to }} className={className}>
      {children}
    </Link>
  );
}
