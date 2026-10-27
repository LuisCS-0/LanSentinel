// Panel principal en modo básico: si la red está bien o no, en una frase;
// lo que necesita atención explicado sin tecnicismos; los equipos de casa y
// lo que se puede hacer. Sin gráficas, IPs ni conexiones.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, Bell, HelpCircle, MonitorSmartphone, ShieldAlert, ShieldCheck, ShieldQuestion, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { PlainAlertItem } from "@/components/basic/PlainAlertItem";
import { useAlerts, useDevices, useSystemStatus } from "@/hooks/useApi";
import { useCurrentUser, useIsAdmin } from "@/hooks/useAuth";
import { useQuarantine } from "@/hooks/useQuarantine";
import { isOnline } from "@/lib/devices";
import { severityRank } from "@/lib/severity";
import { cn } from "@/lib/utils";

const WEEK = 7 * 24 * 3600 * 1000;

export function BasicDashboard() {
  const devices = useDevices();
  const alerts = useAlerts(100);
  const status = useSystemStatus();
  const quarantine = useQuarantine();
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const me = useCurrentUser().data?.username;
  const [now] = useState(() => Date.now());

  const list = devices.data ?? [];
  const byId = new Map(list.map(d => [d.id, d]));
  const pending = (alerts.data ?? [])
    .filter(a => a.status === "new" && a.severity !== "info")
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity) || b.last_seen_at.localeCompare(a.last_seen_at));
  const urgent = pending.filter(a => a.severity === "critical" || a.severity === "high");
  const servicesOk = status.data && status.data.monitor?.running && status.data.security?.running && status.data.firewall?.running;
  const online = list.filter(isOnline).length;
  const unknown = list.filter(d => !d.is_trusted && !d.is_blocked);
  const recent = list.filter(d => d.first_seen && now - new Date(d.first_seen).getTime() < WEEK);

  const state = alerts.isLoading || status.isLoading ? null
    : !servicesOk ? { tone: "warning", icon: ShieldQuestion, title: "LanSentinel no está vigilando del todo",
        text: "Alguna de sus partes no está en marcha. Si no se arregla sola en unos minutos, pide ayuda a quien lo instaló." }
    : urgent.length ? { tone: "destructive", icon: ShieldAlert,
        title: urgent.length === 1 ? "Hay algo importante que revisar" : `Hay ${urgent.length} cosas importantes que revisar`,
        text: "Te contamos abajo qué ha pasado y qué puedes hacer." }
    : pending.length ? { tone: "warning", icon: Bell, title: "Tu red está bien, con algún aviso",
        text: "Nada urgente, pero conviene que le eches un vistazo." }
    : { tone: "success", icon: ShieldCheck, title: "Tu red está protegida",
        text: "LanSentinel vigila tus equipos y no ha visto nada raro." };

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border bg-card/80 p-6 shadow-card sm:p-8">
        <div className="bg-brand pointer-events-none absolute -right-16 -top-24 size-72 rounded-full opacity-20 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-5">
          {state && (
            <div className={cn(
              "rounded-2xl p-4 ring-1 ring-inset",
              state.tone === "destructive" && "bg-destructive/15 text-destructive ring-destructive/30",
              state.tone === "warning" && "bg-warning/15 text-warning ring-warning/30",
              state.tone === "success" && "bg-success/15 text-success ring-success/30",
            )}>
              <state.icon className="size-9" />
            </div>
          )}
          <div className="min-w-0 flex-1 basis-60">
            <p className="text-sm text-muted-foreground">Hola{me ? `, ${me}` : ""}</p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{state?.title ?? "Cargando…"}</h1>
            {state && <p className="mt-1 text-muted-foreground">{state.text}</p>}
          </div>
        </div>
      </div>

      {quarantine.data?.enabled && (
        <p className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/5 p-4 text-sm">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>
            <span className="font-medium">Modo cuarentena activado.</span> Los equipos nuevos no salen a Internet hasta que
            los marques como de confianza en <Link to="/devices" className="text-primary hover:underline">Dispositivos</Link>.
          </span>
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <Card>
          <CardHeaderRow
            title={<><Bell />Necesita tu atención</>}
            description="Lo que LanSentinel ha visto y aún no has revisado, de lo más a lo menos importante."
            actions={pending.length > 5 && (
              <Button size="sm" variant="ghost" onClick={() => navigate("/alerts")}>Ver todo<ArrowRight /></Button>
            )}
          />
          <CardContent>
            {alerts.isLoading ? <Skeleton className="h-40" /> : pending.length ? (
              <ul className="-my-3 divide-y">
                {pending.slice(0, 5).map(a => (
                  <PlainAlertItem key={a.id} alert={a} device={a.device_id ? byId.get(a.device_id) : undefined} />
                ))}
              </ul>
            ) : (
              <EmptyState icon={ShieldCheck} title="Nada pendiente" description="Cuando pase algo que debas saber, aparecerá aquí." />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeaderRow title={<><MonitorSmartphone />Tus equipos</>} />
            <CardContent className="space-y-3 text-sm">
              {devices.isLoading ? <Skeleton className="h-24" /> : (
                <>
                  <p>
                    <span className="text-2xl font-semibold">{online}</span>
                    <span className="text-muted-foreground"> conectados ahora, de {list.length} que conoce LanSentinel.</span>
                  </p>
                  {recent.length > 0 && (
                    <p className="text-muted-foreground">
                      {recent.length === 1 ? "Uno es nuevo" : `${recent.length} son nuevos`} esta semana.
                    </p>
                  )}
                  {unknown.length > 0 ? (
                    <p className="rounded-lg bg-muted/50 p-3">
                      {unknown.length === 1 ? "Hay 1 equipo" : `Hay ${unknown.length} equipos`} que aún no has marcado como de
                      confianza. Si son tuyos, márcalos; así sabrás enseguida cuándo aparece uno que no conoces.
                    </p>
                  ) : list.length > 0 && (
                    <p className="text-success">Todos tus equipos están revisados.</p>
                  )}
                  <Button variant="outline" className="w-full" onClick={() => navigate("/devices")}>
                    Ver mis equipos<ArrowRight />
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {isAdmin && (
            <Card>
              <CardHeaderRow title={<><Sparkles />Revisión con IA</>} />
              <CardContent className="space-y-3 text-sm">
                <p className="text-muted-foreground">
                  Una inteligencia artificial puede revisar tu red entera y decirte, en palabras sencillas, qué mejorar.
                </p>
                <Button variant="outline" className="w-full" onClick={() => navigate("/audit")}>
                  Ir a la Auditoría IA<ArrowRight />
                </Button>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeaderRow title={<><HelpCircle />¿Qué hace LanSentinel?</>} />
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>Vigila los aparatos conectados a tu red de casa (móviles, ordenadores, teles, cámaras…).</p>
              <p>Te avisa si aparece uno nuevo, si alguno hace algo raro o si alguien de fuera intenta entrar, y bloquea lo peligroso.</p>
              <p>
                ¿Quieres ver todo el detalle técnico? Cambia a <span className="font-medium text-foreground">Experto</span> arriba a la derecha.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
