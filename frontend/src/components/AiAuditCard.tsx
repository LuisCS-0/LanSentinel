// Auditoría con IA (solo administradores). Fase 1: la vista previa de la
// instantánea de la red que se enviaría al modelo, para revisar qué sale de
// casa antes de conectar ningún proveedor.

import { useState } from "react";
import { AlertCircle, Check, ChevronRight, Copy, Eye, Loader2, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useAiAuditPreview } from "@/hooks/useAiAudit";
import { extractErrorMessage } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

export function AiAuditCard() {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeaderRow
        title={<><Sparkles />Auditoría con IA</>}
        description="Un modelo de IA revisará el estado de la red y de LanSentinel y propondrá mejoras. Aún no hay ningún proveedor conectado: de momento puedes ver qué datos se le enviarían."
        actions={<Button size="sm" variant="outline" onClick={() => setOpen(true)}><Eye />Ver lo que se enviará</Button>}
      />
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p className="flex items-start gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-success" />
          Cada dispositivo va como «disp-01», «disp-02»… con su fabricante; sin MAC, sin IPs de la red de casa.
        </p>
        <p className="flex items-start gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-success" />
          Sin nombres de red ni historial de dominios, salvo que los actives (AI_AUDIT_INCLUDE_NAMES y AI_AUDIT_INCLUDE_DOMAINS en .env).
        </p>
      </CardContent>
      <PreviewDialog open={open} onClose={() => setOpen(false)} />
    </Card>
  );
}

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
      description="La instantánea de la red tal como saldría ahora mismo. Revísala antes de conectar un proveedor externo."
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
              onClick={() => setShowMapping(s => !s)} aria-expanded={showMapping}
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
