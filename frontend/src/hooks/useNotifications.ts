// Estado de los avisos externos (Telegram, ntfy, correo) y envío de pruebas.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { NotificationStatus } from "@/lib/types";

export function useNotificationStatus() {
  return useQuery({
    queryKey: ["notifications", "status"],
    queryFn: async () => {
      const { data } = await apiClient.get<NotificationStatus>("/system/notifications");
      return data;
    },
    refetchInterval: 30_000,
  });
}

export function useTestNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (channel: string) => {
      // El envío puede tardar (SMTP, reintento de red): más margen que el resto
      await apiClient.post("/system/notifications/test", { channel }, { timeout: 30_000 });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["notifications", "status"] }),
  });
}
