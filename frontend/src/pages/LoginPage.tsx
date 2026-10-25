import { useState, type FormEvent } from "react";
import { Shield, AlertCircle, Loader2 } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLogin } from "@/hooks/useAuth";
import { extractErrorMessage } from "@/lib/api";

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
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <Shield className="h-10 w-10 text-primary mx-auto mb-2" />
          <CardTitle>LanSentinel</CardTitle>
          <CardDescription>Inicia sesión para administrar tu red</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="text-sm font-medium block mb-1.5">
                Usuario
              </label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                disabled={login.isPending}
              />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium block mb-1.5">
                Contraseña
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                disabled={login.isPending}
              />
            </div>

            {login.isError && (
              <div className="flex gap-2 items-start text-sm text-destructive bg-destructive/10 p-3 rounded-md">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>{extractErrorMessage(login.error)}</span>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Entrar
            </Button>

            <p className="text-xs text-muted-foreground text-center">
              ¿Primer acceso? La contraseña inicial está en el servidor:{" "}
              <code className="font-mono">/var/lib/lansentinel/initial_admin_password</code>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
