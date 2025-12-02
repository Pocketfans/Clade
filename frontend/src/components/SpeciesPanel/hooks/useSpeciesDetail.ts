/**
 * useSpeciesDetail - 物种详情加载 Hook (React Query 版)
 */

import { useQuery } from "@tanstack/react-query";
import type { SpeciesDetail } from "@/services/api.types";
import { fetchSpeciesDetail } from "@/services/api";
import { queryKeys } from "@/providers/QueryProvider";

interface UseSpeciesDetailOptions {
  speciesId: string | null;
  refreshTrigger?: number;
}

interface UseSpeciesDetailResult {
  detail: SpeciesDetail | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSpeciesDetail({
  speciesId,
  // refreshTrigger 保留接口兼容性，但 React Query 使用 queryKey 自动管理
}: UseSpeciesDetailOptions): UseSpeciesDetailResult {
  const query = useQuery({
    queryKey: queryKeys.species.detail(speciesId || ""),
    queryFn: () => fetchSpeciesDetail(speciesId!),
    enabled: !!speciesId,
    staleTime: 30_000,
  });

  return {
    detail: query.data ?? null,
    loading: query.isLoading,
    error: query.error?.message ?? null,
    refresh: () => query.refetch(),
  };
}
