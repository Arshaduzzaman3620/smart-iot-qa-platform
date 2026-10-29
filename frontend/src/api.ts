import type { Alert, Sensor, Session, Telemetry } from "./types";

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
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the API");
  }
  if (response.status === 401) throw new AuthError(await detail(response, "Session expired"));
  if (response.status === 503) throw new ApiError("Database unavailable");
  // The dev proxy answers 500/502/504 itself when FastAPI is not running.
  if (response.status >= 500) throw new ApiError("Cannot reach the API");
  if (!response.ok) throw new ApiError(await detail(response, `API error ${response.status}`));
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
