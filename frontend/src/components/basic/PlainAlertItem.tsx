// Una alerta contada en lenguaje sencillo (modo básico): qué ha pasado, a
// qué equipo, qué conviene hacer y los botones justos.

import { Check, ChevronRight, Lightbulb } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useIsAdmin } from "@/hooks/useAuth";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useUpdateAlertStatus } from "@/hooks/useMutations";
import { relativeTime } from "@/lib/dates";
import { deviceName } from "@/lib/devices";
import { explainAlert } from "@/lib/plain";
import { cn } from "@/lib/utils";
import type { Alert, AlertSeverity, Device } from "@/lib/types";

const LEVEL: Record<AlertSeverity, { label: string; dot: string; variant: "destructive" | "warning" | "info" | "secondary" }> = {
  critical: { label: "Urgente", dot: "bg-destructive", variant: "destructive" },
  high: { label: "Importante", dot: "bg-destructive", variant: "destructive" },
  medium: { label: "A revisar", dot: "bg-warning", variant: "warning" },
  low: { label: "Para saber", dot: "bg-info", variant: "info" },
  info: { label: "Información", dot: "bg-muted-foreground", variant: "secondary" },
};

export function PlainAlertItem({ alert, device, compact }: { alert: Alert; device?: Device; compact?: boolean }) {
  const plain = explainAlert(alert);
  const sheet = useDeviceSheet();
  const update = useUpdateAlertStatus();
  const isAdmin = useIsAdmin();
  const level = LEVEL[alert.severity];
  const pending = alert.status === "new";

  return (
    <li className={cn("flex gap-3 py-3", !pending && "opacity-60")}>
      <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", level.dot)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className="font-medium">{plain.title}</p>
          <Badge variant={level.variant}>{level.label}</Badge>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {device ? <>En <span className="font-medium text-foreground">{deviceName(device)}</span> · </> : null}
          {relativeTime(alert.last_seen_at)}
          {alert.occurrences > 1 && ` · ${alert.occurrences} veces`}
        </p>
        {!compact && <p className="mt-1.5 text-sm">{plain.what}</p>}
        <p className="mt-1.5 flex items-start gap-1.5 text-sm text-muted-foreground">
          <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-warning" />{plain.todo}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {device && (
            <Button size="xs" variant="outline" onClick={() => sheet.open(device.id)}>Ver el equipo<ChevronRight /></Button>
          )}
          {pending && isAdmin && (
            <Button size="xs" variant="ghost" onClick={() => update.mutate({ id: alert.id, status: "acknowledged" })} disabled={update.isPending}>
              <Check />Ya lo he visto
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
