// Severidades de las alertas: orden, nombre y colores, iguales en todo el panel.

import type { AlertSeverity } from "@/lib/types";

export const SEVERITY_ORDER: AlertSeverity[] = ["critical", "high", "medium", "low", "info"];

export const SEVERITY: Record<AlertSeverity, { label: string; variant: "destructive" | "warning" | "info" | "secondary"; bar: string; text: string }> = {
  critical: { label: "Crítica", variant: "destructive", bar: "bg-destructive", text: "text-destructive" },
  high: { label: "Alta", variant: "warning", bar: "bg-orange-500", text: "text-orange-500" },
  medium: { label: "Media", variant: "warning", bar: "bg-warning", text: "text-warning" },
  low: { label: "Baja", variant: "info", bar: "bg-info", text: "text-info" },
  info: { label: "Info", variant: "secondary", bar: "bg-muted-foreground", text: "text-muted-foreground" },
};

export function severityRank(s: AlertSeverity): number {
  return SEVERITY_ORDER.indexOf(s);
}
