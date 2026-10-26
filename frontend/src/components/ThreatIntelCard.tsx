// Inteligencia de amenazas: listas de IPs maliciosas que corta el cortafuegos
// (y cuánto tráfico han parado) y reglas de Emerging Threats de Suricata.

import { AlertCircle, Download, Loader2, Radar, ShieldBan } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { useThreatIntel, useUpdateThreatLists } from "@/hooks/useThreatIntel";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { useIsAdmin } from "@/hooks/useAuth";

const LIST_LABEL: Record<string, string> = {
  firehol_level1: "FireHOL nivel 1",
  feodo: "abuse.ch Feodo (botnets)",
  propia: "Lista propia",
};

const compact = (n: number) => new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 1 }).format(n);

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function ThreatIntelCard() {
  const intel = useThreatIntel();
  const update = useUpdateThreatLists();
  const isAdmin = useIsAdmin();
  const t = intel.data;

  const updateNow = async () => {
    try {
      await update.mutateAsync();
      toast({ title: "Descargando las listas", description: "El estado se actualiza en unos segundos." });
    } catch (err) {
      toast({ title: "No se pudieron actualizar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  const s = t?.suricata;
  const rules = s?.loaded ?? s?.rules;

  return (
    <Card>
      <CardHeaderRow
        title={<><Radar />Inteligencia de amenazas</>}
        description="Listas públicas de IPs de botnets y malware que el cortafuegos corta, y reglas de Emerging Threats para Suricata. Se actualizan solas cada día."
        actions={isAdmin && t?.enabled && (
          <Button variant="outline" size="sm" onClick={updateNow} disabled={update.isPending}>
            {update.isPending ? <Loader2 className="animate-spin" /> : <Download />}Actualizar listas
          </Button>
        )}
      />
      <CardContent className="space-y-4 text-sm">
        {intel.isLoading || !t ? <Skeleton className="h-28" /> : (
          <>
            <div className="grid gap-4 rounded-xl border bg-muted/30 p-4 grid-cols-2 lg:grid-cols-4">
              <Stat
                label="IPs bloqueadas"
                value={t.enabled ? compact(t.addresses) : "—"}
                hint={t.enabled ? `${t.lists.reduce((n, l) => n + l.entries, 0).toLocaleString("es-ES")} redes` : "Desactivadas"}
              />
              <Stat
                label="Intentos desde la red"
                value={t.blocked_outgoing.toLocaleString("es-ES")}
                hint={t.applied_at ? `paquetes cortados desde ${relativeTime(t.applied_at)}` : "paquetes cortados"}
              />
              <Stat label="Desde Internet" value={t.blocked_incoming.toLocaleString("es-ES")} hint="paquetes cortados" />
              <Stat
                label="Reglas de Suricata"
                value={rules ? rules.toLocaleString("es-ES") : "—"}
                hint={s?.last_success_at ? `Actualizadas ${relativeTime(s.last_success_at)}` : "Sin descargar todavía"}
              />
            </div>

            {(t.error || s?.error || (s?.failed ?? 0) > 0) && (
              <div className="space-y-1">
                {t.error && <p className="flex items-start gap-2 text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{t.error}</p>}
                {s?.error && <p className="flex items-start gap-2 text-warning"><AlertCircle className="mt-0.5 size-4 shrink-0" />Reglas de Suricata: {s.error}</p>}
                {(s?.failed ?? 0) > 0 && (
                  <p className="flex items-start gap-2 text-muted-foreground">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />{s?.failed} reglas de Suricata no se pudieron cargar (el resto funciona).
                  </p>
                )}
              </div>
            )}

            {t.enabled ? (
              <div className="divide-y rounded-lg border">
                {t.lists.map(l => (
                  <div key={l.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                    <ShieldBan className="size-4 text-muted-foreground" />
                    <span className="font-medium">{LIST_LABEL[l.name] ?? l.name}</span>
                    {l.error ? <Badge variant="warning">Sin actualizar</Badge> : null}
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                      {l.entries.toLocaleString("es-ES")} redes · {l.updated_at ? relativeTime(l.updated_at) : "nunca"}
                    </span>
                    {l.error && <p className="w-full text-xs text-warning">{l.error}</p>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg bg-muted/60 p-3 text-muted-foreground">
                Las listas de IPs están desactivadas (THREAT_LISTS_ENABLED=false en el .env).
              </p>
            )}

            <p className="text-xs text-muted-foreground">
              Si un dispositivo intenta conectar con una IP de las listas, se corta y se crea una alerta: suele ser
              malware llamando a casa.
              {t.removed_unsafe > 0 && ` Se han descartado ${t.removed_unsafe} redes privadas o protegidas que traían las listas.`}
              {" "}Para bloquear IPs a mano, añádelas a /var/lib/lansentinel/amenazas/propia.txt.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
