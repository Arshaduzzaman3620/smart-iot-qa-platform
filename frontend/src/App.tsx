import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, AuthError, fetchActiveAlerts, fetchSensors, setToken } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { FirmwareLibrary } from "./components/FirmwareLibrary";
import { Devices } from "./components/Devices";
import { BellIcon, ChipIcon, DevicesIcon, GridIcon, LogoutIcon, Logo, UsersIcon } from "./components/Icons";
import { LoginForm } from "./components/LoginForm";
import { Overview } from "./components/Overview";
import { SensorDetails } from "./components/SensorDetails";
import { ThemeToggle } from "./components/ThemeToggle";
import { ToastProvider } from "./components/Toast";
import { UsersPanel } from "./components/UsersPanel";
import { clearSession, hasRole, loadSession, saveSession } from "./session";
import type { Alert, Sensor, Session } from "./types";

// Matches the simulator's default SENSOR_INTERVAL, so each refresh usually shows a new reading.
const REFRESH_MS = 5000;

const SECTIONS = [
  { id: "overview", label: "Overview", icon: <GridIcon /> },
  { id: "devices", label: "Devices", icon: <DevicesIcon /> },
  { id: "alerts", label: "Alerts", icon: <BellIcon /> },
  { id: "firmware", label: "Firmware", icon: <ChipIcon /> },
  { id: "users", label: "Users", icon: <UsersIcon />, role: "ADMIN" as const },
];

/** The sensor in the address (?sensor=ID), so a sensor can be bookmarked and Back closes it. */
function sensorFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("sensor");
}

/** Which section is on screen, for the sidebar highlight: the last one whose top has passed the upper
 *  third of the window, or the last section once the page is scrolled to the bottom. */
function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0]);
  const key = ids.join(",");
  useEffect(() => {
    const list = key.split(",");
    let frame = 0;
    function update() {
      frame = 0;
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      let current = list[0];
      for (const id of list) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= window.innerHeight * 0.33) current = id;
      }
      if (atBottom) current = [...list].reverse().find((id) => document.getElementById(id)) ?? current;
      setActive(current);
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [key]);
  return active;
}

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
    <ToastProvider>
      <Shell session={session} onSignOut={signOut} />
    </ToastProvider>
  );
}

function Shell({ session, onSignOut }: { session: Session; onSignOut: (reason?: string | null) => void }) {
  const sections = SECTIONS.filter((s) => !s.role || hasRole(session, s.role));
  const active = useActiveSection(sections.map((s) => s.id));
  const signOut = onSignOut;

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
          {sections.map((s) => (
            <a key={s.id} href={`#${s.id}`} className={active === s.id ? "active" : undefined}
               aria-current={active === s.id ? "location" : undefined} data-testid={`nav-${s.id}`}>
              {s.icon} {s.label}
            </a>
          ))}
        </nav>
        <ThemeToggle />
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
  const [selected, setSelectedState] = useState<string | null>(sensorFromUrl);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const loadRef = useRef<() => void>(() => {});
  // Stable across renders, so the details panel doesn't refetch on every tick.
  const authErrorRef = useRef(onAuthError);
  authErrorRef.current = onAuthError;
  const handleAuthError = useCallback((err: AuthError) => authErrorRef.current(err), []);

  const setSelected = useCallback((sensorId: string | null) => {
    setSelectedState(sensorId);
    const url = new URL(window.location.href);
    if (sensorId) url.searchParams.set("sensor", sensorId);
    else url.searchParams.delete("sensor");
    url.hash = "";
    if (url.href !== window.location.href) window.history.pushState(null, "", url);
  }, []);

  // Back / Forward move between sensors like pages.
  useEffect(() => {
    const onPop = () => setSelectedState(sensorFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

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

      {sensors ? <Overview sensors={sensors} alerts={alerts} /> : !error && <Skeleton />}

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
          <Devices sensors={sensors} now={now} selected={selected} onSelect={setSelected} />
        )}
      </section>

      <div id="firmware" className="anchor">
        <FirmwareLibrary now={now} canUpload={hasRole(session, "ADMIN")} onAuthError={handleAuthError} />
      </div>

      {hasRole(session, "ADMIN") && (
        <div id="users" className="anchor">
          <UsersPanel currentUser={session.user.username} now={now} onAuthError={handleAuthError} />
        </div>
      )}
    </>
  );
}

/** Placeholder shapes while the first load runs, so the page doesn't jump when data arrives. */
function Skeleton() {
  return (
    <div className="overview-wrap" aria-hidden="true">
      <div className="hero skeleton" />
      <div className="overview">
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="tile skeleton" />)}
      </div>
    </div>
  );
}
