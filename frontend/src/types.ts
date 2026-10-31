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
  active_alerts: number;
}

export interface Alert {
  id: number;
  sensor_id: string;
  // LOW_BATTERY / HIGH_TEMPERATURE / LOW_TEMPERATURE / HIGH_HUMIDITY / OFFLINE
  alert_type: string;
  severity: "WARNING" | "CRITICAL";
  value: number | null;
  message: string | null;
  status: "ACTIVE" | "RESOLVED";
  created_at: string;
  resolved_at: string | null;
}

export type Role = "VIEWER" | "OPERATOR" | "ADMIN";

export interface User {
  username: string;
  role: Role;
  created_at: string;
}

/** POST /auth/login response, kept for the browser session. */
export interface Session {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type CommandName = "RESTART" | "REQUEST_TELEMETRY" | "SET_INTERVAL";

export interface Command {
  id: number;
  sensor_id: string;
  command: CommandName;
  params: { interval?: number };
  // SENT until the sensor answers (SUCCEEDED / FAILED) or COMMAND_TIMEOUT passes (TIMED_OUT)
  status: "SENT" | "SUCCEEDED" | "FAILED" | "TIMED_OUT";
  message: string | null;
  requested_by: string;
  created_at: string;
  completed_at: string | null;
}
