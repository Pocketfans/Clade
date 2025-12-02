/**
 * useFoodWebData - 食物网数据管理 Hook (React Query 版)
 *
 * 使用 React Query 进行数据获取和缓存管理
 */

import { useState, useMemo } from "react";
import { useFoodWebQuery, useFoodWebAnalysisQuery, useRepairFoodWebMutation } from "@/queries/useFoodWebQuery";
import type { SpeciesSnapshot } from "@/services/api.types";
import type { GraphNode, GraphLink, GraphData, FilterMode } from "../types";
import { TROPHIC_COLORS, KEYSTONE_COLOR } from "../types";

interface UseFoodWebDataOptions {
  speciesList: SpeciesSnapshot[];
}

interface UseFoodWebDataResult {
  // 数据
  foodWebData: ReturnType<typeof useFoodWebQuery>["data"] | null;
  analysis: ReturnType<typeof useFoodWebAnalysisQuery>["data"] | null;
  graphData: GraphData;

  // 状态
  loading: boolean;
  error: string | null;
  repairing: boolean;

  // 过滤
  filterMode: FilterMode;
  setFilterMode: (mode: FilterMode) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;

  // 操作
  refresh: () => Promise<void>;
  repair: () => Promise<void>;
}

export function useFoodWebData({ speciesList }: UseFoodWebDataOptions): UseFoodWebDataResult {
  // React Query hooks
  const foodWebQuery = useFoodWebQuery();
  const analysisQuery = useFoodWebAnalysisQuery();
  const repairMutation = useRepairFoodWebMutation();

  // 本地过滤状态
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // 构建图数据
  const graphData = useMemo((): GraphData => {
    const foodWebData = foodWebQuery.data;
    if (!foodWebData) return { nodes: [], links: [] };

    const speciesMap = new Map(speciesList.map((s) => [s.lineage_code, s]));

    // 构建节点
    const nodes: GraphNode[] = foodWebData.species.map((s) => {
      const snapshot = speciesMap.get(s.lineage_code);
      const trophicLevel = Math.min(4, Math.max(1, Math.ceil(s.trophic_level || 1)));
      const isKeystone = s.is_keystone || false;

      return {
        id: s.lineage_code,
        name: s.common_name || s.lineage_code,
        val: Math.sqrt(snapshot?.population || 100),
        color: isKeystone ? KEYSTONE_COLOR.main : (TROPHIC_COLORS[trophicLevel]?.main || "#888"),
        group: trophicLevel,
        trophicLevel,
        dietType: s.diet_type || "unknown",
        preyCount: s.prey_count || 0,
        predatorCount: s.predator_count || 0,
        isKeystone,
        population: snapshot?.population || 0,
      };
    });

    // 构建连接
    const links: GraphLink[] = foodWebData.relationships.map((r) => ({
      source: r.predator,
      target: r.prey,
      value: r.strength || 1,
      predatorName: nodes.find((n) => n.id === r.predator)?.name || r.predator,
      preyName: nodes.find((n) => n.id === r.prey)?.name || r.prey,
    }));

    // 应用过滤
    let filteredNodes = nodes;

    if (filterMode === "producers") {
      filteredNodes = nodes.filter((n) => n.trophicLevel === 1);
    } else if (filterMode === "consumers") {
      filteredNodes = nodes.filter((n) => n.trophicLevel > 1);
    } else if (filterMode === "keystone") {
      filteredNodes = nodes.filter((n) => n.isKeystone);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filteredNodes = filteredNodes.filter(
        (n) => n.name.toLowerCase().includes(query) || n.id.toLowerCase().includes(query)
      );
    }

    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredLinks = links.filter(
      (l) => nodeIds.has(l.source as string) && nodeIds.has(l.target as string)
    );

    return { nodes: filteredNodes, links: filteredLinks };
  }, [foodWebQuery.data, speciesList, filterMode, searchQuery]);

  // 刷新数据
  const refresh = async () => {
    await Promise.all([foodWebQuery.refetch(), analysisQuery.refetch()]);
  };

  // 修复食物网
  const repair = async () => {
    await repairMutation.mutateAsync();
  };

  return {
    foodWebData: foodWebQuery.data ?? null,
    analysis: analysisQuery.data ?? null,
    graphData,
    loading: foodWebQuery.isLoading || analysisQuery.isLoading,
    error: foodWebQuery.error?.message || analysisQuery.error?.message || null,
    repairing: repairMutation.isPending,
    filterMode,
    setFilterMode,
    searchQuery,
    setSearchQuery,
    refresh,
    repair,
  };
}
