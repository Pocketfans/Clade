/**
 * useTrendsData - 趋势数据处理 Hook
 */

import { useMemo, useState, useCallback } from "react";
import type {
  Tab,
  ChartType,
  TimeRange,
  TrendDirection,
  SummaryStats,
  EnvironmentDataPoint,
  SpeciesTimelineData,
  PopulationData,
  RoleDistribution,
  HealthMetrics,
  ChartConfig,
} from "../types";
import { ROLE_COLORS } from "../types";
import type { TurnReport, SpeciesSnapshot } from "@/services/api.types";

interface UseTrendsDataOptions {
  reports: TurnReport[];
}

interface UseTrendsDataResult {
  // 当前设置
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  chartType: ChartType;
  setChartType: (type: ChartType) => void;
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;

  // 筛选后的报告
  filteredReports: TurnReport[];

  // 统计摘要
  summaryStats: SummaryStats;

  // 环境数据
  environmentData: EnvironmentDataPoint[];

  // 物种时间线
  speciesTimeline: SpeciesTimelineData[];

  // 种群数据
  populationData: PopulationData[];

  // 角色分布
  roleDistribution: RoleDistribution[];

  // 健康指标
  healthMetrics: HealthMetrics[];

  // 趋势方向
  getTrendDirection: (current: number, previous: number) => TrendDirection;

  // 导出
  exportData: () => void;
}

export function useTrendsData({ reports }: UseTrendsDataOptions): UseTrendsDataResult {
  const [activeTab, setActiveTab] = useState<Tab>("environment");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [timeRange, setTimeRange] = useState<TimeRange>("all");

  // 根据时间范围筛选报告
  const filteredReports = useMemo(() => {
    if (!reports.length) return [];
    if (timeRange === "all") return reports;

    const range = parseInt(timeRange, 10);
    return reports.slice(-range);
  }, [reports, timeRange]);

  // 统计摘要
  const summaryStats = useMemo((): SummaryStats => {
    if (filteredReports.length === 0) {
      return {
        temp: 0,
        seaLevel: 0,
        species: 0,
        population: 0,
        tempDelta: 0,
        seaLevelDelta: 0,
        speciesDelta: 0,
        populationDelta: 0,
      };
    }

    const latest = filteredReports[filteredReports.length - 1];
    const previous = filteredReports.length > 1 ? filteredReports[filteredReports.length - 2] : null;

    const currentTemp = latest.global_temperature ?? 0;
    const currentSeaLevel = latest.sea_level ?? 0;
    const currentSpecies = latest.species?.filter((s) => s.status === "alive").length ?? 0;
    const currentPopulation = latest.species?.reduce((sum, s) => sum + (s.population ?? 0), 0) ?? 0;

    const prevTemp = previous?.global_temperature ?? currentTemp;
    const prevSeaLevel = previous?.sea_level ?? currentSeaLevel;
    const prevSpecies = previous?.species?.filter((s) => s.status === "alive").length ?? currentSpecies;
    const prevPopulation = previous?.species?.reduce((sum, s) => sum + (s.population ?? 0), 0) ?? currentPopulation;

    return {
      temp: currentTemp,
      seaLevel: currentSeaLevel,
      species: currentSpecies,
      population: currentPopulation,
      tempDelta: currentTemp - prevTemp,
      seaLevelDelta: currentSeaLevel - prevSeaLevel,
      speciesDelta: currentSpecies - prevSpecies,
      populationDelta: currentPopulation - prevPopulation,
    };
  }, [filteredReports]);

  // 环境数据
  const environmentData = useMemo((): EnvironmentDataPoint[] => {
    return filteredReports.map((r) => ({
      turn: r.turn_index,
      temperature: r.global_temperature ?? 0,
      humidity: r.global_humidity ?? 0,
      sea_level: r.sea_level ?? 0,
    }));
  }, [filteredReports]);

  // 物种时间线
  const speciesTimeline = useMemo((): SpeciesTimelineData[] => {
    return filteredReports.map((r) => {
      const alive = r.species?.filter((s) => s.status === "alive").length ?? 0;
      const extinct = r.species?.filter((s) => s.status === "extinct").length ?? 0;
      const branching = r.branching_events?.length ?? 0;

      return {
        turn: r.turn_index,
        alive,
        extinct,
        total: alive + extinct,
        branching,
      };
    });
  }, [filteredReports]);

  // 种群数据（只显示前10个物种）
  const populationData = useMemo((): PopulationData[] => {
    if (filteredReports.length === 0) return [];

    // 获取最新报告中人口最多的10个物种
    const latest = filteredReports[filteredReports.length - 1];
    const topSpecies = [...(latest.species || [])]
      .filter((s) => s.status === "alive")
      .sort((a, b) => (b.population ?? 0) - (a.population ?? 0))
      .slice(0, 10)
      .map((s) => s.lineage_code);

    return filteredReports.map((r) => {
      const point: PopulationData = { turn: r.turn_index, total: 0 };
      
      for (const code of topSpecies) {
        const species = r.species?.find((s) => s.lineage_code === code);
        point[code] = species?.population ?? 0;
        point.total += species?.population ?? 0;
      }
      
      return point;
    });
  }, [filteredReports]);

  // 角色分布
  const roleDistribution = useMemo((): RoleDistribution[] => {
    if (filteredReports.length === 0) return [];

    const latest = filteredReports[filteredReports.length - 1];
    const roleCounts: Record<string, number> = {};

    for (const species of latest.species || []) {
      if (species.status !== "alive") continue;
      const role = species.ecological_role || "unknown";
      roleCounts[role] = (roleCounts[role] || 0) + 1;
    }

    return Object.entries(roleCounts).map(([name, value]) => ({
      name,
      value,
      color: ROLE_COLORS[name] || "#888888",
    }));
  }, [filteredReports]);

  // 健康指标
  const healthMetrics = useMemo((): HealthMetrics[] => {
    return filteredReports.map((r, idx) => {
      const aliveSpecies = r.species?.filter((s) => s.status === "alive").length ?? 0;
      const totalSpecies = r.species?.length ?? 0;
      const extinctions = idx > 0 
        ? (filteredReports[idx - 1].species?.filter((s) => s.status === "alive").length ?? 0) - aliveSpecies
        : 0;
      const speciations = r.branching_events?.length ?? 0;

      return {
        turn: r.turn_index,
        biodiversity_index: Math.min(1, aliveSpecies / 50), // 归一化
        ecosystem_stability: totalSpecies > 0 ? aliveSpecies / totalSpecies : 1,
        extinction_rate: aliveSpecies > 0 ? Math.max(0, extinctions) / aliveSpecies : 0,
        speciation_rate: aliveSpecies > 0 ? speciations / aliveSpecies : 0,
      };
    });
  }, [filteredReports]);

  // 趋势方向判断
  const getTrendDirection = useCallback((current: number, previous: number): TrendDirection => {
    const diff = current - previous;
    if (Math.abs(diff) < 0.001) return "neutral";
    return diff > 0 ? "up" : "down";
  }, []);

  // 导出数据
  const exportData = useCallback(() => {
    const data = {
      exportedAt: new Date().toISOString(),
      timeRange,
      summary: summaryStats,
      environment: environmentData,
      speciesTimeline,
      roleDistribution,
      healthMetrics,
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trends_export_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [timeRange, summaryStats, environmentData, speciesTimeline, roleDistribution, healthMetrics]);

  return {
    activeTab,
    setActiveTab,
    chartType,
    setChartType,
    timeRange,
    setTimeRange,
    filteredReports,
    summaryStats,
    environmentData,
    speciesTimeline,
    populationData,
    roleDistribution,
    healthMetrics,
    getTrendDirection,
    exportData,
  };
}

