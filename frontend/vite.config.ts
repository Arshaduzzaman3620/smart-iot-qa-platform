import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard calls /api/*; in dev, Vite forwards that to FastAPI so no CORS setup is needed.
const apiTarget = process.env.VITE_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});
