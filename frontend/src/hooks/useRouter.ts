// Modo router: LanSentinel enruta la red (NAT, WAN cerrada) y da DHCP/DNS.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { RouterStatus } from "@/lib/types";

const KEY = ["firewall", "router"];

export function useRouterStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<RouterStatus>("/firewall/router");
      return data;
    },
    refetchInterval: 15_000,
  });
}

export function useSetRouter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (enabled: boolean) => {
      // Arrancar dnsmasq y reconstruir las reglas puede tardar unos segundos
      const { data } = await apiClient.put<RouterStatus>("/firewall/router", { enabled }, { timeout: 30_000 });
      return data;
    },
    onSuccess: data => {
      queryClient.setQueryData(KEY, data);
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}
