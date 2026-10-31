import { formatRelative } from "../format";
import type { Alert } from "../types";
import { BellIcon, CheckIcon } from "./Icons";

const SEVERITY_ORDER: Record<string, number> = { CRITICAL: 0, WARNING: 1 };

interface Props {
  alerts: Alert[];
  now: number;
}

export function AlertsPanel({ alerts, now }: Props) {
  if (alerts.length === 0) {
    return (
      <p className="alerts-none" data-testid="alerts-none">
        <CheckIcon />No active alerts.
      </p>
    );
  }

  // CRITICAL first, so it can't scroll out of sight behind many warnings; the API already sorts newest first.
  const sorted = [...alerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 2) - (SEVERITY_ORDER[b.severity] ?? 2));

  return (
    <section className="alerts" aria-labelledby="alerts-heading" data-testid="alerts-panel">
      <h2 id="alerts-heading"><BellIcon size={18} />Active alerts ({alerts.length})</h2>
      <ul>
        {sorted.map((alert) => (
          <li key={alert.id} data-testid={`alert-${alert.id}`} className={`alert-item sev-${alert.severity.toLowerCase()}`}>
            <span data-testid="alert-severity" className={`badge badge-${alert.severity.toLowerCase()}`}>
              {alert.severity}
            </span>
            <span data-testid="alert-sensor" className="mono">{alert.sensor_id}</span>
            <span data-testid="alert-message" className="alert-message">{alert.message ?? alert.alert_type}</span>
            <span data-testid="alert-since" className="meta" title={alert.created_at}>
              {formatRelative(alert.created_at, now)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
