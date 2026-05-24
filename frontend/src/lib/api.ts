import axios from "axios";

// El proxy de Vite redirige /api al backend (configurado en vite.config.ts).
// En producción ajustar la baseURL a la dirección real del backend.
export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Helper de error handling: extrae mensajes legibles de respuestas de FastAPI
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.message) return error.message;
  }
  return "Error desconocido";
}
