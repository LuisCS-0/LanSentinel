import { useState, type FormEvent } from "react";
import { AlertCircle, Cable, Loader2, ShieldCheck, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLogin } from "@/hooks/useAuth";
import { extractErrorMessage } from "@/lib/api";

const FEATURES = [
  { icon: ShieldCheck, text: "Detección de intrusiones con Suricata y reglas propias" },
  { icon: Cable, text: "Qué dispositivos hay y con quién hablan, en directo" },
  { icon: Zap, text: "Bloqueo y cuarentena con un clic" },
];

export default function LoginPage() {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    login.mutate({ username: username.trim(), password });
  };

  return (
    <div className="app-backdrop grid min-h-dvh lg:grid-cols-2">
      {/* Presentación (solo en pantallas grandes) */}
      <div className="relative hidden overflow-hidden border-r bg-surface/40 p-12 lg:flex lg:flex-col lg:justify-between">
        <div className="bg-brand pointer-events-none absolute -left-32 top-1/3 size-[28rem] rounded-full opacity-20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-10" />
          <span className="text-lg font-semibold">LanSentinel</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight">
            Tu red, <span className="text-brand">bajo control</span>.
          </h1>
          <ul className="mt-8 space-y-4">
            {FEATURES.map(f => (
              <li key={f.text} className="flex items-center gap-3 text-muted-foreground">
                <span className="rounded-lg bg-primary/10 p-2 text-primary"><f.icon className="size-4" /></span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-muted-foreground">Monitor de seguridad para redes domésticas</p>
      </div>

      {/* Formulario */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm animate-zoom-in">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <img src="/favicon.svg" alt="" className="mb-4 size-12 lg:hidden" />
            <h2 className="text-2xl font-semibold tracking-tight">Inicia sesión</h2>
            <p className="mt-1 text-sm text-muted-foreground">Para administrar tu red</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Usuario</span>
              <Input id="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} autoFocus disabled={login.isPending} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Contraseña</span>
              <Input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} disabled={login.isPending} />
            </label>

            {login.isError && (
              <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />{extractErrorMessage(login.error)}
              </p>
            )}

            <Button type="submit" size="lg" className="w-full" disabled={login.isPending}>
              {login.isPending && <Loader2 className="animate-spin" />}
              Entrar
            </Button>
          </form>

          <p className="mt-8 rounded-lg border bg-card/50 p-3 text-xs text-muted-foreground">
            ¿Primer acceso? La contraseña inicial está en el servidor:{" "}
            <code className="break-all font-mono text-foreground/80">/var/lib/lansentinel/initial_admin_password</code>
          </p>
        </div>
      </div>
    </div>
  );
}
