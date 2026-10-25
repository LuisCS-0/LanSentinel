// El detalle de un dispositivo se abre desde cualquier pantalla (tabla,
// conexiones, alertas, buscador...) con ?device=<id> en la URL. Así se puede
// enlazar, y "atrás" en el navegador lo cierra.

import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export type DeviceTab = "summary" | "connections" | "usage" | "ports";

export function useDeviceSheet() {
  const [params, setParams] = useSearchParams();

  const open = useCallback((id: string, tab?: DeviceTab) => {
    setParams(prev => {
      const next = new URLSearchParams(prev);
      next.set("device", id);
      if (tab) next.set("tab", tab);
      else next.delete("tab");
      return next;
    });
  }, [setParams]);

  const close = useCallback(() => {
    setParams(prev => {
      const next = new URLSearchParams(prev);
      next.delete("device");
      next.delete("tab");
      return next;
    });
  }, [setParams]);

  const setTab = useCallback((tab: DeviceTab) => {
    setParams(prev => {
      const next = new URLSearchParams(prev);
      next.set("tab", tab);
      return next;
    }, { replace: true });
  }, [setParams]);

  return {
    deviceId: params.get("device"),
    tab: (params.get("tab") as DeviceTab | null) ?? "summary",
    open,
    close,
    setTab,
  };
}
