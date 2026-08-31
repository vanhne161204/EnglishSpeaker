import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { login, register } from "@/lib/api";
import { loginWithAuth } from "@/lib/identity";

export const Route = createFileRoute("/login")({
  // `next` remembers where the visitor was headed, so a shared room link still
  // lands them in that room after signing in.
  validateSearch: (search: Record<string, unknown>): { next?: string } => {
    const next = typeof search.next === "string" ? search.next : undefined;
    // Only same-site paths: an absolute URL here would be an open redirect,
    // letting an attacker send people to a lookalike site after login.
    return next && next.startsWith("/") && !next.startsWith("//") ? { next } : {};
  },
  head: () => ({
    meta: [
      { title: "Log in — EnglishTalker" },
      {
        name: "description",
        content:
          "Log in or create an account with a username and password to keep your profile and notes across devices. Optional — guests can practice without an account.",
      },
    ],
  }),
  component: LoginPage,
});

type Mode = "login" | "register";

function LoginPage() {
  const navigate = useNavigate();
  const { next } = Route.useSearch();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setErr(null);
    try {
      const res =
        mode === "login"
          ? await login(username.trim(), password)
          : await register(username.trim(), password);
      loginWithAuth(res);
      // Return the visitor to whatever sent them here — a shared room link, a
      // warm-up they clicked — rather than dumping everyone on /profile.
      // `validateSearch` has already rejected anything that is not a local path.
      navigate({ to: next ?? "/profile" });
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const isLogin = mode === "login";

  return (
    <section className="container-page py-16 max-w-md mx-auto">
      <div className="text-center">
        <span className="chip">{isLogin ? "Log in" : "Create account"}</span>
        <h1 className="mt-5 text-4xl sm:text-5xl text-ink">
          {isLogin ? "Welcome back" : "Create your account"}
        </h1>
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
          {isLogin
            ? "Log in to keep your profile and notes across devices. It's optional; you can also just start practicing as a guest."
            : "Pick a username and password. That's it — no email or phone needed."}
        </p>
      </div>

      {/* Mode toggle */}
      <div className="mt-8 grid grid-cols-2 gap-1 rounded-full border border-border bg-muted/40 p-1">
        {(["login", "register"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              setErr(null);
            }}
            className={`rounded-full py-2 text-sm font-semibold transition ${
              mode === m
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {m === "login" ? "Log in" : "Create account"}
          </button>
        ))}
      </div>

      <div className="mt-6 rounded-4xl border border-border bg-card p-8">
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Username
            </span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              placeholder="quietpanda"
              className="mt-1 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Password
            </span>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              placeholder={isLogin ? "Your password" : "At least 8 characters"}
              className="mt-1 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
            />
            {!isLogin && (
              <span className="mt-1 block text-xs text-muted-foreground">
                Use 3–40 letters, numbers, or underscores for the username. Password: 8+ characters.
              </span>
            )}
          </label>
          {err && <p className="text-sm text-destructive">{err}</p>}
          <button
            type="submit"
            disabled={busy || !username.trim() || !password}
            className="w-full rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {busy ? (isLogin ? "Logging in…" : "Creating…") : isLogin ? "Log in" : "Create account"}
          </button>
        </form>
      </div>

      <p className="mt-5 text-center text-xs text-muted-foreground">
        No account needed to practice.{" "}
        <Link to="/rooms" className="text-primary hover:underline">
          Continue as a guest
        </Link>
      </p>
    </section>
  );
}
