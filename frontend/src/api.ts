import type { Alert, Command, CommandName, Firmware, FirmwareUpdate, Role, Sensor, Session, Telemetry, User } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {}
/** 401: the token is missing, expired, or the user no longer exists. The app signs out. */
export class AuthError extends ApiError {}

let token: string | null = null;

export function setToken(next: string | null): void {
  token = next;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the API");
  }
  if (response.status === 401) throw new AuthError(await detail(response, "Session expired"));
  // 503 is "Database unavailable", or "MQTT broker unreachable" for a command.
  if (response.status === 503) throw new ApiError(await detail(response, "Database unavailable"));
  // The dev proxy answers 500/502/504 itself when FastAPI is not running.
  if (response.status >= 500) throw new ApiError("Cannot reach the API");
  if (!response.ok) throw new ApiError(await detail(response, `API error ${response.status}`));
  // 204 No Content (e.g. DELETE /users/x) has no body to parse.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** The API's own message ({"detail": "..."}), or `fallback` when there is none. */
async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // not JSON
  }
  return fallback;
}

export function login(username: string, password: string): Promise<Session> {
  return request<Session>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
}

export function fetchSensors(signal?: AbortSignal): Promise<Sensor[]> {
  return request<Sensor[]>("/sensors", { signal });
}

export function fetchActiveAlerts(signal?: AbortSignal): Promise<Alert[]> {
  return request<Alert[]>("/alerts?status=ACTIVE", { signal });
}

export function fetchTelemetry(sensorId: string, limit: number, signal?: AbortSignal): Promise<Telemetry[]> {
  return request<Telemetry[]>(`/sensors/${encodeURIComponent(sensorId)}/telemetry?limit=${limit}`, { signal });
}

export function fetchSensorAlerts(sensorId: string, limit: number, signal?: AbortSignal): Promise<Alert[]> {
  return request<Alert[]>(`/sensors/${encodeURIComponent(sensorId)}/alerts?limit=${limit}`, { signal });
}

export function updateSensor(sensorId: string, changes: { name?: string; location?: string }): Promise<Sensor> {
  return request<Sensor>(`/sensors/${encodeURIComponent(sensorId)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function fetchCommands(sensorId: string, limit: number, signal?: AbortSignal): Promise<Command[]> {
  return request<Command[]>(`/sensors/${encodeURIComponent(sensorId)}/commands?limit=${limit}`, { signal });
}

export function sendCommand(sensorId: string, command: CommandName, interval?: number): Promise<Command> {
  return request<Command>(`/sensors/${encodeURIComponent(sensorId)}/commands`, {
    method: "POST",
    body: JSON.stringify(command === "SET_INTERVAL" ? { command, interval } : { command }),
  });
}

export function fetchFirmware(signal?: AbortSignal): Promise<Firmware[]> {
  return request<Firmware[]>("/firmware", { signal });
}

export function uploadFirmware(version: string, file: File): Promise<Firmware> {
  const query = new URLSearchParams({ version, filename: file.name });
  return request<Firmware>(`/firmware?${query}`, {
    method: "POST",
    body: file,
    headers: { "Content-Type": "application/octet-stream" },
  });
}

export function fetchFirmwareUpdates(sensorId: string, limit: number, signal?: AbortSignal): Promise<FirmwareUpdate[]> {
  return request<FirmwareUpdate[]>(`/sensors/${encodeURIComponent(sensorId)}/firmware-updates?limit=${limit}`, { signal });
}

export function startFirmwareUpdate(sensorId: string, firmwareId: number): Promise<FirmwareUpdate> {
  return request<FirmwareUpdate>(`/sensors/${encodeURIComponent(sensorId)}/firmware-updates`, {
    method: "POST",
    body: JSON.stringify({ firmware_id: firmwareId }),
  });
}

// ---- users (ADMIN only, Phase 18 screen) ----

export function fetchUsers(signal?: AbortSignal): Promise<User[]> {
  return request<User[]>("/users", { signal });
}

export function createUser(username: string, password: string, role: Role): Promise<User> {
  return request<User>("/users", { method: "POST", body: JSON.stringify({ username, password, role }) });
}

export function deleteUser(username: string): Promise<void> {
  return request<void>(`/users/${encodeURIComponent(username)}`, { method: "DELETE" });
}
