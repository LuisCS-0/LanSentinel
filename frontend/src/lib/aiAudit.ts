// Auditoría con IA: etiquetas de los informes y nombres de los dispositivos
// en lugar de sus seudónimos.

import { useMemo } from "react";
import type { AiAuditPreview, AiAuditSummary, AiGravedad } from "@/lib/types";

export const GRAVEDAD: Record<AiGravedad, { label: string; variant: "destructive" | "warning" | "info" | "secondary" }> = {
  critica: { label: "Crítica", variant: "destructive" },
  alta: { label: "Alta", variant: "destructive" },
  media: { label: "Media", variant: "warning" },
  baja: { label: "Baja", variant: "info" },
  info: { label: "Info", variant: "secondary" },
};

export const CATEGORIA: Record<string, string> = {
  dispositivo: "Dispositivo",
  servicio_expuesto: "Servicio expuesto",
  alertas: "Alertas",
  cortafuegos: "Cortafuegos",
  configuracion: "Configuración",
  privacidad: "Privacidad",
  otro: "Otro",
};

export const PROVEEDOR: Record<string, string> = {
  anthropic: "Claude",
  openai: "OpenAI",
  compatible: "Compatible con OpenAI",
};

export function usd(value: number) {
  return value.toLocaleString("es-ES", { style: "currency", currency: "USD", maximumFractionDigits: 3 });
}

export function summaryText(r: AiAuditSummary) {
  if (r.status === "running") return "Auditando…";
  if (r.status === "error") return "Falló";
  const total = Object.values(r.findings).reduce((a, b) => a + (b ?? 0), 0);
  if (!total) return "Sin hallazgos";
  const serious = (r.findings.critica ?? 0) + (r.findings.alta ?? 0);
  return `${total} hallazgo${total === 1 ? "" : "s"}${serious ? ` · ${serious} importante${serious === 1 ? "" : "s"}` : ""}`;
}

// disp-NN → nombre del dispositivo. La equivalencia nunca sale de LanSentinel;
// el modelo también cita los seudónimos dentro de los textos
export function useHumanize(mapping: AiAuditPreview["mapping"] | undefined) {
  return useMemo(() => {
    const names = new Map((mapping ?? []).map(m => [m.id, m.nombre ?? m.id]));
    return {
      name: (id: string) => names.get(id) ?? id,
      text: (text: string) => text.replace(/\bdisp-\d+\b/g, id => names.get(id) ?? id),
    };
  }, [mapping]);
}
