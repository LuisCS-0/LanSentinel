// Severidad de una alerta, con el mismo color en todas las pantallas.

import { Badge } from "@/components/ui/badge";
import { SEVERITY } from "@/lib/severity";
import { cn } from "@/lib/utils";
import type { AlertSeverity } from "@/lib/types";

export function SeverityBadge({ severity, className }: { severity: AlertSeverity; className?: string }) {
  const s = SEVERITY[severity];
  return (
    <Badge
      variant={s.variant}
      dot
      className={cn(severity === "high" && "bg-orange-500/15 text-orange-500 ring-orange-500/30", className)}
    >
      {s.label}
    </Badge>
  );
}
