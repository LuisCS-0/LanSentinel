// Alertas en modo básico: lo pendiente primero, contado en lenguaje
// sencillo y con qué hacer. Sin firmas, orígenes ni filtros técnicos.

import { useState } from "react";
import { CheckCheck, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { PlainAlertItem } from "@/components/basic/PlainAlertItem";
import { useAlerts, useDevices } from "@/hooks/useApi";
import { useIsAdmin } from "@/hooks/useAuth";
import { useUpdateAlertStatus } from "@/hooks/useMutations";
import { severityRank } from "@/lib/severity";

type Filter = "pending" | "all";

export function BasicAlerts() {
  const alerts = useAlerts(100);
  const devices = useDevices();
  const update = useUpdateAlertStatus();
  const isAdmin = useIsAdmin();
  const [filter, setFilter] = useState<Filter>("pending");
  const byId = new Map((devices.data ?? []).map(d => [d.id, d]));
  const all = (alerts.data ?? []).filter(a => a.severity !== "info");
  const pending = all.filter(a => a.status === "new");
  const shown = (filter === "pending" ? pending : all)
    .slice()
    .sort((a, b) => (filter === "pending" ? severityRank(a.severity) - severityRank(b.severity) : 0)
      || b.last_seen_at.localeCompare(a.last_seen_at));

  const seenAll = () => pending.forEach(a => update.mutate({ id: a.id, status: "acknowledged" }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Avisos"
        description="Lo que LanSentinel ha visto en tu red, explicado. Lo más importante, arriba."
        actions={isAdmin && pending.length > 1 && (
          <Button variant="outline" onClick={seenAll} disabled={update.isPending}><CheckCheck />Marcar todo como visto</Button>
        )}
      />
      <Segmented<Filter>
        value={filter}
        onChange={setFilter}
        options={[
          { value: "pending", label: `Sin revisar (${pending.length})` },
          { value: "all", label: "Todos" },
        ]}
      />
      <Card>
        <CardContent className="pt-2">
          {alerts.isLoading ? <Skeleton className="h-60" /> : shown.length ? (
            <ul className="divide-y">
              {shown.map(a => <PlainAlertItem key={a.id} alert={a} device={a.device_id ? byId.get(a.device_id) : undefined} />)}
            </ul>
          ) : (
            <EmptyState icon={ShieldCheck} title="Nada que revisar" description="Cuando pase algo que debas saber, aparecerá aquí." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
