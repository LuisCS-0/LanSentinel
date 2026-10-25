import { useState } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog } from "@/components/ui/dialog";
import { useChangePassword } from "@/hooks/useAuth";
import { extractErrorMessage } from "@/lib/api";

const MIN_LENGTH = 10;

interface ChangePasswordDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ChangePasswordDialog({ open, onClose }: ChangePasswordDialogProps) {
  const mutation = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    setCurrent("");
    setNext("");
    setRepeat("");
    setError(null);
    mutation.reset();
    onClose();
  };

  const handleSubmit = async () => {
    setError(null);
    if (next.length < MIN_LENGTH) {
      setError(`La nueva contraseña debe tener al menos ${MIN_LENGTH} caracteres`);
      return;
    }
    if (next !== repeat) {
      setError("Las contraseñas nuevas no coinciden");
      return;
    }
    try {
      await mutation.mutateAsync({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setRepeat("");
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="Cambiar contraseña"
      description="Se cerrarán las sesiones abiertas en otros navegadores."
    >
      {mutation.isSuccess ? (
        <div className="space-y-4">
          <div className="flex gap-2 items-start text-sm bg-muted p-3 rounded-md">
            <Check className="h-4 w-4 flex-shrink-0 mt-0.5 text-primary" />
            <span>Contraseña cambiada correctamente.</span>
          </div>
          <div className="flex justify-end">
            <Button onClick={handleClose}>Cerrar</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium block mb-1.5">Contraseña actual</label>
            <Input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={e => setCurrent(e.target.value)}
              autoFocus
              disabled={mutation.isPending}
            />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1.5">Nueva contraseña</label>
            <Input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={e => setNext(e.target.value)}
              disabled={mutation.isPending}
            />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1.5">Repite la nueva contraseña</label>
            <Input
              type="password"
              autoComplete="new-password"
              value={repeat}
              onChange={e => setRepeat(e.target.value)}
              disabled={mutation.isPending}
            />
          </div>

          {error && (
            <div className="flex gap-2 items-start text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={handleClose} disabled={mutation.isPending}>
              Cancelar
            </Button>
            <Button onClick={handleSubmit} disabled={mutation.isPending || !current}>
              {mutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Cambiar
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
