// Account management (docs/11_Security.md §11.9).
//
// The server enforces every rule this UI hints at — you cannot demote yourself,
// remove the last admin, or suspend your own account. The disabled buttons here
// are a courtesy so the refusal is visible before the click, not the protection.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  adminDeleteUser,
  adminListUsers,
  adminUpdateUser,
  type AdminUser,
  type PlanTier,
  type UserRole,
} from "@/lib/api";
import { useIdentity } from "@/lib/identity";

const PAGE = 25;

export function UsersManager() {
  const qc = useQueryClient();
  const identity = useIdentity();
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<UserRole | "">("");
  const [page, setPage] = useState(0);
  const [confirming, setConfirming] = useState<AdminUser | null>(null);

  const params = {
    q: query.trim() || undefined,
    role: role || undefined,
    limit: PAGE,
    offset: page * PAGE,
  };
  const usersQ = useQuery({
    queryKey: ["admin", "users", params],
    queryFn: () => adminListUsers(params),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["admin"] });
  };

  const updateM = useMutation({
    mutationFn: (v: { id: string; body: Parameters<typeof adminUpdateUser>[1] }) =>
      adminUpdateUser(v.id, v.body),
    onSuccess: refresh,
  });
  const deleteM = useMutation({
    mutationFn: adminDeleteUser,
    onSuccess: () => {
      setConfirming(null);
      refresh();
    },
  });

  const total = usersQ.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder="Search username or display name…"
          className="min-w-[260px] flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:border-primary focus:outline-none"
        />
        <select
          value={role}
          onChange={(e) => {
            setRole(e.target.value as UserRole | "");
            setPage(0);
          }}
          className="rounded-full border border-border bg-background px-4 py-2 text-sm"
        >
          <option value="">All roles</option>
          <option value="admin">Admins</option>
          <option value="user">Users</option>
        </select>
        <span className="text-xs text-muted-foreground">
          {usersQ.isLoading ? "Loading…" : `${total} account${total === 1 ? "" : "s"}`}
        </span>
      </div>

      {(updateM.isError || deleteM.isError) && (
        <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {((updateM.error ?? deleteM.error) as Error).message}
        </p>
      )}

      <div className="overflow-x-auto rounded-4xl border border-border bg-card">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Account</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Plan</th>
              <th className="px-4 py-3 font-medium">Activity</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {usersQ.isSuccess && usersQ.data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  Nobody matches that search.
                </td>
              </tr>
            )}
            {(usersQ.data?.items ?? []).map((u) => (
              <UserRow
                key={u.id}
                user={u}
                isMe={u.id === identity?.id}
                busy={updateM.isPending}
                onChange={(body) => updateM.mutate({ id: u.id, body })}
                onDelete={() => setConfirming(u)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-full border border-border px-4 py-2 disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-muted-foreground">
            Page {page + 1} of {pages}
          </span>
          <button
            disabled={page + 1 >= pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-full border border-border px-4 py-2 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}

      {confirming && (
        <DeleteDialog
          user={confirming}
          busy={deleteM.isPending}
          onCancel={() => setConfirming(null)}
          onConfirm={() => deleteM.mutate(confirming.id)}
        />
      )}
    </div>
  );
}

function UserRow({
  user,
  isMe,
  busy,
  onChange,
  onDelete,
}: {
  user: AdminUser;
  isMe: boolean;
  busy: boolean;
  onChange: (body: {
    role?: UserRole;
    plan?: PlanTier;
    suspended?: boolean;
    suspended_reason?: string;
  }) => void;
  onDelete: () => void;
}) {
  const suspended = user.suspended_at !== null;
  return (
    <tr className={`border-b border-border/60 last:border-0 ${suspended ? "bg-muted/40" : ""}`}>
      <td className="px-4 py-3">
        <div className="font-medium text-foreground">
          {user.display_name}
          {isMe && <span className="ml-2 text-[10px] text-muted-foreground">(you)</span>}
        </div>
        <div className="text-xs text-muted-foreground">@{user.username ?? "—"}</div>
      </td>

      <td className="px-4 py-3">
        <select
          value={user.role}
          disabled={isMe || busy}
          // Changing your own role would leave nobody able to change it back.
          title={isMe ? "You cannot change your own role" : undefined}
          onChange={(e) => onChange({ role: e.target.value as UserRole })}
          className="rounded-full border border-border bg-background px-3 py-1 text-xs disabled:opacity-50"
        >
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
      </td>

      <td className="px-4 py-3">
        <select
          value={user.plan}
          disabled={busy}
          onChange={(e) => onChange({ plan: e.target.value as PlanTier })}
          className="rounded-full border border-border bg-background px-3 py-1 text-xs disabled:opacity-50"
        >
          <option value="free">Free</option>
          <option value="premium">Premium</option>
        </select>
      </td>

      <td className="px-4 py-3 text-xs text-muted-foreground">
        <div>{user.lines_spoken} spoken</div>
        <div>{user.messages_sent} typed</div>
      </td>

      <td className="px-4 py-3">
        {suspended ? (
          <span
            className="rounded-full bg-destructive/10 px-2.5 py-1 text-[11px] font-semibold text-destructive"
            title={user.suspended_reason ?? undefined}
          >
            Suspended
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Active</span>
        )}
        {user.reports_against > 0 && (
          <div className="mt-1 text-[11px] text-amber-700 dark:text-amber-500">
            {user.reports_against} report{user.reports_against === 1 ? "" : "s"}
          </div>
        )}
      </td>

      <td className="px-4 py-3">
        <div className="flex justify-end gap-2">
          {suspended ? (
            <button
              disabled={busy}
              onClick={() => onChange({ suspended: false })}
              className="rounded-full border border-border px-3 py-1 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              Unsuspend
            </button>
          ) : (
            <button
              disabled={isMe || busy}
              title={isMe ? "You cannot suspend your own account" : undefined}
              onClick={() => {
                const reason = window.prompt("Why is this account being suspended?");
                if (reason === null) return; // cancelled
                onChange({ suspended: true, suspended_reason: reason });
              }}
              className="rounded-full border border-border px-3 py-1 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              Suspend
            </button>
          )}
          <button
            disabled={isMe || busy}
            onClick={onDelete}
            title={isMe ? "You cannot delete your own account here" : undefined}
            className="rounded-full border border-destructive/30 px-3 py-1 text-xs font-semibold text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  );
}

/**
 * Deleting an account is permanent and cascades to that person's notes,
 * transcripts and reports. Typing the username is the point: an "Are you sure?"
 * that everyone clicks through protects nobody.
 */
function DeleteDialog({
  user,
  busy,
  onCancel,
  onConfirm,
}: {
  user: AdminUser;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const expected = user.username ?? user.display_name;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-3xl border border-border bg-card p-6 shadow-2xl">
        <h3 className="text-lg text-ink">Delete @{expected}?</h3>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          This removes the account and everything attached to it — saved notes, transcripts and
          coach reports. It cannot be undone.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          Suspending is reversible and is almost always what you want instead.
        </p>

        <label className="mt-5 block">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Type <span className="font-semibold text-foreground">{expected}</span> to confirm
          </span>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoFocus
            className="mt-1 w-full rounded-2xl border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
          />
        </label>

        <div className="mt-5 flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 rounded-full border border-border px-4 py-2.5 text-sm font-semibold hover:bg-muted"
          >
            Cancel
          </button>
          <button
            disabled={typed !== expected || busy}
            onClick={onConfirm}
            className="flex-1 rounded-full bg-destructive px-4 py-2.5 text-sm font-semibold text-destructive-foreground hover:opacity-90 disabled:opacity-40"
          >
            {busy ? "Deleting…" : "Delete forever"}
          </button>
        </div>
      </div>
    </div>
  );
}
