// Estados de una conexión y clave única para listas.

import type { ConnectionStatus, DeviceConnection } from "@/lib/types";

export const CONNECTION_STATUS: Record<ConnectionStatus, { label: string; variant: "success" | "warning" | "secondary" }> = {
  open: { label: "Abierta", variant: "success" },
  pending: { label: "Sin respuesta", variant: "warning" },
  closing: { label: "Cerrándose", variant: "secondary" },
};

export function connectionKey(c: DeviceConnection & { device_id?: string }) {
  return `${c.device_id ?? ""}-${c.protocol}-${c.direction}-${c.local_port}-${c.remote_ip}-${c.remote_port}`;
}
