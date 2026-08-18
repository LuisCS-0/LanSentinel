// Tabla principal de dispositivos. Encapsula el renderizado de la lista,
// los badges de estado y los callbacks de acción para que la página
// quede más legible.

import { Shield, ShieldOff, Ban, ScanLine, Eye } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/dates";
import { TrafficCell } from "@/components/TrafficCell";
import type { Device } from "@/lib/types";

interface DeviceTableProps {
  devices: Device[];
  onTrust: (device: Device) => void;
  onBlock: (device: Device) => void;
  onScan: (device: Device) => void;
  onView: (device: Device) => void;
  scanningId?: string | null;
}

export function DeviceTable({
  devices, onTrust, onBlock, onScan, onView, scanningId,
}: DeviceTableProps) {
  if (devices.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>No hay dispositivos para mostrar.</p>
        <p className="text-sm mt-1">
          Los dispositivos aparecerán según los descubra el sistema.
        </p>
      </div>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left">
            <th className="px-4 py-3 font-medium">Dispositivo</th>
            <th className="px-4 py-3 font-medium">IP / MAC</th>
            <th className="px-4 py-3 font-medium">Estado</th>
            <th className="px-4 py-3 font-medium">Tráfico</th>
            <th className="px-4 py-3 font-medium">Visto</th>
            <th className="px-4 py-3 font-medium text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {devices.map(device => (
            <tr
              key={device.id}
              className="border-t hover:bg-muted/30 transition-colors"
            >
              <td className="px-4 py-3">
                <div className="font-medium">
                  {device.hostname || device.vendor || "Dispositivo desconocido"}
                </div>
                {device.vendor && device.hostname && (
                  <div className="text-xs text-muted-foreground">{device.vendor}</div>
                )}
              </td>
              <td className="px-4 py-3 font-mono text-xs">
                <div>{device.ip || "—"}</div>
                <div className="text-muted-foreground">{device.mac}</div>
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-1.5">
                  {device.is_trusted && (
                    <Badge variant="success" className="gap-1">
                      <Shield className="h-3 w-3" />
                      Confiable
                    </Badge>
                  )}
                  {device.is_blocked && (
                    <Badge variant="destructive" className="gap-1">
                      <Ban className="h-3 w-3" />
                      Bloqueado
                    </Badge>
                  )}
                  {!device.is_trusted && !device.is_blocked && (
                    <span className="text-xs text-muted-foreground">Sin marcar</span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3">
                <TrafficCell deviceId={device.id} />
              </td>
              <td className="px-4 py-3 text-xs text-muted-foreground">
                {relativeTime(device.last_seen)}
              </td>
              <td className="px-4 py-3">
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onView(device)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onScan(device)}
                    disabled={scanningId === device.id}
                    className={cn(scanningId === device.id && "animate-pulse")}
                  >
                    <ScanLine className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onTrust(device)}
                    title={device.is_trusted ? "Quitar confianza" : "Marcar como confiable"}
                  >
                    {device.is_trusted
                      ? <ShieldOff className="h-4 w-4" />
                      : <Shield className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onBlock(device)}
                    title={device.is_blocked ? "Desbloquear" : "Bloquear"}
                  >
                    <Ban className={cn(
                      "h-4 w-4",
                      device.is_blocked && "text-red-600"
                    )} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}