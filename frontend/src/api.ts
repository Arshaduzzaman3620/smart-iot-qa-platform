import type { Alert, Sensor } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the API");
  }
  if (response.status === 503) throw new ApiError("Database unavailable");
  // The dev proxy answers 500/502/504 itself when FastAPI is not running.
  if (response.status >= 500) throw new ApiError("Cannot reach the API");
  if (!response.ok) throw new ApiError(`API error ${response.status}`);
  return (await response.json()) as T;
}

export function fetchSensors(signal?: AbortSignal): Promise<Sensor[]> {
  return getJson<Sensor[]>("/sensors", signal);
}

export function fetchActiveAlerts(signal?: AbortSignal): Promise<Alert[]> {
  return getJson<Alert[]>("/alerts?status=ACTIVE", signal);
}
