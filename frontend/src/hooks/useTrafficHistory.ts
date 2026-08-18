// Hook para consultar el histórico de tráfico total agregado.
// Refetch cada 5 segundos para que la gráfica se actualice fluidamente.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface TrafficSample {
  seconds_ago: number;
  rx_bps: number;
  tx_bps: number;
  total_bps: number;
}

interface TrafficHistoryResponse {
  samples: TrafficSample[];
}

export function useTrafficHistory() {
  return useQuery({
    queryKey: ["network-traffic-history"],
    queryFn: async () => {
      const { data } = await apiClient.get<TrafficHistoryResponse>(
        "/network/traffic/history",
      );
      return data.samples;
    },
    refetchInterval: 5000,
  });
}