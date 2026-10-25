// Confirmación para bloquear una IP de Internet vista en las conexiones.

import { useState } from "react";
import { AlertCircle, Ban, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useBlockIp } from "@/hooks/useMutations";
import { extractErrorMessage } from "@/lib/api";
import { toast } from "@/lib/toast";

export function BlockRemoteDialog({ ip, onClose }: { ip: string | null; onClose: () => void }) {
  const block = useBlockIp();
  const [reason, setReason] = useState("");

  const close = () => {
    setReason("");
    block.reset();
    onClose();
  };

  const confirm = async () => {
    if (!ip) return;
    try {
      await block.mutateAsync({ ip, reason: reason.trim() || `Bloqueada desde Conexiones (${ip})` });
      toast({ title: `IP ${ip} bloqueada`, description: "Puedes quitar el bloqueo en Cortafuegos." });
      close();
    } catch {
      // El error se muestra en el diálogo
    }
  };

  return (
    <Dialog
      open={!!ip}
      onClose={close}
      title={`¿Bloquear ${ip}?`}
      description="Se cortará el tráfico con esta IP para toda la red. Puedes deshacerlo en Cortafuegos."
      icon={<div className="rounded-lg bg-destructive/15 p-2 text-destructive"><Ban className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={block.isPending}>Cancelar</Button>
          <Button variant="destructive" onClick={confirm} disabled={block.isPending}>
            {block.isPending && <Loader2 className="animate-spin" />}
            Bloquear
          </Button>
        </>
      }
    >
      <label className="mb-1.5 block text-sm font-medium">Motivo (opcional)</label>
      <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="Destino sospechoso" autoFocus />
      {block.isError && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          {extractErrorMessage(block.error)}
        </p>
      )}
    </Dialog>
  );
}
