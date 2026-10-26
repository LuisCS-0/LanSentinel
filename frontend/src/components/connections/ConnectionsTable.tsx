// Tabla de conexiones: la usan la página Conexiones (con la columna del
// dispositivo) y el detalle de cada dispositivo (sin ella).

import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Ban, Check, Copy, Globe, House } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeviceLabel } from "@/components/devices/DeviceBits";
import { BlockRemoteDialog } from "@/components/connections/BlockRemoteDialog";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { copyText } from "@/lib/clipboard";
import { CONNECTION_STATUS, connectionKey, formatIdle } from "@/lib/connections";
import { cn } from "@/lib/utils";
import type { Device, DeviceConnection } from "@/lib/types";

type Row = DeviceConnection & { device_id?: string };

interface ConnectionsTableProps {
  connections: Row[];
  devicesById?: Map<string, Device>;   // con él se muestra la columna Dispositivo
  onOpenDevice?: (id: string) => void;
  maxRows?: number;
  // Para espacios estrechos (panel lateral): servicio y actividad van debajo
  // de la IP y del estado en lugar de en columnas propias
  compact?: boolean;
  className?: string;
}

export function ConnectionsTable({
  connections, devicesById, onOpenDevice, maxRows = 200, compact = false, className,
}: ConnectionsTableProps) {
  const [toBlock, setToBlock] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const rows = connections.slice(0, maxRows);
  // En pantallas de móvil, fichas en lugar de tabla: sin scroll lateral
  const narrow = useMediaQuery("(max-width: 640px)");

  const copy = async (ip: string) => {
    if (await copyText(ip)) {
      setCopied(ip);
      window.setTimeout(() => setCopied(null), 1200);
    }
  };

  const actions = (c: Row) => (
    <div className="flex shrink-0 justify-end gap-0.5 opacity-60 transition-opacity group-hover/row:opacity-100">
      <Button
        variant="ghost" size="icon-sm" onClick={() => copy(c.remote_ip)}
        title={copied === c.remote_ip ? "Copiada" : "Copiar IP"}
        className={cn(copied === c.remote_ip && "text-success")}
      >
        {copied === c.remote_ip ? <Check /> : <Copy />}
      </Button>
      {!c.remote_is_lan && (
        <Button
          variant="ghost" size="icon-sm" onClick={() => setToBlock(c.remote_ip)}
          title="Bloquear esta IP" className="hover:text-destructive"
        >
          <Ban />
        </Button>
      )}
    </div>
  );

  const footer = (
    <>
      {connections.length > rows.length && (
        <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">
          Se muestran {rows.length} de {connections.length}. Usa los filtros para acotar.
        </p>
      )}
      <BlockRemoteDialog ip={toBlock} onClose={() => setToBlock(null)} />
    </>
  );

  if (narrow) {
    return (
      <div className={className}>
        <ul className="divide-y">
          {rows.map(c => {
            const status = CONNECTION_STATUS[c.status];
            const device = c.device_id ? devicesById?.get(c.device_id) : undefined;
            const port = c.direction === "outgoing" ? c.remote_port : c.local_port;
            return (
              <li key={connectionKey(c)} className="group/row space-y-1.5 px-4 py-3">
                {device && (
                  <DeviceLabel device={device} onClick={onOpenDevice ? () => onOpenDevice(device.id) : undefined} className="max-w-full" />
                )}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      {c.direction === "outgoing"
                        ? <ArrowUpRight className="size-3.5 shrink-0 text-primary" aria-label="Saliente" />
                        : <ArrowDownLeft className="size-3.5 shrink-0 text-upload" aria-label="Entrante" />}
                      <span className="truncate font-mono text-xs">
                        {c.remote_ip}
                        {c.remote_port != null && <span className="text-muted-foreground">:{c.remote_port}</span>}
                      </span>
                      {c.remote_is_lan && <Badge variant="outline" className="px-1.5"><House />LAN</Badge>}
                    </div>
                    <p className="mt-0.5 text-xs">
                      <span className="font-medium">{c.service ?? "—"}</span>
                      <span className="ml-1.5 font-mono text-muted-foreground">{c.protocol}{port != null && `/${port}`}</span>
                    </p>
                  </div>
                  {actions(c)}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={status.variant} dot title={status.hint}>{status.label}</Badge>
                  <span className={cn("text-xs", c.status === "idle" ? "text-warning" : "text-muted-foreground")}>{formatIdle(c.idle_seconds)}</span>
                </div>
              </li>
            );
          })}
        </ul>
        {footer}
      </div>
    );
  }

  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className={cn("w-full text-sm", !compact && "min-w-[720px]")}>
        <thead>
          <tr className="border-b text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            {devicesById && <th className="px-4 py-2.5 font-medium">Dispositivo</th>}
            <th className="px-4 py-2.5 font-medium">Otro extremo</th>
            {!compact && <th className="px-4 py-2.5 font-medium">Servicio</th>}
            <th className="px-4 py-2.5 font-medium">Estado</th>
            {!compact && <th className="px-4 py-2.5 font-medium" title="Último paquete visto en esta conexión">Actividad</th>}
            {/* Fija a la derecha: con scroll horizontal los botones siguen a la vista */}
            <th className="sticky right-0 w-20 bg-card px-4 py-2.5" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map(c => {
            const status = CONNECTION_STATUS[c.status];
            const device = c.device_id ? devicesById?.get(c.device_id) : undefined;
            const port = c.direction === "outgoing" ? c.remote_port : c.local_port;
            const service = (
              <>
                <span className="font-medium">{c.service ?? "—"}</span>
                <span className="ml-1.5 font-mono text-muted-foreground">{c.protocol}{port != null && `/${port}`}</span>
              </>
            );
            const activity = (
              <span className={cn("whitespace-nowrap text-xs", c.status === "idle" ? "text-warning" : "text-muted-foreground")}>
                {formatIdle(c.idle_seconds)}
              </span>
            );
            return (
              <tr key={connectionKey(c)} className="group/row transition-colors hover:bg-muted/40">
                {devicesById && (
                  <td className="w-56 max-w-[14rem] px-4 py-2.5">
                    {device ? (
                      <DeviceLabel device={device} onClick={onOpenDevice ? () => onOpenDevice(device.id) : undefined} className="max-w-full" />
                    ) : (
                      <span className="text-xs text-muted-foreground">Desconocido</span>
                    )}
                  </td>
                )}
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <span
                      title={c.direction === "outgoing" ? "Saliente: la abrió el dispositivo" : "Entrante: la abrió el otro equipo"}
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-md",
                        c.direction === "outgoing" ? "bg-primary/10 text-primary" : "bg-upload/10 text-upload",
                      )}
                    >
                      {c.direction === "outgoing" ? <ArrowUpRight className="size-3.5" /> : <ArrowDownLeft className="size-3.5" />}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs">
                          {c.remote_ip}
                          {c.remote_port != null && <span className="text-muted-foreground">:{c.remote_port}</span>}
                        </span>
                        {c.remote_is_lan ? (
                          <Badge variant="outline" className="px-1.5"><House />LAN</Badge>
                        ) : (
                          <Globe className="size-3.5 shrink-0 text-muted-foreground" aria-label="Internet" />
                        )}
                      </div>
                      {compact && <p className="mt-0.5 text-xs">{service}</p>}
                    </div>
                  </div>
                </td>
                {!compact && <td className="px-4 py-2.5 text-xs">{service}</td>}
                <td className="px-4 py-2.5">
                  <Badge variant={status.variant} dot title={`${status.hint}${c.state ? ` (${c.state})` : ""}`}>{status.label}</Badge>
                  {compact && <p className="mt-1">{activity}</p>}
                </td>
                {!compact && <td className="px-4 py-2.5">{activity}</td>}
                <td className="sticky right-0 bg-card px-2 py-1.5">{actions(c)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {footer}
    </div>
  );
}
