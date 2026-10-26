// Cortafuegos: modo cuarentena, inteligencia de amenazas, reglas de bloqueo activas (y el historial de
// las ya retiradas) y bloqueo manual de una IP. ?block=1 abre directamente
// el diálogo de bloqueo (lo usa el buscador global).

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertCircle, Ban, Bot, Flame, History, Loader2, Plus, Trash2, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { PageHeader } from "@/components/PageHeader";
import { QuarantineCard } from "@/components/QuarantineCard";
import { ThreatIntelCard } from "@/components/ThreatIntelCard";
import { DeviceLabel } from "@/components/devices/DeviceBits";
import { useDevices, useFirewallRules } from "@/hooks/useApi";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useBlockIp, useUnblockRule } from "@/hooks/useMutations";
import { extractErrorMessage } from "@/lib/api";
import { shortRelative } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { FirewallRule } from "@/lib/types";
import { useIsAdmin } from "@/hooks/useAuth";

export default function FirewallPage() {
  const rules = useFirewallRules(false);
  const unblock = useUnblockRule();
  const devices = useDevices();
  const sheet = useDeviceSheet();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<"active" | "history">("active");
  const [toDelete, setToDelete] = useState<FirewallRule | null>(null);
  const isAdmin = useIsAdmin();

  const blockOpen = params.get("block") === "1";
  const setBlockOpen = (open: boolean) => setParams(prev => {
    const next = new URLSearchParams(prev);
    if (open) next.set("block", "1");
    else next.delete("block");
    return next;
  });

  const all = rules.data ?? [];
  const active = all.filter(r => r.is_active);
  const history = all.filter(r => !r.is_active);
  const shown = (view === "active" ? active : history).sort((a, b) => b.created_at.localeCompare(a.created_at));

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await unblock.mutateAsync(toDelete.id);
      toast({ title: "Bloqueo retirado", description: toDelete.name });
      setToDelete(null);
    } catch {
      // El error se muestra en el diálogo
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cortafuegos"
        description={`${active.length} bloqueos activos · ${active.filter(r => r.auto_generated).length} automáticos`}
        actions={isAdmin && <Button onClick={() => setBlockOpen(true)}><Plus />Bloquear una IP</Button>}
      />

      <QuarantineCard />
      <ThreatIntelCard />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold"><Flame className="size-4 text-muted-foreground" />Reglas de bloqueo</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">Los dispositivos de la LAN se bloquean por IP y por MAC, para que cambiar de IP no sirva para saltárselo</p>
          </div>
          <Segmented
            value={view} onChange={setView} size="sm"
            options={[
              { value: "active", label: <><Ban />Activas</>, count: active.length },
              { value: "history", label: <><History />Historial</>, count: history.length },
            ]}
          />
        </div>

        {rules.isLoading ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-14" />)}</div>
        ) : shown.length === 0 ? (
          <EmptyState
            icon={Flame}
            title={view === "active" ? "No hay bloqueos activos" : "Sin historial"}
            description={view === "active" ? "Se crean al bloquear un dispositivo o una IP, o automáticamente ante ataques graves." : undefined}
            action={isAdmin && view === "active" ? <Button variant="outline" size="sm" onClick={() => setBlockOpen(true)}><Plus />Bloquear una IP</Button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Bloqueo</th>
                  <th className="px-4 py-2.5 font-medium">Afecta a</th>
                  <th className="px-4 py-2.5 font-medium">Origen</th>
                  <th className="px-4 py-2.5 font-medium">{view === "active" ? "Desde" : "Retirada"}</th>
                  <th className="w-14 px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {shown.map(rule => {
                  const device = rule.device_id ? devices.data?.find(d => d.id === rule.device_id) : undefined;
                  return (
                    <tr key={rule.id} className={cn("transition-colors hover:bg-muted/40", !rule.is_active && "text-muted-foreground")}>
                      <td className="max-w-xs px-4 py-3">
                        <p className="truncate font-medium">{rule.name}</p>
                        {rule.description && <p className="line-clamp-1 text-xs text-muted-foreground">{rule.description}</p>}
                      </td>
                      <td className="px-4 py-3">
                        {device ? (
                          <DeviceLabel device={device} onClick={() => sheet.open(device.id)} />
                        ) : (
                          <div className="font-mono text-xs">
                            {rule.src_ip && <p>{rule.src_ip}</p>}
                            {rule.src_mac && <p className="text-muted-foreground" title="Bloqueo por MAC: se mantiene aunque cambie de IP">{rule.src_mac}</p>}
                            {!rule.src_ip && !rule.src_mac && "—"}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {rule.auto_generated
                          ? <Badge variant="warning"><Bot />Automático</Badge>
                          : <Badge variant="outline"><User />Manual</Badge>}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {shortRelative(rule.is_active ? rule.created_at : rule.updated_at)}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {isAdmin && rule.is_active && (
                          <Button variant="ghost" size="icon-sm" title="Retirar bloqueo" className="hover:text-destructive" onClick={() => setToDelete(rule)}>
                            <Trash2 />
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <BlockIpDialog open={isAdmin && blockOpen} onClose={() => setBlockOpen(false)} />

      <Dialog
        open={!!toDelete}
        onClose={() => { setToDelete(null); unblock.reset(); }}
        title="¿Retirar este bloqueo?"
        description="La IP o el dispositivo volverá a tener acceso a la red."
        icon={<div className="rounded-lg bg-destructive/15 p-2 text-destructive"><Trash2 className="size-4" /></div>}
        footer={
          <>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={unblock.isPending}>Cancelar</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={unblock.isPending}>
              {unblock.isPending && <Loader2 className="animate-spin" />}Retirar bloqueo
            </Button>
          </>
        }
      >
        {toDelete && (
          <div className="rounded-lg border bg-muted/30 p-3 text-sm">
            <p className="font-medium">{toDelete.name}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{[toDelete.src_ip, toDelete.src_mac].filter(Boolean).join(" · ")}</p>
          </div>
        )}
        {unblock.isError && (
          <p className="mt-3 flex items-start gap-2 text-sm text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(unblock.error)}</p>
        )}
      </Dialog>
    </div>
  );
}

// ─── Bloqueo manual de una IP ────────────────────────────────────────────────

function BlockIpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const block = useBlockIp();
  const [ip, setIp] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Validación básica; la completa la hace el backend (incluidas las IPs protegidas)
  const isValidIp = (s: string) => /^(\d{1,3}\.){3}\d{1,3}$/.test(s) || (s.includes(":") && /^[0-9a-fA-F:.]+$/.test(s));

  const close = () => {
    setIp("");
    setReason("");
    setError(null);
    onClose();
  };

  const submit = async () => {
    setError(null);
    const value = ip.trim();
    if (!isValidIp(value)) {
      setError("Introduce una dirección IPv4 o IPv6 válida");
      return;
    }
    try {
      await block.mutateAsync({ ip: value, reason: reason.trim() });
      toast({ title: `IP ${value} bloqueada` });
      close();
    } catch (err) {
      setError(extractErrorMessage(err) || "No se pudo aplicar el bloqueo");
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Bloquear una dirección IP"
      description="Se aplica al momento y se mantiene aunque se reinicie LanSentinel."
      icon={<div className="rounded-lg bg-destructive/15 p-2 text-destructive"><Ban className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={block.isPending}>Cancelar</Button>
          <Button variant="destructive" onClick={submit} disabled={block.isPending || !ip.trim()}>
            {block.isPending && <Loader2 className="animate-spin" />}Bloquear
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={e => { e.preventDefault(); submit(); }}>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Dirección IP</span>
          <Input placeholder="203.0.113.7" value={ip} onChange={e => setIp(e.target.value)} autoFocus disabled={block.isPending} className="font-mono" />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Motivo <span className="font-normal text-muted-foreground">(opcional)</span></span>
          <Input placeholder="Actividad sospechosa" value={reason} onChange={e => setReason(e.target.value)} disabled={block.isPending} />
        </label>
        <p className="text-xs text-muted-foreground">
          Para bloquear un equipo de tu red es mejor hacerlo desde Dispositivos: así se bloquea también por MAC.
        </p>
        {error && (
          <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</p>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  );
}
