import { formatNumber, formatRelative } from "../format";
import type { Sensor } from "../types";
import { DevicesIcon } from "./Icons";

const LOW_BATTERY = 20;

export type SortKey = "id" | "temperature" | "humidity" | "battery" | "status" | "last_seen";
export interface SortState { key: SortKey; direction: "asc" | "desc" }

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "id", label: "Sensor ID" },
  { key: "temperature", label: "Temperature", numeric: true },
  { key: "humidity", label: "Humidity", numeric: true },
  { key: "battery", label: "Battery", numeric: true },
  { key: "status", label: "Status" },
  { key: "last_seen", label: "Last seen" },
];

interface Props {
  sensors: Sensor[];
  now: number;
  selected: string | null;
  onSelect: (sensorId: string) => void;
  sort?: SortState | null;
  onSort?: (key: SortKey) => void;
}

export function SensorTable({ sensors, now, selected, onSelect, sort = null, onSort }: Props) {
  if (sensors.length === 0) {
    return (
      <p className="empty" data-testid="sensors-empty">
        No sensors have reported yet. Start the sensor simulator and receiver.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table data-testid="sensor-table">
        <thead>
          <tr>
            {COLUMNS.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th key={c.key} scope="col" className={c.numeric ? "num" : undefined}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}>
                  {onSort ? (
                    <button type="button" className="sort" onClick={() => onSort(c.key)} data-testid={`sort-${c.key}`}>
                      {c.label}
                    </button>
                  ) : c.label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sensors.map((sensor) => {
            const t = sensor.latest_telemetry;
            const lowBattery = sensor.battery != null && sensor.battery < LOW_BATTERY;
            return (
              <tr key={sensor.sensor_id} data-testid={`sensor-row-${sensor.sensor_id}`}
                  className={sensor.sensor_id === selected ? "selected" : undefined}>
                <td>
                  <div className="device-cell">
                    <span className={`device-icon device-${sensor.status.toLowerCase()}`}><DevicesIcon size={18} /></span>
                    <div className="device-text">
                      <button type="button" className="link mono device-id" data-testid="sensor-id"
                              aria-pressed={sensor.sensor_id === selected} onClick={() => onSelect(sensor.sensor_id)}>
                        {sensor.sensor_id}
                      </button>
                      {(sensor.name || sensor.location) && (
                        <span className="device-sub">{[sensor.name, sensor.location].filter(Boolean).join(" · ")}</span>
                      )}
                    </div>
                  </div>
                </td>
                {/* key = value: the span is re-created when the reading changes, which replays its highlight. */}
                <td data-testid="temperature" className="num">
                  <span key={t?.temperature} className="tick">{formatNumber(t?.temperature, "°C")}</span>
                </td>
                <td data-testid="humidity" className="num">
                  <span key={t?.humidity} className="tick">{formatNumber(t?.humidity, "%")}</span>
                </td>
                <td data-testid="battery" className={lowBattery ? "num low" : "num"}>
                  {formatNumber(sensor.battery, "%")}
                  {sensor.battery != null && (
                    <meter className="battery-meter" min={0} max={100} low={LOW_BATTERY} high={50} optimum={100}
                           value={sensor.battery} aria-hidden="true" />
                  )}
                </td>
                <td>
                  <span data-testid="status" className={`badge badge-${sensor.status.toLowerCase()}`}>
                    {sensor.status}
                  </span>
                </td>
                <td data-testid="last-seen" title={sensor.last_seen ?? undefined}>
                  {formatRelative(sensor.last_seen, now)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
