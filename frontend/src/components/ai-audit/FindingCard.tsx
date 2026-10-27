// Un hallazgo del informe: qué pasa, qué dispositivos toca, qué hacer y
// las acciones del plan que lo resuelven (se aplican desde el plan). Se
// puede marcar como hecho, descartar o reabrir.

import { Check, RotateCcw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDevices } from "@/hooks/useApi";
import { useSetFindingState } from "@/hooks/useAiAudit";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { ACCIONES, CATEGORIA, GRAVEDAD } from "@/lib/aiAudit";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { AiAuditDetail, AiFindingState, AiHallazgo } from "@/lib/types";

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
  const setState = useSetFindingState();
  const sheet = useDeviceSheet();

  const targets = finding.dispositivos.map(alias => {
    const m = report.mapping.find(x => x.id === alias);
    return { alias, name: m?.nombre ?? alias, device: m ? devices.data?.find(d => d.id === m.device_id) : undefined };
  });
  const actions = (report.report?.acciones ?? [])
    .map((a, i) => ({ a, i, state: report.action_states[String(i)] }))
    .filter(x => x.a.hallazgo === index);

  const mark = async (estado: "aplicado" | "descartado" | "pendiente") => {
    try {
      await setState.mutateAsync({ id: report.id, index, estado });
    } catch (err) {
      toast({ title: "No se pudo guardar", description: extractErrorMessage(err), severity: "medium" });
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
            {state.estado === "aplicado" ? "Resuelto" : "Descartado"}
            {state.por && ` por ${state.por}`} · {relativeTime(state.en)}
          </Badge>
        )}
      </div>

      <p className="mt-2.5 font-medium">{humanize(finding.titulo)}</p>
      <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{humanize(finding.detalle)}</p>
      <p className="mt-3 rounded-lg bg-muted/50 p-2.5 text-sm">
        <span className="font-medium">Qué hacer: </span>{humanize(finding.recomendacion)}
      </p>

      {actions.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>En el plan:</span>
          {actions.map(({ a, i, state: s }) => {
            const info = ACCIONES[a.tipo];
            const name = info.target === "device" ? (report.mapping.find(m => m.id === a.objetivo)?.nombre ?? a.objetivo)
              : info.target === "ip" ? a.objetivo : "";
            return (
              <Badge key={i} variant={s?.estado === "aplicado" ? "success" : s ? "secondary" : "outline"}>
                <info.icon />{info.label}{name && ` ${name}`}
                {s?.estado === "aplicado" && <Check />}
              </Badge>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {state ? (
          <Button size="xs" variant="ghost" onClick={() => mark("pendiente")} disabled={setState.isPending}>
            <RotateCcw />Reabrir
          </Button>
        ) : (
          <>
            <Button size="xs" variant="outline" onClick={() => mark("aplicado")} disabled={setState.isPending}>
              <Check />Resuelto
            </Button>
            <Button size="xs" variant="ghost" onClick={() => mark("descartado")} disabled={setState.isPending}>
              <X />Descartar
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
