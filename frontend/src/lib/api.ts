import axios from "axios";

// El proxy de Vite (desarrollo) o nginx (producción) redirige /api al
// backend, así que todas las peticiones son al mismo origen y la cookie de
// sesión viaja sola.
export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Evento que se emite cuando el backend responde 401 (sesión caducada o
// cerrada en otro sitio). AuthGate lo escucha y vuelve a la pantalla de login.
export const UNAUTHORIZED_EVENT = "lansentinel:unauthorized";

// Evento de 403: puede que a este usuario le hayan cambiado el rol mientras
// tenía el panel abierto. AuthGate vuelve a preguntar quién es.
export const FORBIDDEN_EVENT = "lansentinel:forbidden";

apiClient.interceptors.response.use(
  response => response,
  error => {
    const url: string = error?.config?.url ?? "";
    // El propio login devuelve 401 con credenciales incorrectas: no es una
    // sesión caducada, lo gestiona el formulario
    if (axios.isAxiosError(error) && error.response?.status === 401 && !url.startsWith("/auth/")) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    if (axios.isAxiosError(error) && error.response?.status === 403) {
      window.dispatchEvent(new Event(FORBIDDEN_EVENT));
    }
    return Promise.reject(error);
  },
);

// Helper de error handling: extrae mensajes legibles de respuestas de FastAPI
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    // Errores de validación de FastAPI: lista de {msg, loc...}
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (error.message) return error.message;
  }
  return "Error desconocido";
}
