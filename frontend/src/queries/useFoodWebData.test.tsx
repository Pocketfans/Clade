/**
 * useFoodWebData Hook 测试 (React Query 版)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useFoodWebData } from "@/components/FoodWebGraph/hooks/useFoodWebData";
import type { SpeciesSnapshot } from "@/services/api.types";

// Mock API 模块
vi.mock("@/services/api", () => ({
  fetchFoodWeb: vi.fn(),
  fetchFoodWebAnalysis: vi.fn(),
  repairFoodWeb: vi.fn(),
}));

import { fetchFoodWeb, fetchFoodWebAnalysis, repairFoodWeb } from "@/services/api";

// 创建测试用的 QueryClient wrapper
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  // eslint-disable-next-line react/display-name
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockFoodWebData = {
  species: [
    {
      lineage_code: "A",
      common_name: "Producer A",
      trophic_level: 1,
      diet_type: "producer",
      prey_count: 0,
      predator_count: 1,
      is_keystone: false,
    },
    {
      lineage_code: "B",
      common_name: "Herbivore B",
      trophic_level: 2,
      diet_type: "herbivore",
      prey_count: 1,
      predator_count: 0,
      is_keystone: true,
    },
  ],
  relationships: [{ predator: "B", prey: "A", strength: 0.8 }],
  keystone_species: ["B"],
};

const mockAnalysis = {
  health_score: 0.75,
  issues: ["Some issue"],
  recommendations: ["Some recommendation"],
};

const mockSpeciesList: SpeciesSnapshot[] = [
  { lineage_code: "A", population: 1000, status: "alive" } as SpeciesSnapshot,
  { lineage_code: "B", population: 500, status: "alive" } as SpeciesSnapshot,
];

describe("useFoodWebData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (fetchFoodWeb as ReturnType<typeof vi.fn>).mockResolvedValue(mockFoodWebData);
    (fetchFoodWebAnalysis as ReturnType<typeof vi.fn>).mockResolvedValue(mockAnalysis);
  });

  it("初始化时应加载数据", async () => {
    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    // 初始状态是 loading
    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFoodWeb).toHaveBeenCalled();
    expect(fetchFoodWebAnalysis).toHaveBeenCalled();
  });

  it("应正确构建图数据", async () => {
    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const { graphData } = result.current;
    expect(graphData.nodes.length).toBe(2);
    expect(graphData.links.length).toBe(1);

    // 检查节点属性
    const nodeA = graphData.nodes.find((n) => n.id === "A");
    expect(nodeA?.trophicLevel).toBe(1);
    expect(nodeA?.population).toBe(1000);

    const nodeB = graphData.nodes.find((n) => n.id === "B");
    expect(nodeB?.isKeystone).toBe(true);
  });

  it("过滤模式应正确筛选节点", async () => {
    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // 筛选生产者
    act(() => {
      result.current.setFilterMode("producers");
    });

    expect(result.current.graphData.nodes.length).toBe(1);
    expect(result.current.graphData.nodes[0].id).toBe("A");

    // 筛选关键物种
    act(() => {
      result.current.setFilterMode("keystone");
    });

    expect(result.current.graphData.nodes.length).toBe(1);
    expect(result.current.graphData.nodes[0].id).toBe("B");
  });

  it("搜索应筛选匹配的节点", async () => {
    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.setSearchQuery("Herbivore");
    });

    expect(result.current.graphData.nodes.length).toBe(1);
    expect(result.current.graphData.nodes[0].name).toBe("Herbivore B");
  });

  it("加载失败时应设置错误状态", async () => {
    (fetchFoodWeb as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Network error");
  });

  it("修复功能应调用 API 并刷新数据", async () => {
    (repairFoodWeb as ReturnType<typeof vi.fn>).mockResolvedValue({ repaired_count: 2 });

    const { result } = renderHook(() => useFoodWebData({ speciesList: mockSpeciesList }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.repair();
    });

    expect(repairFoodWeb).toHaveBeenCalled();
  });
});
