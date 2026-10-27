// La instantánea de la red: la que se enviaría ahora (vista previa) y la
// que se envió en una auditoría ya hecha.

import { useState } from "react";
import { AlertCircle, ChevronRight, Eye, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { JsonViewer } from "@/components/ai-audit/shared";
import { useAiAuditPreview } from "@/hooks/useAiAudit";
import { extractErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AiAuditPreview } from "@/lib/types";

export function PreviewDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const preview = useAiAuditPreview(open);
  const p = preview.data;

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
        <SnapshotView snapshot={p.snapshot} mapping={p.mapping} characters={p.characters} tokens={p.approx_tokens} />
      )}
    </Dialog>
  );
}

export function SentSnapshotDialog({
  open, onClose, snapshot, mapping,
}: { open: boolean; onClose: () => void; snapshot: AiAuditPreview["snapshot"] | null; mapping: AiAuditPreview["mapping"] }) {
  const characters = snapshot ? JSON.stringify(snapshot).length : 0;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="sm:max-w-3xl"
      title="Lo que se envió al modelo"
      description="La instantánea de la red de esta auditoría, exactamente como salió."
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><Eye className="size-4" /></div>}
      footer={<Button variant="outline" onClick={onClose}>Cerrar</Button>}
    >
      {snapshot ? (
        <SnapshotView snapshot={snapshot} mapping={mapping} characters={characters} tokens={Math.round(characters / 3.5)} />
      ) : (
        <p className="text-sm text-muted-foreground">Esta auditoría no guardó la instantánea.</p>
      )}
    </Dialog>
  );
}

function SnapshotView({
  snapshot, mapping, characters, tokens,
}: { snapshot: AiAuditPreview["snapshot"]; mapping: AiAuditPreview["mapping"]; characters: number; tokens: number }) {
  const [showMapping, setShowMapping] = useState(false);
  const omitted = snapshot.omitido;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Tamaño" value={`${(characters / 1000).toFixed(1)} mil caracteres`} />
        <Stat label="Tokens (aprox.)" value={tokens.toLocaleString("es-ES")} />
        <Stat label="Dispositivos" value={String(snapshot.dispositivos.length)} />
        <Stat label="Grupos de alertas" value={String(snapshot.alertas.length)} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Badge variant={snapshot.incluye.nombres_de_red ? "warning" : "secondary"}>
          Nombres de red: {snapshot.incluye.nombres_de_red ? "incluidos" : "no"}
        </Badge>
        <Badge variant={snapshot.incluye.dominios ? "warning" : "secondary"}>
          Dominios: {snapshot.incluye.dominios ? "incluidos" : "no"}
        </Badge>
        {snapshot.compacta && <Badge variant="info">Compacta (modelos con poco contexto)</Badge>}
        {!!(omitted?.alertas || omitted?.dispositivos) && (
          <Badge variant="warning">
            No caben: {omitted.alertas} grupos de alertas y {omitted.dispositivos} dispositivos
          </Badge>
        )}
      </div>

      <JsonViewer value={snapshot} />

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
            {mapping.map(m => (
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
