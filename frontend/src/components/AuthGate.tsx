// Muestra la pantalla de login si no hay sesión y el panel si la hay.

import { useEffect, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
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
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (me.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4 text-center text-muted-foreground">
        <p>No se puede conectar con el backend de LanSentinel. Comprueba que está en marcha.</p>
      </div>
    );
  }

  if (!me.data) return <LoginPage />;

  return <>{children}</>;
}
