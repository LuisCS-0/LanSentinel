// Páginas solo del modo experto (conexiones, tráfico, cortafuegos): en el
// modo básico no salen en el menú y, si se llega por un enlace, se explica
// en lugar de enseñar la pantalla técnica.

import type { ReactNode } from "react";
import { Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/misc";
import { setViewMode, useIsBasic } from "@/lib/viewMode";

export function ExpertOnly({ children }: { children: ReactNode }) {
  if (!useIsBasic()) return <>{children}</>;
  return (
    <Card>
      <EmptyState
        icon={Wrench}
        title="Esta pantalla es del modo experto"
        description="Tiene el detalle técnico de la red. Para verla, cambia al modo experto; puedes volver al básico cuando quieras."
        action={<Button onClick={() => setViewMode("experto")}>Cambiar a modo experto</Button>}
      />
    </Card>
  );
}
