// Tasa de tráfico actual de un dispositivo (descarga y subida), compacta para
// tablas. Si LanSentinel no es su gateway no se puede medir.

import { ArrowDown, ArrowUp } from "lucide-react";
import { useDeviceTraffic } from "@/hooks/useDeviceTraffic";
import { formatBps } from "@/lib/format";

export function TrafficCell({ deviceId }: { deviceId: string }) {
  const { data } = useDeviceTraffic(deviceId);

  if (!data) return <span className="text-xs text-muted-foreground">—</span>;
  if (!data.tracking) return <span className="text-xs text-muted-foreground">No medido</span>;
  if (data.rx_bps <= 0 && data.tx_bps <= 0) return <span className="text-xs text-muted-foreground">En reposo</span>;

  return (
    <div className="tabular flex flex-col gap-0.5 font-mono text-[11px]">
      <span className="flex items-center gap-1"><ArrowDown className="size-3 text-primary" />{formatBps(data.rx_bps)}</span>
      <span className="flex items-center gap-1 text-muted-foreground"><ArrowUp className="size-3 text-upload" />{formatBps(data.tx_bps)}</span>
    </div>
  );
}
