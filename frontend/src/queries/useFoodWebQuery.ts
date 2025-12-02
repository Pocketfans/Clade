/**
 * useFoodWebQuery - 食物网数据查询 Hooks (React Query 版)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchFoodWeb, fetchFoodWebAnalysis, repairFoodWeb } from "@/services/api";
import { queryKeys } from "@/providers/QueryProvider";

/**
 * 获取食物网数据
 */
export function useFoodWebQuery() {
  return useQuery({
    queryKey: queryKeys.foodWeb.data(),
    queryFn: fetchFoodWeb,
    staleTime: 60_000,
  });
}

/**
 * 获取食物网分析
 */
export function useFoodWebAnalysisQuery() {
  return useQuery({
    queryKey: queryKeys.foodWeb.analysis(),
    queryFn: fetchFoodWebAnalysis,
    staleTime: 60_000,
  });
}

/**
 * 获取食物网数据和分析（并行）
 */
export function useFoodWebDataWithAnalysis() {
  const foodWebQuery = useFoodWebQuery();
  const analysisQuery = useFoodWebAnalysisQuery();

  return {
    foodWebData: foodWebQuery.data ?? null,
    analysis: analysisQuery.data ?? null,
    loading: foodWebQuery.isLoading || analysisQuery.isLoading,
    error: foodWebQuery.error?.message || analysisQuery.error?.message || null,
    refetch: () => {
      foodWebQuery.refetch();
      analysisQuery.refetch();
    },
  };
}

/**
 * 修复食物网
 */
export function useRepairFoodWebMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: repairFoodWeb,
    onSuccess: () => {
      // 修复成功后，失效食物网相关缓存
      queryClient.invalidateQueries({
        queryKey: queryKeys.foodWeb.all,
      });
    },
  });
}

