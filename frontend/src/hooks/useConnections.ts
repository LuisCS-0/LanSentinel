// Conexiones abiertas de toda la red (tabla conntrack del gateway). Cambian
// a cada segundo, así que se refrescan a menudo; se puede pausar el refresco
// para leer la tabla con calma.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { NetworkConnections } from "@/lib/types";

export function useNetworkConnections(live = true) {
  return useQuery({
    queryKey: ["connections", "network"],
    queryFn: async () => {
      const { data } = await apiClient.get<NetworkConnections>("/network/connections");
      return data;
    },
    refetchInterval: live ? 5000 : false,
  });
}
