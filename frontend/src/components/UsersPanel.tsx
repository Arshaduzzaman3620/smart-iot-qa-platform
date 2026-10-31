import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, createUser, deleteUser, fetchUsers, updateUser } from "../api";
import { formatRelative } from "../format";
import type { Role, User } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { CheckIcon, PlusIcon, TrashIcon } from "./Icons";
import { useToast } from "./Toast";

const ROLES: Role[] = ["VIEWER", "OPERATOR", "ADMIN"];
const ROLE_HINT: Record<Role, string> = {
  VIEWER: "can look at everything",
  OPERATOR: "can also send commands and update firmware",
  ADMIN: "can also upload firmware and manage users",
};

interface Props {
  currentUser: string;
  now: number;
  onAuthError: (err: AuthError) => void;
}

/** Accounts and their roles (ADMIN only; the API enforces that too). */
export function UsersPanel({ currentUser, now, onAuthError }: Props) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  // Role chosen for each pending sign-up before approving it.
  const [approveAs, setApproveAs] = useState<Record<string, Role>>({});
  const [role, setRole] = useState<Role>("VIEWER");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const toast = useToast();

  useEffect(() => {
    const controller = new AbortController();
    fetchUsers(controller.signal)
      .then(setUsers)
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return onAuthError(err);
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      });
    return () => controller.abort();
  }, [reload, onAuthError]);

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast(done);
      setReload((n) => n + 1);
      return true;
    } catch (err) {
      if (err instanceof AuthError) onAuthError(err);
      else setError(err instanceof ApiError ? err.message : "Unexpected error");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const name = username.trim();
    if (await run(() => createUser(name, password, role, email.trim() || undefined), `User ${name} created as ${role}`)) {
      setUsername("");
      setPassword("");
      setEmail("");
      setRole("VIEWER");
    }
  }

  async function remove(name: string) {
    setConfirm(null);
    const pendingUser = users?.find((u) => u.username === name)?.status === "PENDING";
    await run(() => deleteUser(name), pendingUser ? `Sign-up from ${name} rejected` : `User ${name} deleted`);
  }

  function approve(name: string) {
    const as = approveAs[name] ?? "VIEWER";
    run(() => updateUser(name, { status: "ACTIVE", role: as }), `${name} approved as ${as}`);
  }

  function changeRole(name: string, next: Role) {
    run(() => updateUser(name, { role: next }), `${name} is now ${next}`);
  }

  const pending = users?.filter((u) => u.status === "PENDING") ?? [];
  const active = users?.filter((u) => u.status !== "PENDING") ?? [];

  return (
    <section className="panel" aria-labelledby="users-heading" data-testid="users-panel">
      <div className="panel-head">
        <h2 id="users-heading">Users</h2>
        <span className="meta">
          {users ? `${active.length} accounts` : "Loading…"}
          {pending.length > 0 && <span className="badge badge-warning pending-count" data-testid="pending-count">{pending.length} waiting</span>}
        </span>
      </div>

      {pending.length > 0 && (
        <div className="pending" data-testid="pending-users">
          <h3>Waiting for approval</h3>
          <ul className="plain">
            {pending.map((u) => (
              <li key={u.username} className="pending-item" data-testid={`pending-${u.username}`}>
                <span className="avatar avatar-sm" aria-hidden="true">{u.username.slice(0, 1).toUpperCase()}</span>
                <span className="pending-who">
                  <strong>{u.username}</strong>
                  <span className="meta">{u.email ?? "no email"} · asked {formatRelative(u.created_at, now)}</span>
                </span>
                <select aria-label={`Role for ${u.username}`} value={approveAs[u.username] ?? "VIEWER"} disabled={busy}
                        onChange={(e) => setApproveAs((m) => ({ ...m, [u.username]: e.target.value as Role }))}
                        data-testid="approve-role">
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <button type="button" disabled={busy} onClick={() => approve(u.username)} data-testid="approve">
                  <CheckIcon size={16} /> Approve
                </button>
                <button type="button" className="ghost danger-text" disabled={busy}
                        onClick={() => setConfirm(u.username)} data-testid="reject">Reject</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <form className="edit user-form" onSubmit={submit} data-testid="user-form">
        <label>
          Username
          <input data-testid="user-new-name" required minLength={3} maxLength={50} pattern="[A-Za-z0-9_.\-]+"
                 title="3-50 characters: letters, digits, _ . -" autoComplete="off"
                 value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          Email
          <input data-testid="user-new-email" type="email" maxLength={254} autoComplete="off"
                 placeholder="optional, for recovery" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input data-testid="user-new-password" type="password" required minLength={8} maxLength={128}
                 autoComplete="new-password" placeholder="at least 8 characters"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label>
          Role
          <select data-testid="user-new-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy} data-testid="user-create"><PlusIcon size={18} /> Add user</button>
        <p className="meta role-hint">{role}: {ROLE_HINT[role]}.</p>
      </form>

      {error && <div role="alert" className="error panel-error" data-testid="users-error">{error}</div>}

      {users && (
        <div className="table-wrap">
          <table data-testid="users-table">
            <thead>
              <tr><th scope="col">User</th><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Created</th><th scope="col" /></tr>
            </thead>
            <tbody>
              {active.map((u) => (
                <tr key={u.username} data-testid={`user-row-${u.username}`}>
                  <td>
                    <div className="device-cell">
                      <span className="avatar avatar-sm" aria-hidden="true">{u.username.slice(0, 1).toUpperCase()}</span>
                      <span className="device-id">{u.username}</span>
                      {u.username === currentUser && <span className="badge">you</span>}
                    </div>
                  </td>
                  <td className="email-cell">{u.email ?? <span className="meta">—</span>}</td>
                  <td>
                    {u.username === currentUser ? (
                      <span className={`badge badge-role-${u.role.toLowerCase()}`} data-testid="user-role-cell">{u.role}</span>
                    ) : (
                      <select className={`role-select role-${u.role.toLowerCase()}`} aria-label={`Role of ${u.username}`}
                              value={u.role} disabled={busy} data-testid="user-role-cell"
                              onChange={(e) => changeRole(u.username, e.target.value as Role)}>
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    )}
                  </td>
                  <td title={u.created_at}>{formatRelative(u.created_at, now)}</td>
                  <td className="num">
                    {u.username !== currentUser && (
                      <button type="button" className="ghost danger-text" disabled={busy}
                              onClick={() => setConfirm(u.username)} data-testid="user-delete">
                        <TrashIcon size={16} /> Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog open={confirm !== null}
                     title={pending.some((u) => u.username === confirm) ? `Reject ${confirm}?` : `Delete ${confirm}?`}
                     message={pending.some((u) => u.username === confirm)
                       ? "The sign-up request is removed. They can ask again later."
                       : "They are signed out at once and can no longer sign in. This cannot be undone."}
                     confirmLabel={pending.some((u) => u.username === confirm) ? "Reject" : "Delete user"} onConfirm={() => confirm && remove(confirm)}
                     onCancel={() => setConfirm(null)} />
    </section>
  );
}
