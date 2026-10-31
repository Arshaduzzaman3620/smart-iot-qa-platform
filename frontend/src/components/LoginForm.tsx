import { type FormEvent, useState } from "react";

import { ApiError, login } from "../api";
import type { Session } from "../types";
import { BellIcon, ChipIcon, Logo, ShieldIcon, ThermometerIcon } from "./Icons";

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
    <div className="login-page">
      <section className="login-hero" aria-hidden="true">
        <div className="brand brand-light">
          <Logo size={40} />
          <div>
            <span className="brand-name">SmartIoT</span>
            <span className="brand-sub">Home control center</span>
          </div>
        </div>
        <div className="hero-copy">
          <h2>Every room, every sensor, one place.</h2>
          <p>Live climate readings, instant alerts and over-the-air updates for all your devices.</p>
        </div>
        <ul className="hero-points">
          <li><ThermometerIcon /> Live temperature, humidity and light</li>
          <li><BellIcon /> Alerts the moment something is off</li>
          <li><ChipIcon /> Firmware updates over the air</li>
          <li><ShieldIcon /> Encrypted end to end with TLS</li>
        </ul>
      </section>

      <main className="login-main">
        <form className="login" onSubmit={submit} data-testid="login-form">
          <div className="login-head">
            <h2>Welcome back</h2>
            <p className="meta">Sign in to manage your home.</p>
          </div>
          {notice && !error && <p className="notice" data-testid="login-notice">{notice}. Please sign in again.</p>}
          {error && (
            <div role="alert" className="error" data-testid="login-error">
              {error}
            </div>
          )}
          <label>
            Username
            <input data-testid="login-username" autoComplete="username" required maxLength={50}
                   placeholder="e.g. admin" value={username} onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label>
            Password
            <input data-testid="login-password" type="password" autoComplete="current-password" required maxLength={128}
                   placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="submit" className="primary" disabled={busy} data-testid="login-submit">
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="meta login-foot">Fictional, fully simulated devices · SmartIoT QA platform</p>
        </form>
      </main>
    </div>
  );
}
