import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Dirección del backend para el proxy de desarrollo. En docker-compose.dev.yml
// se fija a host.docker.internal; fuera de Docker, por defecto localhost.
const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000';

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