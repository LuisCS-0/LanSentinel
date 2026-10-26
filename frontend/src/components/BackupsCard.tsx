// Copias de seguridad: estado, copia manual, lista con descarga y cómo
// restaurar (la restauración se hace en el servidor: hay que parar el backend).

import { useState } from "react";
import { AlertCircle, ArchiveRestore, Check, Download, HardDrive, Loader2, Save, Terminal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { backupDownloadUrl, useBackups, useCreateBackup } from "@/hooks/useBackups";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { formatBytes } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { BackupMotivo } from "@/lib/types";
import { useIsAdmin } from "@/hooks/useAuth";

const MOTIVO_LABEL: Record<BackupMotivo, string> = {
  inicial: "Inicial",
  diaria: "Diaria",
  manual: "Manual",
  actualizacion: "Antes de actualizar",
  restauracion: "Antes de restaurar",
};

const SHOWN = 5;

function dateTime(iso: string) {
  return new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function BackupsCard() {
  const backups = useBackups();
  const create = useCreateBackup();
  const isAdmin = useIsAdmin();
  const [showAll, setShowAll] = useState(false);
  const [showRestore, setShowRestore] = useState(false);
  const b = backups.data;

  const backupNow = async () => {
    try {
      const result = await create.mutateAsync();
      toast({ title: "Copia hecha", description: `${result.name} · ${formatBytes(result.size)}` });
    } catch {
      // El error se muestra en la tarjeta
    }
  };

  const failing = b?.last_error && (!b.last_success_at || (b.last_error_at ?? "") > b.last_success_at);
  const list = b ? (showAll ? b.backups : b.backups.slice(0, SHOWN)) : [];

  return (
    <Card>
      <CardHeaderRow
        title={<><HardDrive />Copias de seguridad</>}
        description="Base de datos, configuración, certificados y .env. Contienen secretos: guarda las descargas en un sitio seguro."
        actions={isAdmin && (
          <Button size="sm" onClick={backupNow} disabled={create.isPending || b?.running}>
            {create.isPending || b?.running ? <Loader2 className="animate-spin" /> : <Save />}
            {create.isPending || b?.running ? "Haciendo copia…" : "Hacer copia ahora"}
          </Button>
        )}
      />
      <CardContent className="space-y-4 text-sm">
        {backups.isLoading || !b ? <Skeleton className="h-32" /> : (
          <>
            <div className="grid gap-3 rounded-xl border bg-muted/30 p-4 sm:grid-cols-3">
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Última copia</p>
                <p className={cn("font-medium", !b.last_success_at && "text-warning")}>
                  {b.last_success_at ? relativeTime(b.last_success_at) : "Ninguna todavía"}
                </p>
              </div>
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Automáticas</p>
                {b.enabled ? (
                  <>
                    <p className="font-medium">Cada día a las {String(b.hour).padStart(2, "0")}:00</p>
                    {b.next_at && (
                      <p className="text-xs text-muted-foreground">
                        {/* Si ya toca, se hace en la próxima comprobación del backend (cada 10 min) */}
                        Próxima {new Date(b.next_at) <= new Date() ? "en unos minutos" : relativeTime(b.next_at)}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="font-medium text-warning">Desactivadas</p>
                )}
              </div>
              <div className="min-w-0">
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Se guardan en</p>
                <p className="truncate font-mono text-xs" title={b.location}>{b.location}</p>
                <p className="text-xs text-muted-foreground">Las {b.keep_daily} últimas y {b.keep_weekly} semanales</p>
              </div>
            </div>

            {(failing || create.isError) && (
              <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <span>
                  {create.isError ? extractErrorMessage(create.error) : b.last_error}
                  {!create.isError && b.last_error_at && <span className="block text-xs opacity-80">Falló {relativeTime(b.last_error_at)}</span>}
                </span>
              </p>
            )}

            {b.backups.length > 0 && (
              <div className="divide-y rounded-lg border">
                {list.map(f => (
                  <div key={f.name} className="flex items-center gap-3 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{dateTime(f.created_at)}</p>
                      <p className="truncate font-mono text-[11px] text-muted-foreground">{f.name}</p>
                    </div>
                    <Badge variant={f.motivo === "diaria" || f.motivo === "inicial" ? "secondary" : "info"}>{MOTIVO_LABEL[f.motivo] ?? f.motivo}</Badge>
                    <span className="w-16 text-right text-xs tabular-nums text-muted-foreground">{formatBytes(f.size)}</span>
                    {/* Las copias contienen secretos: solo las descarga un administrador */}
                    {isAdmin && (
                      <Button
                        variant="ghost" size="icon" className="size-8" aria-label={`Descargar ${f.name}`}
                        onClick={() => { window.location.href = backupDownloadUrl(f.name); }}
                      >
                        <Download className="size-4" />
                      </Button>
                    )}
                  </div>
                ))}
                {b.backups.length > SHOWN && (
                  <button className="w-full px-3 py-2 text-xs text-muted-foreground hover:bg-muted/40" onClick={() => setShowAll(s => !s)}>
                    {showAll ? "Ver menos" : `Ver las ${b.backups.length}`}
                  </button>
                )}
              </div>
            )}

            <div className="rounded-lg border">
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-left font-medium hover:bg-muted/40"
                onClick={() => setShowRestore(s => !s)} aria-expanded={showRestore}
              >
                <ArchiveRestore className="size-4 text-muted-foreground" />Cómo restaurar una copia
              </button>
              {showRestore && (
                <div className="space-y-2 px-3 pb-3 text-muted-foreground">
                  <p>
                    Se hace en el servidor, desde la carpeta de LanSentinel. El script hace antes una copia del estado
                    actual, para poder deshacerlo, y para el panel mientras restaura:
                  </p>
                  <pre className="flex items-center gap-2 overflow-auto rounded-md bg-muted/60 p-2 font-mono text-xs text-foreground">
                    <Terminal className="size-3.5 shrink-0" />sudo scripts/restaurar.sh {b.backups[0]?.name ?? "lansentinel-AAAAMMDD-HHMMSS-diaria.tar.gz"}
                  </pre>
                  <p className="flex items-start gap-1.5 text-xs">
                    <Check className="mt-px size-3.5 shrink-0" />
                    En un equipo nuevo: instala LanSentinel con scripts/instalar.sh, copia el fichero a la carpeta de las
                    copias y restaura. El .env del equipo no se sustituye; el de la copia queda al lado como .env.copia.
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
