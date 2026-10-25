// Consumo de la red: totales del periodo, gráfica histórica y ranking de
// dispositivos (pulsar uno abre su detalle).

import { useMemo, useState } from "react";
import { Activity, ArrowDown, ArrowDownUp, ArrowUp, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { PageHeader, StatCard } from "@/components/PageHeader";
import { RangeSelector } from "@/components/RangeSelector";
import { LiveTrafficChart, TrafficLegend, UsageChart } from "@/components/charts";
import { DeviceAvatar } from "@/components/devices/DeviceBits";
import { useDevices } from "@/hooks/useApi";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useTrafficHistory } from "@/hooks/useTrafficHistory";
import { useNetworkUsage, useTopDevices } from "@/hooks/useTrafficUsage";
import { deviceName } from "@/lib/devices";
import { formatBytes } from "@/lib/format";
import type { TrafficRange } from "@/lib/types";

const RANGE_TEXT: Record<TrafficRange, string> = {
  "24h": "las últimas 24 horas",
  "7d": "los últimos 7 días",
  "30d": "los últimos 30 días",
  "1y": "el último año",
};

export default function TrafficPage() {
  const [range, setRange] = useState<TrafficRange>("24h");
  const usage = useNetworkUsage(range);
  const live = useTrafficHistory();

  const recv = usage.data?.total_recv ?? 0;
  const sent = usage.data?.total_sent ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tráfico"
        description={`Consumo de la red en ${RANGE_TEXT[range]}`}
        actions={<RangeSelector value={range} onChange={setRange} />}
      />

      <div className="grid gap-3 sm:grid-cols-3 sm:gap-4">
        <StatCard label="Descarga" icon={ArrowDown} value={usage.isLoading ? "—" : formatBytes(recv)} />
        <StatCard label="Subida" icon={ArrowUp} tone="upload" value={usage.isLoading ? "—" : formatBytes(sent)} />
        <StatCard label="Total" icon={ArrowDownUp} tone="muted" value={usage.isLoading ? "—" : formatBytes(recv + sent)} />
      </div>

      <Card>
        <CardHeaderRow
          title={<><BarChart3 />Consumo de la red</>}
          description="Suma de los dispositivos medidos; la hora en curso puede ir unos minutos por detrás"
          actions={<TrafficLegend />}
        />
        <CardContent>
          {usage.isLoading ? <Skeleton className="h-[280px]" />
            : !usage.data || recv + sent === 0 ? (
              <EmptyState
                icon={BarChart3} title="Sin tráfico registrado en este periodo"
                description="El histórico se guarda cuando LanSentinel actúa como gateway de los dispositivos."
              />
            ) : <UsageChart buckets={usage.data.buckets} unit={usage.data.unit} height={280} />}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-5">
        <DeviceRanking range={range} className="xl:col-span-3" />
        <Card className="xl:col-span-2">
          <CardHeaderRow title={<><Activity />En directo</>} description="Últimos 10 minutos" />
          <CardContent>
            {live.isLoading ? <Skeleton className="h-[220px]" /> : <LiveTrafficChart samples={live.data} height={220} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function DeviceRanking({ range, className }: { range: TrafficRange; className?: string }) {
  const top = useTopDevices(range);
  const devices = useDevices();
  const sheet = useDeviceSheet();
  const [ascending, setAscending] = useState(false);

  const list = useMemo(() => {
    const items = top.data ?? [];
    return ascending ? [...items].reverse() : items;
  }, [top.data, ascending]);
  const max = Math.max(0, ...list.map(d => d.total_bytes));

  return (
    <Card className={className}>
      <CardHeaderRow
        title={<><ArrowDownUp />Consumo por dispositivo</>}
        description={ascending ? "Los que menos consumen primero" : "Los que más consumen primero"}
        actions={
          <Button variant="ghost" size="xs" onClick={() => setAscending(a => !a)}>
            <ArrowDownUp />{ascending ? "Más primero" : "Menos primero"}
          </Button>
        }
      />
      <CardContent className="p-0">
        {top.isLoading ? (
          <div className="space-y-2 p-5 pt-0">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-12" />)}</div>
        ) : list.length === 0 ? (
          <EmptyState icon={ArrowDownUp} title="Sin dispositivos con actividad en este periodo" />
        ) : (
          <ul className="divide-y border-t">
            {list.map((d, i) => {
              const device = devices.data?.find(x => x.id === d.device_id);
              return (
                <li key={d.device_id}>
                  <button
                    onClick={() => sheet.open(d.device_id, "usage")}
                    className="group flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-muted/40"
                  >
                    <span className="tabular w-5 text-right text-xs text-muted-foreground">{ascending ? list.length - i : i + 1}</span>
                    {device && <DeviceAvatar device={device} size="sm" />}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="truncate text-sm font-medium group-hover:text-primary">{device ? deviceName(device) : d.hostname ?? d.mac}</p>
                        <p className="tabular shrink-0 font-mono text-xs">{formatBytes(d.total_bytes)}</p>
                      </div>
                      <div className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-primary" style={{ width: `${max ? (d.bytes_recv / max) * 100 : 0}%` }} />
                        <div className="h-full bg-upload" style={{ width: `${max ? (d.bytes_sent / max) * 100 : 0}%` }} />
                      </div>
                      <p className="tabular mt-1 font-mono text-[11px] text-muted-foreground">
                        ↓ {formatBytes(d.bytes_recv)} · ↑ {formatBytes(d.bytes_sent)} · {d.ip ?? "sin IP"}
                      </p>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
