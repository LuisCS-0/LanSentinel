// Pestaña Dominios de la ficha: con qué dominios habla el dispositivo (por DNS
// o como servidor de una conexión cifrada) y con qué programas (huellas TLS).

import { useMemo, useState } from "react";
import { Fingerprint, Globe, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { useDeviceDomains } from "@/hooks/useDomains";
import { shortRelative } from "@/lib/dates";

const SHOWN = 100;

export function DomainsTab({ deviceId }: { deviceId: string }) {
  const [days, setDays] = useState("7");
  const [query, setQuery] = useState("");
  const data = useDeviceDomains(deviceId, Number(days));
  const d = data.data;

  const domains = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (d?.domains ?? []).filter(x => !q || x.domain.includes(q));
  }, [d, query]);

  if (data.isLoading) return <div className="p-5"><Skeleton className="h-60" /></div>;
  if (d && !d.enabled) {
    return (
      <div className="p-5">
        <EmptyState icon={Globe} title="Registro de dominios desactivado" description="Se activa con DOMAIN_TRACKING_ENABLED=true en el .env." />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          size="sm" value={days} onChange={setDays}
          options={[{ value: "1", label: "24 h" }, { value: "7", label: "7 días" }, { value: "30", label: "30 días" }]}
        />
        <div className="relative ml-auto w-full sm:w-56">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar dominio" className="h-8 pl-8 text-sm" />
        </div>
      </div>

      {!domains.length ? (
        <EmptyState
          icon={Globe} title={query ? "Ningún dominio coincide" : "Sin dominios en este periodo"}
          description="Se ven las consultas DNS y el servidor de cada conexión cifrada que pasan por LanSentinel."
        />
      ) : (
        <div className="divide-y rounded-lg border text-sm">
          {domains.slice(0, SHOWN).map(x => (
            <div key={x.domain} className="flex items-center gap-2 px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-mono text-xs" title={x.domain}>{x.domain}</span>
              {x.via_tls && <Badge variant="secondary" className="px-1.5" title="Servidor de una conexión cifrada (SNI)">TLS</Badge>}
              {x.via_dns && <Badge variant="outline" className="px-1.5" title="Consulta DNS">DNS</Badge>}
              <span className="w-12 text-right text-xs tabular-nums text-muted-foreground" title="Veces vistas">{x.hits.toLocaleString("es-ES")}</span>
              <span className="w-16 text-right text-xs text-muted-foreground" title={new Date(x.last_seen).toLocaleString("es-ES")}>{shortRelative(x.last_seen)}</span>
            </div>
          ))}
          {domains.length > SHOWN && (
            <p className="px-3 py-2 text-xs text-muted-foreground">y {domains.length - SHOWN} más (usa el buscador)</p>
          )}
        </div>
      )}

      {!!d?.fingerprints.length && (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-sm font-medium"><Fingerprint className="size-4 text-muted-foreground" />Programas que abren conexiones cifradas</p>
          <p className="text-xs text-muted-foreground">
            Cada programa (navegador, app, sistema de actualizaciones...) deja una huella TLS (JA4) distinta. Una huella nueva en un
            dispositivo que siempre usa las mismas es un programa nuevo.
          </p>
          <div className="divide-y rounded-lg border text-sm">
            {d.fingerprints.map(f => (
              <div key={f.fingerprint} className="space-y-0.5 px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs" title={f.ja3 ? `JA3 ${f.ja3}` : undefined}>{f.fingerprint}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">{f.hits.toLocaleString("es-ES")}</span>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  Desde {shortRelative(f.first_seen)}{f.last_sni && ` · última vez con ${f.last_sni}`}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Es el historial de navegación del dispositivo: solo lo ve el administrador y se borra a los {d?.history_days ?? 30} días
        sin verse. No incluye lo que va por DNS cifrado (DoH/DoT) ni el tráfico entre dispositivos de la LAN.
      </p>
    </div>
  );
}
