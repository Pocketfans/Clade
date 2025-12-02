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
    if (!foodWebData || !foodWebData.nodes) return { nodes: [], links: [] };

    const speciesMap = new Map(speciesList.map((s) => [s.lineage_code, s]));
    const keystoneSet = new Set(foodWebData.keystone_species || []);

    // 构建节点 - 使用正确的字段名 nodes
    const nodes: GraphNode[] = foodWebData.nodes.map((s) => {
      const snapshot = speciesMap.get(s.id);
      const trophicLevel = Math.min(4, Math.max(1, Math.ceil(s.trophic_level || 1)));
      const isKeystone = keystoneSet.has(s.id);

      return {
        id: s.id,
        name: s.name || s.id,
        val: Math.sqrt(snapshot?.population || s.population || 100),
        color: isKeystone ? KEYSTONE_COLOR.main : (TROPHIC_COLORS[trophicLevel]?.main || "#888"),
        group: trophicLevel,
        trophicLevel,
        dietType: s.diet_type || "unknown",
        preyCount: s.prey_count || 0,
        predatorCount: s.predator_count || 0,
        isKeystone,
        population: snapshot?.population || s.population || 0,
      };
    });

    // 构建连接 - 使用正确的字段名 links
    const links: GraphLink[] = (foodWebData.links || []).map((r) => ({
      source: r.source,
      target: r.target,
      value: r.value || 1,
      predatorName: r.predator_name || nodes.find((n) => n.id === r.target)?.name || r.target,
      preyName: r.prey_name || nodes.find((n) => n.id === r.source)?.name || r.source,
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
