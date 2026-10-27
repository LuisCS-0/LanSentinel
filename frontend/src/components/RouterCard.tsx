// Modo router: interruptor y estado (interfaces, DHCP, reenvío). Encenderlo o
// apagarlo afecta a la conexión de toda la red, así que siempre se confirma.
// Antes de encenderlo se comprueba que la red está lista (IP fija en la LAN,
// salida por la WAN, ningún otro DHCP...) y se explica cómo arreglar lo que no.

import { useState } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, CheckCircle2, Loader2, Network, RefreshCw, Router, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton, Switch } from "@/components/ui/misc";
import { useRouterChecks, useRouterStatus, useSetRouter } from "@/hooks/useRouter";
import { extractErrorMessage } from "@/lib/api";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/hooks/useAuth";
import type { RouterCheck, RouterStatus } from "@/lib/types";

export function RouterCard() {
  const status = useRouterStatus();
  const mutation = useSetRouter();
  const checks = useRouterChecks();
  const isAdmin = useIsAdmin();
  const [confirm, setConfirm] = useState<boolean | null>(null);   // estado al que se quiere pasar
  const r = status.data;
  const blocked = checks.data?.some(c => !c.ok && c.blocking) ?? false;

  const ask = (enabled: boolean) => {
    setConfirm(enabled);
    if (enabled) checks.mutate();
  };
  const close = () => { setConfirm(null); mutation.reset(); checks.reset(); };

  const apply = async (enabled: boolean) => {
    try {
      const result = await mutation.mutateAsync(enabled);
      close();
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
                  onChange={ask}
                  disabled={!isAdmin || mutation.isPending || (!r.enabled && !r.available)}
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
            <Ipv6Row r={r} />
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
        onClose={close}
        title={confirm ? "¿Encender el modo router?" : "¿Apagar el modo router?"}
        icon={<div className={cn("rounded-lg p-2", confirm ? "bg-success/15 text-success" : "bg-warning/15 text-warning")}>
          {confirm ? <Network className="size-4" /> : <AlertTriangle className="size-4" />}
        </div>}
        footer={
          <>
            <Button variant="outline" onClick={close} disabled={mutation.isPending}>Cancelar</Button>
            <Button
              variant={confirm ? "default" : "destructive"} onClick={() => apply(Boolean(confirm))}
              disabled={mutation.isPending || (Boolean(confirm) && (!checks.data || blocked))}
            >
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {confirm ? (mutation.isPending ? "Encendiendo…" : "Encender") : "Apagar"}
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {confirm ? (
            <>
              <p>
                LanSentinel dará salida a Internet a la red por <span className="font-mono">{r.wan_interface}</span> y
                cerrará esa conexión a accesos desde fuera
                {r.dhcp_enabled && <>; además repartirá las IPs y el DNS en <span className="font-mono">{r.lan_interface}</span></>}.
              </p>
              <RouterChecks checks={checks.data} pending={checks.isPending} error={checks.isError ? extractErrorMessage(checks.error) : null}
                onRetry={() => checks.mutate()} />
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

// Resultado de las comprobaciones: lo que falla, con cómo arreglarlo
function RouterChecks({ checks, pending, error, onRetry }: {
  checks: RouterCheck[] | undefined; pending: boolean; error: string | null; onRetry: () => void;
}) {
  if (pending) {
    return (
      <p className="flex items-center gap-2 rounded-lg border bg-muted/40 p-3 text-muted-foreground">
        <Loader2 className="size-4 shrink-0 animate-spin" />Comprobando la red (unos segundos: se espera a ver si responde otro servidor DHCP)…
      </p>
    );
  }
  const blocked = checks?.some(c => !c.ok && c.blocking);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Comprobaciones</p>
        <Button size="sm" variant="ghost" onClick={onRetry}><RefreshCw />Volver a comprobar</Button>
      </div>
      {error && (
        <p className="flex items-start gap-2 text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</p>
      )}
      {checks && (
        <ul className="divide-y rounded-lg border">
          {checks.map(c => {
            const Icon = c.ok ? CheckCircle2 : c.blocking ? XCircle : AlertTriangle;
            const tone = c.ok ? "text-success" : c.blocking ? "text-destructive" : "text-warning";
            return (
              <li key={c.id} className="flex items-start gap-2.5 p-2.5">
                <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} />
                <div className="min-w-0">
                  <p className="font-medium">{c.label}</p>
                  <p className={cn("text-xs", c.ok ? "text-muted-foreground" : tone)}>{c.detail}</p>
                  {!c.ok && c.fix && <p className="mt-1 text-xs text-muted-foreground">{c.fix}</p>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {blocked && (
        <p className="text-xs text-muted-foreground">
          Arregla lo que está en rojo y vuelve a comprobar: encenderlo así podría dejar la red sin conexión.
        </p>
      )}
    </div>
  );
}

// IPv6 en la LAN: de dónde sale el prefijo y si hace falta NAT66
const IPV6_SOURCE: Record<string, string> = {
  static: "Prefijo fijo de la operadora",
  pd: "Prefijo delegado por la operadora",
  ula: "Sin prefijo de la operadora: dirección privada con NAT66",
};

function Ipv6Row({ r }: { r: RouterStatus }) {
  const v6 = r.ipv6;
  if (!v6) return null;
  return (
    <div className="sm:col-span-3">
      <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">IPv6 en la LAN</dt>
      <dd className="mt-1">
        {!v6.enabled ? (
          <span className="text-muted-foreground">Desactivado: la LAN solo usa IPv4 (IPV6_LAN en .env)</span>
        ) : v6.active ? (
          <>
            <span className="break-all font-mono text-xs">{v6.prefix}</span>
            <span className={cn("block text-xs", v6.nat ? "text-warning" : "text-muted-foreground")}>
              {IPV6_SOURCE[v6.source ?? ""] ?? v6.source}
              {v6.source === "ula" && v6.pd_client && " · se sigue pidiendo uno"}
            </span>
            {r.ipv6_forward === false && <span className="block text-xs text-warning">Reenvío IPv6 desactivado: ejecuta scripts/instalar.sh --ipv6</span>}
          </>
        ) : (
          <span className="text-warning">{v6.error ?? (r.active ? "Esperando un prefijo de la operadora…" : "Apagado")}</span>
        )}
      </dd>
    </div>
  );
}

