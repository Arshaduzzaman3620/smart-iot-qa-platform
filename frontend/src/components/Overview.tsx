import { type ReactNode, useEffect, useRef, useState } from "react";

import type { Alert, Sensor } from "../types";
import { BatteryIcon, BellIcon, DropletIcon, HomeIcon, ThermometerIcon, WifiIcon } from "./Icons";

const LOW_BATTERY = 20;

interface Props {
  sensors: Sensor[];
  alerts: Alert[] | null;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : null;
}

/** The home at a glance: a status banner and tiles, computed from the sensor list (no extra API calls). */
export function Overview({ sensors, alerts }: Props) {
  const online = sensors.filter((s) => s.status === "ONLINE").length;
  const offline = sensors.length - online;
  const readings = sensors.map((s) => s.latest_telemetry).filter((t) => t != null);
  const temperature = average(readings.map((t) => t.temperature));
  const humidity = average(readings.map((t) => t.humidity));
  const lowBattery = sensors.filter((s) => s.battery != null && s.battery < LOW_BATTERY).length;
  const critical = alerts?.filter((a) => a.severity === "CRITICAL").length ?? 0;
  const alertCount = alerts?.length ?? 0;

  // One sentence a person can act on, most urgent first.
  const [tone, headline, detail] =
    critical ? ["critical", `${critical} critical ${critical === 1 ? "alert needs" : "alerts need"} attention`,
                "Check the alerts below and the affected devices."]
    : alertCount ? ["warning", `${alertCount} ${alertCount === 1 ? "warning" : "warnings"} to look at`,
                    "Nothing critical, but some devices need a look."]
    : offline ? ["warning", `${offline} of ${sensors.length} devices offline`, "The rest of your home is reporting normally."]
    : sensors.length ? ["ok", "Everything is running smoothly", `All ${sensors.length} devices are online and within range.`]
    : ["ok", "No devices yet", "Start the sensor simulator to see your home come alive."];

  return (
    <section className="overview-wrap" aria-label="Overview">
      <div className={`hero hero-${tone}`} data-testid="home-status">
        <span className="hero-icon"><HomeIcon size={26} /></span>
        <div className="hero-text">
          <span className="hero-kicker">Home status</span>
          <strong data-testid="home-status-headline">{headline}</strong>
          <span>{detail}</span>
        </div>
        {temperature != null && (
          <div className="hero-climate" aria-label="Average indoor climate">
            <span><ThermometerIcon size={18} /> <Count value={temperature} digits={1} /> °C</span>
            <span><DropletIcon size={18} /> <Count value={humidity ?? 0} /> %</span>
          </div>
        )}
      </div>

      <div className="overview">
        <Tile tone="green" icon={<WifiIcon />} label="Devices online"
              value={<><Count value={online} /><small> / {sensors.length}</small></>}
              hint={sensors.length ? `${Math.round((online / sensors.length) * 100)} % connected` : "No devices yet"}
              progress={sensors.length ? online / sensors.length : 0} />
        <Tile tone="orange" icon={<ThermometerIcon />} label="Avg. temperature"
              value={temperature == null ? "—" : <><Count value={temperature} digits={1} /><small> °C</small></>}
              hint={`across ${readings.length} reporting`} />
        <Tile tone="blue" icon={<DropletIcon />} label="Avg. humidity"
              value={humidity == null ? "—" : <><Count value={humidity} /><small> %</small></>}
              hint="relative humidity" progress={humidity == null ? undefined : humidity / 100} />
        <Tile tone={alertCount ? "red" : "violet"} icon={<BellIcon />} label="Active alerts"
              value={alerts == null ? "—" : <Count value={alertCount} />}
              hint={critical ? `${critical} critical` : alertCount ? "warnings only" : "all clear"} />
        <Tile tone={lowBattery ? "red" : "teal"} icon={<BatteryIcon />} label="Low battery"
              value={<Count value={lowBattery} />} hint={`below ${LOW_BATTERY} %`} />
      </div>
    </section>
  );
}

interface TileProps {
  tone: string;
  icon: ReactNode;
  label: string;
  value: ReactNode;
  hint: string;
  progress?: number;
}

function Tile({ tone, icon, label, value, hint, progress }: TileProps) {
  return (
    <div className={`tile tone-${tone}`}>
      <span className="tile-icon">{icon}</span>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}</span>
      {progress != null && (
        <meter className="tile-meter" min={0} max={1} value={progress} aria-hidden="true" />
      )}
      <span className="tile-hint">{hint}</span>
    </div>
  );
}

const REDUCED_MOTION = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A number that glides to its new value instead of jumping (skipped when the user prefers less motion). */
function Count({ value, digits = 0 }: { value: number; digits?: number }) {
  // Counts up from 0 on first show, then glides between refreshes.
  const [shown, setShown] = useState(REDUCED_MOTION ? value : 0);
  // What is on screen right now, so an interrupted glide continues from there.
  const current = useRef(shown);

  useEffect(() => {
    const begin = current.current;
    if (REDUCED_MOTION || begin === value) {
      current.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const step = (time: number) => {
      const p = Math.min(1, (time - start) / 600);
      current.current = begin + (value - begin) * (1 - (1 - p) ** 3); // ease-out
      setShown(current.current);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <>{shown.toFixed(digits)}</>;
}
