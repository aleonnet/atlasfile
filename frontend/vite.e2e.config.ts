// Config temporária de E2E: espelho da vite.config.ts com cacheDir separado
// (dois dev servers no mesmo node_modules/.vite misturam hashes de deps e
// quebram os hooks do React) e proxy para o backend E2E. Não usada pelo build.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  cacheDir: "node_modules/.vite-e2e",
  server: {
    proxy: {
      "/api": "http://localhost:8023",
      "/health": "http://localhost:8023",
    },
  },
});
