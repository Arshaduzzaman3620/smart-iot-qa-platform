// Mirrors backend/app/schemas.py. Datetimes are UTC ISO 8601 strings ending in "Z".

export interface Telemetry {
  id: number;
  sensor_id: string;
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  light: number;
  battery: number;
  received_at: string;
}

export interface Sensor {
  sensor_id: string;
  sensor_type: string;
  name: string | null;
  location: string | null;
  // ONLINE / OFFLINE / ERROR (later CONNECTING / UPDATING)
  status: string;
  firmware_version: string | null;
  battery: number | null;
  last_seen: string | null;
  created_at: string;
  updated_at: string;
  latest_telemetry: Telemetry | null;
}
