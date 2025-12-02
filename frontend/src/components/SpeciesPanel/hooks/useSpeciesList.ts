/**
 * useSpeciesList - 物种列表管理 Hook
 */

import { useState, useMemo, useCallback } from "react";
import type { SpeciesSnapshot } from "@/services/api.types";
import type { FilterOptions, SortField, SortOrder, PopulationTrend } from "../types";

interface UseSpeciesListOptions {
  speciesList: SpeciesSnapshot[];
  previousPopulations?: Map<string, number>;
}

interface UseSpeciesListResult {
  // 过滤后的列表
  filteredList: SpeciesSnapshot[];
  
  // 过滤选项
  filters: FilterOptions;
  setSearchQuery: (query: string) => void;
  setRoleFilter: (role: string | null) => void;
  setStatusFilter: (status: FilterOptions["statusFilter"]) => void;
  clearFilters: () => void;
  
  // 排序选项
  sortField: SortField;
  sortOrder: SortOrder;
  setSortField: (field: SortField) => void;
  toggleSortOrder: () => void;
  
  // 统计
  stats: {
    total: number;
    alive: number;
    extinct: number;
    totalPopulation: number;
  };
  
  // 趋势计算
  getPopulationTrend: (species: SpeciesSnapshot) => PopulationTrend;
  getPopulationChange: (species: SpeciesSnapshot) => number;
}

export function useSpeciesList({
  speciesList,
  previousPopulations,
}: UseSpeciesListOptions): UseSpeciesListResult {
  // 过滤状态
  const [filters, setFilters] = useState<FilterOptions>({
    searchQuery: "",
    roleFilter: null,
    statusFilter: "all",
  });
  
  // 排序状态
  const [sortField, setSortField] = useState<SortField>("population");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  // 统计
  const stats = useMemo(() => {
    const alive = speciesList.filter((s) => s.status === "alive");
    return {
      total: speciesList.length,
      alive: alive.length,
      extinct: speciesList.length - alive.length,
      totalPopulation: alive.reduce((sum, s) => sum + (s.population || 0), 0),
    };
  }, [speciesList]);

  // 过滤
  const filteredList = useMemo(() => {
    let result = [...speciesList];

    // 状态过滤
    if (filters.statusFilter !== "all") {
      result = result.filter((s) => s.status === filters.statusFilter);
    }

    // 角色过滤
    if (filters.roleFilter) {
      result = result.filter((s) => s.ecological_role === filters.roleFilter);
    }

    // 搜索过滤
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      result = result.filter(
        (s) =>
          s.common_name?.toLowerCase().includes(query) ||
          s.latin_name?.toLowerCase().includes(query) ||
          s.lineage_code?.toLowerCase().includes(query)
      );
    }

    // 排序
    result.sort((a, b) => {
      let comparison = 0;
      
      switch (sortField) {
        case "name":
          comparison = (a.common_name || "").localeCompare(b.common_name || "");
          break;
        case "population":
          comparison = (a.population || 0) - (b.population || 0);
          break;
        case "role":
          comparison = (a.ecological_role || "").localeCompare(b.ecological_role || "");
          break;
        case "status":
          comparison = (a.status || "").localeCompare(b.status || "");
          break;
      }
      
      return sortOrder === "asc" ? comparison : -comparison;
    });

    return result;
  }, [speciesList, filters, sortField, sortOrder]);

  // 趋势计算
  const getPopulationTrend = useCallback(
    (species: SpeciesSnapshot): PopulationTrend => {
      if (!previousPopulations) return "stable";
      const prev = previousPopulations.get(species.lineage_code);
      if (prev === undefined) return "stable";
      
      const current = species.population || 0;
      const change = current - prev;
      const changeRate = prev > 0 ? Math.abs(change) / prev : 0;
      
      if (changeRate < 0.05) return "stable";
      return change > 0 ? "up" : "down";
    },
    [previousPopulations]
  );

  const getPopulationChange = useCallback(
    (species: SpeciesSnapshot): number => {
      if (!previousPopulations) return 0;
      const prev = previousPopulations.get(species.lineage_code) || 0;
      return (species.population || 0) - prev;
    },
    [previousPopulations]
  );

  // Actions
  const setSearchQuery = useCallback((query: string) => {
    setFilters((prev) => ({ ...prev, searchQuery: query }));
  }, []);

  const setRoleFilter = useCallback((role: string | null) => {
    setFilters((prev) => ({ ...prev, roleFilter: role }));
  }, []);

  const setStatusFilter = useCallback((status: FilterOptions["statusFilter"]) => {
    setFilters((prev) => ({ ...prev, statusFilter: status }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ searchQuery: "", roleFilter: null, statusFilter: "all" });
  }, []);

  const toggleSortOrder = useCallback(() => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  }, []);

  return {
    filteredList,
    filters,
    setSearchQuery,
    setRoleFilter,
    setStatusFilter,
    clearFilters,
    sortField,
    sortOrder,
    setSortField,
    toggleSortOrder,
    stats,
    getPopulationTrend,
    getPopulationChange,
  };
}

