// Sección "Conexiones" del detalle de un dispositivo: lo que tiene abierto
// ahora mismo según la tabla conntrack del gateway. Se refresca cada 5 s.
// Las conexiones que se están cerrando (TIME_WAIT...) se ocultan por defecto
// porque suelen ser la mayoría y no aportan mucho.

import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDeviceConnections } from "@/hooks/useDevices";
import type { ConnectionStatus, DeviceConnection } from "@/lib/types";

// Filas que se pintan como mucho; un equipo con muchas conexiones (p. ej. un
// cliente P2P) haría el diálogo interminable
const MAX_ROWS = 50;

const STATUS_BADGE: Record<ConnectionStatus, { label: string; variant: "success" | "warning" | "secondary" }> = {
  open: { label: "Abierta", variant: "success" },
  pending: { label: "Sin respuesta", variant: "warning" },
  closing: { label: "Cerrándose", variant: "secondary" },
};

function connectionKey(c: DeviceConnection) {
  return `${c.protocol}-${c.direction}-${c.local_port}-${c.remote_ip}-${c.remote_port}`;
}

export function DeviceConnections({ deviceId }: { deviceId: string }) {
  const query = useDeviceConnections(deviceId);
  const [showClosing, setShowClosing] = useState(false);

  const all = query.data?.connections ?? [];
  const closingCount = all.filter(c => c.status === "closing").length;
  const openCount = all.filter(c => c.status === "open").length;
  const visible = showClosing ? all : all.filter(c => c.status !== "closing");

  return (
    <div className="mt-4 pb-4 border-b">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h3 className="font-medium text-sm">Conexiones</h3>
          <p className="text-xs text-muted-foreground">
            {query.data?.available
              ? `${openCount} abiertas · ${all.length} en total · se actualiza cada 5 s`
              : "Lo que el dispositivo tiene abierto ahora mismo"}
          </p>
        </div>
        {closingCount > 0 && (
          <Button variant="outline" size="sm" onClick={() => setShowClosing(v => !v)}>
            {showClosing ? "Ocultar cerradas" : `Mostrar cerradas (${closingCount})`}
          </Button>
        )}
      </div>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground text-center py-6">Cargando conexiones…</p>
      ) : query.isError || !query.data ? (
        <p className="text-sm text-destructive text-center py-6">No se pudieron cargar las conexiones.</p>
      ) : !query.data.available ? (
        <p className="text-sm text-muted-foreground text-center py-6">
          El backend no puede leer la tabla de conexiones (falta la herramienta
          conntrack o el permiso NET_ADMIN).
        </p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-6">
          {all.length === 0
            ? "No hay conexiones activas que pasen por LanSentinel."
            : "Solo hay conexiones que se están cerrando."}
        </p>
      ) : (
        <div className="border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Otro extremo</th>
                <th className="px-3 py-2 text-left font-medium">Servicio</th>
                <th className="px-3 py-2 text-left font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {visible.slice(0, MAX_ROWS).map(c => {
                const status = STATUS_BADGE[c.status];
                const port = c.direction === "outgoing" ? c.remote_port : c.local_port;
                return (
                  <tr key={connectionKey(c)} className="border-t">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        {c.direction === "outgoing" ? (
                          <ArrowUpRight className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" aria-label="Saliente" />
                        ) : (
                          <ArrowDownLeft className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" aria-label="Entrante" />
                        )}
                        <span className="font-mono text-xs">
                          {c.remote_ip}
                          {c.remote_port != null && `:${c.remote_port}`}
                        </span>
                        {c.remote_is_lan && <Badge variant="outline" className="text-[10px]">LAN</Badge>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {c.service ?? "—"}
                      <span className="text-muted-foreground">
                        {" "}· {c.protocol}{port != null && `/${port}`}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={status.variant} className="text-xs" title={c.state ?? undefined}>
                        {status.label}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {visible.length > MAX_ROWS && (
            <p className="px-3 py-2 border-t text-xs text-muted-foreground">
              Y {visible.length - MAX_ROWS} más.
            </p>
          )}
        </div>
      )}

      <p className="mt-2 text-xs text-muted-foreground">
        Solo aparecen las conexiones que pasan por LanSentinel (hacia Internet o
        hacia este equipo); el tráfico directo entre equipos de la LAN no se ve.
      </p>
    </div>
  );
}
