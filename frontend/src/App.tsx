import { useEffect, useState } from "react";

import { ApiError, fetchSensors } from "./api";
import { SensorTable } from "./components/SensorTable";
import type { Sensor } from "./types";

// Matches the simulator's default SENSOR_INTERVAL, so each refresh usually shows a new reading.
const REFRESH_MS = 5000;

export default function App() {
  const [sensors, setSensors] = useState<Sensor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let controller = new AbortController();

    async function load() {
      controller.abort();
      controller = new AbortController();
      try {
        setSensors(await fetchSensors(controller.signal));
        setError(null);
        setUpdatedAt(Date.now());
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        // Keep showing the last good data; just flag that it may be stale.
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      }
    }

    load();
    const poll = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      controller.abort();
      clearInterval(poll);
      clearInterval(tick);
    };
  }, []);

  return (
    <main>
      <header>
        <h1>SmartIoT Sensors</h1>
        <p className="meta" data-testid="last-updated">
          {updatedAt
            ? `Updated ${new Date(updatedAt).toLocaleTimeString()} · refreshes every ${REFRESH_MS / 1000}s`
            : error
              ? "Not connected"
              : "Loading…"}
        </p>
      </header>

      {error && (
        <div role="alert" className="error" data-testid="error-banner">
          {error}. {sensors ? "Showing last known data." : "Retrying…"}
        </div>
      )}

      {sensors === null ? (
        !error && <p className="empty" data-testid="loading">Loading sensors…</p>
      ) : (
        <SensorTable sensors={sensors} now={now} />
      )}
    </main>
  );
}
