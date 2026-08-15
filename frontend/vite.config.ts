import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Respeta PORT si viene del entorno: si el 5173 esta ocupado, arrancar en
    // otro puerto es mejor que no arrancar.
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    // El backend se sirve bajo /api, asi que en desarrollo se proxyfica y el
    // frontend puede usar rutas relativas: ni CORS ni URLs absolutas en el codigo.
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
});
