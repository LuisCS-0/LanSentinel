import { useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, KeyRound, Loader2 } from "lucide-react";
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
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><KeyRound className="size-4" /></div>}
      footer={mutation.isSuccess ? (
        <Button onClick={handleClose}>Cerrar</Button>
      ) : (
        <>
          <Button variant="outline" onClick={handleClose} disabled={mutation.isPending}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={mutation.isPending || !current}>
            {mutation.isPending && <Loader2 className="animate-spin" />}
            Cambiar
          </Button>
        </>
      )}
    >
      {mutation.isSuccess ? (
        <p className="flex items-start gap-2 rounded-lg bg-success/10 p-3 text-sm text-success">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
          Contraseña cambiada correctamente.
        </p>
      ) : (
        <form className="space-y-4" onSubmit={e => { e.preventDefault(); handleSubmit(); }}>
          <Field label="Contraseña actual">
            <Input type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} autoFocus disabled={mutation.isPending} />
          </Field>
          <Field label="Nueva contraseña" hint={`Al menos ${MIN_LENGTH} caracteres`}>
            <Input type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} disabled={mutation.isPending} />
          </Field>
          <Field label="Repite la nueva contraseña">
            <Input type="password" autoComplete="new-password" value={repeat} onChange={e => setRepeat(e.target.value)} disabled={mutation.isPending} />
          </Field>
          {error && (
            <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />{error}
            </p>
          )}
          {/* Enter envía el formulario */}
          <button type="submit" className="hidden" />
        </form>
      )}
    </Dialog>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between text-sm font-medium">
        {label}
        {hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  );
}
