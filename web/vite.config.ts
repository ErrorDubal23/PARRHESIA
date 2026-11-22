import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api va a la puerta de entrada de Docker (http://localhost:8080).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
});
