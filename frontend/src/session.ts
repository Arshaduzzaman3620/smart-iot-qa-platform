import type { Role, Session } from "./types";

// sessionStorage, not localStorage: the session ends when the tab is closed.
const KEY = "smartiot.session";
const ROLES: Role[] = ["VIEWER", "OPERATOR", "ADMIN"];

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null; // storage blocked or corrupt: just sign in again
  }
}

export function saveSession(session: Session): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // storage blocked: the session lasts until the page is reloaded
  }
}

export function clearSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}

/** UI hint only -- the API enforces every permission itself. */
export function hasRole(session: Session | null, required: Role): boolean {
  return session != null && ROLES.indexOf(session.user.role) >= ROLES.indexOf(required);
}
