/**
 * QueryProvider - React Query 配置
 *
 * 提供统一的数据获取、缓存和状态管理
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// 创建 QueryClient 实例
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 数据在 30 秒内被认为是新鲜的
      staleTime: 30_000,
      // 组件卸载后缓存保留 5 分钟
      gcTime: 5 * 60 * 1000,
      // 失败后重试 1 次
      retry: 1,
      // 重试延迟
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
      // 窗口重新获得焦点时不自动刷新（游戏场景可能不需要）
      refetchOnWindowFocus: false,
    },
    mutations: {
      // 突变失败后不自动重试
      retry: false,
    },
  },
});

interface QueryProviderProps {
  children: ReactNode;
}

export function QueryProvider({ children }: QueryProviderProps) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

// 导出 queryClient 供高级用法（如手动失效缓存）
export { queryClient };

// 常用的 Query Keys
export const queryKeys = {
  // 物种相关
  species: {
    all: ["species"] as const,
    list: () => [...queryKeys.species.all, "list"] as const,
    detail: (id: string) => [...queryKeys.species.all, "detail", id] as const,
  },

  // 地图相关
  map: {
    all: ["map"] as const,
    overview: (viewMode: string) => [...queryKeys.map.all, "overview", viewMode] as const,
    heightMap: () => [...queryKeys.map.all, "height"] as const,
  },

  // 族谱相关
  lineage: {
    all: ["lineage"] as const,
    tree: () => [...queryKeys.lineage.all, "tree"] as const,
  },

  // 食物网相关
  foodWeb: {
    all: ["foodWeb"] as const,
    data: () => [...queryKeys.foodWeb.all, "data"] as const,
    analysis: () => [...queryKeys.foodWeb.all, "analysis"] as const,
  },

  // 配置相关
  config: {
    all: ["config"] as const,
    ui: () => [...queryKeys.config.all, "ui"] as const,
    pressureTemplates: () => [...queryKeys.config.all, "pressureTemplates"] as const,
  },

  // 队列状态
  queue: {
    all: ["queue"] as const,
    status: () => [...queryKeys.queue.all, "status"] as const,
  },

  // 存档相关
  saves: {
    all: ["saves"] as const,
    list: () => [...queryKeys.saves.all, "list"] as const,
  },

  // 历史记录
  history: {
    all: ["history"] as const,
    reports: (limit?: number) => [...queryKeys.history.all, "reports", limit] as const,
  },
} as const;












