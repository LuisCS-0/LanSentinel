// Auditoría con IA (solo administradores): lanzar auditorías, el historial
// de informes y, de cada uno, sus hallazgos con lo que se puede hacer con
// ellos. ?report=<id> abre un informe concreto.

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle, ChevronRight, Eye, Loader2, Lock, Sparkles, ThumbsUp, Trash2, TrendingDown, TrendingUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { ActionPlan } from "@/components/ai-audit/ActionPlan";
import { FindingCard } from "@/components/ai-audit/FindingCard";
import { ProviderBar } from "@/components/ai-audit/ProviderBar";
import { PreviewDialog, SentSnapshotDialog } from "@/components/ai-audit/SnapshotDialogs";
import { ScoreBadge } from "@/components/ai-audit/shared";
import { ACCIONES, PROVEEDOR, summaryText, usd, useHumanize } from "@/lib/aiAudit";
import { useAiAuditReport, useAiAuditReports, useDeleteAiAudit } from "@/hooks/useAiAudit";
import { useIsAdmin } from "@/hooks/useAuth";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { AiAuditDetail, AiAuditSummary } from "@/lib/types";

export default function AuditPage() {
  const isAdmin = useIsAdmin();
  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <PageHeader title="Auditoría IA" />
        <Card>
          <EmptyState icon={Lock} title="Solo para administradores" description="La auditoría con IA y sus informes solo los ve un administrador." />
        </Card>
      </div>
    );
  }
  return <AuditView />;
}

function AuditView() {
  const reports = useAiAuditReports(30);
  const [params, setParams] = useSearchParams();
  const [preview, setPreview] = useState(false);
  const list = reports.data ?? [];

  // Por defecto, el último terminado (o el que está en marcha si no hay otro)
  const requested = Number(params.get("report")) || null;
  const selectedId = list.some(r => r.id === requested) ? requested
    : (list.find(r => r.status === "done") ?? list[0])?.id ?? null;
  const select = (id: number) => setParams(prev => {
    const next = new URLSearchParams(prev);
    next.set("report", String(id));
    return next;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Auditoría IA"
        description="Un modelo de IA revisa la red y LanSentinel y propone mejoras. Tú decides qué se aplica."
        actions={<Button variant="outline" onClick={() => setPreview(true)}><Eye />Ver lo que se enviará</Button>}
      />
      <ProviderBar onStarted={select} className="bg-card" />

      {reports.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState
            icon={Sparkles}
            title="Todavía no hay auditorías"
            description="Configura un proveedor en .env (Claude, OpenAI o un modelo en tu red) y pulsa Auditar ahora. Antes puedes ver exactamente qué se enviará."
          />
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
          <History reports={list} selectedId={selectedId} onSelect={select} />
          {selectedId !== null && <ReportView key={selectedId} id={selectedId} reports={list} />}
        </div>
      )}
      <PreviewDialog open={preview} onClose={() => setPreview(false)} />
    </div>
  );
}

// ─── Historial ───────────────────────────────────────────────────────────────

function History({
  reports, selectedId, onSelect,
}: { reports: AiAuditSummary[]; selectedId: number | null; onSelect: (id: number) => void }) {
  return (
    <Card className="h-fit overflow-hidden lg:sticky lg:top-20">
      <p className="border-b px-4 py-3 text-sm font-medium">Informes</p>
      <ul className="max-h-[70dvh] divide-y overflow-y-auto">
        {reports.map(r => (
          <li key={r.id}>
            <button
              onClick={() => onSelect(r.id)}
              className={cn(
                "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40",
                r.id === selectedId && "bg-primary/10",
              )}
            >
              <ScoreBadge score={r.status === "done" ? r.score : null} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {summaryText(r)}
                  {r.status === "running" && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
                </p>
                <p className="truncate text-xs text-muted-foreground">{relativeTime(r.created_at)} · {r.model}</p>
              </div>
              {r.status === "done" && r.pending > 0 && (
                <Badge variant="warning" title="Hallazgos sin aplicar ni descartar">{r.pending}</Badge>
              )}
              <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ─── Informe ─────────────────────────────────────────────────────────────────

function ReportView({ id, reports }: { id: number; reports: AiAuditSummary[] }) {
  const detail = useAiAuditReport(id);
  const d = detail.data;

  if (detail.isLoading || !d) {
    return detail.isError ? (
      <ErrorBox text={extractErrorMessage(detail.error)} />
    ) : (
      <Skeleton className="h-80 w-full" />
    );
  }
  if (d.status === "running") {
    return (
      <Card>
        <EmptyState
          icon={Loader2}
          className="[&_svg]:animate-spin"
          title="El modelo está revisando la red"
          description="Suele tardar uno o dos minutos (más con un modelo local). El informe aparecerá aquí."
        />
      </Card>
    );
  }
  if (d.status === "error" || !d.report) {
    return (
      <div className="space-y-4">
        <ReportHeader d={d} reports={reports} />
        <ErrorBox text={d.error ?? "La auditoría no terminó"} />
      </div>
    );
  }
  return <DoneReport d={d} reports={reports} />;
}

function DoneReport({ d, reports }: { d: AiAuditDetail; reports: AiAuditSummary[] }) {
  const humanize = useHumanize(d.mapping);
  const report = d.report!;
  const indexed = report.hallazgos.map((h, index) => ({ h, index, state: d.finding_states[String(index)] }));
  const pending = indexed.filter(f => !f.state);
  const [filter, setFilter] = useState<"pending" | "all">(pending.length ? "pending" : "all");
  const [showDiscarded, setShowDiscarded] = useState(false);
  const shown = filter === "pending" ? pending : indexed;

  return (
    <div className="min-w-0 space-y-4">
      <ReportHeader d={d} reports={reports} humanize={humanize.text} />
      <ActionPlan report={d} humanize={humanize.text} />

      {report.hallazgos.length > 0 ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">Hallazgos</p>
            <Segmented
              size="sm"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "pending", label: `Pendientes (${pending.length})` },
                { value: "all", label: `Todos (${indexed.length})` },
              ]}
            />
          </div>
          {shown.length ? (
            <ul className="space-y-3">
              {shown.map(({ h, index, state }) => (
                <FindingCard key={index} report={d} index={index} finding={h} state={state} humanize={humanize.text} />
              ))}
            </ul>
          ) : (
            <Card><EmptyState icon={ThumbsUp} title="Nada pendiente" description="Todos los hallazgos están aplicados o descartados." /></Card>
          )}
        </div>
      ) : (
        <Card><EmptyState icon={ThumbsUp} title="Sin hallazgos" description="El modelo no ha encontrado nada que mejorar." /></Card>
      )}

      {report.positivos.length > 0 && (
        <Card className="p-4">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium"><ThumbsUp className="size-4 text-success" />Lo que está bien</p>
          <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
            {report.positivos.map((p, i) => <li key={i}>{humanize.text(p)}</li>)}
          </ul>
        </Card>
      )}

      {d.discarded.length > 0 && (
        <Card className="overflow-hidden">
          <button
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm hover:bg-muted/40"
            onClick={() => setShowDiscarded(v => !v)} aria-expanded={showDiscarded}
          >
            <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", showDiscarded && "rotate-90")} />
            <span className="font-medium">{d.discarded.length} propuesta{d.discarded.length === 1 ? "" : "s"} descartada{d.discarded.length === 1 ? "" : "s"} por LanSentinel</span>
            <span className="text-muted-foreground">: no se sostenían con los datos</span>
          </button>
          {showDiscarded && (
            <ul className="divide-y border-t text-sm">
              {d.discarded.map((x, i) => (
                <li key={i} className="px-4 py-2.5">
                  <p>
                    {x.hallazgo ? `Hallazgo: ${x.hallazgo.titulo}`
                      : x.accion ? `Acción: ${ACCIONES[x.accion.tipo]?.label ?? x.accion.tipo}${x.accion.objetivo ? ` ${x.accion.objetivo}` : ""}`
                      : "—"}
                  </p>
                  <p className="text-xs text-muted-foreground">{x.motivo}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}

function ReportHeader({
  d, reports, humanize,
}: { d: AiAuditDetail; reports: AiAuditSummary[]; humanize?: (text: string) => string }) {
  const remove = useDeleteAiAudit();
  const [, setParams] = useSearchParams();
  const [confirming, setConfirming] = useState(false);
  const [sent, setSent] = useState(false);

  // Comparación con la auditoría terminada anterior
  const previous = reports.find(r => r.id < d.id && r.status === "done" && r.score != null);
  const delta = d.report && previous ? d.report.puntuacion - previous.score! : null;

  const confirmDelete = async () => {
    try {
      await remove.mutateAsync(d.id);
      setConfirming(false);
      setParams(prev => {
        const next = new URLSearchParams(prev);
        next.delete("report");
        return next;
      });
      toast({ title: "Informe borrado" });
    } catch (err) {
      toast({ title: "No se pudo borrar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start gap-4">
        {d.report && (
          <div className="flex flex-col items-center gap-1">
            <ScoreBadge score={d.report.puntuacion} size="lg" />
            {delta !== null && delta !== 0 && (
              <span className={cn("flex items-center gap-0.5 text-xs font-medium tabular-nums", delta > 0 ? "text-success" : "text-destructive")}>
                {delta > 0 ? <TrendingUp className="size-3.5" /> : <TrendingDown className="size-3.5" />}
                {delta > 0 ? "+" : ""}{delta}
              </span>
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          {d.report && <p className="whitespace-pre-line text-sm leading-relaxed">{humanize ? humanize(d.report.resumen) : d.report.resumen}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{relativeTime(d.created_at)}{d.requested_by && ` · ${d.requested_by}`}</span>
            <span>{PROVEEDOR[d.provider] ?? d.provider} · <span className="font-mono">{d.model}</span></span>
            {d.local && <Badge variant="success">local</Badge>}
            {d.input_tokens != null && (
              <span>{d.input_tokens.toLocaleString("es-ES")} tokens enviados, {(d.output_tokens ?? 0).toLocaleString("es-ES")} recibidos</span>
            )}
            {d.cost_usd != null && <span>{usd(d.cost_usd)}</span>}
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap justify-end gap-2 border-t pt-3">
        <Button size="xs" variant="ghost" onClick={() => setSent(true)}><Eye />Lo que se envió</Button>
        <Button size="xs" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setConfirming(true)}>
          <Trash2 />Borrar
        </Button>
      </div>

      <SentSnapshotDialog open={sent} onClose={() => setSent(false)} snapshot={d.snapshot} mapping={d.mapping} />
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Borrar este informe"
        description="Se borran el informe, la instantánea que se envió y lo que se marcó en sus hallazgos. Lo aplicado en la red no cambia."
        icon={<div className="rounded-lg bg-destructive/15 p-2 text-destructive"><Trash2 className="size-4" /></div>}
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={remove.isPending}>Cancelar</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={remove.isPending}>
              {remove.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />}Borrar
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">El registro de acciones conserva quién lo borró.</p>
      </Dialog>
    </Card>
  );
}

function ErrorBox({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />{text}
    </p>
  );
}
