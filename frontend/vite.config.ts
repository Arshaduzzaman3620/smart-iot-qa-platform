import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard calls /api/*; in dev, Vite forwards that to FastAPI so no CORS setup is needed.
// 127.0.0.1 rather than localhost: the API listens on IPv4 only, and "localhost" may resolve to ::1 first.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});
