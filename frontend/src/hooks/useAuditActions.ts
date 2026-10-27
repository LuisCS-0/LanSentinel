// Plan de acciones de la auditoría con IA: a qué apunta cada acción, si ya
// está hecha y cómo se aplica. Se aplica por las mismas rutas que el resto
// del panel (con sus protecciones y su registro): la auditoría no tiene una
// vía propia para cambiar la red.

import { useCallback, useMemo } from "react";
import { useDevices, useFirewallRules } from "@/hooks/useApi";
import { useCreateBackup } from "@/hooks/useBackups";
import { useBlockDevice, useForceNetworkScan, useScanPorts, useTrustDevice } from "@/hooks/useDevices";
import { useBlockIp, useUnblockRule } from "@/hooks/useMutations";
import { useQuarantine, useSetQuarantine } from "@/hooks/useQuarantine";
import { useUpdateThreatLists } from "@/hooks/useThreatIntel";
import { ACCIONES } from "@/lib/aiAudit";
import type { AiAccion, AiAuditDetail, Device } from "@/lib/types";

export interface ResolvedAction {
  index: number;
  action: AiAccion;
  label: string;                // "Bloquear PCS Systemtechnik" / "Bloquear IP 185.15.58.224"
  device?: Device;
  missing: boolean;             // su dispositivo ya no está en LanSentinel
  done: boolean;                // ya está así (el equipo ya es de confianza, la cuarentena ya está...)
}

export function useAuditActions(report: AiAuditDetail) {
  const devices = useDevices();
  const rules = useFirewallRules(true);
  const quarantine = useQuarantine();
  const block = useBlockDevice();
  const trust = useTrustDevice();
  const scan = useScanPorts();
  const blockIp = useBlockIp();
  const unblockRule = useUnblockRule();
  const setQuarantine = useSetQuarantine();
  const updateLists = useUpdateThreatLists();
  const scanNetwork = useForceNetworkScan();
  const backup = useCreateBackup();

  const ipRule = useCallback(
    (ip: string) => (rules.data ?? []).find(r => r.is_active && r.src_ip === ip && !r.device_id),
    [rules.data],
  );

  const resolved: ResolvedAction[] = useMemo(() => (report.report?.acciones ?? []).map((action, index) => {
    const info = ACCIONES[action.tipo];
    if (info.target === "device") {
      const m = report.mapping.find(x => x.id === action.objetivo);
      const device = m ? devices.data?.find(d => d.id === m.device_id) : undefined;
      const name = m?.nombre ?? action.objetivo;
      const done = !!device && (
        action.tipo === "bloquear_dispositivo" ? device.is_blocked
          : action.tipo === "desbloquear_dispositivo" ? !device.is_blocked
          : action.tipo === "marcar_confianza" ? device.is_trusted
          : action.tipo === "quitar_confianza" ? !device.is_trusted
          : false);
      return { index, action, label: `${info.label}: ${name}`, device, missing: !!devices.data && !device, done };
    }
    if (info.target === "ip") {
      const blocked = !!ipRule(action.objetivo);
      const done = rules.data ? (action.tipo === "bloquear_ip" ? blocked : !blocked) : false;
      return { index, action, label: `${info.label} ${action.objetivo}`, missing: false, done };
    }
    const done = action.tipo === "activar_cuarentena" ? !!quarantine.data?.enabled
      : action.tipo === "desactivar_cuarentena" ? quarantine.data?.enabled === false
      : false;
    return { index, action, label: info.label, missing: false, done };
  }), [report, devices.data, rules.data, quarantine.data, ipRule]);

  // Aplica una acción; lanza el error de la ruta si falla
  const run = useCallback(async (r: ResolvedAction) => {
    const { tipo, objetivo, motivo } = r.action;
    const id = r.device?.id;
    if (ACCIONES[tipo].target === "device" && !id) throw new Error("El dispositivo ya no está en LanSentinel");
    switch (tipo) {
      case "bloquear_dispositivo": return block.mutateAsync({ id: id!, blocked: true });
      case "desbloquear_dispositivo": return block.mutateAsync({ id: id!, blocked: false });
      case "marcar_confianza": return trust.mutateAsync({ id: id!, trusted: true });
      case "quitar_confianza": return trust.mutateAsync({ id: id!, trusted: false });
      case "escanear_puertos": return scan.mutateAsync({ id: id! });
      case "bloquear_ip": return blockIp.mutateAsync({ ip: objetivo, reason: `Auditoría con IA: ${motivo}`.slice(0, 250) });
      case "desbloquear_ip": {
        const rule = ipRule(objetivo);
        if (!rule) throw new Error("Esa IP ya no está bloqueada");
        return unblockRule.mutateAsync(rule.id);
      }
      case "activar_cuarentena": return setQuarantine.mutateAsync(true);
      case "desactivar_cuarentena": return setQuarantine.mutateAsync(false);
      case "actualizar_listas": return updateLists.mutateAsync();
      case "escanear_red": return scanNetwork.mutateAsync();
      case "hacer_copia": return backup.mutateAsync();
    }
  }, [block, trust, scan, blockIp, unblockRule, setQuarantine, updateLists, scanNetwork, backup, ipRule]);

  return { resolved, run };
}
