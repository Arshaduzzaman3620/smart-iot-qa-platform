import { type FormEvent, type KeyboardEvent, type ReactNode, useState } from "react";

import { ApiError, forgotPassword, login, resetPassword } from "../api";
import type { Session } from "../types";
import {
  BellIcon, CheckIcon, ChipIcon, DropletIcon, Logo, ShieldIcon, ThermometerIcon, WifiIcon,
} from "./Icons";

interface Props {
  onLogin: (session: Session) => void;
  /** Why the user is here again, e.g. "Token expired". */
  notice?: string | null;
}

type Mode = "signin" | "forgot" | "reset";

/** The reset token from an emailed link (?reset=...), if the page was opened from one. */
function resetTokenFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("reset");
}

/** The signed-out home: sign in, or recover a username or password (Phase 19). Accounts are created by
 *  an administrator in Users, never here. */
export function LoginForm({ onLogin, notice }: Props) {
  const [token] = useState(resetTokenFromUrl);
  const [mode, setMode] = useState<Mode>(token ? "reset" : "signin");
  const [flash, setFlash] = useState<string | null>(null); // a success to show on the sign-in form

  function go(next: Mode, message: string | null = null) {
    setFlash(message);
    setMode(next);
    if (next !== "reset" && token) {
      // The link is used up (or abandoned): take it out of the address.
      const url = new URL(window.location.href);
      url.searchParams.delete("reset");
      window.history.replaceState(null, "", url);
    }
  }

  return (
    <div className="login-page" data-testid="auth-page">
      <Showcase />
      <main className="login-main">
        <div className="auth-card">
          <div className="auth-view" key={mode}>
            {mode === "signin" && (
              <SignIn onLogin={onLogin} notice={notice} flash={flash} onForgot={() => go("forgot")} />
            )}
            {mode === "forgot" && <Forgot onBack={() => go("signin")} />}
            {mode === "reset" && token && <Reset token={token} onDone={(m) => go("signin", m)} onBack={() => go("forgot")} />}
          </div>
        </div>
        <p className="meta login-foot">SmartIoT · Smart home control center</p>
      </main>
    </div>
  );
}

// ---- the four forms -------------------------------------------------------------------------------

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}

function SignIn({ onLogin, notice, flash, onForgot }: {
  onLogin: (s: Session) => void; notice?: string | null; flash: string | null; onForgot: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useSubmit();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async () => {
      try {
        onLogin(await login(username, password));
      } catch (err) {
        setPassword("");
        throw err;
      }
    });
  }

  return (
    <form className="login" onSubmit={submit} data-testid="login-form">
      <Heading title="Welcome back" text="Sign in to manage your home." />
      {flash && !error && <p className="success" role="status" data-testid="auth-flash"><CheckIcon size={18} />{flash}</p>}
      {notice && !error && !flash && <p className="notice" data-testid="login-notice">{notice}. Please sign in again.</p>}
      {error && <div role="alert" className="error" data-testid="login-error">{error}</div>}
      <label>
        Username
        <input data-testid="login-username" autoComplete="username" required maxLength={50}
               placeholder="e.g. admin" value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <PasswordField label="Password" testId="login-password" autoComplete="current-password"
                     value={password} onChange={setPassword} minLength={1} />
      <button type="button" className="link forgot" onClick={onForgot} data-testid="forgot-link">
        Forgot username or password?
      </button>
      <Submit busy={busy} testId="login-submit" idle="Sign in" working="Signing in…" />
      <p className="meta login-note" data-testid="no-signup-note">Need an account? Ask your administrator.</p>
    </form>
  );
}

function Forgot({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { busy, error, run } = useSubmit();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async () => setDone((await forgotPassword(email.trim())).detail));
  }

  if (done) return <Done testId="forgot-done" title="Check your email" text={done} action="Back to sign in" onAction={onBack} />;

  return (
    <form className="login" onSubmit={submit} data-testid="forgot-form">
      <Heading title="Forgot username or password?"
               text="Enter your account's email. We'll send you the username and a link to choose a new password." />
      {error && <div role="alert" className="error" data-testid="forgot-error">{error}</div>}
      <label>
        Email
        <input data-testid="forgot-email" type="email" autoComplete="email" required maxLength={254}
               placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <Submit busy={busy} testId="forgot-submit" idle="Send instructions" working="Sending…" />
      <button type="button" className="link back" onClick={onBack} data-testid="back-to-signin">← Back to sign in</button>
    </form>
  );
}

function Reset({ token, onDone, onBack }: { token: string; onDone: (message: string) => void; onBack: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const { busy, error, setError, run } = useSubmit();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) return setError("The passwords don't match");
    run(async () => onDone((await resetPassword(token, password)).detail));
  }

  return (
    <form className="login" onSubmit={submit} data-testid="reset-form">
      <Heading title="Choose a new password" text="Every device signed in to your account will be signed out." />
      {error && (
        <div role="alert" className="error" data-testid="reset-error">
          {error}
          {error.includes("expired") && (
            <button type="button" className="link" onClick={onBack} data-testid="reset-new-link"> Send a new link</button>
          )}
        </div>
      )}
      <PasswordField label="New password" testId="reset-password" autoComplete="new-password" value={password}
                     onChange={setPassword} strength />
      <PasswordField label="Confirm new password" testId="reset-confirm" autoComplete="new-password" value={confirm}
                     onChange={setConfirm} />
      <Submit busy={busy} testId="reset-submit" idle="Save new password" working="Saving…" />
    </form>
  );
}

// ---- pieces ------------------------------------------------------------------------------------------

function Heading({ title, text }: { title: string; text: string }) {
  return (
    <div className="login-head">
      <h2>{title}</h2>
      <p className="meta">{text}</p>
    </div>
  );
}

function Submit({ busy, testId, idle, working }: { busy: boolean; testId: string; idle: string; working: string }) {
  return (
    <button type="submit" className="primary" disabled={busy} data-testid={testId}>
      {busy && <span className="spinner" aria-hidden="true" />}
      {busy ? working : idle}
    </button>
  );
}

function Done({ testId, title, text, action, onAction }: {
  testId: string; title: string; text: string; action: string; onAction: () => void;
}) {
  return (
    <div className="login done" data-testid={testId} role="status">
      <span className="done-icon"><CheckIcon size={30} /></span>
      <Heading title={title} text={text} />
      <button type="button" className="primary" onClick={onAction} data-testid="back-to-signin">{action}</button>
    </div>
  );
}

/** 1 = too short (under the API's 8), then 2-4 for length and variety: a hint, not a rule. */
export function passwordStrength(password: string): number {
  if (password.length < 8) return password ? 1 : 0;
  let score = 2;
  if (password.length >= 12) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}
const STRENGTH = ["", "Too short", "Fair", "Good", "Strong"];

function PasswordField({ label, testId, autoComplete, value, onChange, minLength = 8, strength = false }: {
  label: string; testId: string; autoComplete: string; value: string; onChange: (v: string) => void;
  minLength?: number; strength?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const score = passwordStrength(value);
  const caps = (e: KeyboardEvent<HTMLInputElement>) => setCapsLock(e.getModifierState?.("CapsLock") ?? false);

  return (
    <label>
      {label}
      <span className="password">
        <input data-testid={testId} type={visible ? "text" : "password"} autoComplete={autoComplete} required
               minLength={minLength} maxLength={128} placeholder={minLength > 1 ? "at least 8 characters" : "••••••••"}
               value={value} onChange={(e) => onChange(e.target.value)} onKeyUp={caps} onKeyDown={caps}
               onBlur={() => setCapsLock(false)} />
        <button type="button" className="reveal" onClick={() => setVisible((v) => !v)} data-testid={`${testId}-toggle`}
                aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible}>
          {visible ? "Hide" : "Show"}
        </button>
      </span>
      {capsLock && <span className="hint warn" data-testid={`${testId}-caps`}>Caps Lock is on</span>}
      {strength && value && (
        <span className={`strength s${score}`} data-testid="password-strength">
          <span className="strength-bar" aria-hidden="true"><i /><i /><i /><i /></span>
          {STRENGTH[score]}
        </span>
      )}
    </label>
  );
}

// ---- the animated showcase on the left ----------------------------------------------------------

function Showcase() {
  return (
    <section className="login-hero" aria-hidden="true">
      <div className="mesh" />
      <div className="brand brand-light">
        <Logo size={40} />
        <div>
          <span className="brand-name">SmartIoT</span>
          <span className="brand-sub">Home control center</span>
        </div>
      </div>

      <div className="scene">
        <svg className="house" viewBox="0 0 240 200">
          <circle className="ring r1" cx="120" cy="96" r="40" />
          <circle className="ring r2" cx="120" cy="96" r="40" />
          <circle className="ring r3" cx="120" cy="96" r="40" />
          <path className="house-body" d="M58 110 120 58l62 52v62a6 6 0 0 1-6 6H64a6 6 0 0 1-6-6Z" />
          <path className="house-roof" d="M44 118 120 52l76 66" />
          <rect className="window w1" x="80" y="118" width="26" height="22" rx="4" />
          <rect className="window w2" x="134" y="118" width="26" height="22" rx="4" />
          <rect className="door" x="108" y="146" width="24" height="32" rx="4" />
        </svg>
        <Widget className="wg1" icon={<ThermometerIcon size={18} />} label="Living room" value="22.4 °C" />
        <Widget className="wg2" icon={<DropletIcon size={18} />} label="Humidity" value="46 %" />
        <Widget className="wg3" icon={<WifiIcon size={18} />} label="Devices online" value="5 / 5" />
        <Widget className="wg4 alert" icon={<BellIcon size={18} />} label="Freezer" value="Back to normal" />
      </div>

      <div className="hero-copy">
        <h2>Every room, every sensor, one place.</h2>
        <p>Live climate readings, instant alerts and over-the-air updates, encrypted end to end.</p>
        <ul className="hero-chips">
          <li><ShieldIcon size={16} /> TLS everywhere</li>
          <li><ChipIcon size={16} /> OTA firmware</li>
          <li><BellIcon size={16} /> Smart alerts</li>
        </ul>
      </div>
    </section>
  );
}

function Widget({ className, icon, label, value }: { className: string; icon: ReactNode; label: string; value: string }) {
  return (
    <div className={`widget ${className}`}>
      <span className="widget-icon">{icon}</span>
      <span><small>{label}</small><strong>{value}</strong></span>
    </div>
  );
}
