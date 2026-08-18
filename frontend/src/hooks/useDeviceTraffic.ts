// Hook para consultar la tasa de tráfico de un dispositivo.
// Refetch cada 3 segundos para que la tabla muestre datos actualizados.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface DeviceTraffic {
  device_id: string;
  ip: string | null;
  rx_bps: number;
  tx_bps: number;
  total_bps: number;
  tracking: boolean;
}

export function useDeviceTraffic(deviceId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["device-traffic", deviceId],
    queryFn: async () => {
      if (!deviceId) return null;
      const { data } = await apiClient.get<DeviceTraffic>(
        `/devices/${deviceId}/traffic`,
      );
      return data;
    },
    enabled: enabled && !!deviceId,
    refetchInterval: 3000,
  });
}
