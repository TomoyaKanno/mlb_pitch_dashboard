import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI app serves the built bundle in production. In dev, `npm run dev`
// starts Vite with hot-reload and proxies API traffic to the running FastAPI
// server so the frontend and backend feel like one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
