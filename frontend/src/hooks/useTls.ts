// Certificado HTTPS del panel y CA de LanSentinel.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { TlsStatus } from "@/lib/types";

export const CA_DOWNLOAD_URL = "/api/v1/system/tls/ca.crt";

export function useTlsStatus() {
  return useQuery({
    queryKey: ["system", "tls"],
    queryFn: async () => {
      const { data } = await apiClient.get<TlsStatus>("/system/tls");
      return data;
    },
    staleTime: 5 * 60_000,
  });
}
