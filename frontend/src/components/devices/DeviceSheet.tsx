// Detalle de un dispositivo en un panel lateral. Se abre desde cualquier
// pantalla con ?device=<id> (ver useDeviceSheet) y tiene pestañas para no
// obligar a hacer scroll: resumen, conexiones, consumo y puertos.

import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowDown, ArrowUp, Ban, Cable, ChevronRight, Loader2, Network,
  ScanLine, ShieldAlert, ShieldCheck, ShieldOff, X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { Sheet } from "@/components/ui/sheet";
import { RangeSelector } from "@/components/RangeSelector";
import { SeverityBadge } from "@/components/SeverityBadge";
import { TrafficLegend, UsageChart } from "@/components/charts";
import { ConnectionsTable } from "@/components/connections/ConnectionsTable";
import { DeviceAvatar, DeviceStatusBadge } from "@/components/devices/DeviceBits";
import { DomainsTab } from "@/components/devices/DomainsTab";
import { useAlerts, useDevices } from "@/hooks/useApi";
import { useDeviceSheet, type DeviceTab } from "@/hooks/useDeviceSheet";
import { useDeviceTraffic } from "@/hooks/useDeviceTraffic";
import {
  useBlockDevice, useDeviceConnections, useDevicePorts, useScanPorts, useTrustDevice,
} from "@/hooks/useDevices";
import { useQuarantine } from "@/hooks/useQuarantine";
import { useDeviceUsage, useUsageProfile } from "@/hooks/useTrafficUsage";
import { extractErrorMessage } from "@/lib/api";
import { isActive } from "@/lib/connections";
import { relativeTime, shortRelative } from "@/lib/dates";
import { deviceName, isOnline } from "@/lib/devices";
import { formatBps, formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Device, TrafficRange } from "@/lib/types";
import { useIsAdmin } from "@/hooks/useAuth";
import { useIsBasic } from "@/lib/viewMode";
import { explainAlert } from "@/lib/plain";

export function DeviceSheet() {
  const sheet = useDeviceSheet();
  const devices = useDevices();
  const device = devices.data?.find(d => d.id === sheet.deviceId) ?? null;

  return (
    <Sheet open={!!sheet.deviceId} onClose={sheet.close} label="Detalle del dispositivo">
      {device ? (
        <DeviceDetail device={device} tab={sheet.tab} onTab={sheet.setTab} onClose={sheet.close} />
      ) : (
        <div className="flex flex-1 flex-col">
          <div className="flex justify-end p-3">
            <Button variant="ghost" size="icon-sm" onClick={sheet.close} aria-label="Cerrar"><X /></Button>
          </div>
          {devices.isLoading ? (
            <div className="space-y-3 p-6"><Skeleton className="h-14 w-14" /><Skeleton className="h-6 w-1/2" /><Skeleton className="h-40" /></div>
          ) : (
            <EmptyState icon={Network} title="Dispositivo no encontrado" description="Puede que se haya eliminado de la lista." />
          )}
        </div>
      )}
    </Sheet>
  );
}

function DeviceDetail({
  device, tab, onTab, onClose,
}: { device: Device; tab: DeviceTab; onTab: (t: DeviceTab) => void; onClose: () => void }) {
  const quarantine = useQuarantine();
  const trust = useTrustDevice();
  const block = useBlockDevice();
  const scan = useScanPorts();
  const isAdmin = useIsAdmin();
  const basic = useIsBasic();
  const conns = useDeviceConnections(device.id);
  const ports = useDevicePorts(device.id);

  const openCount = conns.data?.connections.filter(c => c.status === "open").length;
  const riskyPorts = latestPorts(ports.data ?? []).filter(p => p.risk_severity).length;
  const error = block.error ?? trust.error ?? scan.error;
  const shown: DeviceTab = basic && tab !== "usage" ? "summary" : tab;

  return (
    <>
      {/* Cabecera fija */}
      <div className="relative border-b bg-gradient-to-b from-primary/[0.07] to-transparent px-5 pb-4 pt-5">
        <Button variant="ghost" size="icon-sm" onClick={onClose} className="absolute right-3 top-3" aria-label="Cerrar">
          <X />
        </Button>
        <div className="flex items-start gap-4 pr-8">
          <DeviceAvatar device={device} size="lg" />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold">{deviceName(device)}</h2>
            {!basic && (
              <p className="font-mono text-xs text-muted-foreground">
                {device.ip ?? "sin IP"} · {device.mac}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <DeviceStatusBadge device={device} quarantine={quarantine.data?.enabled ?? false} />
              <Badge variant={isOnline(device) ? "success" : "outline"} dot>
                {isOnline(device) ? "En línea" : `Visto ${relativeTime(device.last_seen)}`}
              </Badge>
            </div>
          </div>
        </div>

        {isAdmin && <div className="mt-4 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={device.is_trusted ? "outline" : "success"}
            onClick={() => trust.mutate({ id: device.id, trusted: !device.is_trusted })}
            disabled={trust.isPending}
          >
            {device.is_trusted ? <ShieldOff /> : <ShieldCheck />}
            {device.is_trusted ? "Quitar confianza" : "Marcar de confianza"}
          </Button>
          <Button
            size="sm"
            variant={device.is_blocked ? "outline" : "destructive"}
            onClick={() => block.mutate({ id: device.id, blocked: !device.is_blocked })}
            disabled={block.isPending}
          >
            {block.isPending ? <Loader2 className="animate-spin" /> : <Ban />}
            {device.is_blocked ? "Desbloquear" : "Bloquear"}
          </Button>
          {!basic && (
            <Button size="sm" variant="outline" onClick={() => scan.mutate({ id: device.id })} disabled={scan.isPending}>
              {scan.isPending ? <Loader2 className="animate-spin" /> : <ScanLine />}
              {scan.isPending ? "Escaneando…" : "Escanear puertos"}
            </Button>
          )}
        </div>}
        {error && (
          <p className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 p-2.5 text-xs text-destructive">
            <AlertCircle className="mt-px size-3.5 shrink-0" />{extractErrorMessage(error)}
          </p>
        )}
      </div>

      {/* Pestañas (en el modo básico, solo el resumen y el consumo) */}
      <div className="border-b px-5 py-2.5">
        <Segmented<DeviceTab>
          value={shown}
          onChange={onTab}
          size="sm"
          options={basic ? [
            { value: "summary", label: "Resumen" },
            { value: "usage", label: "Consumo" },
          ] : [
            { value: "summary", label: "Resumen" },
            { value: "connections", label: "Conexiones", count: openCount },
            // El historial de dominios solo lo ven los administradores
            ...(isAdmin ? [{ value: "domains" as const, label: "Dominios" }] : []),
            { value: "usage", label: "Consumo" },
            { value: "ports", label: "Puertos", count: riskyPorts || undefined, tone: "destructive" },
          ]}
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {shown === "summary" && <SummaryTab device={device} onTab={onTab} />}
        {shown === "connections" && <ConnectionsTab deviceId={device.id} />}
        {shown === "domains" && isAdmin && <DomainsTab deviceId={device.id} />}
        {shown === "usage" && <UsageTab deviceId={device.id} />}
        {shown === "ports" && <PortsTab device={device} scanning={scan.isPending} />}
      </div>
    </>
  );
}

// ─── Resumen ─────────────────────────────────────────────────────────────────

function SummaryTab({ device, onTab }: { device: Device; onTab: (t: DeviceTab) => void }) {
  const traffic = useDeviceTraffic(device.id);
  const conns = useDeviceConnections(device.id);
  const alerts = useAlerts(100);
  const usage = useDeviceUsage(device.id, "24h");
  const basic = useIsBasic();

  const deviceAlerts = (alerts.data ?? []).filter(a => a.device_id === device.id).slice(0, 4);
  const open = (conns.data?.connections ?? []).filter(c => c.status === "open");
  // Destinos más frecuentes entre las conexiones abiertas
  const remoteCounts = new Map<string, { count: number; service: string | null }>();
  for (const c of open) {
    const entry = remoteCounts.get(c.remote_ip) ?? { count: 0, service: c.service };
    entry.count++;
    remoteCounts.set(c.remote_ip, entry);
  }
  const topRemotes = [...remoteCounts.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 5);

  return (
    <div className="space-y-5 p-5">
      {/* Ahora mismo */}
      <div className={cn("grid gap-3", basic ? "grid-cols-2" : "grid-cols-3")}>
        <MiniStat icon={ArrowDown} tone="text-primary" label="Descarga" value={traffic.data?.tracking ? formatBps(traffic.data.rx_bps) : "—"} />
        <MiniStat icon={ArrowUp} tone="text-upload" label="Subida" value={traffic.data?.tracking ? formatBps(traffic.data.tx_bps) : "—"} />
        {!basic && (
          <MiniStat
            icon={Cable} tone="text-success" label="Conexiones"
            value={conns.data?.available === false ? "—" : String(open.length)}
            onClick={() => onTab("connections")}
          />
        )}
      </div>

      {/* Datos del dispositivo */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border bg-muted/30 p-4 text-sm">
        <Info label="Fabricante" value={device.vendor ?? "Desconocido"} />
        <Info label="Nombre de red" value={device.hostname ?? "—"} />
        {!basic && <Info label="Dirección IP" value={device.ip ?? "—"} mono />}
        {!basic && <Info label="Dirección MAC" value={device.mac} mono />}
        <Info label="Última vez visto" value={shortRelative(device.last_seen)} />
        {!basic && <Info label="Último escaneo de puertos" value={device.last_port_scan_at ? shortRelative(device.last_port_scan_at) : "Nunca"} />}
        {/* Las IPv6 en uso (las de privacidad cambian cada día) */}
        {!basic && !!device.ipv6_addresses?.length && (
          <div className="col-span-2 min-w-0">
            <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Direcciones IPv6</dt>
            <dd className="mt-0.5 space-y-0.5 font-mono text-xs">
              {device.ipv6_addresses.map(a => <span key={a} className="block truncate" title={a}>{a}</span>)}
            </dd>
          </div>
        )}
      </dl>

      {/* Consumo de hoy */}
      <Section title="Consumo en las últimas 24 h" action={<LinkButton onClick={() => onTab("usage")}>Ver más</LinkButton>}>
        {usage.data && usage.data.total_recv + usage.data.total_sent > 0 ? (
          <>
            <p className="tabular mb-2 text-xs text-muted-foreground">
              <span className="text-primary">↓ {formatBytes(usage.data.total_recv)}</span>
              <span className="mx-2">·</span>
              <span className="text-upload">↑ {formatBytes(usage.data.total_sent)}</span>
            </p>
            <UsageChart buckets={usage.data.buckets} unit={usage.data.unit} height={130} />
          </>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">Sin tráfico registrado.</p>
        )}
      </Section>

      {/* Destinos */}
      {!basic && <Section title="Con quién habla ahora" action={<LinkButton onClick={() => onTab("connections")}>Todas</LinkButton>}>
        {topRemotes.length === 0 ? (
          <p className="py-3 text-center text-sm text-muted-foreground">Sin conexiones abiertas que pasen por LanSentinel.</p>
        ) : (
          <ul className="divide-y rounded-xl border">
            {topRemotes.map(([ip, info]) => (
              <li key={ip} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="font-mono text-xs">{ip}</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {info.service ?? "—"}
                  <Badge variant="secondary" className="tabular">{info.count}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>}

      {/* Alertas del dispositivo */}
      <Section title={basic ? "Avisos de este equipo" : "Alertas recientes"} action={<Link to="/alerts" className="text-xs font-medium text-primary hover:underline">Ir a alertas</Link>}>
        {deviceAlerts.length === 0 ? (
          <p className="py-3 text-center text-sm text-muted-foreground">Ninguna alerta asociada a este dispositivo.</p>
        ) : (
          <ul className="space-y-2">
            {deviceAlerts.map(a => (
              <li key={a.id}>
                <Link
                  to={`/alerts?alert=${a.id}`}
                  className="flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50"
                >
                  <SeverityBadge severity={a.severity} className="mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{basic ? explainAlert(a).title : a.title}</p>
                    <p className="text-xs text-muted-foreground">{relativeTime(a.last_seen_at)}{a.occurrences > 1 && ` · ×${a.occurrences}`}</p>
                  </div>
                  <ChevronRight className="mt-1 size-4 text-muted-foreground" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

// ─── Conexiones ──────────────────────────────────────────────────────────────

function ConnectionsTab({ deviceId }: { deviceId: string }) {
  const conns = useDeviceConnections(deviceId);
  const [filter, setFilter] = useState<"active" | "queries" | "all">("active");
  const all = conns.data?.connections ?? [];
  const visible = filter === "all" ? all : filter === "queries" ? all.filter(c => c.status === "done") : all.filter(isActive);

  if (conns.isLoading) return <div className="space-y-2 p-5">{[0, 1, 2].map(i => <Skeleton key={i} className="h-10" />)}</div>;
  if (conns.data?.available === false) {
    return (
      <EmptyState
        icon={AlertCircle} title="No se puede leer la tabla de conexiones"
        description="Falta la herramienta conntrack en el backend o el permiso NET_ADMIN."
      />
    );
  }

  return (
    <div className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pb-3">
        <Segmented
          value={filter} onChange={setFilter} size="sm"
          options={[
            { value: "active", label: "Activas", count: all.filter(isActive).length },
            { value: "queries", label: "Consultas", count: all.filter(c => c.status === "done").length },
            { value: "all", label: "Todas", count: all.length },
          ]}
        />
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="size-1.5 animate-pulse rounded-full bg-success" />Se actualiza cada 5 s
        </span>
      </div>
      {visible.length === 0 ? (
        <EmptyState icon={Cable} title="Sin conexiones activas" description="Solo se ven las que pasan por LanSentinel (hacia Internet o hacia este equipo)." />
      ) : (
        <ConnectionsTable connections={visible} compact />
      )}
    </div>
  );
}

// ─── Consumo ─────────────────────────────────────────────────────────────────

function UsageTab({ deviceId }: { deviceId: string }) {
  const [range, setRange] = useState<TrafficRange>("24h");
  const usage = useDeviceUsage(deviceId, range);
  const recv = usage.data?.total_recv ?? 0;
  const sent = usage.data?.total_sent ?? 0;

  return (
    <div className="space-y-4 p-5">
      <RangeSelector value={range} onChange={setRange} size="sm" />
      <div className="grid grid-cols-3 gap-3">
        <MiniStat icon={ArrowDown} tone="text-primary" label="Descarga" value={formatBytes(recv)} />
        <MiniStat icon={ArrowUp} tone="text-upload" label="Subida" value={formatBytes(sent)} />
        <MiniStat icon={Activity} tone="text-foreground" label="Total" value={formatBytes(recv + sent)} />
      </div>
      {usage.isLoading ? (
        <Skeleton className="h-60" />
      ) : recv + sent === 0 || !usage.data ? (
        <EmptyState icon={Activity} title="Sin tráfico en este periodo" />
      ) : (
        <div className="rounded-xl border p-3">
          <div className="mb-2 flex justify-end"><TrafficLegend /></div>
          <UsageChart buckets={usage.data.buckets} unit={usage.data.unit} height={240} />
        </div>
      )}
      <UsageProfileBox deviceId={deviceId} />
    </div>
  );
}

// Lo habitual de este dispositivo por hora y a partir de cuánto se avisa de un pico
function UsageProfileBox({ deviceId }: { deviceId: string }) {
  const profile = useUsageProfile(deviceId);
  const p = profile.data;
  if (!p?.enabled) return null;
  const learning = p.active_hours < p.min_hours;
  const row = (label: string, d: typeof p.upload, icon: ReactNode) => d && (
    <div className="flex items-center gap-2">
      {icon}<span className="w-20 text-muted-foreground">{label}</span>
      <span className="tabular font-medium">{formatBytes(d.median)}/h</span>
      <span className="ml-auto text-xs text-muted-foreground">aviso por encima de {formatBytes(d.threshold)}/h</span>
    </div>
  );
  return (
    <div className="space-y-2 rounded-xl border bg-muted/30 p-4 text-sm">
      <p className="font-medium">Consumo habitual por hora</p>
      {learning ? (
        <p className="text-muted-foreground">
          Aprendiendo su patrón: {p.active_hours} de {p.min_hours} horas con actividad. Hasta entonces no se avisa de picos.
        </p>
      ) : (
        <>
          {row("Subida", p.upload, <ArrowUp className="size-3.5 text-upload" />)}
          {row("Descarga", p.download, <ArrowDown className="size-3.5 text-primary" />)}
          <p className="text-xs text-muted-foreground">
            Mediana de sus horas con actividad de los últimos {p.days} días. Si una hora se dispara por encima, se crea una alerta.
          </p>
        </>
      )}
    </div>
  );
}

// ─── Puertos ─────────────────────────────────────────────────────────────────

type PortRow = NonNullable<ReturnType<typeof useDevicePorts>["data"]>[number];

// El backend guarda el histórico de escaneos: nos quedamos con el último de cada puerto
function latestPorts(ports: PortRow[]): PortRow[] {
  return Array.from(
    new Map(
      [...ports].sort((a, b) => b.scanned_at.localeCompare(a.scanned_at)).map(p => [`${p.port}-${p.protocol}`, p]),
    ).values(),
  ).sort((a, b) => a.port - b.port);
}

function PortsTab({ device, scanning }: { device: Device; scanning: boolean }) {
  const ports = useDevicePorts(device.id);
  const list = latestPorts(ports.data ?? []);

  return (
    <div className="space-y-3 p-5">
      <p className="text-xs text-muted-foreground">
        {scanning ? "Escaneo en curso, puede tardar un par de minutos…"
          : device.last_port_scan_at ? `Último escaneo completo ${relativeTime(device.last_port_scan_at)}. Se repite automáticamente cada día.`
          : "Aún no se ha escaneado. Se hace automáticamente cada día o con el botón de arriba."}
      </p>
      {ports.isLoading ? (
        <Skeleton className="h-32" />
      ) : list.length === 0 ? (
        <EmptyState icon={ShieldCheck} title="Sin puertos abiertos" description={device.last_port_scan_at ? "El último escaneo no encontró servicios expuestos." : undefined} />
      ) : (
        <ul className="space-y-2">
          {list.map(p => (
            <li
              key={`${p.port}-${p.protocol}`}
              className={cn("rounded-xl border p-3", p.risk_severity && "border-destructive/30 bg-destructive/[0.04]")}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="tabular rounded-md bg-muted px-2 py-1 font-mono text-xs font-medium">{p.port}/{p.protocol}</span>
                  <div>
                    <p className="text-sm font-medium">{p.service ?? "Desconocido"}</p>
                    {p.version && <p className="text-xs text-muted-foreground">{p.version}</p>}
                  </div>
                </div>
                {p.risk_severity ? <SeverityBadge severity={p.risk_severity} /> : <Badge variant="success" dot>{p.state === "open" ? "Abierto" : p.state}</Badge>}
              </div>
              {p.risk_reason && (
                <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
                  <ShieldAlert className="mt-px size-3.5 shrink-0 text-destructive" />{p.risk_reason}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Piezas ──────────────────────────────────────────────────────────────────

function MiniStat({
  icon: Icon, tone, label, value, onClick,
}: { icon: typeof Activity; tone: string; label: string; value: string; onClick?: () => void }) {
  const body = (
    <>
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <Icon className={cn("size-3.5", tone)} />{label}
      </p>
      <p className="tabular mt-1.5 truncate font-mono text-sm font-semibold sm:text-base" title={value}>{value}</p>
    </>
  );
  const classes = "rounded-xl border bg-muted/30 p-3 text-left";
  return onClick
    ? <button onClick={onClick} className={cn(classes, "transition-colors hover:border-primary/40")}>{body}</button>
    : <div className={classes}>{body}</div>;
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className={cn("mt-0.5 truncate", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function LinkButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return <button onClick={onClick} className="text-xs font-medium text-primary hover:underline">{children}</button>;
}
