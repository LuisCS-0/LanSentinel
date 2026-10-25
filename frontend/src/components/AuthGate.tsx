// Muestra la pantalla de login si no hay sesión y el panel si la hay.

import { useEffect, type ReactNode } from "react";
import { Loader2, ServerCrash } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrentUser, ME_QUERY_KEY } from "@/hooks/useAuth";
import { UNAUTHORIZED_EVENT } from "@/lib/api";
import LoginPage from "@/pages/LoginPage";

export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useCurrentUser();

  // Cualquier 401 de la API (sesión caducada, contraseña cambiada en otro
  // navegador...) devuelve al login
  useEffect(() => {
    const handler = () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [queryClient]);

  if (me.isLoading) {
    return (
      <div className="app-backdrop flex min-h-dvh flex-col items-center justify-center gap-4 text-muted-foreground">
        <img src="/favicon.svg" alt="" className="size-12 animate-pulse" />
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  if (me.isError) {
    return (
      <div className="app-backdrop flex min-h-dvh flex-col items-center justify-center gap-3 p-4 text-center">
        <div className="rounded-2xl bg-destructive/10 p-4 text-destructive"><ServerCrash className="size-8" /></div>
        <p className="font-medium">No se puede conectar con LanSentinel</p>
        <p className="max-w-sm text-sm text-muted-foreground">Comprueba que el backend está en marcha. El panel lo reintentará al recargar.</p>
      </div>
    );
  }

  if (!me.data) return <LoginPage />;

  return <>{children}</>;
}
