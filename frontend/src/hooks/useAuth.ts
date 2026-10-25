// Hooks de sesión. El token viaja en una cookie httpOnly que gestiona el
// navegador: el frontend nunca lo ve, solo pregunta a /auth/me quién es.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { apiClient } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";

export const ME_QUERY_KEY = ["auth", "me"];

// Usuario de la sesión actual, o null si no hay sesión
export function useCurrentUser() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<CurrentUser | null> => {
      try {
        const { data } = await apiClient.get<CurrentUser>("/auth/me");
        return data;
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 401) return null;
        throw err;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ username, password }: { username: string; password: string }) => {
      await apiClient.post("/auth/login", { username, password });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.post("/auth/logout");
    },
    onSettled: () => {
      // Volver al login y no dejar en caché datos de la sesión cerrada
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.removeQueries({ predicate: q => q.queryKey[0] !== "auth" });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (payload: { current_password: string; new_password: string }) => {
      await apiClient.post("/auth/password", payload);
    },
  });
}
