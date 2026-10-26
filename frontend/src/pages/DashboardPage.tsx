// Panel principal: el estado de la red de un vistazo y atajos a lo que
// requiere atención (alertas, dispositivos, conexiones), con acciones
// rápidas sin salir de la página.

import { Link, useNavigate } from "react-router-dom";
import {
  Activity, ArrowDown, ArrowRight, ArrowUp, Bell, Cable, Check, CheckCheck, Globe,
  MonitorSmartphone, ShieldAlert, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { StatCard } from "@/components/PageHeader";
import { SeverityBadge } from "@/components/SeverityBadge";
import { QuarantineCard } from "@/components/QuarantineCard";
import { LiveTrafficChart, Sparkline, TrafficLegend } from "@/components/charts";
import { DeviceLabel } from "@/components/devices/DeviceBits";
import { useAlerts, useDevices, useSystemStatus } from "@/hooks/useApi";
import { useCurrentUser, useIsAdmin } from "@/hooks/useAuth";
import { useNetworkConnections } from "@/hooks/useConnections";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useUpdateAlertStatus } from "@/hooks/useMutations";
import { useTrafficHistory } from "@/hooks/useTrafficHistory";
import { useTopDevices } from "@/hooks/useTrafficUsage";
import { relativeTime } from "@/lib/dates";
import { isOnline } from "@/lib/devices";
import { formatBps, formatBytes } from "@/lib/format";
import { severityRank } from "@/lib/severity";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const devices = useDevices();
  const alerts = useAlerts(100);
  const status = useSystemStatus();
  const conns = useNetworkConnections();
  const traffic = useTrafficHistory();
  const sheet = useDeviceSheet();

  const deviceList = devices.data ?? [];
  const online = deviceList.filter(isOnline).length;
  const pending = (alerts.data ?? []).filter(a => a.status === "new");
  const urgent = pending.filter(a => a.severity === "critical" || a.severity === "high");
  const openConns = (conns.data?.connections ?? []).filter(c => c.status === "open");
  const internetHosts = new Set(openConns.filter(c => !c.remote_is_lan).map(c => c.remote_ip)).size;
  const samples = traffic.data ?? [];
  const now = samples[0];
  const servicesOk = status.data && status.data.monitor?.running && status.data.security?.running && status.data.firewall?.running;

  return (
    <div className="space-y-6">
      <Hero urgent={urgent.length} pending={pending.length} servicesOk={!!servicesOk} loading={alerts.isLoading} />

      {/* Indicadores: cada uno lleva a su sección */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          to="/devices" label="Dispositivos" icon={MonitorSmartphone}
          value={devices.isLoading ? "—" : <>{online}<span className="text-base font-normal text-muted-foreground"> / {deviceList.length}</span></>}
          hint={`${online} en línea · ${deviceList.filter(d => d.is_trusted).length} de confianza`}
        />
        <StatCard
          to="/alerts" label="Alertas sin revisar" icon={Bell}
          tone={urgent.length ? "destructive" : pending.length ? "warning" : "success"}
          value={alerts.isLoading ? "—" : pending.length}
          hint={urgent.length ? `${urgent.length} de prioridad alta o crítica` : "Nada urgente"}
        />
        <StatCard
          to="/connections" label="Conexiones abiertas" icon={Cable} tone="info"
          value={conns.data?.available === false ? "—" : openConns.length}
          hint={<span className="flex items-center gap-1"><Globe className="size-3" />{internetHosts} destinos en Internet</span>}
        />
        <StatCard
          to="/traffic" label="Tráfico ahora" icon={Activity} tone="upload"
          value={now ? formatBps(now.total_bps) : "—"}
          hint={now && (
            <span className="tabular flex gap-3 font-mono">
              <span className="flex items-center gap-0.5"><ArrowDown className="size-3 text-primary" />{formatBps(now.rx_bps)}</span>
              <span className="flex items-center gap-0.5"><ArrowUp className="size-3 text-upload" />{formatBps(now.tx_bps)}</span>
            </span>
          )}
        >
          <div className="-mx-1 mt-2"><Sparkline values={[...samples].reverse().slice(-40).map(s => s.total_bps)} /></div>
        </StatCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {/* Tráfico en directo */}
        <Card className="xl:col-span-2">
          <CardHeaderRow
            title={<><Activity />Tráfico de la red en directo</>}
            description="Últimos 10 minutos, suma de los dispositivos medidos"
            actions={<TrafficLegend />}
          />
          <CardContent>
            {traffic.isLoading ? <Skeleton className="h-[260px]" />
              : samples.length === 0 ? <EmptyState icon={Activity} title="Esperando muestras del medidor…" />
              : <LiveTrafficChart samples={samples} />}
          </CardContent>
        </Card>

        <TopConsumers onOpen={sheet.open} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <RecentAlerts />
        <div className="space-y-4">
          <QuarantineCard compact />
          <TopDestinations />
        </div>
      </div>
    </div>
  );
}

// ─── Cabecera con el estado general ──────────────────────────────────────────

function Hero({ urgent, pending, servicesOk, loading }: { urgent: number; pending: number; servicesOk: boolean; loading: boolean }) {
  const me = useCurrentUser().data?.username;
  const navigate = useNavigate();
  const hour = new Date().getHours();
  const greeting = hour < 7 ? "Buenas noches" : hour < 14 ? "Buenos días" : hour < 21 ? "Buenas tardes" : "Buenas noches";
  const state = loading ? null
    : urgent > 0 ? { tone: "destructive", icon: ShieldAlert, title: `${urgent} ${urgent === 1 ? "alerta necesita" : "alertas necesitan"} tu atención`, text: "Hay eventos de prioridad alta o crítica sin revisar." }
    : pending > 0 ? { tone: "warning", icon: Bell, title: `${pending} ${pending === 1 ? "alerta" : "alertas"} sin revisar`, text: "Nada urgente, pero conviene echarles un vistazo." }
    : !servicesOk ? { tone: "warning", icon: ShieldAlert, title: "Algún servicio no está en marcha", text: "Revisa el estado al pie de la barra lateral." }
    : { tone: "success", icon: ShieldCheck, title: "Tu red está tranquila", text: "No hay alertas pendientes y todos los servicios funcionan." };

  return (
    <div className="relative overflow-hidden rounded-2xl border bg-card/80 p-5 shadow-card sm:p-6">
      <div className="bg-brand pointer-events-none absolute -right-16 -top-24 size-72 rounded-full opacity-20 blur-3xl" />
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {state && (
            <div
              className={cn(
                "rounded-2xl p-3 ring-1 ring-inset",
                state.tone === "destructive" && "bg-destructive/15 text-destructive ring-destructive/30",
                state.tone === "warning" && "bg-warning/15 text-warning ring-warning/30",
                state.tone === "success" && "bg-success/15 text-success ring-success/30",
              )}
            >
              <state.icon className="size-7" />
            </div>
          )}
          <div>
            <p className="text-sm text-muted-foreground">{greeting}{me ? `, ${me}` : ""}</p>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{state?.title ?? "Cargando…"}</h1>
            {state && <p className="mt-0.5 text-sm text-muted-foreground">{state.text}</p>}
          </div>
        </div>
        {pending > 0 && (
          <Button variant={urgent ? "destructive" : "default"} onClick={() => navigate("/alerts?status=new")}>
            Revisar alertas<ArrowRight />
          </Button>
        )}
      </div>
    </div>
  );
}

// ─── Mayor consumo ───────────────────────────────────────────────────────────

function TopConsumers({ onOpen }: { onOpen: (id: string) => void }) {
  const top = useTopDevices("24h");
  const devices = useDevices();
  const list = (top.data ?? []).filter(d => d.total_bytes > 0).slice(0, 6);
  const max = list[0]?.total_bytes ?? 0;

  return (
    <Card>
      <CardHeaderRow
        title={<><Activity />Más consumo hoy</>}
        description="Últimas 24 horas"
        actions={<Link to="/traffic" className="text-xs font-medium text-primary hover:underline">Ver tráfico</Link>}
      />
      <CardContent className="space-y-3">
        {top.isLoading ? [0, 1, 2, 3].map(i => <Skeleton key={i} className="h-9" />)
          : list.length === 0 ? <EmptyState icon={Activity} title="Sin consumo registrado" className="py-8" />
          : list.map(d => {
            const device = devices.data?.find(x => x.id === d.device_id);
            return (
              <div key={d.device_id}>
                <div className="flex items-center justify-between gap-2">
                  {device ? <DeviceLabel device={device} onClick={() => onOpen(device.id)} /> : <span className="text-sm">{d.hostname ?? d.mac}</span>}
                  <span className="tabular shrink-0 font-mono text-xs">{formatBytes(d.total_bytes)}</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="bg-brand h-full rounded-full" style={{ width: `${max ? (d.total_bytes / max) * 100 : 0}%` }} />
                </div>
              </div>
            );
          })}
      </CardContent>
    </Card>
  );
}

// ─── Alertas recientes con acciones rápidas ──────────────────────────────────

function RecentAlerts() {
  const alerts = useAlerts(100);
  const update = useUpdateAlertStatus();
  const sheet = useDeviceSheet();
  const devices = useDevices();
  const isAdmin = useIsAdmin();

  // Las pendientes primero, por gravedad y luego por fecha
  const list = (alerts.data ?? [])
    .filter(a => a.status !== "resolved")
    .sort((a, b) => Number(b.status === "new") - Number(a.status === "new")
      || severityRank(a.severity) - severityRank(b.severity)
      || b.last_seen_at.localeCompare(a.last_seen_at))
    .slice(0, 6);

  return (
    <Card className="xl:col-span-2">
      <CardHeaderRow
        title={<><Bell />Alertas que requieren atención</>}
        description="Las nuevas primero, ordenadas por gravedad"
        actions={<Link to="/alerts" className="text-xs font-medium text-primary hover:underline">Ver todas</Link>}
      />
      <CardContent className="p-0">
        {alerts.isLoading ? (
          <div className="space-y-2 p-5 pt-0">{[0, 1, 2].map(i => <Skeleton key={i} className="h-14" />)}</div>
        ) : list.length === 0 ? (
          <EmptyState icon={CheckCheck} title="Todo revisado" description="No hay alertas pendientes." />
        ) : (
          <ul className="divide-y border-t">
            {list.map(a => {
              const device = a.device_id ? devices.data?.find(d => d.id === a.device_id) : undefined;
              return (
                <li key={a.id} className="group flex items-start gap-3 px-5 py-3 transition-colors hover:bg-muted/40">
                  <SeverityBadge severity={a.severity} className="mt-0.5 w-[72px] justify-center" />
                  <Link to={`/alerts?alert=${a.id}`} className="min-w-0 flex-1">
                    <p className={cn("truncate text-sm", a.status === "new" ? "font-medium" : "text-muted-foreground")}>{a.title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {relativeTime(a.last_seen_at)}{a.occurrences > 1 && ` · ×${a.occurrences}`}
                      {a.status === "acknowledged" && " · en seguimiento"}
                    </p>
                  </Link>
                  <div className="flex shrink-0 items-center gap-1">
                    {device && (
                      <Button variant="ghost" size="xs" onClick={() => sheet.open(device.id)} className="hidden sm:inline-flex">
                        Ver equipo
                      </Button>
                    )}
                    {isAdmin && a.status === "new" && (
                      <Button
                        variant="ghost" size="icon-sm" title="Marcar como en seguimiento"
                        onClick={() => update.mutate({ id: a.id, status: "acknowledged" })}
                      >
                        <Check />
                      </Button>
                    )}
                    {isAdmin && (
                      <Button
                        variant="ghost" size="icon-sm" title="Resolver" className="hover:text-success"
                        onClick={() => update.mutate({ id: a.id, status: "resolved" })}
                      >
                        <CheckCheck />
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Destinos con más conexiones ─────────────────────────────────────────────

function TopDestinations() {
  const conns = useNetworkConnections();
  const counts = new Map<string, { count: number; service: string | null; devices: Set<string> }>();
  for (const c of conns.data?.connections ?? []) {
    if (c.status !== "open" || c.remote_is_lan) continue;
    const entry = counts.get(c.remote_ip) ?? { count: 0, service: c.service, devices: new Set<string>() };
    entry.count++;
    entry.devices.add(c.device_id);
    counts.set(c.remote_ip, entry);
  }
  const top = [...counts.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 5);

  return (
    <Card>
      <CardHeaderRow
        title={<><Globe />Destinos en Internet</>}
        description="Con más conexiones abiertas ahora"
        actions={<Link to="/connections" className="text-xs font-medium text-primary hover:underline">Conexiones</Link>}
      />
      <CardContent>
        {top.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Sin conexiones a Internet abiertas.</p>
        ) : (
          <ul className="space-y-1">
            {top.map(([ip, info]) => (
              <li key={ip}>
                <Link
                  to={`/connections?q=${encodeURIComponent(ip)}`}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-muted/50"
                >
                  <span className="font-mono text-xs">{ip}</span>
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    {info.service ?? "—"} · {info.devices.size} {info.devices.size === 1 ? "equipo" : "equipos"}
                    <span className="tabular rounded-full bg-foreground/5 px-1.5">{info.count}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
