import type { Sensor } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {}

export async function fetchSensors(signal?: AbortSignal): Promise<Sensor[]> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/sensors`, { signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the API");
  }
  if (response.status === 503) throw new ApiError("Database unavailable");
  // The dev proxy answers 500/502/504 itself when FastAPI is not running.
  if (response.status >= 500) throw new ApiError("Cannot reach the API");
  if (!response.ok) throw new ApiError(`API error ${response.status}`);
  return (await response.json()) as Sensor[];
}
