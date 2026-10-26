// Registro de acciones (solo administradores): quién cambió qué, desde qué
// IP y con qué resultado. Los intentos de un usuario de solo lectura salen
// como "Denegado". Las contraseñas nunca llegan aquí: el backend las tapa.

import { useState } from "react";
import { Check, ChevronRight, Copy, History, Loader2, Lock, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeaderRow } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { useAuditLog } from "@/hooks/useUsers";
import { copyText } from "@/lib/clipboard";
import { relativeTime } from "@/lib/dates";
import { cn } from "@/lib/utils";
import type { AuditEntry } from "@/lib/types";

function outcome(code: number) {
  if (code < 400) return { label: "Hecho", variant: "success" as const, icon: Check, tone: "bg-success/10 text-success" };
  if (code === 401 || code === 403) return { label: "Denegado", variant: "warning" as const, icon: Lock, tone: "bg-warning/10 text-warning" };
  return { label: `Error ${code}`, variant: "destructive" as const, icon: X, tone: "bg-destructive/10 text-destructive" };
}

export function AuditCard() {
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const log = useAuditLog(filter === "failed");
  const entries = log.data?.pages.flat() ?? [];

  return (
    <Card className="overflow-hidden">
      <CardHeaderRow
        title={<><History />Registro de acciones</>}
        description="Cada cambio hecho desde el panel o la API, con usuario, IP y resultado. Se guarda un año."
        actions={
          <Segmented
            size="sm" value={filter} onChange={setFilter}
            options={[{ value: "all", label: "Todo" }, { value: "failed", label: "Denegado o fallido" }]}
          />
        }
      />
      {log.isLoading ? <div className="p-5"><Skeleton className="h-40" /></div> : entries.length === 0 ? (
        <EmptyState icon={History} title="Nada registrado" description={filter === "failed" ? "Ninguna acción denegada ni fallida." : "Aún no se ha cambiado nada."} />
      ) : (
        <>
          <ul className="divide-y border-t">
            {entries.map(e => <AuditRow key={e.id} entry={e} />)}
          </ul>
          {log.hasNextPage && (
            <button
              className="flex w-full items-center justify-center gap-2 border-t px-3 py-2.5 text-xs text-muted-foreground hover:bg-muted/40"
              onClick={() => log.fetchNextPage()} disabled={log.isFetchingNextPage}
            >
              {log.isFetchingNextPage && <Loader2 className="size-3.5 animate-spin" />}Cargar más
            </button>
          )}
        </>
      )}
    </Card>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [open, setOpen] = useState(false);
  const o = outcome(entry.status_code);
  const details = entry.details ? JSON.stringify(entry.details, null, 2) : null;

  return (
    <li className="px-5 py-3">
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 rounded-lg p-1.5", o.tone)}><o.icon className="size-3.5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            <span className="font-medium">{entry.action}</span>
            {entry.target && <span className="text-muted-foreground"> · {entry.target}</span>}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            <span className="font-medium text-foreground/80">{entry.username ?? "desconocido"}</span>
            {entry.ip && <> desde <span className="font-mono">{entry.ip}</span></>}
            {" · "}
            <span title={new Date(entry.created_at).toLocaleString("es-ES")}>{relativeTime(entry.created_at)}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge variant={o.variant}>{o.label}</Badge>
          {details && (
            <Button variant="ghost" size="icon-sm" onClick={() => setOpen(v => !v)} aria-label="Ver detalles" aria-expanded={open}>
              <ChevronRight className={cn("transition-transform", open && "rotate-90")} />
            </Button>
          )}
        </div>
      </div>
      {open && details && (
        <div className="relative ml-9 mt-2">
          <pre className="max-h-60 overflow-auto rounded-lg border bg-muted/50 p-3 pr-10 font-mono text-[11px] leading-relaxed">
            {entry.method} {entry.path}{"\n"}{details}
          </pre>
          <Button variant="ghost" size="icon-sm" className="absolute right-1.5 top-1.5" onClick={() => copyText(details)} aria-label="Copiar">
            <Copy />
          </Button>
        </div>
      )}
    </li>
  );
}
