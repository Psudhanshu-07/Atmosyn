/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // @ts-expect-error vitest config augmentation
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    proxy: {
      // Backend uvicorn default port (matches .env.example / docker-compose).
      "/api": "http://localhost:8000",
    },
  },
});
