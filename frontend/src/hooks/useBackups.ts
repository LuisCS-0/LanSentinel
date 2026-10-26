// Copias de seguridad: estado, lista y copia manual.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { BackupFile, BackupStatus } from "@/lib/types";

const KEY = ["system", "backups"];

export const backupDownloadUrl = (name: string) => `/api/v1/system/backups/${encodeURIComponent(name)}`;

export function useBackups() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<BackupStatus>("/system/backups");
      return data;
    },
    refetchInterval: 60_000,
  });
}

export function useCreateBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      // Volcar la base de datos y comprimir puede tardar
      const { data } = await apiClient.post<BackupFile>("/system/backups", null, { timeout: 300_000 });
      return data;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
