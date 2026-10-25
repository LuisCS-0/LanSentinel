import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowDownUp, RefreshCw } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RangeSelector } from "@/components/RangeSelector";
import { UsageChart } from "@/components/UsageChart";
import { useNetworkUsage, useTopDevices } from "@/hooks/useTrafficUsage";
import { formatBytes } from "@/lib/format";
import type { DeviceUsage, TrafficRange } from "@/lib/types";

const RANGE_TEXT: Record<TrafficRange, string> = {
  "24h": "las últimas 24 horas",
  "7d": "los últimos 7 días",
  "30d": "los últimos 30 días",
  "1y": "el último año",
};

export default function TrafficPage() {
  const [range, setRange] = useState<TrafficRange>("24h");
  const usage = useNetworkUsage(range);
  const top = useTopDevices(range);

  const totalRecv = usage.data?.total_recv ?? 0;
  const totalSent = usage.data?.total_sent ?? 0;

  return (
    <div className="container py-8 space-y-6">
      {/* Cabecera */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Tráfico</h1>
          <p className="text-muted-foreground mt-1">
            Consumo de la red y de cada dispositivo en {RANGE_TEXT[range]}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <RangeSelector value={range} onChange={setRange} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => { usage.refetch(); top.refetch(); }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refrescar
          </Button>
        </div>
      </div>

      {/* Totales */}
      <div className="grid gap-4 sm:grid-cols-3">
        <TotalCard label="Descarga" value={totalRecv} icon={<ArrowDown className="h-4 w-4 text-emerald-600" />} />
        <TotalCard label="Subida" value={totalSent} icon={<ArrowUp className="h-4 w-4 text-blue-600" />} />
        <TotalCard label="Total" value={totalRecv + totalSent} icon={<ArrowDownUp className="h-4 w-4 text-muted-foreground" />} />
      </div>

      {/* Gráfica */}
      <Card>
        <CardHeader>
          <CardTitle>Consumo de la red</CardTitle>
          <CardDescription>
            Suma de los dispositivos medidos. Se actualiza cada pocos minutos.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usage.isLoading ? (
            <p className="text-center py-12 text-muted-foreground text-sm">Cargando histórico…</p>
          ) : !usage.data || totalRecv + totalSent === 0 ? (
            <p className="text-center py-12 text-muted-foreground text-sm">
              Aún no hay tráfico registrado en este periodo. El histórico se
              guarda cuando LanSentinel actúa como gateway de los dispositivos.
            </p>
          ) : (
            <UsageChart buckets={usage.data.buckets} unit={usage.data.unit} />
          )}
        </CardContent>
      </Card>

      {/* Ranking */}
      <DeviceRanking devices={top.data ?? []} loading={top.isLoading} />
    </div>
  );
}

// ─── Tarjeta de total ────────────────────────────────────────────────────────

function TotalCard({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{label}</span>
          {icon}
        </div>
        <p className="text-2xl font-bold mt-1">{formatBytes(value)}</p>
      </CardContent>
    </Card>
  );
}

// ─── Ranking de dispositivos ─────────────────────────────────────────────────

function DeviceRanking({ devices, loading }: { devices: DeviceUsage[]; loading: boolean }) {
  // El backend los devuelve de mayor a menor consumo
  const [ascending, setAscending] = useState(false);

  const sorted = useMemo(
    () => (ascending ? [...devices].reverse() : devices),
    [devices, ascending],
  );
  const max = devices.length > 0 ? devices[0].total_bytes : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle>Consumo por dispositivo</CardTitle>
            <CardDescription>
              {ascending ? "Los que menos consumen primero" : "Los que más consumen primero"}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => setAscending(a => !a)}>
            <ArrowDownUp className="h-4 w-4 mr-2" />
            {ascending ? "Más consumo primero" : "Menos consumo primero"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-center py-8 text-muted-foreground text-sm">Cargando…</p>
        ) : sorted.length === 0 ? (
          <p className="text-center py-8 text-muted-foreground text-sm">
            No hay dispositivos con actividad en este periodo.
          </p>
        ) : (
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-4 py-3 font-medium">Dispositivo</th>
                  <th className="px-4 py-3 font-medium text-right">Descarga</th>
                  <th className="px-4 py-3 font-medium text-right">Subida</th>
                  <th className="px-4 py-3 font-medium w-1/3">Total</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(d => (
                  <tr key={d.device_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <p className="font-medium">{d.hostname || d.vendor || d.mac}</p>
                      <p className="text-xs text-muted-foreground font-mono">
                        {d.ip || "sin IP"} · {d.mac}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{formatBytes(d.bytes_recv)}</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{formatBytes(d.bytes_sent)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded bg-muted overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{ width: max > 0 ? `${(d.total_bytes / max) * 100}%` : "0%" }}
                          />
                        </div>
                        <span className="font-mono text-xs w-20 text-right">{formatBytes(d.total_bytes)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
