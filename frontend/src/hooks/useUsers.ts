// Usuarios del panel y registro de acciones (solo administradores).

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { AuditEntry, UserAccount, UserRole } from "@/lib/types";

const USERS_KEY = ["users"];
const AUDIT_PAGE = 30;

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: USERS_KEY,
    queryFn: async () => (await apiClient.get<UserAccount[]>("/users")).data,
    enabled,
  });
}

function useUserMutation<T>(fn: (payload: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USERS_KEY });
      queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useCreateUser() {
  return useUserMutation((payload: { username: string; password: string; role: UserRole }) =>
    apiClient.post("/users", payload));
}

export function useUpdateUser() {
  return useUserMutation(({ id, ...changes }: { id: number; role?: UserRole; is_active?: boolean }) =>
    apiClient.patch(`/users/${id}`, changes));
}

export function useSetUserPassword() {
  return useUserMutation(({ id, new_password }: { id: number; new_password: string }) =>
    apiClient.post(`/users/${id}/password`, { new_password }));
}

export function useDeleteUser() {
  return useUserMutation((id: number) => apiClient.delete(`/users/${id}`));
}

// Registro de acciones por páginas: cada una pide las anteriores al último id recibido
export function useAuditLog(onlyFailed: boolean, enabled = true) {
  return useInfiniteQuery({
    queryKey: ["audit", onlyFailed],
    queryFn: async ({ pageParam }) => {
      const { data } = await apiClient.get<AuditEntry[]>("/audit", {
        params: { limit: AUDIT_PAGE, only_failed: onlyFailed, before_id: pageParam ?? undefined },
      });
      return data;
    },
    initialPageParam: null as number | null,
    getNextPageParam: last => (last.length === AUDIT_PAGE ? last[last.length - 1].id : undefined),
    enabled,
    refetchInterval: 30_000,
  });
}
