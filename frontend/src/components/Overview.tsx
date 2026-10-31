import type { ReactNode } from "react";

import type { Alert, Sensor } from "../types";
import { BatteryIcon, BellIcon, DropletIcon, ThermometerIcon, WifiIcon } from "./Icons";

const LOW_BATTERY = 20;

interface Props {
  sensors: Sensor[];
  alerts: Alert[] | null;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : null;
}

/** The home at a glance: tiles computed from the sensor list, no extra API calls. */
export function Overview({ sensors, alerts }: Props) {
  const online = sensors.filter((s) => s.status === "ONLINE").length;
  const readings = sensors.map((s) => s.latest_telemetry).filter((t) => t != null);
  const temperature = average(readings.map((t) => t.temperature));
  const humidity = average(readings.map((t) => t.humidity));
  const lowBattery = sensors.filter((s) => s.battery != null && s.battery < LOW_BATTERY).length;
  const critical = alerts?.filter((a) => a.severity === "CRITICAL").length ?? 0;

  return (
    <section className="overview" aria-label="Overview">
      <Tile tone="green" icon={<WifiIcon />} label="Devices online"
            value={<>{online}<small> / {sensors.length}</small></>}
            hint={sensors.length ? `${Math.round((online / sensors.length) * 100)} % connected` : "No devices yet"} />
      <Tile tone="orange" icon={<ThermometerIcon />} label="Avg. temperature"
            value={temperature == null ? "—" : <>{temperature.toFixed(1)}<small> °C</small></>}
            hint={`across ${readings.length} reporting`} />
      <Tile tone="blue" icon={<DropletIcon />} label="Avg. humidity"
            value={humidity == null ? "—" : <>{humidity.toFixed(0)}<small> %</small></>}
            hint="relative humidity" />
      <Tile tone={alerts?.length ? "red" : "violet"} icon={<BellIcon />} label="Active alerts"
            value={alerts == null ? "—" : alerts.length}
            hint={critical ? `${critical} critical` : alerts?.length ? "warnings only" : "all clear"} />
      <Tile tone={lowBattery ? "red" : "teal"} icon={<BatteryIcon />} label="Low battery"
            value={lowBattery} hint={`below ${LOW_BATTERY} %`} />
    </section>
  );
}

interface TileProps {
  tone: string;
  icon: ReactNode;
  label: string;
  value: ReactNode;
  hint: string;
}

function Tile({ tone, icon, label, value, hint }: TileProps) {
  return (
    <div className={`tile tone-${tone}`}>
      <span className="tile-icon">{icon}</span>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}</span>
      <span className="tile-hint">{hint}</span>
    </div>
  );
}
