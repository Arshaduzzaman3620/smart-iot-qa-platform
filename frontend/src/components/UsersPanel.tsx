import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, createUser, deleteUser, fetchUsers } from "../api";
import { formatRelative } from "../format";
import type { Role, User } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { PlusIcon, TrashIcon } from "./Icons";
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
    if (await run(() => createUser(name, password, role), `User ${name} created as ${role}`)) {
      setUsername("");
      setPassword("");
      setRole("VIEWER");
    }
  }

  async function remove(name: string) {
    setConfirm(null);
    await run(() => deleteUser(name), `User ${name} deleted`);
  }

  return (
    <section className="panel" aria-labelledby="users-heading" data-testid="users-panel">
      <div className="panel-head">
        <h2 id="users-heading">Users</h2>
        <span className="meta">{users ? `${users.length} accounts` : "Loading…"}</span>
      </div>

      <form className="edit user-form" onSubmit={submit} data-testid="user-form">
        <label>
          Username
          <input data-testid="user-new-name" required minLength={3} maxLength={50} pattern="[A-Za-z0-9_.\-]+"
                 title="3-50 characters: letters, digits, _ . -" autoComplete="off"
                 value={username} onChange={(e) => setUsername(e.target.value)} />
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
              <tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Created</th><th scope="col" /></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.username} data-testid={`user-row-${u.username}`}>
                  <td>
                    <div className="device-cell">
                      <span className="avatar avatar-sm" aria-hidden="true">{u.username.slice(0, 1).toUpperCase()}</span>
                      <span className="device-id">{u.username}</span>
                      {u.username === currentUser && <span className="badge">you</span>}
                    </div>
                  </td>
                  <td><span className={`badge badge-role-${u.role.toLowerCase()}`} data-testid="user-role-cell">{u.role}</span></td>
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

      <ConfirmDialog open={confirm !== null} title={`Delete ${confirm}?`}
                     message="They are signed out at once and can no longer sign in. This cannot be undone."
                     confirmLabel="Delete user" onConfirm={() => confirm && remove(confirm)}
                     onCancel={() => setConfirm(null)} />
    </section>
  );
}
