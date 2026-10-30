import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, fetchSensorAlerts, fetchTelemetry, updateSensor } from "../api";
import { formatNumber, formatRelative } from "../format";
import type { Alert, Sensor, Telemetry } from "../types";
import { CommandsPanel } from "./CommandsPanel";
import { FirmwarePanel } from "./FirmwarePanel";

const HISTORY_ROWS = 20;

interface Props {
  sensor: Sensor;
  now: number;
  canEdit: boolean;
  onClose: () => void;
  onAuthError: (err: AuthError) => void;
  onUpdated: () => void;
}

export function SensorDetails({ sensor, now, canEdit, onClose, onAuthError, onUpdated }: Props) {
  const [history, setHistory] = useState<Telemetry[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Refetch history whenever the list refresh brings a newer reading.
  const latestId = sensor.latest_telemetry?.id ?? null;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchTelemetry(sensor.sensor_id, HISTORY_ROWS, controller.signal),
      fetchSensorAlerts(sensor.sensor_id, HISTORY_ROWS, controller.signal),
    ])
      .then(([nextHistory, nextAlerts]) => {
        setHistory(nextHistory);
        setAlerts(nextAlerts);
        setError(null);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return onAuthError(err);
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      });
    return () => controller.abort();
  }, [sensor.sensor_id, latestId, onAuthError]);

  return (
    <section className="card details" aria-labelledby="details-heading" data-testid="sensor-details">
      <div className="details-head">
        <h2 id="details-heading" className="mono">{sensor.sensor_id}</h2>
        <button type="button" className="link" onClick={onClose} data-testid="details-close">Close</button>
      </div>

      <dl className="facts">
        <dt>Name</dt><dd data-testid="details-name">{sensor.name ?? "—"}</dd>
        <dt>Location</dt><dd data-testid="details-location">{sensor.location ?? "—"}</dd>
        <dt>Type</dt><dd>{sensor.sensor_type}</dd>
        <dt>Firmware</dt><dd data-testid="details-firmware">{sensor.firmware_version ?? "—"}</dd>
        <dt>Status</dt><dd>{sensor.status}</dd>
        <dt>Last seen</dt><dd>{formatRelative(sensor.last_seen, now)}</dd>
      </dl>

      {canEdit && <EditSensor sensor={sensor} onAuthError={onAuthError} onUpdated={onUpdated} />}

      <CommandsPanel sensorId={sensor.sensor_id} now={now} canSend={canEdit} onAuthError={onAuthError} />

      <FirmwarePanel sensor={sensor} now={now} canUpdate={canEdit} onAuthError={onAuthError} />

      {error && <div role="alert" className="error" data-testid="details-error">{error}</div>}

      <h3>Recent readings</h3>
      {history === null ? (
        !error && <p className="meta">Loading…</p>
      ) : history.length === 0 ? (
        <p className="meta" data-testid="history-empty">No readings yet.</p>
      ) : (
        <div className="table-wrap">
          <table data-testid="history-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col" className="num">Temp</th>
                <th scope="col" className="num">Humidity</th>
                <th scope="col" className="num">Pressure</th>
                <th scope="col" className="num">Light</th>
                <th scope="col" className="num">Battery</th>
              </tr>
            </thead>
            <tbody>
              {history.map((t) => (
                <tr key={t.id}>
                  <td title={t.timestamp}>{new Date(t.timestamp).toLocaleTimeString()}</td>
                  <td className="num">{formatNumber(t.temperature, "°C")}</td>
                  <td className="num">{formatNumber(t.humidity, "%")}</td>
                  <td className="num">{formatNumber(t.pressure, "hPa")}</td>
                  <td className="num">{formatNumber(t.light, "lx", 0)}</td>
                  <td className="num">{formatNumber(t.battery, "%")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Alert history</h3>
      {alerts && alerts.length === 0 && <p className="meta" data-testid="details-alerts-empty">No alerts.</p>}
      {alerts && alerts.length > 0 && (
        <ul className="plain" data-testid="details-alerts">
          {alerts.map((a) => (
            <li key={a.id}>
              <span className={`badge badge-${a.status === "ACTIVE" ? a.severity.toLowerCase() : "resolved"}`}>
                {a.status === "ACTIVE" ? a.severity : "RESOLVED"}
              </span>{" "}
              {a.message ?? a.alert_type} <span className="meta">{formatRelative(a.created_at, now)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function EditSensor({ sensor, onAuthError, onUpdated }: Pick<Props, "sensor" | "onAuthError" | "onUpdated">) {
  const [name, setName] = useState(sensor.name ?? "");
  const [location, setLocation] = useState(sensor.location ?? "");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await updateSensor(sensor.sensor_id, { name, location });
      setMessage({ ok: true, text: "Saved" });
      onUpdated();
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err);
      setMessage({ ok: false, text: err instanceof ApiError ? err.message : "Unexpected error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="edit" onSubmit={submit} data-testid="edit-sensor">
      <label>
        Name
        <input data-testid="edit-name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Location
        <input data-testid="edit-location" maxLength={100} value={location}
               onChange={(e) => setLocation(e.target.value)} />
      </label>
      <button type="submit" disabled={busy} data-testid="edit-save">Save</button>
      {message && (
        <span role="status" className={message.ok ? "meta" : "low"} data-testid="edit-message">{message.text}</span>
      )}
    </form>
  );
}
