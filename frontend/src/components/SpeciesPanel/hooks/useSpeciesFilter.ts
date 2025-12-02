/**
 * useSpeciesFilter - 物种列表过滤与排序 Hook
 */

import { useState, useMemo, useCallback } from "react";
import type { SpeciesSnapshot } from "@/services/api.types";
import type { FilterOptions, TrendInfo } from "../types";
import { getTrend } from "../utils";

interface UseSpeciesFilterOptions {
  speciesList: SpeciesSnapshot[];
  previousPopulations: Map<string, number>;
}

interface UseSpeciesFilterResult {
  filteredList: SpeciesSnapshot[];
  filters: FilterOptions;
  setSearchQuery: (query: string) => void;
  setRoleFilter: (role: string | null) => void;
  setStatusFilter: (status: string | null) => void;
  setSortBy: (sortBy: FilterOptions["sortBy"]) => void;
  toggleSortOrder: () => void;
  resetFilters: () => void;
  getTrendForSpecies: (species: SpeciesSnapshot) => TrendInfo;
}

const defaultFilters: FilterOptions = {
  searchQuery: "",
  roleFilter: null,
  statusFilter: null,
  sortBy: "population",
  sortOrder: "desc",
};

export function useSpeciesFilter({
  speciesList,
  previousPopulations,
}: UseSpeciesFilterOptions): UseSpeciesFilterResult {
  const [filters, setFilters] = useState<FilterOptions>(defaultFilters);

  const getTrendForSpecies = useCallback(
    (species: SpeciesSnapshot): TrendInfo => {
      const prevPop = previousPopulations.get(species.lineage_code);
      return getTrend(species.population, prevPop, species.status);
    },
    [previousPopulations]
  );

  const filteredList = useMemo(() => {
    let result = [...speciesList];

    // 搜索过滤
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      result = result.filter(
        (s) =>
          s.common_name.toLowerCase().includes(query) ||
          s.latin_name.toLowerCase().includes(query) ||
          s.lineage_code.toLowerCase().includes(query)
      );
    }

    // 角色过滤
    if (filters.roleFilter) {
      result = result.filter((s) => s.ecological_role === filters.roleFilter);
    }

    // 状态过滤
    if (filters.statusFilter) {
      result = result.filter((s) => s.status === filters.statusFilter);
    }

    // 排序
    result.sort((a, b) => {
      let comparison = 0;

      switch (filters.sortBy) {
        case "population":
          comparison = a.population - b.population;
          break;
        case "name":
          comparison = a.common_name.localeCompare(b.common_name);
          break;
        case "trend": {
          const trendA = getTrendForSpecies(a);
          const trendB = getTrendForSpecies(b);
          // 按趋势排序：繁荣 > 增长 > 稳定 > 下降 > 衰退 > 危急 > 灭绝
          const trendOrder = ["繁荣", "增长", "稳定", "下降", "衰退", "危急", "灭绝"];
          comparison = trendOrder.indexOf(trendA.label) - trendOrder.indexOf(trendB.label);
          break;
        }
      }

      return filters.sortOrder === "desc" ? -comparison : comparison;
    });

    return result;
  }, [speciesList, filters, getTrendForSpecies]);

  const setSearchQuery = useCallback((query: string) => {
    setFilters((prev) => ({ ...prev, searchQuery: query }));
  }, []);

  const setRoleFilter = useCallback((role: string | null) => {
    setFilters((prev) => ({ ...prev, roleFilter: role }));
  }, []);

  const setStatusFilter = useCallback((status: string | null) => {
    setFilters((prev) => ({ ...prev, statusFilter: status }));
  }, []);

  const setSortBy = useCallback((sortBy: FilterOptions["sortBy"]) => {
    setFilters((prev) => ({ ...prev, sortBy }));
  }, []);

  const toggleSortOrder = useCallback(() => {
    setFilters((prev) => ({
      ...prev,
      sortOrder: prev.sortOrder === "asc" ? "desc" : "asc",
    }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(defaultFilters);
  }, []);

  return {
    filteredList,
    filters,
    setSearchQuery,
    setRoleFilter,
    setStatusFilter,
    setSortBy,
    toggleSortOrder,
    resetFilters,
    getTrendForSpecies,
  };
}

