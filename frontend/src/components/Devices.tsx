import { useEffect, useMemo, useRef, useState } from "react";

import { formatNumber, formatRelative } from "../format";
import { type DeviceView, loadView, saveView } from "../prefs";
import type { Sensor } from "../types";
import { DevicesIcon, DropletIcon, GridIcon, ListIcon, PinIcon, SearchIcon } from "./Icons";
import { type SortKey, SensorTable, type SortState } from "./SensorTable";

const LOW_BATTERY = 20;
const FILTERS = ["ALL", "ONLINE", "OFFLINE", "ERROR"] as const;
type Filter = (typeof FILTERS)[number];

interface Props {
  sensors: Sensor[];
  now: number;
  selected: string | null;
  onSelect: (sensorId: string) => void;
}

function sortValue(sensor: Sensor, key: SortKey): string | number {
  switch (key) {
    case "id": return sensor.sensor_id;
    case "temperature": return sensor.latest_telemetry?.temperature ?? -Infinity;
    case "humidity": return sensor.latest_telemetry?.humidity ?? -Infinity;
    case "battery": return sensor.battery ?? -Infinity;
    case "status": return sensor.status;
    case "last_seen": return sensor.last_seen ? Date.parse(sensor.last_seen) : -Infinity;
  }
}

/** How a room feels, from its latest reading: a friendlier summary than two numbers. */
export function comfort(sensor: Sensor): { label: string; tone: string } {
  const t = sensor.latest_telemetry;
  if (!t) return { label: "No data", tone: "muted" };
  if (t.temperature >= 30) return { label: "Hot", tone: "red" };
  if (t.temperature > 26) return { label: "Warm", tone: "orange" };
  if (t.temperature < 10) return { label: "Cold", tone: "blue" };
  if (t.temperature < 18) return { label: "Cool", tone: "teal" };
  if (t.humidity > 65) return { label: "Humid", tone: "blue" };
  if (t.humidity < 30) return { label: "Dry", tone: "yellow" };
  return { label: "Comfortable", tone: "green" };
}

/** The device list with search, status filter, sorting and a list / rooms view. All client-side. */
export function Devices({ sensors, now, selected, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortState | null>(null); // null = API order
  const [view, setView] = useState<DeviceView>(loadView);
  const search = useRef<HTMLInputElement>(null);

  // "/" jumps to the search box, as in many web apps (not while typing somewhere else).
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (event.key !== "/" || target.closest("input, textarea, select, [contenteditable]")) return;
      event.preventDefault();
      search.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { ALL: sensors.length, ONLINE: 0, OFFLINE: 0, ERROR: 0 };
    for (const s of sensors) if (s.status in c) c[s.status as Filter] += 1;
    return c;
  }, [sensors]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = sensors.filter((s) =>
      (filter === "ALL" || s.status === filter) &&
      (!q || [s.sensor_id, s.name, s.location].some((v) => v?.toLowerCase().includes(q))));
    if (sort) {
      const dir = sort.direction === "asc" ? 1 : -1;
      list = [...list].sort((a, b) => {
        const x = sortValue(a, sort.key);
        const y = sortValue(b, sort.key);
        return (x < y ? -1 : x > y ? 1 : 0) * dir;
      });
    }
    return list;
  }, [sensors, query, filter, sort]);

  function toggleSort(key: SortKey) {
    setSort((s) => (s?.key === key ? { key, direction: s.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" }));
  }

  function chooseView(next: DeviceView) {
    setView(next);
    saveView(next);
  }

  if (sensors.length === 0) return <SensorTable sensors={sensors} now={now} selected={selected} onSelect={onSelect} />;

  return (
    <>
      <div className="toolbar">
        <label className="search">
          <SearchIcon size={18} />
          <span className="sr-only">Search devices</span>
          <input ref={search} type="search" placeholder="Search by ID, name or room…" value={query}
                 onChange={(e) => setQuery(e.target.value)} data-testid="device-search" />
          <kbd aria-hidden="true">/</kbd>
        </label>
        <div className="segmented" role="radiogroup" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f} type="button" role="radio" aria-checked={filter === f}
                    className={filter === f ? "on" : undefined} onClick={() => setFilter(f)}
                    data-testid={`filter-${f.toLowerCase()}`}>
              {f === "ALL" ? "All" : f[0] + f.slice(1).toLowerCase()} <span className="count">{counts[f]}</span>
            </button>
          ))}
        </div>
        <div className="segmented" role="radiogroup" aria-label="View">
          <button type="button" role="radio" aria-checked={view === "list"} className={view === "list" ? "on" : undefined}
                  onClick={() => chooseView("list")} data-testid="view-list" title="List">
            <ListIcon size={16} /><span className="sr-only">List</span>
          </button>
          <button type="button" role="radio" aria-checked={view === "grid"} className={view === "grid" ? "on" : undefined}
                  onClick={() => chooseView("grid")} data-testid="view-grid" title="Rooms">
            <GridIcon size={16} /><span className="sr-only">Rooms</span>
          </button>
        </div>
      </div>

      {shown.length < sensors.length && (
        <p className="meta toolbar-note" data-testid="devices-count">Showing {shown.length} of {sensors.length} devices</p>
      )}

      {shown.length === 0 ? (
        <div className="no-match" data-testid="devices-no-match">
          <SearchIcon size={28} />
          <p>No devices match {query.trim() ? `“${query.trim()}”` : "this filter"}.</p>
          <button type="button" className="ghost" onClick={() => { setQuery(""); setFilter("ALL"); }}
                  data-testid="devices-clear">Clear search and filter</button>
        </div>
      ) : view === "list" ? (
        <SensorTable sensors={shown} now={now} selected={selected} onSelect={onSelect} sort={sort} onSort={toggleSort} />
      ) : (
        <div className="device-grid" data-testid="device-grid">
          {shown.map((s) => <DeviceCard key={s.sensor_id} sensor={s} now={now} selected={s.sensor_id === selected}
                                        onSelect={onSelect} />)}
        </div>
      )}
    </>
  );
}

function DeviceCard({ sensor, now, selected, onSelect }: { sensor: Sensor; now: number; selected: boolean;
                                                           onSelect: (id: string) => void }) {
  const t = sensor.latest_telemetry;
  const feel = comfort(sensor);
  const lowBattery = sensor.battery != null && sensor.battery < LOW_BATTERY;
  return (
    <button type="button" className={`device-card${selected ? " selected" : ""}`} aria-pressed={selected}
            onClick={() => onSelect(sensor.sensor_id)} data-testid={`device-card-${sensor.sensor_id}`}>
      <span className="card-top">
        <span className={`device-icon device-${sensor.status.toLowerCase()}`}><DevicesIcon size={18} /></span>
        <span className={`badge badge-${sensor.status.toLowerCase()} dot`}>{sensor.status}</span>
      </span>
      <span className="card-name">{sensor.name || sensor.sensor_id}</span>
      <span className="card-where">
        <PinIcon size={13} /> {sensor.location || "No room set"} · <span className="mono">{sensor.sensor_id}</span>
      </span>
      <span className="card-temp">
        <span key={t?.temperature} className="tick">{t ? t.temperature.toFixed(1) : "—"}</span><small> °C</small>
      </span>
      <span className={`comfort tone-${feel.tone}`}>{feel.label}</span>
      <span className="card-stats">
        <span><DropletIcon size={14} /> {formatNumber(t?.humidity, "%", 0)}</span>
        <span className={lowBattery ? "low" : undefined}>
          <meter className="battery-meter inline" min={0} max={100} low={LOW_BATTERY} high={50} optimum={100}
                 value={sensor.battery ?? 0} aria-hidden="true" />
          {formatNumber(sensor.battery, "%", 0)}
        </span>
        <span className="meta">{formatRelative(sensor.last_seen, now)}</span>
      </span>
    </button>
  );
}
