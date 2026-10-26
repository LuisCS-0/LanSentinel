// Alertas en dos columnas: la lista filtrable a la izquierda y el detalle de
// la seleccionada a la derecha (en el móvil, en un modal). La alerta y el
// filtro de estado van en la URL para poder enlazarlos desde otras pantallas.

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Ban, Bell, Check, CheckCheck, ChevronRight, Clock, Copy, EyeOff, Layers, MonitorSmartphone,
  RotateCcw, Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EmptyState, Select, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { SeverityBadge } from "@/components/SeverityBadge";
import { BlockRemoteDialog } from "@/components/connections/BlockRemoteDialog";
import { DeviceLabel } from "@/components/devices/DeviceBits";
import { useAlerts, useDevices } from "@/hooks/useApi";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useUpdateAlertStatus } from "@/hooks/useMutations";
import { copyText } from "@/lib/clipboard";
import { relativeTime } from "@/lib/dates";
import { SEVERITY, SEVERITY_ORDER } from "@/lib/severity";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { Alert, AlertSeverity, AlertStatus } from "@/lib/types";

type StatusFilter = "new" | "acknowledged" | "resolved" | "all";

const SOURCE_LABEL: Record<string, string> = {
  monitor: "Monitor", suricata: "Suricata", firewall: "Cortafuegos", system: "Sistema",
};
const STATUS_LABEL: Record<AlertStatus, string> = {
  new: "Sin revisar", acknowledged: "En seguimiento", resolved: "Resuelta", ignored: "Ignorada",
};

export default function AlertsPage() {
  const alerts = useAlerts(100);
  const update = useUpdateAlertStatus();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState<AlertSeverity | "">("");
  const [source, setSource] = useState("");
  const wide = useMediaQuery("(min-width: 1024px)");

  const status = (params.get("status") as StatusFilter | null) ?? "new";
  const selectedId = Number(params.get("alert")) || null;
  const setParam = (key: string, value: string | null) => setParams(prev => {
    const next = new URLSearchParams(prev);
    if (value) next.set(key, value);
    else next.delete(key);
    return next;
  }, { replace: key === "status" });

  const list = useMemo(() => alerts.data ?? [], [alerts.data]);
  const counts = {
    new: list.filter(a => a.status === "new").length,
    acknowledged: list.filter(a => a.status === "acknowledged").length,
    resolved: list.filter(a => a.status === "resolved" || a.status === "ignored").length,
    all: list.length,
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return list
      .filter(a => {
        if (status === "resolved" ? a.status !== "resolved" && a.status !== "ignored" : status !== "all" && a.status !== status) return false;
        if (severity && a.severity !== severity) return false;
        if (source && a.source !== source) return false;
        if (q && !`${a.title} ${a.description ?? ""}`.toLowerCase().includes(q)) return false;
        return true;
      })
      .sort((a, b) => b.last_seen_at.localeCompare(a.last_seen_at));
  }, [list, status, severity, source, search]);

  const bySeverity = SEVERITY_ORDER.map(s => ({
    value: s,
    count: list.filter(a => a.severity === s && (status === "all" || a.status === status || (status === "resolved" && a.status === "ignored"))).length,
  }));
  const selected = list.find(a => a.id === selectedId) ?? null;

  // Acción en bloque sobre las alertas sin revisar que se están viendo
  const visibleNew = filtered.filter(a => a.status === "new");
  const acknowledgeAll = async () => {
    await Promise.all(visibleNew.map(a => update.mutateAsync({ id: a.id, status: "acknowledged" })));
    toast({ title: `${visibleNew.length} alertas marcadas como en seguimiento` });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alertas"
        description={`${counts.new} sin revisar · ${counts.acknowledged} en seguimiento · ${counts.all} en total`}
        actions={visibleNew.length > 0 && (
          <Button variant="outline" onClick={acknowledgeAll} disabled={update.isPending}>
            <CheckCheck />Marcar {visibleNew.length} como vistas
          </Button>
        )}
      />

      <div className="grid gap-4 lg:grid-cols-12">
        {/* Lista */}
        <Card className="overflow-hidden lg:col-span-5">
          <div className="space-y-3 border-b p-4">
            <Segmented<StatusFilter>
              value={status} onChange={v => setParam("status", v)} size="sm"
              options={[
                { value: "new", label: "Sin revisar", count: counts.new, tone: "warning" },
                { value: "acknowledged", label: "Seguimiento", count: counts.acknowledged },
                { value: "resolved", label: "Resueltas", count: counts.resolved },
                { value: "all", label: "Todas", count: counts.all },
              ]}
            />
            <div className="flex flex-wrap gap-1.5">
              {bySeverity.map(({ value, count }) => (
                <button
                  key={value}
                  onClick={() => setSeverity(s => (s === value ? "" : value))}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                    severity === value ? "border-primary/50 bg-primary/10 text-foreground" : "text-muted-foreground hover:text-foreground",
                    count === 0 && severity !== value && "opacity-50",
                  )}
                >
                  <span className={cn("size-1.5 rounded-full", SEVERITY[value].bar)} />
                  {SEVERITY[value].label}
                  <span className="tabular">{count}</span>
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Input icon={Search} value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar en las alertas…" />
              <Select value={source} onChange={e => setSource(e.target.value)} aria-label="Origen" className="w-36 shrink-0">
                <option value="">Todo origen</option>
                {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            </div>
          </div>

          {alerts.isLoading ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-16" />)}</div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={status === "new" ? CheckCheck : Bell}
              title={status === "new" && !search && !severity && !source ? "Todo revisado" : "Ninguna alerta coincide"}
              description={status === "new" && !search && !severity && !source ? "No hay alertas pendientes. Buen trabajo." : "Prueba con otros filtros."}
            />
          ) : (
            <ul className="max-h-[calc(100dvh-22rem)] divide-y overflow-y-auto lg:max-h-[calc(100dvh-20rem)]">
              {filtered.map(a => (
                <li key={a.id}>
                  <button
                    onClick={() => setParam("alert", String(a.id))}
                    className={cn(
                      "relative flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40",
                      selectedId === a.id && "bg-primary/[0.07]",
                    )}
                  >
                    <span className={cn("absolute inset-y-2 left-0 w-1 rounded-r", SEVERITY[a.severity].bar, a.status !== "new" && "opacity-30")} />
                    <div className="min-w-0 flex-1">
                      <p className={cn("line-clamp-2 text-sm", a.status === "new" ? "font-medium" : "text-muted-foreground")}>{a.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                        <span className={SEVERITY[a.severity].text}>{SEVERITY[a.severity].label}</span>
                        <span>·</span>
                        <span>{SOURCE_LABEL[a.source] ?? a.source}</span>
                        <span>·</span>
                        <span>{relativeTime(a.last_seen_at)}</span>
                        {a.occurrences > 1 && <Badge variant="secondary" className="px-1.5 py-0"><Layers />×{a.occurrences}</Badge>}
                      </div>
                    </div>
                    <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Detalle: columna en escritorio */}
        <div className="hidden lg:col-span-7 lg:block">
          <Card className="sticky top-24">
            {selected ? <AlertDetail alert={selected} /> : (
              <EmptyState icon={Bell} title="Selecciona una alerta" description="Su detalle y las acciones aparecerán aquí." className="py-24" />
            )}
          </Card>
        </div>
      </div>

      {/* Detalle: modal en el móvil (en escritorio va en la columna derecha) */}
      <Dialog open={!!selected && !wide} onClose={() => setParam("alert", null)} title="Detalle de la alerta" className="max-w-2xl">
        {selected && <AlertDetail alert={selected} bare />}
      </Dialog>
    </div>
  );
}

// ─── Detalle ─────────────────────────────────────────────────────────────────

function AlertDetail({ alert, bare = false }: { alert: Alert; bare?: boolean }) {
  const update = useUpdateAlertStatus();
  const devices = useDevices();
  const sheet = useDeviceSheet();
  const [toBlock, setToBlock] = useState<string | null>(null);
  const device = alert.device_id ? devices.data?.find(d => d.id === alert.device_id) : undefined;

  // Suricata guarda la IP de origen del evento: si es de Internet se ofrece bloquearla
  const srcIp = typeof alert.raw_payload?.src_ip === "string" ? alert.raw_payload.src_ip : null;
  const srcIsPublic = srcIp && !/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.|169\.254\.|f[cd]|fe80)/i.test(srcIp);
  const setStatus = (status: AlertStatus) => update.mutate({ id: alert.id, status });

  return (
    <div className={cn(!bare && "p-6")}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={alert.severity} />
        <Badge variant="outline">{SOURCE_LABEL[alert.source] ?? alert.source}</Badge>
        <Badge variant={alert.status === "new" ? "warning" : alert.status === "acknowledged" ? "info" : "success"}>
          {STATUS_LABEL[alert.status]}
        </Badge>
      </div>
      <h2 className="mt-3 text-lg font-semibold leading-snug">{alert.title}</h2>
      {alert.description && <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">{alert.description}</p>}

      {/* Acciones */}
      <div className="mt-5 flex flex-wrap gap-2">
        {alert.status === "new" && (
          <Button variant="soft" size="sm" onClick={() => setStatus("acknowledged")} disabled={update.isPending}><Check />En seguimiento</Button>
        )}
        {alert.status !== "resolved" && (
          <Button variant="success" size="sm" onClick={() => setStatus("resolved")} disabled={update.isPending}><CheckCheck />Resolver</Button>
        )}
        {alert.status !== "new" && (
          <Button variant="outline" size="sm" onClick={() => setStatus("new")} disabled={update.isPending}><RotateCcw />Reabrir</Button>
        )}
        {alert.status !== "ignored" && alert.status !== "resolved" && (
          <Button variant="ghost" size="sm" onClick={() => setStatus("ignored")} disabled={update.isPending}><EyeOff />Ignorar</Button>
        )}
        {srcIsPublic && (
          <Button variant="outline" size="sm" className="hover:text-destructive" onClick={() => setToBlock(srcIp)}><Ban />Bloquear {srcIp}</Button>
        )}
      </div>

      <dl className="mt-6 grid gap-4 rounded-xl border bg-muted/30 p-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground"><Clock className="size-3" />{alert.occurrences > 1 ? "Primera vez" : "Detectada"}</dt>
          <dd className="mt-1">{new Date(alert.created_at).toLocaleString("es-ES")}</dd>
          <dd className="text-xs text-muted-foreground">{relativeTime(alert.created_at)}</dd>
        </div>
        {alert.occurrences > 1 && (
          <div>
            <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground"><Layers className="size-3" />Última vez · {alert.occurrences} eventos</dt>
            <dd className="mt-1">{new Date(alert.last_seen_at).toLocaleString("es-ES")}</dd>
            <dd className="text-xs text-muted-foreground">{relativeTime(alert.last_seen_at)}</dd>
          </div>
        )}
        {device && (
          <div className="sm:col-span-2">
            <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground"><MonitorSmartphone className="size-3" />Dispositivo</dt>
            <dd className="mt-1.5 flex items-center justify-between gap-2">
              <DeviceLabel device={device} onClick={() => sheet.open(device.id)} />
              <Button variant="ghost" size="xs" onClick={() => sheet.open(device.id)}>Abrir<ChevronRight /></Button>
            </dd>
          </div>
        )}
      </dl>

      {alert.raw_payload && <RawPayload payload={alert.raw_payload} />}
      <BlockRemoteDialog ip={toBlock} onClose={() => setToBlock(null)} />
    </div>
  );
}

function RawPayload({ payload }: { payload: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const text = JSON.stringify(payload, null, 2);
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <button onClick={() => setOpen(o => !o)} className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />Datos originales del evento
        </button>
        {open && (
          <Button variant="ghost" size="xs" onClick={() => copyText(text)}><Copy />Copiar</Button>
        )}
      </div>
      {open && <pre className="mt-2 max-h-72 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-[11px] leading-relaxed">{text}</pre>}
    </div>
  );
}
