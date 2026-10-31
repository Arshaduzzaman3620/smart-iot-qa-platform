import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, AuthError, fetchActiveAlerts, fetchSensors, setToken } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { FirmwareLibrary } from "./components/FirmwareLibrary";
import { LoginForm } from "./components/LoginForm";
import { SensorDetails } from "./components/SensorDetails";
import { SensorTable } from "./components/SensorTable";
import { clearSession, hasRole, loadSession, saveSession } from "./session";
import type { Alert, Sensor, Session } from "./types";

// Matches the simulator's default SENSOR_INTERVAL, so each refresh usually shows a new reading.
const REFRESH_MS = 5000;

export default function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const saved = loadSession();
    setToken(saved?.access_token ?? null);
    return saved;
  });
  const [notice, setNotice] = useState<string | null>(null);

  function signIn(next: Session) {
    saveSession(next);
    setToken(next.access_token);
    setNotice(null);
    setSession(next);
  }

  const signOut = useCallback((reason: string | null = null) => {
    clearSession();
    setToken(null);
    setNotice(reason);
    setSession(null);
  }, []);

  return (
    <main>
      <header className="top">
        <h1>SmartIoT Sensors</h1>
        {session && (
          <div className="user" data-testid="user-menu">
            <span data-testid="user-name">{session.user.username}</span>
            <span className="badge" data-testid="user-role">{session.user.role}</span>
            <button type="button" className="link" onClick={() => signOut()} data-testid="logout">Sign out</button>
          </div>
        )}
      </header>
      {session ? (
        <Dashboard session={session} onAuthError={(err) => signOut(err.message)} />
      ) : (
        <LoginForm onLogin={signIn} notice={notice} />
      )}
    </main>
  );
}

interface DashboardProps {
  session: Session;
  onAuthError: (err: AuthError) => void;
}

function Dashboard({ session, onAuthError }: DashboardProps) {
  const [sensors, setSensors] = useState<Sensor[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const loadRef = useRef<() => void>(() => {});
  // Stable across renders, so the details panel doesn't refetch on every tick.
  const authErrorRef = useRef(onAuthError);
  authErrorRef.current = onAuthError;
  const handleAuthError = useCallback((err: AuthError) => authErrorRef.current(err), []);

  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;

    async function load() {
      // Skip a tick while the previous load is still running. Cancelling it instead would mean an
      // API slower than REFRESH_MS never shows anything at all (every response aborted by the next tick).
      if (inFlight) return;
      inFlight = true;
      try {
        const [nextSensors, nextAlerts] = await Promise.all([
          fetchSensors(controller.signal),
          fetchActiveAlerts(controller.signal),
        ]);
        setSensors(nextSensors);
        setAlerts(nextAlerts);
        setError(null);
        setUpdatedAt(Date.now());
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return handleAuthError(err);
        // Keep showing the last good data; just flag that it may be stale.
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      } finally {
        inFlight = false;
      }
    }

    loadRef.current = load;
    load();
    const poll = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      controller.abort();
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [handleAuthError]);

  const selectedSensor = sensors?.find((s) => s.sensor_id === selected) ?? null;

  return (
    <>
      <p className="meta status-line" data-testid="last-updated">
        {updatedAt
          ? `Updated ${new Date(updatedAt).toLocaleTimeString()} · refreshes every ${REFRESH_MS / 1000}s`
          : error
            ? "Not connected"
            : "Loading…"}
      </p>

      {error && (
        <div role="alert" className="error" data-testid="error-banner">
          {error}. {sensors ? "Showing last known data." : "Retrying…"}
        </div>
      )}

      {alerts && <AlertsPanel alerts={alerts} now={now} />}

      {selectedSensor && (
        <SensorDetails
          key={selectedSensor.sensor_id}
          sensor={selectedSensor}
          now={now}
          canEdit={hasRole(session, "OPERATOR")}
          onClose={() => setSelected(null)}
          onAuthError={handleAuthError}
          onUpdated={() => loadRef.current()}
        />
      )}

      {sensors === null ? (
        !error && <p className="empty" data-testid="loading">Loading sensors…</p>
      ) : (
        <SensorTable sensors={sensors} now={now} selected={selected} onSelect={setSelected} />
      )}

      <FirmwareLibrary now={now} canUpload={hasRole(session, "ADMIN")} onAuthError={handleAuthError} />
    </>
  );
}
