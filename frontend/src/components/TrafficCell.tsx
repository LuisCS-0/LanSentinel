// Celda compacta que muestra la tasa de tráfico actual de un dispositivo.
// Se usa como columna en DeviceTable. Si el dispositivo no está siendo
// rastreado (porque LanSentinel no actúa como su gateway), muestra "—".

import { ArrowDown, ArrowUp } from "lucide-react";
import { useDeviceTraffic } from "@/hooks/useDeviceTraffic";
import { formatBps } from "@/lib/format";

interface TrafficCellProps {
  deviceId: string;
}

export function TrafficCell({ deviceId }: TrafficCellProps) {
  const { data, isLoading } = useDeviceTraffic(deviceId);

  if (isLoading || !data) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  if (!data.tracking) {
    return <span className="text-xs text-muted-foreground">No medido</span>;
  }

  const hasTraffic = data.rx_bps > 0 || data.tx_bps > 0;

  if (!hasTraffic) {
    return <span className="text-xs text-muted-foreground">0 B/s</span>;
  }

  return (
    <div className="flex flex-col text-xs gap-0.5">
      <div className="flex items-center gap-1">
        <ArrowDown className="h-3 w-3 text-emerald-600" />
        <span className="font-mono">{formatBps(data.rx_bps)}</span>
      </div>
      <div className="flex items-center gap-1">
        <ArrowUp className="h-3 w-3 text-blue-600" />
        <span className="font-mono">{formatBps(data.tx_bps)}</span>
      </div>
    </div>
  );
}
