// Badge que muestra la severidad de una alerta con el color apropiado.
// Centralizar este componente garantiza que la misma severidad se ve
// igual en todas las pantallas del dashboard.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AlertSeverity } from "@/lib/types";

interface SeverityBadgeProps {
  severity: AlertSeverity;
  className?: string;
}

const severityConfig: Record<AlertSeverity, { label: string; classes: string }> = {
  info: {
    label: "INFO",
    classes: "bg-slate-100 text-slate-700 border-slate-200",
  },
  low: {
    label: "BAJA",
    classes: "bg-blue-100 text-blue-700 border-blue-200",
  },
  medium: {
    label: "MEDIA",
    classes: "bg-amber-100 text-amber-700 border-amber-200",
  },
  high: {
    label: "ALTA",
    classes: "bg-orange-100 text-orange-700 border-orange-200",
  },
  critical: {
    label: "CRÍTICA",
    classes: "bg-red-100 text-red-700 border-red-200",
  },
};

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const config = severityConfig[severity];
  return (
    <Badge variant="outline" className={cn(config.classes, "font-semibold", className)}>
      {config.label}
    </Badge>
  );
}
