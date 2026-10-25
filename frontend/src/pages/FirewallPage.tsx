import { useState } from "react";
import {
  Lock, Plus, Trash2, RefreshCw, Bot, User, AlertCircle, Loader2,
} from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { useFirewallRules } from "@/hooks/useApi";
import { useBlockIp, useUnblockRule } from "@/hooks/useMutations";
import { relativeTime } from "@/lib/dates";
import type { FirewallRule } from "@/lib/types";

export default function FirewallPage() {
  const rules = useFirewallRules(false); // todas, activas e inactivas
  const blockMutation = useBlockIp();
  const unblockMutation = useUnblockRule();

  const [showBlockDialog, setShowBlockDialog] = useState(false);
  const [ruleToDelete, setRuleToDelete] = useState<FirewallRule | null>(null);

  const activeRules = (rules.data || []).filter(r => r.is_active);

  const handleConfirmDelete = () => {
    if (ruleToDelete) {
      unblockMutation.mutate(ruleToDelete.id);
      setRuleToDelete(null);
    }
  };

  return (
    <div className="container py-8 space-y-6">
      {/* Cabecera */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Firewall</h1>
          <p className="text-muted-foreground mt-1">
            {activeRules.length} reglas activas
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setShowBlockDialog(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Bloquear IP
          </Button>
          <Button variant="outline" size="sm" onClick={() => rules.refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refrescar
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Reglas activas</CardTitle>
          <CardDescription>
            IPs y dispositivos que están siendo bloqueados en este momento
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rules.isLoading ? (
            <p className="text-center py-12 text-muted-foreground">
              Cargando reglas…
            </p>
          ) : activeRules.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Lock className="h-10 w-10 mx-auto mb-3 opacity-50" />
              <p>No hay reglas activas</p>
              <p className="text-sm mt-1">
                Las reglas se crean al bloquear manualmente una IP o por la
                política de bloqueo automático.
              </p>
            </div>
          ) : (
            <RuleTable
              rules={activeRules}
              onDelete={setRuleToDelete}
            />
          )}
        </CardContent>
      </Card>

      {/* Modal para crear bloqueo */}
      <BlockIpDialog
        open={showBlockDialog}
        onClose={() => setShowBlockDialog(false)}
      />

      {/* Modal de confirmación de borrado */}
      <Dialog
        open={!!ruleToDelete}
        onClose={() => setRuleToDelete(null)}
        title="¿Eliminar regla?"
        description="Esta acción quitará el bloqueo de iptables. La IP o el dispositivo volverá a tener acceso a la red."
      >
        <div className="space-y-4">
          {ruleToDelete && (
            <div className="bg-muted p-3 rounded-md text-sm">
              <p className="font-medium">{ruleToDelete.name}</p>
              {ruleToDelete.src_ip && (
                <p className="text-xs text-muted-foreground mt-1">
                  IP: <span className="font-mono">{ruleToDelete.src_ip}</span>
                </p>
              )}
              {ruleToDelete.src_mac && (
                <p className="text-xs text-muted-foreground mt-1">
                  MAC: <span className="font-mono">{ruleToDelete.src_mac}</span>
                </p>
              )}
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => setRuleToDelete(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete}>
              Eliminar regla
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

// ─── Tabla de reglas ─────────────────────────────────────────────────────────

interface RuleTableProps {
  rules: FirewallRule[];
  onDelete: (rule: FirewallRule) => void;
}

function RuleTable({ rules, onDelete }: RuleTableProps) {
  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left">
            <th className="px-4 py-3 font-medium">Nombre</th>
            <th className="px-4 py-3 font-medium">Bloquea</th>
            <th className="px-4 py-3 font-medium">Acción</th>
            <th className="px-4 py-3 font-medium">Origen</th>
            <th className="px-4 py-3 font-medium">Creada</th>
            <th className="px-4 py-3 font-medium text-right"></th>
          </tr>
        </thead>
        <tbody>
          {rules.map(rule => (
            <tr key={rule.id} className="border-t hover:bg-muted/30">
              <td className="px-4 py-3">
                <p className="font-medium">{rule.name}</p>
                {rule.description && (
                  <p className="text-xs text-muted-foreground line-clamp-1">
                    {rule.description}
                  </p>
                )}
              </td>
              <td className="px-4 py-3 font-mono text-xs">
                {rule.src_ip && <p>{rule.src_ip}</p>}
                {rule.src_mac && (
                  <p
                    className="text-muted-foreground"
                    title="Bloqueo por MAC: se mantiene aunque el dispositivo cambie de IP"
                  >
                    {rule.src_mac}
                  </p>
                )}
                {!rule.src_ip && !rule.src_mac && "—"}
              </td>
              <td className="px-4 py-3">
                <Badge variant="destructive" className="text-xs uppercase">
                  {rule.action}
                </Badge>
              </td>
              <td className="px-4 py-3">
                {rule.auto_generated ? (
                  <Badge variant="warning" className="gap-1 text-xs">
                    <Bot className="h-3 w-3" />
                    Automático
                  </Badge>
                ) : (
                  <Badge variant="outline" className="gap-1 text-xs">
                    <User className="h-3 w-3" />
                    Manual
                  </Badge>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-muted-foreground">
                {relativeTime(rule.created_at)}
              </td>
              <td className="px-4 py-3 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDelete(rule)}
                  title="Eliminar regla"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Modal de creación de bloqueo ────────────────────────────────────────────

interface BlockIpDialogProps {
  open: boolean;
  onClose: () => void;
}

function BlockIpDialog({ open, onClose }: BlockIpDialogProps) {
  const blockMutation = useBlockIp();
  const [ip, setIp] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Validación básica de IPv4 / IPv6 (el backend hace la validación completa)
  const isValidIp = (s: string) => {
    const v = s.trim();
    return /^(\d{1,3}\.){3}\d{1,3}$/.test(v) || (v.includes(":") && /^[0-9a-fA-F:.]+$/.test(v));
  };

  const handleSubmit = async () => {
    setError(null);
    if (!isValidIp(ip)) {
      setError("Introduce una dirección IPv4 o IPv6 válida");
      return;
    }
    try {
      await blockMutation.mutateAsync({ ip: ip.trim(), reason: reason.trim() });
      setIp("");
      setReason("");
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "No se pudo aplicar el bloqueo");
    }
  };

  const handleClose = () => {
    setIp("");
    setReason("");
    setError(null);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="Bloquear dirección IP"
      description="La IP será bloqueada inmediatamente en iptables y persistida."
    >
      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium block mb-1.5">
            Dirección IP <span className="text-destructive">*</span>
          </label>
          <Input
            placeholder="192.168.56.20"
            value={ip}
            onChange={e => setIp(e.target.value)}
            autoFocus
            disabled={blockMutation.isPending}
          />
        </div>

        <div>
          <label className="text-sm font-medium block mb-1.5">
            Motivo (opcional)
          </label>
          <Input
            placeholder="Actividad sospechosa"
            value={reason}
            onChange={e => setReason(e.target.value)}
            disabled={blockMutation.isPending}
          />
        </div>

        {error && (
          <div className="flex gap-2 items-start text-sm text-destructive bg-destructive/10 p-3 rounded-md">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={handleClose} disabled={blockMutation.isPending}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            disabled={blockMutation.isPending}
          >
            {blockMutation.isPending && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Bloquear
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
