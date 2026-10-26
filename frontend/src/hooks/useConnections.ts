// Conexiones abiertas de toda la red (tabla conntrack del gateway). Cambian
// a cada segundo, así que se refrescan a menudo. La caché es compartida (la
// barra lateral, el Panel y Dispositivos también la usan), así que para
// "pausar" una vista hay que guardar una copia de los datos, no dejar de pedirlos.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { NetworkConnections } from "@/lib/types";

export function useNetworkConnections() {
  return useQuery({
    queryKey: ["connections", "network"],
    queryFn: async () => {
      const { data } = await apiClient.get<NetworkConnections>("/network/connections");
      return data;
    },
    refetchInterval: 5000,
  });
}
