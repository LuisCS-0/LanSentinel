// Modal de detalle de un dispositivo: información completa, consumo histórico
// y tabla de puertos detectados (si los hay). Se abre desde la tabla principal.

import { useState } from "react";
import { Loader2, ScanLine } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RangeSelector } from "@/components/RangeSelector";
import { UsageChart } from "@/components/UsageChart";
import { useDevicePorts, useScanPorts } from "@/hooks/useDevices";
import { useDeviceUsage } from "@/hooks/useTrafficUsage";
import { relativeTime } from "@/lib/dates";
import { formatBytes } from "@/lib/format";
import type { Device, TrafficRange } from "@/lib/types";

interface DeviceDetailDialogProps {
  device: Device | null;
  onClose: () => void;
}

export function DeviceDetailDialog({ device, onClose }: DeviceDetailDialogProps) {
  const ports = useDevicePorts(device?.id || null);
  const scanMutation = useScanPorts();
  const [range, setRange] = useState<TrafficRange>("24h");
  const usage = useDeviceUsage(device?.id || null, range);

  if (!device) return null;

  // Deduplicar puertos: el backend guarda histórico, mostramos solo el más reciente por puerto
  const latestPorts = Array.from(
    new Map(
      (ports.data || [])
        .sort((a, b) => b.scanned_at.localeCompare(a.scanned_at))
        .map(p => [`${p.port}-${p.protocol}`, p])
    ).values()
  );

  return (
    <Dialog
      open={!!device}
      onClose={onClose}
      title={device.hostname || device.vendor || "Dispositivo"}
      description={`MAC ${device.mac}`}
      className="max-w-2xl"
    >
      {/* Info básica */}
      <div className="grid grid-cols-2 gap-4 text-sm pb-4 border-b">
        <div>
          <p className="text-xs text-muted-foreground">Dirección IP</p>
          <p className="font-mono">{device.ip || "—"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Fabricante</p>
          <p>{device.vendor || "Desconocido"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Última vez visto</p>
          <p>{relativeTime(device.last_seen)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Estado</p>
          <div className="flex gap-1.5 mt-1">
            {device.is_trusted && <Badge variant="success">Confiable</Badge>}
            {device.is_blocked && <Badge variant="destructive">Bloqueado</Badge>}
            {!device.is_trusted && !device.is_blocked && (
              <span className="text-xs text-muted-foreground">Sin marcar</span>
            )}
          </div>
        </div>
      </div>

      {/* Consumo histórico */}
      <div className="mt-4 pb-4 border-b">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h3 className="font-medium text-sm">Consumo</h3>
            {usage.data && (
              <p className="text-xs text-muted-foreground">
                Descarga {formatBytes(usage.data.total_recv)} · Subida {formatBytes(usage.data.total_sent)}
              </p>
            )}
          </div>
          <RangeSelector value={range} onChange={setRange} />
        </div>
        {usage.isLoading ? (
          <p className="text-sm text-muted-foreground text-center py-6">Cargando consumo…</p>
        ) : !usage.data || usage.data.total_recv + usage.data.total_sent === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Sin tráfico registrado en este periodo.
          </p>
        ) : (
          <UsageChart buckets={usage.data.buckets} unit={usage.data.unit} height={180} />
        )}
      </div>

      {/* Puertos detectados */}
      <div className="mt-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-sm">Puertos detectados</h3>
          <Button
            variant="outline"
            size="sm"
            onClick={() => scanMutation.mutate({ id: device.id })}
            disabled={scanMutation.isPending}
          >
            {scanMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <ScanLine className="h-4 w-4 mr-2" />
            )}
            Escanear
          </Button>
        </div>

        {ports.isLoading ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Cargando puertos…
          </p>
        ) : latestPorts.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Aún no se ha escaneado este dispositivo.
          </p>
        ) : (
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Puerto</th>
                  <th className="px-3 py-2 text-left font-medium">Servicio</th>
                  <th className="px-3 py-2 text-left font-medium">Versión</th>
                  <th className="px-3 py-2 text-left font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {latestPorts.map(p => (
                  <tr key={`${p.port}-${p.protocol}`} className="border-t">
                    <td className="px-3 py-2 font-mono">{p.port}/{p.protocol}</td>
                    <td className="px-3 py-2">{p.service || "—"}</td>
                    <td className="px-3 py-2 text-xs">{p.version || "—"}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant={p.state === "open" ? "success" : "secondary"}
                        className="text-xs"
                      >
                        {p.state}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Dialog>
  );
}
