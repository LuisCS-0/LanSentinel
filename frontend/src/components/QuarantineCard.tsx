// Tarjeta del modo cuarentena: estado, explicación y activación con
// confirmación (muestra qué dispositivos se quedarán sin Internet).

import { useState } from "react";
import { AlertCircle, AlertTriangle, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useQuarantine, useSetQuarantine } from "@/hooks/useQuarantine";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";

export function QuarantineCard() {
  const status = useQuarantine();
  const mutation = useSetQuarantine();
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

  return (
    <Card className={enabled ? "border-amber-400" : undefined}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              {enabled ? <ShieldAlert className="h-4 w-4 text-amber-600" /> : <ShieldCheck className="h-4 w-4" />}
              Modo cuarentena
              {enabled ? <Badge variant="warning">Activo</Badge> : <Badge variant="outline">Desactivado</Badge>}
            </CardTitle>
            <CardDescription className="mt-1">
              Con el modo activo, solo los dispositivos marcados como de confianza pueden salir a
              Internet. Los demás, también los que se conecten por primera vez, quedan retenidos
              hasta que los apruebes. Siguen pudiendo acceder a LanSentinel, así que siempre
              puedes desactivarlo desde aquí.
            </CardDescription>
          </div>
          {enabled ? (
            <Button variant="outline" onClick={() => apply(false)} disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Desactivar
            </Button>
          ) : (
            <Button onClick={() => setConfirming(true)} disabled={!data}>
              Activar cuarentena
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="text-sm space-y-2">
        {data && (
          <p className="text-muted-foreground">
            {data.trusted_count} dispositivos de confianza ·{" "}
            {enabled
              ? `${affected.length} en cuarentena`
              : `${affected.length} se quedarían sin Internet`}
          </p>
        )}
        {enabled && affected.length > 0 && (
          <ul className="space-y-1">
            {affected.map(d => (
              <li key={d.id} className="flex flex-wrap gap-x-2 text-xs">
                <span className="font-medium">{d.hostname || d.vendor || d.mac}</span>
                <span className="font-mono text-muted-foreground">{d.ip || "sin IP"} · {d.mac}</span>
                <span className="text-muted-foreground">visto {relativeTime(d.last_seen)}</span>
              </li>
            ))}
          </ul>
        )}
        {mutation.isError && !confirming && (
          <p className="flex items-start gap-1 text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            {extractErrorMessage(mutation.error)}
          </p>
        )}
      </CardContent>

      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="¿Activar el modo cuarentena?"
        description="Los dispositivos que no sean de confianza perderán el acceso a Internet al momento."
      >
        <div className="space-y-4 text-sm">
          {data && data.trusted_count === 0 && (
            <div className="flex gap-2 items-start text-destructive bg-destructive/10 p-3 rounded-md">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>
                Ningún dispositivo está marcado como de confianza: toda la red, incluido el equipo
                desde el que administras, se quedará sin Internet. Marca antes tus dispositivos.
              </span>
            </div>
          )}
          {affected.length > 0 ? (
            <div>
              <p className="font-medium mb-2">Se quedarán sin Internet ({affected.length}):</p>
              <ul className="max-h-48 overflow-auto space-y-1 border rounded-md p-2">
                {affected.map(d => (
                  <li key={d.id} className="text-xs">
                    <span className="font-medium">{d.hostname || d.vendor || d.mac}</span>{" "}
                    <span className="font-mono text-muted-foreground">{d.ip || "sin IP"} · {d.mac}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-muted-foreground">
              Todos los dispositivos vistos en las últimas 24 horas son de confianza.
            </p>
          )}
          {mutation.isError && (
            <p className="flex items-start gap-1 text-destructive">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              {extractErrorMessage(mutation.error)}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={mutation.isPending}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => apply(true)} disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Activar
            </Button>
          </div>
        </div>
      </Dialog>
    </Card>
  );
}
