// Proveedor configurado (o qué falta), Probar conexión y Auditar ahora.

import { Check, Loader2, PlugZap, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PROVEEDOR } from "@/lib/aiAudit";
import { useAiAuditReports, useAiAuditStatus, useCheckAiProvider, useRunAiAudit } from "@/hooks/useAiAudit";
import { extractErrorMessage } from "@/lib/api";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export function ProviderBar({ onStarted, className }: { onStarted?: (id: number) => void; className?: string }) {
  const status = useAiAuditStatus();
  const reports = useAiAuditReports();
  const run = useRunAiAudit();
  const check = useCheckAiProvider();
  const s = status.data;
  const running = s?.running || reports.data?.some(r => r.status === "running");

  const launch = async () => {
    try {
      const { id } = await run.mutateAsync();
      toast({ title: "Auditoría en marcha", description: "El informe aparecerá en Auditoría en uno o dos minutos." });
      onStarted?.(id);
    } catch (err) {
      toast({ title: "No se pudo lanzar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  return (
    <div className={cn("flex flex-wrap items-center gap-3 rounded-xl border bg-muted/30 p-3 text-sm", className)}>
      <div className="min-w-0 flex-1 basis-64">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Proveedor</p>
        {s?.configured ? (
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-medium">
            <span>{PROVEEDOR[s.provider ?? ""] ?? s.provider}</span>
            <span className="font-mono text-xs">{s.model}</span>
            {s.endpoint && <span className="font-mono text-xs text-muted-foreground">en {s.endpoint}</span>}
            <Badge variant={s.local ? "success" : "outline"}>{s.local ? "local: los datos no salen" : "externo"}</Badge>
            {s.compact && <Badge variant="secondary">instantánea compacta</Badge>}
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
  );
}
