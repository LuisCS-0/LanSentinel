// Inteligencia de amenazas: listas de IPs maliciosas y reglas de Suricata.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { ThreatIntelStatus } from "@/lib/types";

const KEY = ["security", "threat-intel"];

export function useThreatIntel() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<ThreatIntelStatus>("/security/threat-intel");
      return data;
    },
    refetchInterval: 30_000,
  });
}

export function useUpdateThreatLists() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.post("/security/threat-intel/update");
    },
    // La descarga tarda unos segundos: se vuelve a consultar un poco después
    onSuccess: () => window.setTimeout(() => queryClient.invalidateQueries({ queryKey: KEY }), 8000),
  });
}
