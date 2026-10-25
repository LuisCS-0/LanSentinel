// Dispositivos de la red. Pulsar una fila abre su detalle en el panel lateral;
// las acciones frecuentes (confianza, bloqueo, escaneo) están en la propia fila.

import { useMemo, useState, type MouseEvent } from "react";
import {
  AlertCircle, ArrowUpDown, Ban, Cable, Loader2, MonitorSmartphone, Radar, ScanLine, Search,
  ShieldCheck, ShieldOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, Select, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { TrafficCell } from "@/components/TrafficCell";
import { DeviceAvatar, DeviceStatusBadge } from "@/components/devices/DeviceBits";
import { useDevices } from "@/hooks/useApi";
import { useNetworkConnections } from "@/hooks/useConnections";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useBlockDevice, useForceNetworkScan, useScanPorts, useTrustDevice } from "@/hooks/useDevices";
import { useQuarantine } from "@/hooks/useQuarantine";
import { extractErrorMessage } from "@/lib/api";
import { shortRelative } from "@/lib/dates";
import { compareIp, deviceName, isOnline } from "@/lib/devices";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { Device } from "@/lib/types";

type Filter = "all" | "online" | "trusted" | "unreviewed" | "blocked";
type Sort = "seen" | "name" | "ip";

export default function DevicesPage() {
  const devices = useDevices();
  const conns = useNetworkConnections();
  const quarantine = useQuarantine();
  const networkScan = useForceNetworkScan();
  const trust = useTrustDevice();
  const block = useBlockDevice();
  const scan = useScanPorts();
  const sheet = useDeviceSheet();

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("seen");
  const quarantineOn = quarantine.data?.enabled ?? false;
  const list = useMemo(() => devices.data ?? [], [devices.data]);

  // Conexiones abiertas por dispositivo, de una sola consulta
  const openByDevice = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of conns.data?.connections ?? []) {
      if (c.status === "open") map.set(c.device_id, (map.get(c.device_id) ?? 0) + 1);
    }
    return map;
  }, [conns.data]);

  const counts = {
    all: list.length,
    online: list.filter(isOnline).length,
    trusted: list.filter(d => d.is_trusted).length,
    unreviewed: list.filter(d => !d.is_trusted && !d.is_blocked).length,
    blocked: list.filter(d => d.is_blocked).length,
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return list
      .filter(d => {
        if (q && ![d.ip, d.mac, d.hostname, d.vendor].some(v => (v ?? "").toLowerCase().includes(q))) return false;
        switch (filter) {
          case "online": return isOnline(d);
          case "trusted": return d.is_trusted;
          case "unreviewed": return !d.is_trusted && !d.is_blocked;
          case "blocked": return d.is_blocked;
          default: return true;
        }
      })
      .sort((a, b) =>
        sort === "name" ? deviceName(a).localeCompare(deviceName(b), "es")
          : sort === "ip" ? compareIp(a.ip, b.ip)
          : b.last_seen.localeCompare(a.last_seen));
  }, [list, search, filter, sort]);

  const runScan = () => networkScan.mutate(undefined, {
    onSuccess: () => toast({ title: "Escaneo de la red lanzado", description: "Los dispositivos nuevos aparecerán en unos segundos." }),
  });

  // Las acciones de la fila no deben abrir el detalle
  const act = (fn: () => void) => (e: MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  const actions = {
    trust: (d: Device) => act(() => trust.mutate({ id: d.id, trusted: !d.is_trusted })),
    block: (d: Device) => act(() => block.mutate({ id: d.id, blocked: !d.is_blocked })),
    scan: (d: Device) => act(() => scan.mutate({ id: d.id }, {
      onSuccess: r => toast({ title: `Escaneo de ${deviceName(d)} terminado`, description: `${r.ports_found} puertos abiertos.` }),
    })),
    connections: (d: Device) => act(() => sheet.open(d.id, "connections")),
  };
  const scanningId = scan.isPending ? scan.variables?.id : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dispositivos"
        description={`${counts.all} detectados · ${counts.online} en línea ahora`}
        actions={
          <Button onClick={runScan} disabled={networkScan.isPending}>
            {networkScan.isPending ? <Loader2 className="animate-spin" /> : <Radar />}
            Escanear la red
          </Button>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center">
          <Segmented<Filter>
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "Todos", count: counts.all },
              { value: "online", label: "En línea", count: counts.online },
              { value: "trusted", label: "De confianza", count: counts.trusted },
              { value: "unreviewed", label: quarantineOn ? "En cuarentena" : "Sin revisar", count: counts.unreviewed, tone: "warning" },
              { value: "blocked", label: "Bloqueados", count: counts.blocked, tone: "destructive" },
            ]}
          />
          <div className="flex flex-1 gap-2 lg:justify-end">
            <Input
              icon={Search} value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Nombre, IP, MAC o fabricante…" className="lg:w-72"
            />
            <Select value={sort} onChange={e => setSort(e.target.value as Sort)} aria-label="Ordenar" className="w-40 shrink-0">
              <option value="seen">Vistos hace poco</option>
              <option value="name">Nombre</option>
              <option value="ip">Dirección IP</option>
            </Select>
          </div>
        </div>

        {(block.isError || trust.isError) && (
          <p className="flex items-start gap-2 border-b bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(block.error ?? trust.error)}
          </p>
        )}

        {devices.isLoading ? (
          <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-14" />)}</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={MonitorSmartphone}
            title={list.length === 0 ? "Aún no hay dispositivos" : "Ningún dispositivo coincide"}
            description={list.length === 0 ? "Aparecerán según el escaneo ARP los descubra." : "Prueba con otro filtro o búsqueda."}
          />
        ) : (
          <>
            {/* Escritorio: tabla */}
            <table className="hidden w-full text-sm md:table">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Dispositivo</th>
                  <th className="px-4 py-2.5 font-medium">Dirección</th>
                  <th className="px-4 py-2.5 font-medium">Estado</th>
                  <th className="px-4 py-2.5 font-medium">Tráfico ahora</th>
                  <th className="px-4 py-2.5 font-medium">Conexiones</th>
                  <th className="hidden px-4 py-2.5 font-medium xl:table-cell">
                    <span className="flex items-center gap-1"><ArrowUpDown className="size-3" />Visto</span>
                  </th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {filtered.map(d => (
                  <tr
                    key={d.id}
                    onClick={() => sheet.open(d.id)}
                    className={cn("group cursor-pointer transition-colors hover:bg-muted/40", d.is_blocked && "bg-destructive/[0.03]")}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <DeviceAvatar device={d} />
                        <div className="min-w-0">
                          <p className="truncate font-medium group-hover:text-primary">{deviceName(d)}</p>
                          <p className="truncate text-xs text-muted-foreground">{d.hostname && d.vendor ? d.vendor : isOnline(d) ? "En línea" : "Desconectado"}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      <p>{d.ip ?? "—"}</p>
                      <p className="text-muted-foreground">{d.mac}</p>
                    </td>
                    <td className="px-4 py-3"><DeviceStatusBadge device={d} quarantine={quarantineOn} /></td>
                    <td className="px-4 py-3"><TrafficCell deviceId={d.id} /></td>
                    <td className="px-4 py-3">
                      <button
                        onClick={actions.connections(d)}
                        className="tabular inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors hover:bg-primary/10 hover:text-primary"
                        title="Ver sus conexiones"
                      >
                        <Cable className="size-3.5" />{openByDevice.get(d.id) ?? 0}
                      </button>
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-xs text-muted-foreground xl:table-cell" title={new Date(d.last_seen).toLocaleString("es-ES")}>{shortRelative(d.last_seen)}</td>
                    <td className="px-3 py-3">
                      <RowActions device={d} actions={actions} scanning={scanningId === d.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Móvil: tarjetas */}
            <ul className="divide-y md:hidden">
              {filtered.map(d => (
                <li key={d.id} onClick={() => sheet.open(d.id)} className="flex cursor-pointer items-center gap-3 p-4 active:bg-muted/40">
                  <DeviceAvatar device={d} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{deviceName(d)}</p>
                    <p className="truncate font-mono text-xs text-muted-foreground">{d.ip ?? "sin IP"}</p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <DeviceStatusBadge device={d} quarantine={quarantineOn} />
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Cable className="size-3" />{openByDevice.get(d.id) ?? 0}
                      </span>
                    </div>
                  </div>
                  <RowActions device={d} actions={actions} scanning={scanningId === d.id} />
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}

type RowAction = (d: Device) => (e: MouseEvent) => void;

function RowActions({
  device, actions, scanning,
}: { device: Device; actions: Record<"trust" | "block" | "scan", RowAction>; scanning: boolean }) {
  return (
    <div className="flex justify-end gap-0.5 md:opacity-60 md:transition-opacity md:group-hover:opacity-100">
      <Button
        variant="ghost" size="icon-sm" onClick={actions.trust(device)}
        title={device.is_trusted ? "Quitar confianza" : "Marcar de confianza"}
        className={cn(device.is_trusted ? "text-success" : "hover:text-success")}
      >
        {device.is_trusted ? <ShieldOff /> : <ShieldCheck />}
      </Button>
      <Button
        variant="ghost" size="icon-sm" onClick={actions.scan(device)} disabled={scanning}
        title="Escanear puertos" className="hidden sm:inline-flex"
      >
        {scanning ? <Loader2 className="animate-spin" /> : <ScanLine />}
      </Button>
      <Button
        variant="ghost" size="icon-sm" onClick={actions.block(device)}
        title={device.is_blocked ? "Desbloquear" : "Bloquear"}
        className={cn(device.is_blocked ? "text-destructive" : "hover:text-destructive")}
      >
        <Ban />
      </Button>
    </div>
  );
}
