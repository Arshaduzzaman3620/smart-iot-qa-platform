import { type FormEvent, useState } from "react";

import { ApiError, login } from "../api";
import type { Session } from "../types";

interface Props {
  onLogin: (session: Session) => void;
  /** Why the user is here again, e.g. "Token expired". */
  notice?: string | null;
}

export function LoginForm({ onLogin, notice }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await login(username, password));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card login" onSubmit={submit} data-testid="login-form">
      <h2>Sign in</h2>
      {notice && !error && <p className="meta" data-testid="login-notice">{notice}. Please sign in again.</p>}
      {error && (
        <div role="alert" className="error" data-testid="login-error">
          {error}
        </div>
      )}
      <label>
        Username
        <input data-testid="login-username" autoComplete="username" required maxLength={50}
               value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        Password
        <input data-testid="login-password" type="password" autoComplete="current-password" required maxLength={128}
               value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      <button type="submit" disabled={busy} data-testid="login-submit">
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
