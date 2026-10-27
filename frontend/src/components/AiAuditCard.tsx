// Auditoría con IA (solo administradores): proveedor configurado, probar la
// conexión, lanzar una auditoría, ver los últimos informes y la vista previa
// de la instantánea de la red que se envía al modelo.

import { useState } from "react";
import {
  AlertCircle, Check, ChevronRight, Copy, Eye, Loader2, PlugZap, Sparkles, ThumbsUp, X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import {
  useAiAuditPreview, useAiAuditReport, useAiAuditReports, useAiAuditStatus, useCheckAiProvider, useRunAiAudit,
} from "@/hooks/useAiAudit";
import { extractErrorMessage } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { AiAuditSummary, AiGravedad, AiHallazgo } from "@/lib/types";

const GRAVEDAD: Record<AiGravedad, { label: string; variant: "destructive" | "warning" | "info" | "secondary" | "outline" }> = {
  critica: { label: "Crítica", variant: "destructive" },
  alta: { label: "Alta", variant: "destructive" },
  media: { label: "Media", variant: "warning" },
  baja: { label: "Baja", variant: "info" },
  info: { label: "Info", variant: "secondary" },
};

const ACCION: Record<AiHallazgo["accion"], string | null> = {
  ninguna: null,
  revisar: "Revisar",
  bloquear: "Bloquear",
  escanear_puertos: "Escanear puertos",
  marcar_confianza: "Marcar de confianza",
  activar_cuarentena: "Activar cuarentena",
};

export function AiAuditCard() {
  const status = useAiAuditStatus();
  const reports = useAiAuditReports();
  const run = useRunAiAudit();
  const check = useCheckAiProvider();
  const [preview, setPreview] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const s = status.data;
  const running = s?.running || reports.data?.some(r => r.status === "running");

  const launch = async () => {
    try {
      await run.mutateAsync();
      toast({ title: "Auditoría en marcha", description: "Tarda uno o dos minutos: el informe aparecerá aquí." });
    } catch (err) {
      toast({ title: "No se pudo lanzar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  return (
    <Card>
      <CardHeaderRow
        title={<><Sparkles />Auditoría con IA</>}
        description="Un modelo de IA revisa el estado de la red y de LanSentinel y propone mejoras. Solo recibe la instantánea seudonimizada que puedes ver aquí."
        actions={<Button size="sm" variant="outline" onClick={() => setPreview(true)}><Eye />Ver lo que se enviará</Button>}
      />
      <CardContent className="space-y-4 text-sm">
        {/* Proveedor */}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-muted/30 p-3">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Proveedor</p>
            {s?.configured ? (
              <p className="mt-0.5 font-medium">
                {s.provider} · <span className="font-mono text-xs">{s.model}</span>
                <Badge variant={s.local ? "success" : "outline"} className="ml-2">{s.local ? "local" : "externo"}</Badge>
              </p>
            ) : (
              <p className="mt-0.5 text-muted-foreground">{s?.problem ?? "…"}</p>
            )}
            {check.data && (
              <p className={cn("mt-1 flex items-center gap-1 text-xs", check.data.ok ? "text-success" : "text-destructive")}>
                {check.data.ok ? <Check className="size-3.5" /> : <X className="size-3.5" />}{check.data.detail}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => check.mutate()} disabled={!s?.configured || check.isPending}>
              {check.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />}Probar conexión
            </Button>
            <Button size="sm" onClick={launch} disabled={!s?.configured || running || run.isPending}>
              {running || run.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {running ? "Auditando…" : "Auditar ahora"}
            </Button>
          </div>
        </div>

        {/* Últimos informes */}
        {!!reports.data?.length && (
          <ul className="divide-y rounded-xl border">
            {reports.data.map(r => <ReportRow key={r.id} r={r} onOpen={() => setOpenId(r.id)} />)}
          </ul>
        )}
      </CardContent>
      <PreviewDialog open={preview} onClose={() => setPreview(false)} />
      <ReportDialog id={openId} onClose={() => setOpenId(null)} />
    </Card>
  );
}

function ReportRow({ r, onOpen }: { r: AiAuditSummary; onOpen: () => void }) {
  return (
    <li>
      <button className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/40 disabled:cursor-default" onClick={onOpen} disabled={r.status === "running"}>
        <ScoreBadge score={r.status === "done" ? r.score : null} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {r.status === "running" ? "Auditando…" : r.status === "error" ? "Falló" : summaryText(r)}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {relativeTime(r.created_at)} · {r.model}
            {r.cost_usd != null && ` · ${r.cost_usd.toLocaleString("es-ES", { style: "currency", currency: "USD", maximumFractionDigits: 3 })}`}
            {r.status === "error" && r.error && ` · ${r.error}`}
          </p>
        </div>
        {r.status === "running" ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
      </button>
    </li>
  );
}

function summaryText(r: AiAuditSummary) {
  const total = Object.values(r.findings).reduce((a, b) => a + (b ?? 0), 0);
  if (!total) return "Sin hallazgos";
  const serious = (r.findings.critica ?? 0) + (r.findings.alta ?? 0);
  return `${total} hallazgo${total === 1 ? "" : "s"}${serious ? ` · ${serious} importante${serious === 1 ? "" : "s"}` : ""}`;
}

function ScoreBadge({ score, large }: { score: number | null; large?: boolean }) {
  const tone = score == null ? "bg-muted text-muted-foreground"
    : score >= 80 ? "bg-success/15 text-success" : score >= 50 ? "bg-warning/15 text-warning" : "bg-destructive/15 text-destructive";
  return (
    <span className={cn("flex shrink-0 items-center justify-center rounded-lg font-semibold tabular-nums", tone, large ? "size-14 text-xl" : "size-9 text-sm")}>
      {score ?? "–"}
    </span>
  );
}

// ─── Informe ─────────────────────────────────────────────────────────────────

function ReportDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const detail = useAiAuditReport(id);
  const d = detail.data;
  // disp-NN → nombre del dispositivo (la equivalencia nunca sale de LanSentinel)
  const names = new Map((d?.mapping ?? []).map(m => [m.id, m.nombre ?? m.id]));
  // El modelo también cita los seudónimos en los textos
  const h = (text: string) => text.replace(/\bdisp-\d+\b/g, id => names.get(id) ?? id);

  return (
    <Dialog
      open={id !== null}
      onClose={onClose}
      className="sm:max-w-3xl"
      title="Informe de auditoría"
      description={d ? `${relativeTime(d.created_at)} · ${d.provider} · ${d.model}` : undefined}
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><Sparkles className="size-4" /></div>}
      footer={<Button variant="outline" onClick={onClose}>Cerrar</Button>}
    >
      {detail.isLoading || !d ? (
        <div className="flex justify-center py-10 text-muted-foreground"><Loader2 className="size-5 animate-spin" /></div>
      ) : d.status === "error" || !d.report ? (
        <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />{d.error ?? "La auditoría no terminó"}
        </p>
      ) : (
        <div className="space-y-5 text-sm">
          <div className="flex items-start gap-4">
            <ScoreBadge score={d.report.puntuacion} large />
            <p className="min-w-0 flex-1 whitespace-pre-line">{h(d.report.resumen)}</p>
          </div>

          {d.report.hallazgos.length > 0 && (
            <ul className="space-y-3">
              {d.report.hallazgos.map((f, i) => (
                <li key={i} className="rounded-xl border p-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={GRAVEDAD[f.gravedad].variant}>{GRAVEDAD[f.gravedad].label}</Badge>
                    {f.dispositivos.map(dv => <Badge key={dv} variant="outline">{names.get(dv) ?? dv}</Badge>)}
                    {ACCION[f.accion] && <Badge variant="info" className="ml-auto">{ACCION[f.accion]}</Badge>}
                  </div>
                  <p className="mt-2 font-medium">{h(f.titulo)}</p>
                  <p className="mt-1 whitespace-pre-line text-muted-foreground">{h(f.detalle)}</p>
                  <p className="mt-2 rounded-lg bg-muted/50 p-2 text-xs"><span className="font-medium">Qué hacer: </span>{h(f.recomendacion)}</p>
                </li>
              ))}
            </ul>
          )}

          {d.report.positivos.length > 0 && (
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 font-medium"><ThumbsUp className="size-4 text-success" />Lo que está bien</p>
              <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
                {d.report.positivos.map((p, i) => <li key={i}>{h(p)}</li>)}
              </ul>
            </div>
          )}

          <p className="text-xs text-muted-foreground">
            {d.input_tokens != null && `${d.input_tokens.toLocaleString("es-ES")} tokens enviados, ${(d.output_tokens ?? 0).toLocaleString("es-ES")} recibidos`}
            {d.cost_usd != null && ` · ${d.cost_usd.toLocaleString("es-ES", { style: "currency", currency: "USD", maximumFractionDigits: 3 })}`}
            {d.discarded.length > 0 && ` · ${d.discarded.length} hallazgo${d.discarded.length === 1 ? "" : "s"} descartado${d.discarded.length === 1 ? "" : "s"} por citar dispositivos que no existen`}
          </p>
        </div>
      )}
    </Dialog>
  );
}

// ─── Vista previa ────────────────────────────────────────────────────────────

function PreviewDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const preview = useAiAuditPreview(open);
  const [copied, setCopied] = useState(false);
  const [showMapping, setShowMapping] = useState(false);
  const p = preview.data;
  const text = p ? JSON.stringify(p.snapshot, null, 2) : "";

  const copy = async () => {
    if (await copyText(text)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="sm:max-w-3xl"
      title="Lo que se enviaría al modelo"
      description="La instantánea de la red tal como saldría ahora mismo. Revísala antes de usar un proveedor externo."
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><Eye className="size-4" /></div>}
      footer={<Button variant="outline" onClick={onClose}>Cerrar</Button>}
    >
      {preview.isLoading ? (
        <div className="flex justify-center py-10 text-muted-foreground"><Loader2 className="size-5 animate-spin" /></div>
      ) : preview.isError || !p ? (
        <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(preview.error)}
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Tamaño" value={`${(p.characters / 1000).toFixed(1)} mil caracteres`} />
            <Stat label="Tokens (aprox.)" value={p.approx_tokens.toLocaleString("es-ES")} />
            <Stat label="Dispositivos" value={String(p.snapshot.dispositivos.length)} />
            <Stat label="Grupos de alertas" value={String(p.snapshot.alertas.length)} />
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant={p.snapshot.incluye.nombres_de_red ? "warning" : "secondary"}>
              Nombres de red: {p.snapshot.incluye.nombres_de_red ? "incluidos" : "no"}
            </Badge>
            <Badge variant={p.snapshot.incluye.dominios ? "warning" : "secondary"}>
              Dominios: {p.snapshot.incluye.dominios ? "incluidos" : "no"}
            </Badge>
          </div>

          <div className="relative">
            <pre className="max-h-[45dvh] overflow-auto rounded-lg border bg-muted/50 p-3 pr-10 font-mono text-[11px] leading-relaxed">{text}</pre>
            <Button variant="ghost" size="icon-sm" className="absolute right-1.5 top-1.5" onClick={copy} aria-label="Copiar">
              {copied ? <Check className="text-success" /> : <Copy />}
            </Button>
          </div>

          <div className="rounded-lg border">
            <button
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/40"
              onClick={() => setShowMapping(v => !v)} aria-expanded={showMapping}
            >
              <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", showMapping && "rotate-90")} />
              Equivalencias (se quedan en LanSentinel, no se envían)
            </button>
            {showMapping && (
              <ul className="divide-y border-t text-xs">
                {p.mapping.map(m => (
                  <li key={m.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2">
                    <span className="w-16 font-mono font-medium">{m.id}</span>
                    <span className="min-w-0 flex-1 truncate">{m.nombre ?? "—"}</span>
                    <span className="font-mono text-muted-foreground">{m.ip ?? "sin IP"}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium">{value}</p>
    </div>
  );
}
