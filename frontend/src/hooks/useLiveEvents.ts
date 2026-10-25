// Conexión en tiempo real con el backend (Server-Sent Events).
//
// Al llegar una alerta nueva: se refrescan las consultas afectadas, se
// muestra un aviso flotante y, si la pestaña está en segundo plano y el
// usuario lo ha permitido, una notificación del navegador. El sondeo
// periódico de React Query sigue activo como respaldo.

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import type { AlertSeverity } from "@/lib/types";

export type LiveStatus = "connecting" | "live" | "offline";

interface AlertEventData {
  id: number;
  severity: AlertSeverity;
  title: string;
  description: string | null;
}

const STREAM_URL = "/api/v1/events/stream";
const RECONNECT_MS = 10_000;
const SEVERITY_ORDER: AlertSeverity[] = ["info", "low", "medium", "high", "critical"];

// Avisos flotantes desde "low" (incluye dispositivos nuevos); notificación
// del navegador solo para lo importante
const TOAST_MIN: AlertSeverity = "low";
const BROWSER_NOTIFICATION_MIN: AlertSeverity = "high";

function atLeast(severity: AlertSeverity, minimum: AlertSeverity) {
  return SEVERITY_ORDER.indexOf(severity) >= SEVERITY_ORDER.indexOf(minimum);
}

export function browserNotificationsSupported() {
  // La API de notificaciones solo existe en contextos seguros (HTTPS o localhost)
  return typeof window !== "undefined" && "Notification" in window && window.isSecureContext;
}

function showBrowserNotification(alert: AlertEventData) {
  if (!browserNotificationsSupported() || Notification.permission !== "granted") return;
  if (!document.hidden) return; // con la pestaña visible basta el aviso flotante
  try {
    new Notification(`LanSentinel: ${alert.title}`, {
      body: alert.description ?? undefined,
      tag: `alert-${alert.id}`,
    });
  } catch {
    // Algunos navegadores solo permiten notificaciones desde un service worker
  }
}

export function useLiveEvents(): LiveStatus {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("connecting");

  useEffect(() => {
    let source: EventSource | null = null;
    let reconnectTimer: number | undefined;
    let stopped = false;

    const refreshAlerts = () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    };

    const connect = () => {
      setStatus("connecting");
      source = new EventSource(STREAM_URL);

      source.onopen = () => setStatus("live");

      source.addEventListener("alert.created", (e: MessageEvent) => {
        const alert: AlertEventData = JSON.parse(e.data).data;
        refreshAlerts();
        // Las alertas de dispositivos nuevos o bloqueos cambian también estas vistas
        queryClient.invalidateQueries({ queryKey: ["devices"] });
        queryClient.invalidateQueries({ queryKey: ["firewall", "rules"] });
        if (atLeast(alert.severity, TOAST_MIN)) {
          toast({ title: alert.title, description: alert.description, severity: alert.severity });
        }
        if (atLeast(alert.severity, BROWSER_NOTIFICATION_MIN)) {
          showBrowserNotification(alert);
        }
      });

      source.addEventListener("alert.updated", refreshAlerts);

      source.onerror = () => {
        setStatus("offline");
        // EventSource reintenta solo si la conexión se corta; si el servidor
        // responde con error (p. ej. 502 mientras el backend reinicia) se
        // cierra para siempre y hay que reconectar a mano
        if (source?.readyState === EventSource.CLOSED && !stopped) {
          reconnectTimer = window.setTimeout(connect, RECONNECT_MS);
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [queryClient]);

  return status;
}
