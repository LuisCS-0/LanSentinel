// Plan de acciones del informe: el dueño marca las que quiere, las revisa
// en una confirmación y se aplican una detrás de otra. Cada una queda como
// aplicada (o se puede descartar); cuando todas las de un hallazgo están
// aplicadas, el hallazgo también.

import { useState } from "react";
import { Check, ListChecks, Loader2, RotateCcw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useSetActionState, useSetFindingState } from "@/hooks/useAiAudit";
import { useAuditActions, type ResolvedAction } from "@/hooks/useAuditActions";
import { ACCIONES } from "@/lib/aiAudit";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { AiAuditDetail } from "@/lib/types";

export function ActionPlan({ report, humanize }: { report: AiAuditDetail; humanize: (text: string) => string }) {
  const { resolved, run } = useAuditActions(report);
  const setActionState = useSetActionState();
  const setFindingState = useSetFindingState();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState<number | null>(null);    // índice de la que se está aplicando

  if (!resolved.length) return null;
  const states = report.action_states;
  const hallazgos = report.report?.hallazgos ?? [];
  const selectable = (r: ResolvedAction) => !states[String(r.index)] && !r.done && !r.missing;
  const chosen = resolved.filter(r => selected.has(r.index) && selectable(r));
  const pending = resolved.filter(r => !states[String(r.index)]);

  const toggle = (index: number) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    return next;
  });
  const allSelectable = resolved.filter(selectable);
  const toggleAll = () => setSelected(
    chosen.length === allSelectable.length ? new Set() : new Set(allSelectable.map(r => r.index)),
  );

  const mark = (index: number, estado: "aplicado" | "descartado" | "pendiente") =>
    setActionState.mutateAsync({ id: report.id, index, estado });

  const apply = async () => {
    const applied = new Set<number>();
    const failed: string[] = [];
    // Una detrás de otra: así cada error dice de cuál es y el escaneo no compite con nada
    for (const r of chosen) {
      setWorking(r.index);
      try {
        await run(r);
        await mark(r.index, "aplicado");
        applied.add(r.index);
      } catch (err) {
        failed.push(`${r.label}: ${extractErrorMessage(err)}`);
      }
    }
    setWorking(null);
    setConfirming(false);
    setSelected(new Set());

    // Hallazgos con todas sus acciones aplicadas (antes o ahora): aplicados también
    for (let i = 0; i < hallazgos.length; i++) {
      const own = resolved.filter(r => r.action.hallazgo === i);
      const allDone = own.length > 0 && own.every(r => applied.has(r.index) || states[String(r.index)]?.estado === "aplicado");
      if (allDone && own.some(r => applied.has(r.index)) && !report.finding_states[String(i)]) {
        await setFindingState.mutateAsync({ id: report.id, index: i, estado: "aplicado" }).catch(() => undefined);
      }
    }
    if (applied.size) toast({ title: `${applied.size} ${applied.size === 1 ? "acción" : "acciones"} aplicada${applied.size === 1 ? "" : "s"}` });
    if (failed.length) toast({ title: `${failed.length} no se pudo aplicar`, description: failed.join(" · "), severity: "medium" });
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <ListChecks className="size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1 basis-60">
          <p className="text-sm font-medium">Plan de acciones</p>
          <p className="text-xs text-muted-foreground">
            Lo que propone el modelo. Marca lo que quieras aplicar; nada se hace sin tu confirmación.
          </p>
        </div>
        {allSelectable.length > 1 && (
          <Button size="xs" variant="ghost" onClick={toggleAll}>
            {chosen.length === allSelectable.length ? "Quitar todas" : "Marcar todas"}
          </Button>
        )}
        <Button size="sm" onClick={() => setConfirming(true)} disabled={!chosen.length || working !== null}>
          <Check />Aplicar {chosen.length ? `(${chosen.length})` : ""}
        </Button>
      </div>

      <ul className="divide-y">
        {resolved.map(r => {
          const info = ACCIONES[r.action.tipo];
          const state = states[String(r.index)];
          const finding = hallazgos[r.action.hallazgo];
          const canSelect = selectable(r);
          return (
            <li key={r.index} className={cn("flex items-start gap-3 px-4 py-3", (state || r.done) && "opacity-70")}>
              <input
                type="checkbox"
                className="mt-1 size-4 shrink-0 accent-primary disabled:opacity-40"
                checked={selected.has(r.index) && canSelect}
                disabled={!canSelect || working !== null}
                onChange={() => toggle(r.index)}
                aria-label={r.label}
              />
              <div className="min-w-0 flex-1">
                <p className="flex items-start gap-2 text-sm font-medium">
                  <info.icon className={cn("mt-0.5 size-4 shrink-0", info.destructive ? "text-destructive" : "text-primary")} />
                  <span className="min-w-0">{r.label}</span>
                  {working === r.index && <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin text-muted-foreground" />}
                </p>
                <p className="mt-0.5 text-sm text-muted-foreground">{humanize(r.action.motivo)}</p>
                {finding && <p className="mt-1 truncate text-xs text-muted-foreground">Por: {humanize(finding.titulo)}</p>}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {state ? (
                  <>
                    <Badge variant={state.estado === "aplicado" ? "success" : "secondary"}>
                      {state.estado === "aplicado" ? <Check /> : <X />}
                      {state.estado === "aplicado" ? "Aplicada" : "Descartada"} · {relativeTime(state.en)}
                    </Badge>
                    <Button size="xs" variant="ghost" onClick={() => mark(r.index, "pendiente")} disabled={working !== null}>
                      <RotateCcw />Reabrir
                    </Button>
                  </>
                ) : (
                  <>
                    {r.done && <Badge variant="success"><Check />Ya está hecho</Badge>}
                    {r.missing && <Badge variant="outline">El equipo ya no está</Badge>}
                    <Button size="xs" variant="ghost" onClick={() => mark(r.index, "descartado")} disabled={working !== null}>
                      <X />Descartar
                    </Button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {pending.length === 0 && (
        <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">Todas las acciones están aplicadas o descartadas.</p>
      )}

      <Dialog
        open={confirming}
        onClose={() => working === null && setConfirming(false)}
        className="sm:max-w-xl"
        title={`Aplicar ${chosen.length} ${chosen.length === 1 ? "acción" : "acciones"}`}
        description="Las propone la auditoría con IA: revísalas. Se aplican una detrás de otra por las rutas normales del panel."
        icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><ListChecks className="size-4" /></div>}
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={working !== null}>Cancelar</Button>
            <Button
              variant={chosen.some(r => ACCIONES[r.action.tipo].destructive) ? "destructive" : "default"}
              onClick={apply} disabled={working !== null || !chosen.length}
            >
              {working !== null ? <Loader2 className="animate-spin" /> : <Check />}Aplicar
            </Button>
          </>
        }
      >
        <ul className="space-y-3 text-sm">
          {chosen.map(r => {
            const info = ACCIONES[r.action.tipo];
            return (
              <li key={r.index} className="flex gap-2.5">
                <info.icon className={cn("mt-0.5 size-4 shrink-0", info.destructive ? "text-destructive" : "text-primary")} />
                <div>
                  <p className="font-medium">
                    {r.label}
                    {working === r.index && <Loader2 className="ml-1.5 inline size-3.5 animate-spin" />}
                  </p>
                  <p className="text-muted-foreground">{info.explain}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </Dialog>
    </Card>
  );
}
