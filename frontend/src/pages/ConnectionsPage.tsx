// Todas las conexiones abiertas de la red en una sola vista (tabla conntrack
// del gateway). Se puede filtrar por dispositivo, estado, destino o servicio,
// agrupar por dispositivo y pausar el refresco para leer con calma.

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle, Cable, ChevronRight, Globe, House, List, MessageCircleQuestion, Pause, Play, Rows3, Search, Server,
  Timer, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, Select, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader, StatCard } from "@/components/PageHeader";
import { ConnectionsTable } from "@/components/connections/ConnectionsTable";
import { DeviceAvatar } from "@/components/devices/DeviceBits";
import { useDevices } from "@/hooks/useApi";
import { useNetworkConnections } from "@/hooks/useConnections";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { isActive, serviceKey } from "@/lib/connections";
import { compareIp, deviceName } from "@/lib/devices";
import { cn } from "@/lib/utils";
import type { Device, NetworkConnection, NetworkConnections } from "@/lib/types";

type StatusFilter = "active" | "open" | "idle" | "pending" | "queries" | "closing" | "all";
type Scope = "all" | "internet" | "lan";
type View = "list" | "grouped";

export default function ConnectionsPage() {
  const [params, setParams] = useSearchParams();
  const conns = useNetworkConnections();
  // Pausa: copia de los datos en el momento de pausar. Mientras exista, la
  // página muestra esa copia aunque la caché compartida se siga refrescando
  const [frozen, setFrozen] = useState<{ data: NetworkConnections; at: Date } | null>(null);
  const live = frozen === null;
  const data = frozen?.data ?? conns.data;
  const togglePause = () => setFrozen(f => (f || !conns.data ? null : { data: conns.data, at: new Date() }));
  const devices = useDevices();
  const sheet = useDeviceSheet();

  const [status, setStatus] = useState<StatusFilter>("active");
  const [scope, setScope] = useState<Scope>("all");
  const [view, setView] = useState<View>("list");
  const [deviceFilter, setDeviceFilter] = useState("");
  // Filtro exacto por servicio (al pulsar uno de la lista de servicios)
  const [serviceFilter, setServiceFilter] = useState("");
  // La búsqueda va en la URL para poder llegar aquí ya filtrado desde el Panel
  const search = params.get("q") ?? "";
  const setSearch = (q: string) => setParams(prev => {
    const next = new URLSearchParams(prev);
    if (q) next.set("q", q);
    else next.delete("q");
    return next;
  }, { replace: true });

  const devicesById = useMemo(() => new Map((devices.data ?? []).map(d => [d.id, d])), [devices.data]);
  const all = useMemo(() => data?.connections ?? [], [data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter(c => {
      if (status === "active" && !isActive(c)) return false;
      if (status === "queries" && c.status !== "done") return false;
      if (["open", "idle", "pending", "closing"].includes(status) && c.status !== status) return false;
      if (serviceFilter && serviceKey(c) !== serviceFilter) return false;
      if (scope === "internet" && c.remote_is_lan) return false;
      if (scope === "lan" && !c.remote_is_lan) return false;
      if (deviceFilter && c.device_id !== deviceFilter) return false;
      if (q) {
        const d = devicesById.get(c.device_id);
        const text = `${c.remote_ip} ${c.remote_name ?? ""} ${c.remote_port ?? ""} ${serviceKey(c)} ${c.protocol} ${d ? `${deviceName(d)} ${d.ip}` : ""}`.toLowerCase();
        if (!q.split(/\s+/).every(w => text.includes(w))) return false;
      }
      return true;
    });
  }, [all, status, scope, deviceFilter, serviceFilter, search, devicesById]);

  const open = all.filter(c => c.status === "open");
  const stats = {
    open: open.length,
    idle: all.filter(c => c.status === "idle").length,
    pending: all.filter(c => c.status === "pending").length,
    queries: all.filter(c => c.status === "done").length,
    closing: all.filter(c => c.status === "closing").length,
    devices: new Set(open.map(c => c.device_id)).size,
    internet: new Set(open.filter(c => !c.remote_is_lan).map(c => c.remote_ip)).size,
  };

  const top = (key: (c: NetworkConnection) => string | null, source = open) => {
    const counts = new Map<string, number>();
    for (const c of source) {
      const k = key(c);
      if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  };
  const topDestinations = top(c => (c.remote_is_lan ? null : c.remote_name ?? c.remote_ip));
  const topServices = top(serviceKey);
  // Consultas sueltas recientes (DNS, NTP, ping): a qué servidor pregunta la red
  const topQueries = top(c => `${serviceKey(c)} · ${c.remote_ip}`, all.filter(c => c.status === "done"));

  const deviceOptions = [...new Set(all.map(c => c.device_id))]
    .map(id => devicesById.get(id))
    .filter((d): d is Device => !!d)
    .sort((a, b) => compareIp(a.ip, b.ip));

  const hasFilters = search || deviceFilter || serviceFilter || scope !== "all" || status !== "active";
  const clearFilters = () => {
    setSearch("");
    setDeviceFilter("");
    setServiceFilter("");
    setScope("all");
    setStatus("active");
  };

  if (data?.available === false) {
    return (
      <div className="space-y-6">
        <PageHeader title="Conexiones" />
        <Card>
          <EmptyState
            icon={AlertCircle} title="No se puede leer la tabla de conexiones"
            description="El backend necesita la herramienta conntrack y el permiso NET_ADMIN (vienen en la imagen de Docker)."
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Conexiones"
        description={live
          ? "Lo que tiene abierto cada dispositivo ahora mismo, a través de LanSentinel"
          : `En pausa: se muestran las conexiones de las ${frozen.at.toLocaleTimeString("es-ES")}`}
        actions={
          <Button
            variant={live ? "outline" : "soft"} onClick={togglePause} disabled={!conns.data}
            title={live ? "Congela la tabla para leerla con calma" : "Vuelve a mostrar los datos en directo"}
          >
            {live ? <Pause /> : <Play />}
            {live ? "Pausar" : "Reanudar"}
            <span className={cn("size-1.5 rounded-full", live ? "animate-pulse bg-success" : "bg-muted-foreground")} />
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Abiertas" icon={Cable} tone="success" value={conns.isLoading ? "—" : stats.open} onClick={() => setStatus("open")} />
        <StatCard label="Dispositivos activos" icon={Server} tone="primary" value={conns.isLoading ? "—" : stats.devices} hint={`de ${devicesById.size} conocidos`} />
        <StatCard label="Destinos en Internet" icon={Globe} tone="info" value={conns.isLoading ? "—" : stats.internet} onClick={() => setScope("internet")} />
        <StatCard
          label="Sin respuesta" icon={Timer} tone={stats.pending ? "warning" : "muted"} value={conns.isLoading ? "—" : stats.pending}
          hint="Intentos que nadie ha contestado" onClick={() => setStatus("pending")}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        <Card className="min-w-0 overflow-hidden xl:col-span-3">
          {/* Filtros */}
          <div className="flex flex-col gap-3 border-b p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Segmented<StatusFilter>
                value={status} onChange={setStatus} size="sm"
                options={[
                  { value: "active", label: "Activas", count: stats.open + stats.idle + stats.pending },
                  { value: "open", label: "Abiertas", count: stats.open },
                  { value: "idle", label: "Inactivas", count: stats.idle, tone: "warning" },
                  { value: "pending", label: "Sin respuesta", count: stats.pending, tone: "warning" },
                  { value: "queries", label: "Consultas", count: stats.queries },
                  { value: "closing", label: "Cerrándose", count: stats.closing },
                  { value: "all", label: "Todas", count: all.length },
                ]}
              />
              <Segmented<Scope>
                value={scope} onChange={setScope} size="sm"
                options={[
                  { value: "all", label: "Todo" },
                  { value: "internet", label: <><Globe />Internet</> },
                  { value: "lan", label: <><House />LAN</> },
                ]}
              />
              <Segmented<View>
                value={view} onChange={setView} size="sm" className="xl:ml-auto"
                options={[
                  { value: "list", label: <><List />Lista</> },
                  { value: "grouped", label: <><Rows3 />Por equipo</> },
                ]}
              />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input icon={Search} value={search} onChange={e => setSearch(e.target.value)} placeholder="IP, puerto, servicio o dispositivo…" />
              <Select value={deviceFilter} onChange={e => setDeviceFilter(e.target.value)} aria-label="Dispositivo" className="sm:w-64">
                <option value="">Todos los dispositivos</option>
                {deviceOptions.map(d => <option key={d.id} value={d.id}>{deviceName(d)} ({d.ip})</option>)}
              </Select>
              {hasFilters && (
                <Button variant="ghost" onClick={clearFilters}><X />Quitar filtros</Button>
              )}
            </div>
            {serviceFilter && (
              <div>
                <button
                  onClick={() => setServiceFilter("")}
                  className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/25 hover:bg-primary/20"
                  title="Quitar este filtro"
                >
                  Servicio: <span className="font-mono">{serviceFilter}</span><X className="size-3" />
                </button>
              </div>
            )}
          </div>

          {conns.isLoading ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-10" />)}</div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Cable}
              title={all.length === 0 ? "No hay conexiones abiertas" : "Ninguna conexión coincide"}
              description={all.length === 0
                ? "Solo se ven las conexiones que pasan por LanSentinel: las que salen a Internet y las dirigidas a este equipo."
                : "Prueba a quitar algún filtro."}
              action={hasFilters ? <Button variant="outline" size="sm" onClick={clearFilters}>Quitar filtros</Button> : undefined}
            />
          ) : view === "list" ? (
            <ConnectionsTable connections={filtered} devicesById={devicesById} onOpenDevice={id => sheet.open(id, "connections")} />
          ) : (
            <GroupedView connections={filtered} devicesById={devicesById} onOpenDevice={id => sheet.open(id, "connections")} />
          )}
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1 xl:content-start">
          <TopList
            title="Destinos principales" icon={Globe} items={topDestinations} mono
            empty="Sin conexiones a Internet." onPick={ip => { setSearch(ip); setScope("all"); }}
          />
          <TopList
            title="Servicios" icon={Server} items={topServices} empty="Sin conexiones abiertas."
            onPick={s => { setServiceFilter(s); if (status === "queries" || status === "closing") setStatus("active"); }}
          />
          <TopList
            title="Consultas recientes" icon={MessageCircleQuestion} items={topQueries} mono
            description="DNS, NTP, ping… de los últimos ~30 s · pulsa para verlas"
            empty="Ninguna en los últimos segundos."
            onPick={label => {
              const [service, ip] = label.split(" · ");
              setStatus("queries");
              setServiceFilter(service);
              setSearch(ip);
            }}
          />
        </div>
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Solo aparecen las conexiones que atraviesan LanSentinel; el tráfico directo entre equipos de la LAN no pasa por aquí.
      </p>
    </div>
  );
}

// ─── Agrupadas por dispositivo ───────────────────────────────────────────────

function GroupedView({
  connections, devicesById, onOpenDevice,
}: { connections: NetworkConnection[]; devicesById: Map<string, Device>; onOpenDevice: (id: string) => void }) {
  const groups = useMemo(() => {
    const map = new Map<string, NetworkConnection[]>();
    for (const c of connections) map.set(c.device_id, [...(map.get(c.device_id) ?? []), c]);
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [connections]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const toggle = (id: string) => setCollapsed(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  return (
    <div className="divide-y">
      {groups.map(([id, list]) => {
        const device = devicesById.get(id);
        const isOpen = !collapsed.has(id);
        return (
          <section key={id}>
            <div className="flex items-center gap-3 bg-muted/30 px-4 py-2.5">
              <button onClick={() => toggle(id)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-90")} />
                {device && <DeviceAvatar device={device} size="sm" />}
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{device ? deviceName(device) : "Desconocido"}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{device?.ip}</p>
                </div>
                <span className="tabular ml-auto rounded-full bg-foreground/5 px-2 text-xs text-muted-foreground">{list.length}</span>
              </button>
              <Button variant="ghost" size="xs" onClick={() => onOpenDevice(id)}>Detalle</Button>
            </div>
            {isOpen && <ConnectionsTable connections={list} maxRows={50} />}
          </section>
        );
      })}
    </div>
  );
}

// ─── Lista de "lo más frecuente" ─────────────────────────────────────────────

function TopList({
  title, icon: Icon, items, onPick, empty, mono, description = "Entre las conexiones abiertas · pulsa para filtrar",
}: { title: string; icon: typeof Globe; items: [string, number][]; onPick: (v: string) => void; empty: string; mono?: boolean; description?: string }) {
  const max = items[0]?.[1] ?? 0;
  return (
    <Card>
      <CardHeaderRow title={<><Icon />{title}</>} description={description} />
      <CardContent className="space-y-1">
        {items.length === 0 ? (
          <p className="py-3 text-center text-sm text-muted-foreground">{empty}</p>
        ) : items.map(([label, count]) => (
          <button
            key={label}
            onClick={() => onPick(label)}
            className="group relative block w-full overflow-hidden rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-muted/50"
          >
            <span className="absolute inset-y-1 left-0 rounded-r bg-primary/10" style={{ width: `${max ? (count / max) * 100 : 0}%` }} />
            <span className="relative flex items-center justify-between gap-2 text-sm">
              <span className={cn("truncate", mono && "font-mono text-xs")}>{label}</span>
              <span className="tabular text-xs text-muted-foreground">{count}</span>
            </span>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
