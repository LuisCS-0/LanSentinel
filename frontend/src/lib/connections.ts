// Estados de una conexión, cuáles cuentan como activas y clave única para listas.

import type { ConnectionStatus, DeviceConnection } from "@/lib/types";

export const CONNECTION_STATUS: Record<ConnectionStatus, { label: string; variant: "success" | "warning" | "secondary" | "outline"; hint: string }> = {
  open: { label: "Abierta", variant: "success", hint: "Conexión en uso" },
  idle: { label: "Inactiva", variant: "warning", hint: "Establecida pero sin tráfico desde hace rato: en reposo o un resto de una conexión ya muerta" },
  pending: { label: "Sin respuesta", variant: "warning", hint: "El otro extremo no ha contestado" },
  done: { label: "Terminada", variant: "outline", hint: "Intercambio suelto ya terminado (una consulta DNS, NTP...); el sistema lo recuerda unos segundos" },
  closing: { label: "Cerrándose", variant: "secondary", hint: "Conexión TCP en proceso de cierre" },
};

// Lo que se muestra por defecto: lo que está vivo o merece atención
export const ACTIVE_STATUSES: ConnectionStatus[] = ["open", "idle", "pending"];

export function isActive(c: { status: ConnectionStatus }): boolean {
  return ACTIVE_STATUSES.includes(c.status);
}

// "ahora", "12 s", "5 min", "3 h", "2 d"
export function formatIdle(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 5) return "ahora";
  if (seconds < 60) return `hace ${seconds} s`;
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`;
  return `hace ${Math.floor(seconds / 86400)} d`;
}

// Servicio de una conexión: su nombre (HTTPS, DNS...) o, si no se conoce,
// protocolo/puerto del lado que ofrece el servicio ("tcp/3000")
export function serviceKey(c: DeviceConnection): string {
  const port = c.direction === "outgoing" ? c.remote_port : c.local_port;
  return c.service ?? (port != null ? `${c.protocol}/${port}` : c.protocol);
}

export function connectionKey(c: DeviceConnection & { device_id?: string }) {
  return `${c.device_id ?? ""}-${c.protocol}-${c.direction}-${c.local_port}-${c.remote_ip}-${c.remote_port}`;
}
