// Modo router: interruptor y estado (interfaces, DHCP, reenvío). Encenderlo o
// apagarlo afecta a la conexión de toda la red, así que siempre se confirma.

import { useState } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, Loader2, Network, Router } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton, Switch } from "@/components/ui/misc";
import { useRouterStatus, useSetRouter } from "@/hooks/useRouter";
import { extractErrorMessage } from "@/lib/api";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export function RouterCard() {
  const status = useRouterStatus();
  const mutation = useSetRouter();
  const [confirm, setConfirm] = useState<boolean | null>(null);   // estado al que se quiere pasar
  const r = status.data;

  const apply = async (enabled: boolean) => {
    try {
      const result = await mutation.mutateAsync(enabled);
      setConfirm(null);
      toast({
        title: enabled ? "Modo router encendido" : "Modo router apagado",
        description: enabled
          ? result.dhcp.running ? `Repartiendo IPs de ${result.dhcp.range_start} a ${result.dhcp.range_end}.` : undefined
          : "LanSentinel ya no enruta la red ni reparte IPs.",
      });
    } catch {
      // El error se muestra en el diálogo
    }
  };

  if (status.isLoading || !r) return <Card className="p-5"><Skeleton className="h-24" /></Card>;

  return (
    <Card className={cn("overflow-hidden", r.active && "border-success/40")}>
      <div className={cn("p-5", r.active && "bg-gradient-to-r from-success/10 to-transparent")}>
        <div className="flex items-start gap-4">
          <div className={cn("rounded-xl p-2.5 ring-1 ring-inset", r.active ? "bg-success/15 text-success ring-success/30" : "bg-muted text-muted-foreground ring-border")}>
            <Router className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Modo router</h3>
              <div className="flex items-center gap-2">
                {mutation.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                <Switch
                  checked={r.enabled} tone="success" label="Modo router"
                  onChange={value => setConfirm(value)}
                  disabled={mutation.isPending || (!r.enabled && !r.available)}
                />
              </div>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              LanSentinel hace de router de tu red: da salida a Internet con NAT, cierra la conexión de Internet a
              accesos desde fuera{r.dhcp_enabled && " y reparte las IPs y el DNS (DHCP)"}.
            </p>
          </div>
        </div>

        {!r.available && (
          <p className="mt-4 flex items-start gap-2 rounded-lg bg-muted/60 p-3 text-sm text-muted-foreground">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />{r.problem}
          </p>
        )}

        {r.available && (
          <dl className="mt-4 grid gap-3 rounded-xl border bg-card/60 p-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Interfaces</dt>
              <dd className="mt-1 flex items-center gap-1.5 font-mono text-xs">
                <span title="Hacia el router de la operadora">{r.wan_interface}</span>
                <ArrowRight className="size-3 text-muted-foreground" />
                <span title="Red local">{r.lan_interface}</span>
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">DHCP y DNS</dt>
              <dd className="mt-1">
                {!r.dhcp_enabled ? <span className="text-muted-foreground">Los da otro equipo</span>
                  : r.dhcp.running ? (
                    <>
                      <span className="font-mono text-xs">{r.dhcp.range_start} – {r.dhcp.range_end}</span>
                      <span className="block text-xs text-muted-foreground">{r.dhcp.active_leases} dispositivos con IP</span>
                    </>
                  )
                  : <span className="text-muted-foreground">{r.enabled ? "Detenido" : "Apagado"}</span>}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Reenvío del sistema</dt>
              <dd className={cn("mt-1", r.ip_forward ? "text-success" : "text-warning")}>
                {r.ip_forward ? "Activado" : "Desactivado"}
                {!r.ip_forward && <span className="block text-xs text-muted-foreground">Ejecuta scripts/instalar.sh</span>}
              </dd>
            </div>
          </dl>
        )}

        {(r.dhcp.error || (r.enabled && !r.active && r.available)) && (
          <p className="mt-3 flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {r.dhcp.error ?? "El modo router está encendido pero no se pudo aplicar: revisa los logs del backend."}
          </p>
        )}
      </div>

      <Dialog
        open={confirm !== null}
        onClose={() => { setConfirm(null); mutation.reset(); }}
        title={confirm ? "¿Encender el modo router?" : "¿Apagar el modo router?"}
        icon={<div className={cn("rounded-lg p-2", confirm ? "bg-success/15 text-success" : "bg-warning/15 text-warning")}>
          {confirm ? <Network className="size-4" /> : <AlertTriangle className="size-4" />}
        </div>}
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirm(null)} disabled={mutation.isPending}>Cancelar</Button>
            <Button variant={confirm ? "default" : "destructive"} onClick={() => apply(Boolean(confirm))} disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {confirm ? "Encender" : "Apagar"}
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {confirm ? (
            <>
              <p>LanSentinel dará salida a Internet a la red por <span className="font-mono">{r.wan_interface}</span> y cerrará esa conexión a accesos desde fuera.</p>
              {r.dhcp_enabled && (
                <p className="flex items-start gap-2 rounded-lg bg-warning/10 p-3 text-warning">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  Empezará a repartir IPs en <span className="font-mono">{r.lan_interface}</span>. Asegúrate de que no hay
                  otro servidor DHCP en la red (el del router de la operadora debe estar desactivado).
                </p>
              )}
            </>
          ) : (
            <>
              <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-destructive">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                Los dispositivos que usan LanSentinel como puerta de enlace se quedarán sin Internet.
              </p>
              {r.dhcp_enabled && (
                <p className="text-muted-foreground">
                  El DHCP y el DNS se detendrán: las IPs ya repartidas siguen valiendo hasta que caduquen, pero los
                  dispositivos nuevos no recibirán ninguna. El panel seguirá accesible desde la LAN.
                </p>
              )}
            </>
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
