import { useState, useMemo } from "react";
import {
  Check, Archive, RefreshCw, Search, Filter,
} from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useAlerts } from "@/hooks/useApi";
import { useUpdateAlertStatus } from "@/hooks/useMutations";
import { relativeTime } from "@/lib/dates";
import type { Alert, AlertSeverity, AlertStatus } from "@/lib/types";

type SeverityFilter = "all" | AlertSeverity;
type StatusFilter = "all" | AlertStatus;

export default function AlertsPage() {
  const alerts = useAlerts(100);
  const updateMutation = useUpdateAlertStatus();

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [detailAlert, setDetailAlert] = useState<Alert | null>(null);

  // Filtrado de alertas según criterios
  const filtered = useMemo(() => {
    const list = alerts.data || [];
    return list.filter(a => {
      if (severity !== "all" && a.severity !== severity) return false;
      if (status !== "all" && a.status !== status) return false;
      if (search) {
        const q = search.toLowerCase();
        const matchesSearch =
          a.title.toLowerCase().includes(q) ||
          (a.description || "").toLowerCase().includes(q) ||
          a.source.toLowerCase().includes(q);
        if (!matchesSearch) return false;
      }
      return true;
    });
  }, [alerts.data, search, severity, status]);

  // Conteos para los filtros
  const counts = useMemo(() => {
    const list = alerts.data || [];
    return {
      total: list.length,
      new: list.filter(a => a.status === "new").length,
      acknowledged: list.filter(a => a.status === "acknowledged").length,
    };
  }, [alerts.data]);

  const handleAcknowledge = (alert: Alert) => {
    updateMutation.mutate({ id: alert.id, status: "acknowledged" });
  };

  const handleResolve = (alert: Alert) => {
    updateMutation.mutate({ id: alert.id, status: "resolved" });
  };

  return (
    <div className="container py-8 space-y-6">
      {/* Cabecera */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Alertas</h1>
          <p className="text-muted-foreground mt-1">
            {counts.new} sin revisar · {counts.acknowledged} en seguimiento ·{" "}
            {counts.total} en total
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => alerts.refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refrescar
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Eventos detectados</CardTitle>
          <CardDescription>
            Filtra y revisa las alertas generadas por el sistema
          </CardDescription>

          {/* Buscador */}
          <div className="relative pt-3">
            <Search className="absolute left-3 top-1/2 translate-y-[2px] h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar en título, descripción o fuente…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Filtros */}
          <div className="flex flex-wrap gap-2 pt-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground mr-1">
              <Filter className="h-3 w-3" />
              Severidad:
            </div>
            {(["all", "critical", "high", "medium", "low", "info"] as SeverityFilter[]).map(s => (
              <Button
                key={s}
                variant={severity === s ? "default" : "outline"}
                size="sm"
                onClick={() => setSeverity(s)}
              >
                {s === "all" ? "Todas" : s}
              </Button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground mr-1">
              <Filter className="h-3 w-3" />
              Estado:
            </div>
            {(["all", "new", "acknowledged", "resolved"] as StatusFilter[]).map(s => (
              <Button
                key={s}
                variant={status === s ? "default" : "outline"}
                size="sm"
                onClick={() => setStatus(s)}
              >
                {s === "all" && "Todos"}
                {s === "new" && "Sin revisar"}
                {s === "acknowledged" && "En seguimiento"}
                {s === "resolved" && "Resueltos"}
              </Button>
            ))}
          </div>
        </CardHeader>

        <CardContent>
          {alerts.isLoading ? (
            <p className="text-center py-12 text-muted-foreground">
              Cargando alertas…
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-center py-12 text-muted-foreground">
              No hay alertas que coincidan con los filtros aplicados.
            </p>
          ) : (
            <div className="space-y-2">
              {filtered.map(alert => (
                <AlertItem
                  key={alert.id}
                  alert={alert}
                  onView={() => setDetailAlert(alert)}
                  onAcknowledge={() => handleAcknowledge(alert)}
                  onResolve={() => handleResolve(alert)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDetailDialog alert={detailAlert} onClose={() => setDetailAlert(null)} />
    </div>
  );
}

// ─── Subcomponente: una fila de alerta ───────────────────────────────────────

interface AlertItemProps {
  alert: Alert;
  onView: () => void;
  onAcknowledge: () => void;
  onResolve: () => void;
}

function AlertItem({ alert, onView, onAcknowledge, onResolve }: AlertItemProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-md border hover:bg-muted/30 transition-colors">
      <SeverityBadge severity={alert.severity} className="mt-0.5 flex-shrink-0" />

      <div className="flex-1 min-w-0 cursor-pointer" onClick={onView}>
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-medium text-sm">{alert.title}</p>
          <Badge variant="outline" className="text-xs">{alert.source}</Badge>
          {alert.occurrences > 1 && (
            <Badge
              variant="secondary"
              className="text-xs"
              title="Eventos repetidos agrupados en esta alerta"
            >
              ×{alert.occurrences}
            </Badge>
          )}
          {alert.status === "acknowledged" && (
            <Badge variant="secondary" className="text-xs">en seguimiento</Badge>
          )}
          {alert.status === "resolved" && (
            <Badge variant="secondary" className="text-xs">resuelta</Badge>
          )}
        </div>
        {alert.description && (
          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
            {alert.description}
          </p>
        )}
        <p className="text-xs text-muted-foreground mt-1">
          {relativeTime(alert.last_seen_at ?? alert.created_at)}
        </p>
      </div>

      {/* Acciones rápidas */}
      <div className="flex gap-1 flex-shrink-0">
        {alert.status === "new" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onAcknowledge}
            title="Marcar como en seguimiento"
          >
            <Check className="h-4 w-4" />
          </Button>
        )}
        {alert.status !== "resolved" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onResolve}
            title="Marcar como resuelta"
          >
            <Archive className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

// ─── Subcomponente: modal con el detalle completo ────────────────────────────

interface AlertDetailDialogProps {
  alert: Alert | null;
  onClose: () => void;
}

function AlertDetailDialog({ alert, onClose }: AlertDetailDialogProps) {
  if (!alert) return null;

  return (
    <Dialog open={!!alert} onClose={onClose} title={alert.title} className="max-w-2xl">
      <div className="space-y-4">
        {/* Metadatos */}
        <div className="grid grid-cols-3 gap-3 text-sm pb-3 border-b">
          <div>
            <p className="text-xs text-muted-foreground">Severidad</p>
            <SeverityBadge severity={alert.severity} className="mt-1" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Fuente</p>
            <p className="font-mono text-xs mt-1">{alert.source}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Estado</p>
            <p className="text-xs mt-1">{alert.status}</p>
          </div>
        </div>

        {alert.description && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Descripción</p>
            <p className="text-sm">{alert.description}</p>
          </div>
        )}

        <div>
          <p className="text-xs text-muted-foreground mb-1">
            {alert.occurrences > 1 ? "Primera detección" : "Detectada"}
          </p>
          <p className="text-sm">
            {new Date(alert.created_at).toLocaleString("es-ES")} ({relativeTime(alert.created_at)})
          </p>
        </div>

        {alert.occurrences > 1 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              Última detección · {alert.occurrences} eventos agrupados
            </p>
            <p className="text-sm">
              {new Date(alert.last_seen_at).toLocaleString("es-ES")} ({relativeTime(alert.last_seen_at)})
            </p>
          </div>
        )}

        {alert.raw_payload && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Datos originales</p>
            <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-64 font-mono">
              {JSON.stringify(alert.raw_payload, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </Dialog>
  );
}
