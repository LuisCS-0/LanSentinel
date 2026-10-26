import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Dirección del backend para el proxy de desarrollo. El backend solo escucha
// en 127.0.0.1 (red del equipo), igual dentro que fuera de Docker.
const backendUrl = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
     '/api': {
       target: backendUrl,
       changeOrigin: true,
     },
     '/health': {
       target: backendUrl,
       changeOrigin: true,
     },
    },
  },
});