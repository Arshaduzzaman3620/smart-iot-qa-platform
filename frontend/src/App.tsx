import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, AuthError, fetchActiveAlerts, fetchSensors, setToken } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { FirmwareLibrary } from "./components/FirmwareLibrary";
import { BellIcon, ChipIcon, DevicesIcon, GridIcon, LogoutIcon, Logo } from "./components/Icons";
import { LoginForm } from "./components/LoginForm";
import { Overview } from "./components/Overview";
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

  if (!session) return <LoginForm onLogin={signIn} notice={notice} />;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Logo />
          <div>
            <h1>SmartIoT</h1>
            <span className="brand-sub">Home control center</span>
          </div>
        </div>
        <nav className="nav" aria-label="Sections">
          <a href="#overview"><GridIcon /> Overview</a>
          <a href="#devices"><DevicesIcon /> Devices</a>
          <a href="#alerts"><BellIcon /> Alerts</a>
          <a href="#firmware"><ChipIcon /> Firmware</a>
        </nav>
        <div className="user" data-testid="user-menu">
          <span className="avatar" aria-hidden="true">{session.user.username.slice(0, 1).toUpperCase()}</span>
          <div className="user-text">
            <span className="user-name" data-testid="user-name">{session.user.username}</span>
            <span className="badge badge-role" data-testid="user-role">{session.user.role}</span>
          </div>
          <button type="button" className="icon-button" onClick={() => signOut()} data-testid="logout"
                  title="Sign out">
            <LogoutIcon /><span className="sr-only">Sign out</span>
          </button>
        </div>
      </aside>
      <main className="content">
        <Dashboard session={session} onAuthError={(err) => signOut(err.message)} />
      </main>
    </div>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 5 ? "Good night" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
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
      <header className="page-head" id="overview">
        <div>
          <h2 className="greeting">{greeting()}, {session.user.username}</h2>
          <p className="meta">Here is what is happening across your home.</p>
        </div>
        <span className={`live ${error ? "live-down" : updatedAt ? "live-up" : ""}`}>
          <span className="live-dot" aria-hidden="true" />
          <span data-testid="last-updated">
            {updatedAt
              ? `Updated ${new Date(updatedAt).toLocaleTimeString()} · refreshes every ${REFRESH_MS / 1000}s`
              : error
                ? "Not connected"
                : "Loading…"}
          </span>
        </span>
      </header>

      {error && (
        <div role="alert" className="error" data-testid="error-banner">
          {error}. {sensors ? "Showing last known data." : "Retrying…"}
        </div>
      )}

      {sensors && <Overview sensors={sensors} alerts={alerts} />}

      <div id="alerts" className="anchor">{alerts && <AlertsPanel alerts={alerts} now={now} />}</div>

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

      <section className="panel" id="devices" aria-labelledby="devices-heading">
        <div className="panel-head">
          <h2 id="devices-heading">Devices</h2>
          {sensors && <span className="meta">{sensors.length} total · select one for details</span>}
        </div>
        {sensors === null ? (
          !error && <p className="empty" data-testid="loading">Loading sensors…</p>
        ) : (
          <SensorTable sensors={sensors} now={now} selected={selected} onSelect={setSelected} />
        )}
      </section>

      <div id="firmware" className="anchor">
        <FirmwareLibrary now={now} canUpload={hasRole(session, "ADMIN")} onAuthError={handleAuthError} />
      </div>
    </>
  );
}
