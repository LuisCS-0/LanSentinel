// Modo cuarentena: estado, explicación y activación con confirmación (muestra
// qué dispositivos se quedarán sin Internet). "compact" es la versión del Panel.

import { useState } from "react";
import { AlertCircle, AlertTriangle, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/misc";
import { DeviceLabel } from "@/components/devices/DeviceBits";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useQuarantine, useSetQuarantine } from "@/hooks/useQuarantine";
import { extractErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/hooks/useAuth";

export function QuarantineCard({ compact = false }: { compact?: boolean }) {
  const status = useQuarantine();
  const mutation = useSetQuarantine();
  const isAdmin = useIsAdmin();
  const sheet = useDeviceSheet();
  const [confirming, setConfirming] = useState(false);

  const data = status.data;
  const enabled = data?.enabled ?? false;
  const affected = data?.quarantined ?? [];

  const apply = async (value: boolean) => {
    try {
      await mutation.mutateAsync(value);
      setConfirming(false);
    } catch {
      // El error se muestra en la tarjeta o en el diálogo
    }
  };

  const toggle = (value: boolean) => (value ? setConfirming(true) : apply(false));

  return (
    <Card className={cn("overflow-hidden", enabled && "border-warning/50")}>
      <div className={cn("p-5", enabled && "bg-gradient-to-r from-warning/10 to-transparent")}>
        <div className="flex items-start gap-4">
          <div className={cn("rounded-xl p-2.5 ring-1 ring-inset", enabled ? "bg-warning/15 text-warning ring-warning/30" : "bg-success/10 text-success ring-success/20")}>
            {enabled ? <ShieldAlert className="size-5" /> : <ShieldCheck className="size-5" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Modo cuarentena</h3>
              <div className="flex items-center gap-2">
                {mutation.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                <Switch checked={enabled} onChange={toggle} disabled={!isAdmin || !data || mutation.isPending} label="Modo cuarentena" />
              </div>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {enabled
                ? `Activo: solo los dispositivos de confianza salen a Internet. ${affected.length} retenidos.`
                : compact
                  ? `Desactivado. Al activarlo, ${affected.length === 1
                    ? "1 dispositivo sin confianza se quedaría"
                    : `${affected.length} dispositivos sin confianza se quedarían`} sin Internet.`
                  : "Solo los dispositivos marcados como de confianza pueden salir a Internet; los demás, también los que se conecten por primera vez, quedan retenidos hasta que los apruebes. Siguen pudiendo abrir este panel, así que siempre puedes desactivarlo."}
            </p>
            {!compact && data && (
              <p className="mt-2 text-xs text-muted-foreground">
                {data.trusted_count} de confianza · {affected.length} {enabled ? "en cuarentena" : "se quedarían sin Internet"}
              </p>
            )}
          </div>
        </div>

        {!compact && enabled && affected.length > 0 && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {affected.map(d => (
              <div key={d.id} className="flex items-center justify-between gap-2 rounded-lg border bg-card/60 p-2.5">
                <DeviceLabel device={d} onClick={() => sheet.open(d.id)} />
              </div>
            ))}
          </div>
        )}
        {mutation.isError && !confirming && (
          <p className="mt-3 flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(mutation.error)}
          </p>
        )}
      </div>

      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="¿Activar el modo cuarentena?"
        description="Los dispositivos que no sean de confianza perderán el acceso a Internet al momento."
        icon={<div className="rounded-lg bg-warning/15 p-2 text-warning"><ShieldAlert className="size-4" /></div>}
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={mutation.isPending}>Cancelar</Button>
            <Button variant="destructive" onClick={() => apply(true)} disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="animate-spin" />}
              Activar cuarentena
            </Button>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          {data && data.trusted_count === 0 && (
            <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              Ningún dispositivo está marcado como de confianza: toda la red, incluido el equipo desde el que
              administras, se quedará sin Internet. Marca antes tus dispositivos.
            </p>
          )}
          {affected.length > 0 ? (
            <div>
              <p className="mb-2 font-medium">Se quedarán sin Internet ({affected.length}):</p>
              <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border p-2">
                {affected.map(d => <DeviceLabel key={d.id} device={d} className="p-1" />)}
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground">Todos los dispositivos vistos en las últimas 24 horas son de confianza.</p>
          )}
          {mutation.isError && (
            <p className="flex items-start gap-2 text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(mutation.error)}
            </p>
          )}
        </div>
      </Dialog>
    </Card>
  );
}
