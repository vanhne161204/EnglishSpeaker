import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  useRouterState,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { logout, useHydrated, useIdentity } from "../lib/identity";
import { isAdminPath, isProtectedPath } from "../lib/require-auth";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl text-foreground">404</h1>
        <p className="mt-3 text-muted-foreground">This page wandered off mid-sentence.</p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center justify-center rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Back home
        </Link>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-2xl text-foreground">Something broke</h1>
        <p className="mt-2 text-sm text-muted-foreground">Try refreshing the page.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "EnglishTalker — Practice speaking English, every day" },
      {
        name: "description",
        content:
          "Join speaking rooms, match 1-on-1, and improve fluency with an in-room AI coach. Practice English without the fear.",
      },
      { property: "og:title", content: "EnglishTalker — Practice speaking English, every day" },
      {
        property: "og:description",
        content:
          "Join speaking rooms, match 1-on-1, and improve fluency with an in-room AI coach. Practice English without the fear.",
      },
      { property: "og:type", content: "website" },
      { property: "og:site_name", content: "EnglishTalker" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "EnglishTalker — Practice speaking English, every day" },
      {
        name: "twitter:description",
        content:
          "Join speaking rooms, match 1-on-1, and improve fluency with an in-room AI coach. Practice English without the fear.",
      },
      {
        property: "og:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/18f355b1-8b7e-4c0b-a7cf-0eaa121e79de/id-preview-a8719717--6ef75d6a-ccb6-4dfb-b7ad-fe2d602d55d6.lovable.app-1782374440223.png",
      },
      {
        name: "twitter:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/18f355b1-8b7e-4c0b-a7cf-0eaa121e79de/id-preview-a8719717--6ef75d6a-ccb6-4dfb-b7ad-fe2d602d55d6.lovable.app-1782374440223.png",
      },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

// Two navs, because the header answers a different question depending on who is
// looking. A visitor is being sold the product; a signed-in learner is trying to
// get into a room. Showing a visitor links to Rooms / Warm-up / Match only to
// bounce them to /login is the worst of both.
const PUBLIC_NAV = [
  { to: "/", label: "Home" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/topics", label: "Topics" },
  { to: "/pricing", label: "Pricing" },
  { to: "/about", label: "About" },
];

// Profile is deliberately absent: it lives in the account menu, so the same
// thing does not appear twice in one header.
const APP_NAV = [
  { to: "/", label: "Home" },
  { to: "/warmup", label: "Warm-up" },
  { to: "/rooms", label: "Rooms" },
  { to: "/match", label: "Match" },
  { to: "/topics", label: "Topics" },
  { to: "/notes", label: "Notes" },
];

function SiteHeader() {
  const [open, setOpen] = useState(false);
  const identity = useIdentity();
  const hydrated = useHydrated();
  // Before hydration we cannot know who this is, so show the public nav — it is
  // the subset that is correct for everybody.
  const signedIn = hydrated && !!identity?.token;
  const nav = signedIn ? APP_NAV : PUBLIC_NAV;
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
      <div className="container-page flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-display text-xl text-ink">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground font-display text-lg">
            E
          </span>
          EnglishTalker
        </Link>
        <nav className="hidden md:flex items-center gap-1">
          {nav.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              activeOptions={{ exact: n.to === "/" }}
              className="rounded-full px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              activeProps={{
                className: "rounded-full px-4 py-2 text-sm text-foreground bg-muted font-medium",
              }}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="hidden md:flex items-center gap-2">
          <AccountControl />
        </div>
        <button
          onClick={() => setOpen(!open)}
          aria-label="Menu"
          className="md:hidden rounded-full p-2 hover:bg-muted"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
      </div>
      {open && (
        <div className="md:hidden border-t border-border bg-background">
          <div className="container-page py-3 flex flex-col">
            {nav.map((n) => (
              <Link
                key={n.to}
                to={n.to}
                onClick={() => setOpen(false)}
                className="py-2 text-sm text-foreground"
              >
                {n.label}
              </Link>
            ))}
            <MobileAccount onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </header>
  );
}

/** Desktop header account control: a profile chip + menu when signed in, else
 *  "Log in" and a sign-up CTA. Practising requires an account, so the CTA sends
 *  visitors to /login rather than to a room they would be bounced out of. */
function AccountControl() {
  const identity = useIdentity();
  const hydrated = useHydrated();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  // One frame of neutral space instead of a wrong answer: rendering "Log in"
  // here and swapping it for the user's name a moment later is the flicker that
  // makes a signed-in session look signed out.
  if (!hydrated) {
    return <div className="h-9 w-32 rounded-full bg-muted/50" aria-hidden />;
  }

  if (!identity?.token) {
    return (
      <>
        <Link
          to="/login"
          className="rounded-full px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted"
        >
          Log in
        </Link>
        <Link
          to="/login"
          search={{ next: "/rooms" }}
          className="rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-[var(--shadow-soft)] hover:opacity-90"
        >
          Start practicing
        </Link>
      </>
    );
  }

  const initial = identity.display_name.charAt(0).toUpperCase();
  return (
    <>
      <Link
        to="/rooms"
        className="rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-[var(--shadow-soft)] hover:opacity-90"
      >
        Start practicing
      </Link>
      <div
        className="relative"
        onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}
      >
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-1.5 pr-3 text-sm hover:bg-muted"
        >
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            {initial}
          </span>
          <span className="max-w-[120px] truncate font-medium text-foreground">
            {identity.display_name}
          </span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        {open && (
          <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-border bg-card p-1.5 shadow-lg">
            <div className="px-3 py-2">
              <p className="truncate text-sm font-medium text-foreground">
                {identity.display_name}
              </p>
              {identity.username && (
                <p className="truncate text-xs text-muted-foreground">@{identity.username}</p>
              )}
            </div>
            <div className="my-1 h-px bg-border" />
            <Link
              to="/profile"
              onClick={() => setOpen(false)}
              className="block rounded-xl px-3 py-2 text-sm text-foreground hover:bg-muted"
            >
              Edit profile
            </Link>
            <Link
              to="/notes"
              onClick={() => setOpen(false)}
              className="block rounded-xl px-3 py-2 text-sm text-foreground hover:bg-muted"
            >
              My notes
            </Link>
            {identity.is_admin && (
              <Link
                to="/admin"
                onClick={() => setOpen(false)}
                className="block rounded-xl px-3 py-2 text-sm text-foreground hover:bg-muted"
              >
                Admin
              </Link>
            )}
            <button
              onClick={() => {
                setOpen(false);
                logout();
                // Land somewhere that makes sense signed out. `<AuthWatcher>`
                // would eject us from a protected page anyway, but going home
                // deliberately reads as "you logged out", not as a redirect.
                void router.navigate({ to: "/" });
              }}
              className="mt-0.5 block w-full rounded-xl px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10"
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </>
  );
}

/** Mobile menu account row. */
function MobileAccount({ onNavigate }: { onNavigate: () => void }) {
  const identity = useIdentity();
  const hydrated = useHydrated();
  const router = useRouter();

  if (!hydrated) return <div className="mt-2 h-11 rounded-full bg-muted/50" aria-hidden />;

  if (!identity?.token) {
    return (
      <>
        <Link
          to="/login"
          onClick={onNavigate}
          className="mt-2 rounded-full border border-border bg-background px-5 py-2.5 text-center text-sm font-medium text-foreground"
        >
          Log in
        </Link>
        <Link
          to="/login"
          search={{ next: "/rooms" }}
          onClick={onNavigate}
          className="mt-2 rounded-full bg-primary px-5 py-2.5 text-center text-sm font-medium text-primary-foreground"
        >
          Start practicing
        </Link>
      </>
    );
  }
  return (
    <>
      <Link
        to="/profile"
        onClick={onNavigate}
        className="mt-2 flex items-center justify-between rounded-2xl border border-border bg-card px-3 py-2"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-foreground">
            {identity.display_name}
          </span>
          {identity.username && (
            <span className="block truncate text-xs text-muted-foreground">
              @{identity.username}
            </span>
          )}
        </span>
        <span className="flex-none text-xs text-muted-foreground">Edit profile</span>
      </Link>
      <button
        onClick={() => {
          onNavigate();
          logout();
          void router.navigate({ to: "/" });
        }}
        className="mt-2 rounded-full border border-destructive/30 px-5 py-2.5 text-sm font-medium text-destructive"
      >
        Log out
      </button>
    </>
  );
}

/**
 * Keeps the page in sync with who is signed in, on every render path.
 *
 * `beforeLoad` guards cannot do this alone: on a hard page load they run on the
 * server, where localStorage does not exist, and they are not re-run after the
 * client hydrates. This watcher runs in the browser, so it catches both the
 * fresh-tab case and logging out while sitting on a protected page.
 *
 * It is convenience, not security — the API rejects the request either way.
 */
function AuthWatcher() {
  const identity = useIdentity();
  const hydrated = useHydrated();
  const router = useRouter();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    if (!hydrated) return;
    if (!isProtectedPath(pathname)) return;

    if (!identity?.token) {
      // `replace` so the back button does not bounce between the guarded page
      // and the login screen.
      void router.navigate({ to: "/login", search: { next: pathname }, replace: true });
      return;
    }
    if (isAdminPath(pathname) && !identity.is_admin) {
      void router.navigate({ to: "/", replace: true });
    }
  }, [hydrated, identity, pathname, router]);

  return null;
}

function SiteFooter() {
  const identity = useIdentity();
  const hydrated = useHydrated();
  const isAdmin = hydrated && !!identity?.is_admin;
  return (
    <footer className="border-t border-border bg-cream mt-24">
      <div className="container-page py-14 grid gap-10 md:grid-cols-4">
        <div className="md:col-span-2">
          <Link to="/" className="flex items-center gap-2 font-display text-xl text-ink">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground font-display text-lg">
              E
            </span>
            EnglishTalker
          </Link>
          <p className="mt-3 max-w-sm text-sm text-muted-foreground">
            A safe, friendly place to practice English speaking every day — with real people and a
            kind AI coach.
          </p>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-foreground mb-3">Product</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>
              <Link to="/features" className="hover:text-foreground">
                Features
              </Link>
            </li>
            <li>
              <Link to="/topics" className="hover:text-foreground">
                Topics
              </Link>
            </li>
            <li>
              <Link to="/how-it-works" className="hover:text-foreground">
                How it works
              </Link>
            </li>
            <li>
              <Link to="/pricing" className="hover:text-foreground">
                Pricing
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-foreground mb-3">Company</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>
              <Link to="/about" className="hover:text-foreground">
                About
              </Link>
            </li>
            <li>
              <Link to="/safety" className="hover:text-foreground">
                Safety & Privacy
              </Link>
            </li>
            <li>
              <Link to="/contact" className="hover:text-foreground">
                Contact
              </Link>
            </li>
            {/* Only admins can open this page, so only admins should see it —
                for everyone else it was a link that bounced them home. */}
            {isAdmin && (
              <li>
                <Link to="/admin" className="hover:text-foreground">
                  Admin
                </Link>
              </li>
            )}
          </ul>
        </div>
      </div>
      <div className="border-t border-border">
        <div className="container-page py-5 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>© {new Date().getFullYear()} EnglishTalker. Speak more, fear less.</span>
          <span>Made for learners, worldwide.</span>
        </div>
      </div>
    </footer>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <AuthWatcher />
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">
          <Outlet />
        </main>
        <SiteFooter />
      </div>
    </QueryClientProvider>
  );
}
