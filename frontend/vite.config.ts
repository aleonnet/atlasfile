import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: true,
    // Dev only: permite testar contra a API local sem CORS (VITE_API_URL same-origin)
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000"
    }
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"]
  }
});
