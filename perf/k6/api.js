// API load test (Phase 15g). Each virtual user is a dashboard tab: it refreshes the sensor list and
// active alerts, and looks at one sensor's recent readings, then waits like the 5 s refresh does.
//
//   docker compose --profile perf run --rm k6 run -e PROFILE=load /scripts/api.js
//
// PROFILE: smoke (default) | load | stress | spike | soak. Results: docs/testing/performance.md.
import http from "k6/http";
import { check, sleep } from "k6";

const API = __ENV.API_URL || "http://api:8000";
const THINK = Number(__ENV.THINK_SECONDS || 1); // pause between refreshes (the real dashboard waits 5 s)

const PROFILES = {
  smoke: { executor: "constant-vus", vus: 1, duration: "30s" },
  // 50 dashboards refreshing every second: ~10x the polling 50 people would cause at 5 s.
  load: { executor: "constant-vus", vus: 50, duration: "2m" },
  stress: {
    executor: "ramping-vus", startVUs: 0,
    stages: [{ duration: "1m", target: 100 }, { duration: "1m", target: 200 }, { duration: "1m", target: 300 },
             { duration: "30s", target: 0 }],
  },
  spike: {
    executor: "ramping-vus", startVUs: 10,
    stages: [{ duration: "30s", target: 10 }, { duration: "10s", target: 300 }, { duration: "30s", target: 300 },
             { duration: "10s", target: 10 }, { duration: "30s", target: 10 }],
  },
  soak: { executor: "constant-vus", vus: 20, duration: __ENV.SOAK_DURATION || "10m" },
};

const profile = __ENV.PROFILE || "smoke";
if (!PROFILES[profile]) throw new Error(`unknown PROFILE ${profile}`);

export const options = {
  scenarios: { [profile]: PROFILES[profile] },
  thresholds: {
    // Pass/fail criteria for smoke, load and soak; stress and spike are run to find the limits.
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:sensors}": ["p(95)<300"],
    "http_req_duration{name:alerts}": ["p(95)<300"],
    "http_req_duration{name:telemetry}": ["p(95)<300"],
  },
  summaryTrendStats: ["avg", "med", "p(95)", "p(99)", "max"],
};

export function setup() {
  // Sign in once: logging in per iteration would measure scrypt (and trip the login rate limit).
  const res = http.post(`${API}/auth/login`,
    JSON.stringify({ username: __ENV.API_USER || "admin", password: __ENV.API_PASSWORD || "admin-dev-password" }),
    { headers: { "Content-Type": "application/json" } });
  check(res, { "logged in": (r) => r.status === 200 }) || fail_(`login failed: ${res.status} ${res.body}`);
  const headers = { Authorization: `Bearer ${res.json("access_token")}` };
  const sensors = http.get(`${API}/sensors`, { headers }).json().map((s) => s.sensor_id);
  if (!sensors.length) fail_("no sensors: start the simulator first");
  return { headers, sensors };
}

function fail_(message) {
  throw new Error(message);
}

export default function ({ headers, sensors }) {
  const params = (name) => ({ headers, tags: { name } });
  const list = http.get(`${API}/sensors`, params("sensors"));
  check(list, { "sensors 200": (r) => r.status === 200 });
  const alerts = http.get(`${API}/alerts?status=ACTIVE`, params("alerts"));
  check(alerts, { "alerts 200": (r) => r.status === 200 });
  const id = sensors[Math.floor(Math.random() * sensors.length)];
  const history = http.get(`${API}/sensors/${id}/telemetry?limit=20`, params("telemetry"));
  check(history, { "telemetry 200": (r) => r.status === 200 });
  sleep(THINK);
}
