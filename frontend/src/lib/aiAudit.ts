// Auditoría con IA: etiquetas de los informes y nombres de los dispositivos
// en lugar de sus seudónimos.

import { useMemo } from "react";
import {
  Ban, CircleCheck, DatabaseBackup, Radar, RefreshCw, ScanSearch, ShieldAlert, ShieldCheck, ShieldOff, ShieldX,
  type LucideIcon,
} from "lucide-react";
import type { AiAuditPreview, AiAuditSummary, AiGravedad, AiTipoAccion } from "@/lib/types";

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


// Cada tipo de acción del plan: qué es, sobre qué y qué hará al aplicarla
export const ACCIONES: Record<AiTipoAccion, {
  label: string;
  target: "device" | "ip" | "none";
  icon: LucideIcon;
  destructive?: boolean;
  explain: string;
}> = {
  bloquear_dispositivo: {
    label: "Bloquear", target: "device", icon: Ban, destructive: true,
    explain: "Se corta su tráfico a Internet y al resto de la red (por MAC y por IP).",
  },
  desbloquear_dispositivo: {
    label: "Desbloquear", target: "device", icon: CircleCheck,
    explain: "Se quitan sus bloqueos y vuelve a tener acceso.",
  },
  marcar_confianza: {
    label: "Marcar de confianza", target: "device", icon: ShieldCheck,
    explain: "El bloqueo automático no lo tocará y, con la cuarentena, seguirá saliendo a Internet.",
  },
  quitar_confianza: {
    label: "Quitar de confianza", target: "device", icon: ShieldX,
    explain: "Vuelve a poder bloquearse automáticamente y la cuarentena le afecta.",
  },
  escanear_puertos: {
    label: "Escanear puertos", target: "device", icon: Radar,
    explain: "Escaneo completo con nmap (unos minutos); los servicios inseguros generan alertas.",
  },
  bloquear_ip: {
    label: "Bloquear IP", target: "ip", icon: Ban, destructive: true,
    explain: "Se corta el tráfico con esa dirección de Internet en el cortafuegos.",
  },
  desbloquear_ip: {
    label: "Desbloquear IP", target: "ip", icon: CircleCheck,
    explain: "Se quita el bloqueo de esa dirección.",
  },
  activar_cuarentena: {
    label: "Activar cuarentena", target: "none", icon: ShieldAlert, destructive: true,
    explain: "Solo los dispositivos de confianza salen a Internet; el resto sigue llegando al panel, al DHCP y al DNS.",
  },
  desactivar_cuarentena: {
    label: "Desactivar cuarentena", target: "none", icon: ShieldOff,
    explain: "Todos los dispositivos vuelven a salir a Internet.",
  },
  actualizar_listas: {
    label: "Actualizar listas de amenazas", target: "none", icon: RefreshCw,
    explain: "Descarga ahora las listas de IPs maliciosas.",
  },
  escanear_red: {
    label: "Escanear la red", target: "none", icon: ScanSearch,
    explain: "Busca ahora dispositivos nuevos en la red.",
  },
  hacer_copia: {
    label: "Hacer copia de seguridad", target: "none", icon: DatabaseBackup,
    explain: "Copia de la base de datos y la configuración, como la automática.",
  },
};
