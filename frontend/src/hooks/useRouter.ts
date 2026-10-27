// Modo router: LanSentinel enruta la red (NAT, WAN cerrada) y da DHCP/DNS.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { RouterCheck, RouterStatus } from "@/lib/types";

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
      // Al encenderlo se vuelve a comprobar la red (unos segundos) y arrancar
      // dnsmasq y reconstruir las reglas también tarda
      const { data } = await apiClient.put<RouterStatus>("/firewall/router", { enabled }, { timeout: 30_000 });
      return data;
    },
    onSuccess: data => {
      queryClient.setQueryData(KEY, data);
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}

// Interfaces, IP fija en la LAN, salida por la WAN, reenvío y otro DHCP en la
// LAN (esta espera unos segundos a que responda)
export function useRouterChecks() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<RouterCheck[]>("/firewall/router/check", undefined, { timeout: 30_000 });
      return data;
    },
  });
}
