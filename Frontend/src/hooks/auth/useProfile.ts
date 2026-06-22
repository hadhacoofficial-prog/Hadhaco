import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { useAuthContext } from "@/providers/auth-context";
import type { AppRole } from "@/types/auth";
import type { ProfileDto } from "@/types/profile";

/**
 * Fetches the authenticated user's backend profile (GET /me).
 * Side-effect: sets the authoritative role in AuthContext once the profile loads.
 */
export function useProfile() {
  const { isAuthenticated, setRole } = useAuthContext();

  const query = useQuery({
    queryKey: queryKeys.profile.me,
    queryFn: () => api.get<ProfileDto>("/me"),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });

  const role = query.data?.role;

  useEffect(() => {
    if (role === "customer" || role === "admin" || role === "super_admin") {
      setRole(role as AppRole);
    }
  }, [role, setRole]);

  return query;
}
