import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend local : le proxy /api pointe vers FastAPI (127.0.0.1:8000).
// En production, le build est servi par FastAPI lui-même (même origine).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
