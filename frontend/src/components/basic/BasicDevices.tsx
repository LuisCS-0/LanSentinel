// Dispositivos en modo básico: tarjetas con el nombre, si está conectado y
// si es de confianza, con dos preguntas sencillas: ¿es tuyo? Sin IPs, MAC,
// puertos ni conexiones (el detalle sigue a un clic).

import { useMemo, useState } from "react";
import { Ban, ChevronRight, ShieldCheck, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { DeviceAvatar, DeviceStatusBadge } from "@/components/devices/DeviceBits";
import { useDevices } from "@/hooks/useApi";
import { useIsAdmin } from "@/hooks/useAuth";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useBlockDevice, useTrustDevice } from "@/hooks/useDevices";
import { useQuarantine } from "@/hooks/useQuarantine";
import { relativeTime } from "@/lib/dates";
import { deviceName, isOnline } from "@/lib/devices";
import { cn } from "@/lib/utils";
import type { Device } from "@/lib/types";

type Filter = "pending" | "all";

export function BasicDevices() {
  const devices = useDevices();
  const quarantine = useQuarantine();
  const list = useMemo(() => devices.data ?? [], [devices.data]);
  const pending = list.filter(d => !d.is_trusted && !d.is_blocked);
  // Hasta que se elija, "por revisar" si hay alguno (se decide con los datos ya cargados)
  const [chosen, setFilter] = useState<Filter | null>(null);
  const filter: Filter = chosen ?? (pending.length ? "pending" : "all");
  const shown = (filter === "pending" ? pending : list)
    .slice()
    .sort((a, b) => Number(isOnline(b)) - Number(isOnline(a)) || deviceName(a).localeCompare(deviceName(b), "es"));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tus equipos"
        description="Todo lo que se conecta a tu red. Marca como de confianza lo que es tuyo; así sabrás al momento cuándo aparece algo que no conoces."
      />
      <Segmented<Filter>
        value={filter}
        onChange={setFilter}
        options={[
          { value: "pending", label: `Por revisar (${pending.length})` },
          { value: "all", label: `Todos (${list.length})` },
        ]}
      />
      {devices.isLoading ? <Skeleton className="h-60" /> : shown.length === 0 ? (
        <Card>
          <EmptyState icon={ShieldCheck} title="No hay nada por revisar" description="Todos tus equipos están marcados como de confianza o bloqueados." />
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map(d => <DeviceTile key={d.id} device={d} quarantine={!!quarantine.data?.enabled} />)}
        </div>
      )}
    </div>
  );
}

function DeviceTile({ device: d, quarantine }: { device: Device; quarantine: boolean }) {
  const sheet = useDeviceSheet();
  const trust = useTrustDevice();
  const block = useBlockDevice();
  const isAdmin = useIsAdmin();
  const online = isOnline(d);
  const busy = trust.isPending || block.isPending;

  return (
    <Card className="flex flex-col gap-3 p-4">
      <button onClick={() => sheet.open(d.id)} className="group flex items-center gap-3 text-left">
        <DeviceAvatar device={d} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium group-hover:text-primary">{deviceName(d)}</p>
          <p className={cn("text-sm", online ? "text-success" : "text-muted-foreground")}>
            {online ? "Conectado ahora" : `Visto ${relativeTime(d.last_seen)}`}
          </p>
        </div>
        <ChevronRight className="size-4 text-muted-foreground" />
      </button>
      <div><DeviceStatusBadge device={d} quarantine={quarantine} /></div>
      {isAdmin && (
        <div className="mt-auto flex flex-wrap gap-2">
          {d.is_blocked ? (
            <Button size="sm" variant="outline" onClick={() => block.mutate({ id: d.id, blocked: false })} disabled={busy}>
              <Undo2 />Desbloquear
            </Button>
          ) : d.is_trusted ? (
            <Button size="sm" variant="ghost" onClick={() => trust.mutate({ id: d.id, trusted: false })} disabled={busy}>
              Ya no es de confianza
            </Button>
          ) : (
            <>
              <Button size="sm" variant="success" onClick={() => trust.mutate({ id: d.id, trusted: true })} disabled={busy}>
                <ShieldCheck />Es mío
              </Button>
              <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive"
                      onClick={() => block.mutate({ id: d.id, blocked: true })} disabled={busy}>
                <Ban />No lo conozco: bloquear
              </Button>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
