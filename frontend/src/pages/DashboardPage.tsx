import {
  HardDrive, Bell, Lock, Activity, AlertCircle, RefreshCw,
} from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/MetricCard";
import { ServiceStatus } from "@/components/ServiceStatus";
import { SeverityBadge } from "@/components/SeverityBadge";
import {
  useDevicesSummary, useAlerts, useFirewallRules,
  useSystemStatus, useHealth,
} from "@/hooks/useApi";
import { relativeTime } from "@/lib/dates";
import { useQueryClient } from "@tanstack/react-query";

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const health = useHealth();
  const status = useSystemStatus();
  const summary = useDevicesSummary();
  const alerts = useAlerts(5);
  const rules = useFirewallRules(true);

  const recentAlerts = (alerts.data || [])
    .filter(a => a.status !== "resolved")
    .slice(0, 5);

  const unresolvedCount = (alerts.data || []).filter(
    a => a.status !== "resolved"
  ).length;

  const handleRefresh = () => {
    queryClient.invalidateQueries();
  };

  return (
    <div className="container py-8 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Vista general del sistema LanSentinel
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refrescar
        </Button>
      </div>

      {health.isError && (
        <Card className="border-destructive">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">
                No se puede conectar con el backend
              </p>
              <p className="text-sm text-muted-foreground">
                Verifica que el servicio está corriendo en la VM
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Dispositivos"
          value={summary.data?.total ?? "—"}
          icon={HardDrive}
          description={
            summary.data
              ? `${summary.data.trusted} confiables, ${summary.data.blocked} bloqueados`
              : "Cargando..."
          }
        />
        <MetricCard
          label="Alertas pendientes"
          value={unresolvedCount}
          icon={Bell}
          description="Sin resolver"
          iconClassName={unresolvedCount > 0 ? "bg-amber-100 text-amber-700" : ""}
        />
        <MetricCard
          label="Reglas firewall"
          value={rules.data?.length ?? "—"}
          icon={Lock}
          description="Activas"
        />
        <MetricCard
          label="Dispositivos en línea"
          value={status.data?.monitor?.devices_online ?? "—"}
          icon={Activity}
          description={
            status.data?.monitor?.last_scan_at
              ? `Último escaneo ${relativeTime(status.data.monitor.last_scan_at)}`
              : "—"
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Alertas recientes</CardTitle>
            <CardDescription>
              Últimos eventos detectados por el sistema
            </CardDescription>
          </CardHeader>
          <CardContent>
            {recentAlerts.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No hay alertas pendientes
              </p>
            ) : (
              <div className="space-y-3">
                {recentAlerts.map(alert => (
                  <div
                    key={alert.id}
                    className="flex items-start gap-3 pb-3 border-b last:border-0 last:pb-0"
                  >
                    <SeverityBadge severity={alert.severity} className="mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{alert.title}</p>
                      {alert.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                          {alert.description}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {alert.source} · {relativeTime(alert.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Estado de los servicios</CardTitle>
            <CardDescription>
              {health.data
                ? `LanSentinel v${health.data.version}`
                : "Conexión con el backend"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ServiceStatus
              name="Monitor"
              running={status.data?.monitor?.running ?? false}
              info={
                status.data?.monitor
                  ? `Interfaz ${status.data.monitor.interface}`
                  : undefined
              }
            />
            <ServiceStatus
              name="Suricata"
              running={status.data?.security?.running ?? false}
              info={
                status.data?.security?.events_processed !== undefined
                  ? `${status.data.security.events_processed} eventos procesados`
                  : undefined
              }
            />
            <ServiceStatus
              name="Firewall"
              running={status.data?.firewall?.running ?? false}
              info={
                status.data?.firewall
                  ? `${status.data.firewall.rules_applied} reglas aplicadas`
                  : undefined
              }
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
