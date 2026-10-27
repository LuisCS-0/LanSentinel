// Un hallazgo del informe con lo que se puede hacer con él. La acción que
// propone el modelo nunca se ejecuta sola: se confirma y va por las mismas
// rutas que el resto del panel (bloquear, confianza, escaneo, cuarentena),
// con sus comprobaciones y su registro. Al terminar, el hallazgo queda como
// aplicado; también se puede marcar a mano o descartar.

import { useState } from "react";
import {
  Ban, Check, Loader2, Radar, RotateCcw, ShieldAlert, ShieldCheck, X, type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { CATEGORIA, GRAVEDAD } from "@/lib/aiAudit";
import { useDevices } from "@/hooks/useApi";
import { useSetFindingState } from "@/hooks/useAiAudit";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useBlockDevice, useScanPorts, useTrustDevice } from "@/hooks/useDevices";
import { useQuarantine, useSetQuarantine } from "@/hooks/useQuarantine";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { AiAuditDetail, AiFindingState, AiHallazgo, Device } from "@/lib/types";

type Accion = AiHallazgo["accion"];

interface ActionInfo {
  label: string;
  done: string;                // cuando ya no hay nada que hacer
  icon: LucideIcon;
  destructive?: boolean;
  explain: string;
}

const ACTIONS: Partial<Record<Accion, ActionInfo>> = {
  bloquear: {
    label: "Bloquear", done: "Ya bloqueado", icon: Ban, destructive: true,
    explain: "Se cortará su tráfico a Internet y al resto de la red (por MAC y por IP). Se deshace desde Cortafuegos o desde el dispositivo.",
  },
  marcar_confianza: {
    label: "Marcar de confianza", done: "Ya es de confianza", icon: ShieldCheck,
    explain: "El bloqueo automático no lo tocará y, con el modo cuarentena, seguirá saliendo a Internet.",
  },
  escanear_puertos: {
    label: "Escanear puertos", done: "", icon: Radar,
    explain: "Escaneo completo de puertos con nmap. Puede tardar unos minutos; los servicios inseguros que encuentre generan alertas.",
  },
  activar_cuarentena: {
    label: "Activar cuarentena", done: "Cuarentena activa", icon: ShieldAlert, destructive: true,
    explain: "Solo los dispositivos de confianza saldrán a Internet; el resto seguirá llegando al panel, al DHCP y al DNS. Se quita desde Cortafuegos.",
  },
};

interface Target {
  alias: string;
  name: string;
  device: Device | undefined;      // undefined: ya no está en LanSentinel
}

export function FindingCard({
  report, index, finding, state, humanize,
}: {
  report: AiAuditDetail;
  index: number;
  finding: AiHallazgo;
  state: AiFindingState | undefined;
  humanize: (text: string) => string;
}) {
  const devices = useDevices();
  const quarantine = useQuarantine();
  const block = useBlockDevice();
  const trust = useTrustDevice();
  const scan = useScanPorts();
  const setQuarantine = useSetQuarantine();
  const setState = useSetFindingState();
  const sheet = useDeviceSheet();
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState(false);

  const targets: Target[] = finding.dispositivos.map(alias => {
    const m = report.mapping.find(x => x.id === alias);
    return {
      alias,
      name: m?.nombre ?? alias,
      device: m ? devices.data?.find(d => d.id === m.device_id) : undefined,
    };
  });
  const present = targets.filter(t => t.device);
  const action = ACTIONS[finding.accion];
  const pendingTargets = finding.accion === "bloquear" ? present.filter(t => !t.device!.is_blocked)
    : finding.accion === "marcar_confianza" ? present.filter(t => !t.device!.is_trusted)
    : present;
  const alreadyDone = finding.accion === "activar_cuarentena" ? !!quarantine.data?.enabled
    : action && finding.accion !== "escanear_puertos" ? present.length > 0 && pendingTargets.length === 0
    : false;
  const unavailable = !!action && finding.accion !== "activar_cuarentena" && present.length === 0;

  const mark = async (estado: "aplicado" | "descartado" | "pendiente") => {
    try {
      await setState.mutateAsync({ id: report.id, index, estado });
    } catch (err) {
      toast({ title: "No se pudo guardar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  const execute = async () => {
    setWorking(true);
    const failed: string[] = [];
    try {
      if (finding.accion === "activar_cuarentena") {
        await setQuarantine.mutateAsync(true);
      } else {
        // Uno detrás de otro: el escaneo es pesado y así cada error dice de quién es
        for (const t of pendingTargets) {
          try {
            if (finding.accion === "bloquear") await block.mutateAsync({ id: t.device!.id, blocked: true });
            else if (finding.accion === "marcar_confianza") await trust.mutateAsync({ id: t.device!.id, trusted: true });
            else if (finding.accion === "escanear_puertos") await scan.mutateAsync({ id: t.device!.id });
          } catch (err) {
            failed.push(`${t.name}: ${extractErrorMessage(err)}`);
          }
        }
      }
      if (failed.length) {
        toast({ title: `${action!.label}: no se pudo con todos`, description: failed.join(" · "), severity: "medium" });
      } else {
        await mark("aplicado");
        toast({ title: `${action!.label}: hecho`, description: humanize(finding.titulo) });
      }
      setConfirming(false);
    } catch (err) {
      toast({ title: `${action!.label}: falló`, description: extractErrorMessage(err), severity: "medium" });
    } finally {
      setWorking(false);
    }
  };

  const g = GRAVEDAD[finding.gravedad];
  return (
    <li className={cn("rounded-xl border bg-card p-4 transition-opacity", state && "opacity-70")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={g.variant}>{g.label}</Badge>
        <Badge variant="outline">{CATEGORIA[finding.categoria] ?? finding.categoria}</Badge>
        {targets.map(t => t.device ? (
          <button key={t.alias} onClick={() => sheet.open(t.device!.id)} className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <Badge variant="secondary" className="hover:bg-accent">{t.name}</Badge>
          </button>
        ) : (
          <Badge key={t.alias} variant="outline" className="line-through" title="Ya no está en LanSentinel">{t.name}</Badge>
        ))}
        {state && (
          <Badge variant={state.estado === "aplicado" ? "success" : "secondary"} className="ml-auto">
            {state.estado === "aplicado" ? <Check /> : <X />}
            {state.estado === "aplicado" ? "Aplicado" : "Descartado"}
            {state.por && ` por ${state.por}`} · {relativeTime(state.en)}
          </Badge>
        )}
      </div>

      <p className="mt-2.5 font-medium">{humanize(finding.titulo)}</p>
      <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{humanize(finding.detalle)}</p>
      <p className="mt-3 rounded-lg bg-muted/50 p-2.5 text-sm">
        <span className="font-medium">Qué hacer: </span>{humanize(finding.recomendacion)}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {state ? (
          <Button size="xs" variant="ghost" onClick={() => mark("pendiente")} disabled={setState.isPending}>
            <RotateCcw />Reabrir
          </Button>
        ) : (
          <>
            {action && (
              alreadyDone ? (
                <Badge variant="success"><Check />{action.done}</Badge>
              ) : (
                <Button
                  size="xs" variant={action.destructive ? "destructive" : "soft"}
                  onClick={() => setConfirming(true)} disabled={unavailable || working}
                  title={unavailable ? "Los dispositivos de este hallazgo ya no están en LanSentinel" : undefined}
                >
                  {working ? <Loader2 className="animate-spin" /> : <action.icon />}{action.label}
                </Button>
              )
            )}
            <Button size="xs" variant="outline" onClick={() => mark("aplicado")} disabled={setState.isPending}>
              <Check />{finding.accion === "revisar" || finding.accion === "ninguna" || alreadyDone ? "Revisado" : "Ya lo he hecho"}
            </Button>
            <Button size="xs" variant="ghost" onClick={() => mark("descartado")} disabled={setState.isPending}>
              <X />Descartar
            </Button>
          </>
        )}
      </div>

      {action && (
        <Dialog
          open={confirming}
          onClose={() => !working && setConfirming(false)}
          title={`${action.label}${finding.accion === "activar_cuarentena" ? "" : `: ${pendingTargets.map(t => t.name).join(", ")}`}`}
          description="Lo propone la auditoría con IA: revísalo antes de aplicarlo."
          icon={
            <div className={cn("rounded-lg p-2", action.destructive ? "bg-destructive/15 text-destructive" : "bg-primary/15 text-primary")}>
              <action.icon className="size-4" />
            </div>
          }
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirming(false)} disabled={working}>Cancelar</Button>
              <Button variant={action.destructive ? "destructive" : "default"} onClick={execute} disabled={working}>
                {working ? <Loader2 className="animate-spin" /> : <action.icon />}{action.label}
              </Button>
            </>
          }
        >
          <div className="space-y-3 text-sm">
            <p>{action.explain}</p>
            <p className="rounded-lg bg-muted/50 p-2.5 text-muted-foreground">
              <span className="font-medium text-foreground">Por qué: </span>{humanize(finding.titulo)}
            </p>
            {targets.length > present.length && (
              <p className="text-xs text-muted-foreground">
                {targets.length - present.length} de los dispositivos citados ya no están en LanSentinel y se omiten.
              </p>
            )}
          </div>
        </Dialog>
      )}
    </li>
  );
}
