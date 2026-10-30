import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, fetchFirmware, fetchFirmwareUpdates, startFirmwareUpdate } from "../api";
import { formatRelative } from "../format";
import type { Firmware, FirmwareUpdate, Sensor } from "../types";

const HISTORY_ROWS = 5;
const POLL_MS = 1000; // while an update is in progress
const FINAL = ["SUCCEEDED", "FAILED", "TIMED_OUT"];

interface Props {
  sensor: Sensor;
  now: number;
  canUpdate: boolean;
  onAuthError: (err: AuthError) => void;
}

/** A sensor's firmware updates (Phase 15e), and starting one. */
export function FirmwarePanel({ sensor, now, canUpdate, onAuthError }: Props) {
  const [updates, setUpdates] = useState<FirmwareUpdate[] | null>(null);
  const [images, setImages] = useState<Firmware[]>([]);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const running = updates?.some((u) => !FINAL.includes(u.status)) ?? false;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchFirmwareUpdates(sensor.sensor_id, HISTORY_ROWS, controller.signal), fetchFirmware(controller.signal)])
      .then(([nextUpdates, nextImages]) => {
        setUpdates(nextUpdates);
        setImages(nextImages);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return onAuthError(err);
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      });
    return () => controller.abort();
  }, [sensor.sensor_id, reload, onAuthError]);

  useEffect(() => {
    if (!running) return;
    const timer = setTimeout(() => setReload((n) => n + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [running, updates]);

  const choices = images.filter((f) => f.version !== sensor.firmware_version);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await startFirmwareUpdate(sensor.sensor_id, Number(choice));
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err);
      setError(err instanceof ApiError ? err.message : "Unexpected error");
    } finally {
      setBusy(false);
      setReload((n) => n + 1);
    }
  }

  return (
    <div data-testid="firmware-panel">
      <h3>Firmware</h3>
      {canUpdate && (
        <form className="edit" onSubmit={submit} data-testid="fw-form">
          <label>
            Update to
            <select data-testid="fw-select" required value={choice} onChange={(e) => setChoice(e.target.value)}>
              <option value="">{choices.length ? "Choose a version…" : "No other versions uploaded"}</option>
              {choices.map((f) => (
                <option key={f.id} value={f.id}>{f.version}</option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy || running || !choice} data-testid="fw-start">
            {running ? "Update in progress…" : "Update"}
          </button>
        </form>
      )}
      {error && <div role="alert" className="error" data-testid="fw-error">{error}</div>}
      {updates && updates.length === 0 && <p className="meta" data-testid="fw-none">No firmware updates yet.</p>}
      {updates && updates.length > 0 && (
        <ul className="plain" data-testid="fw-updates">
          {updates.map((u) => (
            <li key={u.id} data-testid={`fw-update-${u.id}`}>
              <span className={`badge badge-fw-${u.status.toLowerCase()}`} data-testid="fw-status">{u.status}</span>{" "}
              <span className="mono" data-testid="fw-versions">{u.from_version ?? "?"} → {u.version}</span>{" "}
              {u.error_message && <span className="low" data-testid="fw-message">{u.error_message}</span>}{" "}
              <span className="meta">by {u.requested_by}, {formatRelative(u.started_at, now)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
