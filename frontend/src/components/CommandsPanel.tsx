import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, fetchCommands, sendCommand } from "../api";
import { formatRelative } from "../format";
import type { Command, CommandName } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { PulseIcon, RestartIcon } from "./Icons";
import { useToast } from "./Toast";

const HISTORY_ROWS = 10;
// While a command is still SENT, check for its outcome this often.
const PENDING_POLL_MS = 1000;

interface Props {
  sensorId: string;
  now: number;
  canSend: boolean;
  onAuthError: (err: AuthError) => void;
}

function describe(command: Command): string {
  return command.command === "SET_INTERVAL" ? `SET_INTERVAL ${command.params.interval} s` : command.command;
}

export function CommandsPanel({ sensorId, now, canSend, onAuthError }: Props) {
  const [commands, setCommands] = useState<Command[] | null>(null);
  const [interval, setInterval_] = useState("10");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const toast = useToast();
  const pending = commands?.some((c) => c.status === "SENT") ?? false;

  useEffect(() => {
    const controller = new AbortController();
    fetchCommands(sensorId, HISTORY_ROWS, controller.signal)
      .then((next) => setCommands(next))
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return onAuthError(err);
        setError(err instanceof ApiError ? err.message : "Unexpected error");
      });
    return () => controller.abort();
  }, [sensorId, reload, onAuthError]);

  // Poll only while something is waiting for the sensor's answer.
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => setReload((n) => n + 1), PENDING_POLL_MS);
    return () => clearTimeout(timer);
  }, [pending, commands]);

  async function send(command: CommandName, seconds?: number) {
    setBusy(true);
    setError(null);
    try {
      await sendCommand(sensorId, command, seconds);
      toast(command === "SET_INTERVAL" ? `Interval ${seconds} s sent to ${sensorId}`
            : `${command === "RESTART" ? "Restart" : "Reading request"} sent to ${sensorId}`);
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err);
      setError(err instanceof ApiError ? err.message : "Unexpected error");
    } finally {
      setBusy(false);
      setReload((n) => n + 1); // a failed send is recorded too
    }
  }

  function submitInterval(event: FormEvent) {
    event.preventDefault();
    send("SET_INTERVAL", Number(interval));
  }

  return (
    <div data-testid="commands">
      <h3>Commands</h3>
      {canSend && (
        <div className="edit">
          <button type="button" disabled={busy} onClick={() => send("REQUEST_TELEMETRY")} data-testid="cmd-request">
            <PulseIcon size={16} /> Request reading
          </button>
          {/* A restart takes the device offline for a few seconds: ask first. */}
          <button type="button" disabled={busy} onClick={() => setConfirmRestart(true)} data-testid="cmd-restart">
            <RestartIcon size={16} /> Restart
          </button>
          <form className="inline" onSubmit={submitInterval}>
            <label>
              Interval (s)
              <input data-testid="cmd-interval-value" type="number" min={1} max={3600} step={1} required
                     value={interval} onChange={(e) => setInterval_(e.target.value)} />
            </label>
            <button type="submit" disabled={busy} data-testid="cmd-interval">Set interval</button>
          </form>
        </div>
      )}
      <ConfirmDialog open={confirmRestart} title={`Restart ${sensorId}?`}
                     message="The device goes offline for a few seconds and misses readings meanwhile."
                     confirmLabel="Restart device" onCancel={() => setConfirmRestart(false)}
                     onConfirm={() => { setConfirmRestart(false); send("RESTART"); }} />
      {error && <div role="alert" className="error" data-testid="cmd-error">{error}</div>}
      {commands && commands.length === 0 && <p className="meta" data-testid="commands-empty">No commands yet.</p>}
      {commands && commands.length > 0 && (
        <ul className="plain" data-testid="command-list">
          {commands.map((c) => (
            <li key={c.id} data-testid={`command-${c.id}`}>
              <span className={`badge badge-cmd-${c.status.toLowerCase()}`} data-testid="command-status">
                {c.status}
              </span>{" "}
              <span className="mono" data-testid="command-name">{describe(c)}</span>{" "}
              {c.message && <span data-testid="command-message">{c.message}</span>}{" "}
              <span className="meta">by {c.requested_by}, {formatRelative(c.created_at, now)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
