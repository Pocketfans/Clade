/**
 * useSpeciesQuery - 物种数据查询 Hooks (React Query 版)
 *
 * 示例：如何使用 React Query 替代手写的 useEffect + fetch
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchSpeciesList,
  fetchSpeciesDetail,
  editSpecies,
  generateSpecies,
  generateSpeciesAdvanced,
  type GenerateSpeciesAdvancedParams,
} from "@/services/api";
import { queryKeys } from "@/providers/QueryProvider";

/**
 * 获取物种列表
 */
export function useSpeciesListQuery() {
  return useQuery({
    queryKey: queryKeys.species.list(),
    queryFn: fetchSpeciesList,
    // 物种列表变化较少，可以设置较长的 staleTime
    staleTime: 60_000,
  });
}

/**
 * 获取物种详情
 */
export function useSpeciesDetailQuery(lineageCode: string | null) {
  return useQuery({
    queryKey: queryKeys.species.detail(lineageCode || ""),
    queryFn: () => fetchSpeciesDetail(lineageCode!),
    // 只有在有 lineageCode 时才启用查询
    enabled: !!lineageCode,
    // 详情数据变化较少
    staleTime: 30_000,
  });
}

/**
 * 编辑物种
 */
export function useEditSpeciesMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      lineageCode,
      data,
    }: {
      lineageCode: string;
      data: { description?: string; morphology?: string; traits?: string };
    }) => editSpecies(lineageCode, data),

    onSuccess: (_data, variables) => {
      // 更新成功后，失效相关缓存
      queryClient.invalidateQueries({
        queryKey: queryKeys.species.detail(variables.lineageCode),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.species.list(),
      });
    },
  });
}

/**
 * 生成物种（简单版）
 */
export function useGenerateSpeciesMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ prompt, lineageCode }: { prompt: string; lineageCode?: string }) =>
      generateSpecies(prompt, lineageCode),

    onSuccess: () => {
      // 生成成功后，失效物种列表缓存
      queryClient.invalidateQueries({
        queryKey: queryKeys.species.list(),
      });
      // 同时失效族谱缓存（新物种会影响族谱）
      queryClient.invalidateQueries({
        queryKey: queryKeys.lineage.tree(),
      });
    },
  });
}

/**
 * 生成物种（高级版）
 */
export function useGenerateSpeciesAdvancedMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: GenerateSpeciesAdvancedParams) => generateSpeciesAdvanced(params),

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.species.list(),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.lineage.tree(),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.foodWeb.all,
      });
    },
  });
}




