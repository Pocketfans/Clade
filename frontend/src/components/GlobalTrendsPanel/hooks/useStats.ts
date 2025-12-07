/**
 * useStats - 统计数据计算 Hook
 */

import { useMemo } from "react";
import type { TurnReport } from "@/services/api.types";
import type { SummaryStats, TimeRange } from "../types";

// 图表数据类型（本地定义）
interface EnvironmentChartData {
  turn: number;
  temperature: number;
  seaLevel: number;
}

interface BiodiversityChartData {
  turn: number;
  speciesCount: number;
  totalPopulation: number;
  extinctions: number;
  branches: number;
}

/**
 * 根据时间范围筛选报告
 */
export function filterReportsByRange(reports: TurnReport[], range: TimeRange): TurnReport[] {
  if (range === "all" || reports.length === 0) return reports;

  const limit = parseInt(range);
  return reports.slice(-limit);
}

/**
 * 计算汇总统计数据
 */
export function useSummaryStats(reports: TurnReport[], range: TimeRange): SummaryStats {
  return useMemo(() => {
    const filtered = filterReportsByRange(reports, range);

    if (filtered.length === 0) {
      return {
        temp: 0,
        seaLevel: 0,
        species: 0,
        population: 0,
        tempDelta: 0,
        seaLevelDelta: 0,
        speciesDelta: 0,
        populationDelta: 0,
        turnSpan: 0,
        latestTurn: 0,
        baselineTurn: 0,
        extinctions: 0,
        branchingCount: 0,
        migrationCount: 0,
        avgDeathRate: 0,
        totalDeaths: 0,
        mapChanges: 0,
        tectonicStage: "unknown",
      };
    }

    const first = filtered[0];
    const last = filtered[filtered.length - 1];

    // 计算物种相关数据
    const lastAlive = last.species.filter((s) => s.status === "alive");
    const firstAlive = first.species.filter((s) => s.status === "alive");

    // 累计事件统计
    let extinctions = 0;
    let branchingCount = 0;
    let migrationCount = 0;
    let totalDeaths = 0;
    let totalDeathRateSum = 0;
    let mapChanges = 0;

    for (const r of filtered) {
      extinctions += r.extinction_count ?? 0;
      branchingCount += r.branching_events?.length ?? 0;
      migrationCount += r.migration_events?.length ?? 0;
      mapChanges += r.map_changes?.length ?? 0;

      for (const s of r.species) {
        totalDeaths += s.deaths ?? 0;
        totalDeathRateSum += s.death_rate ?? 0;
      }
    }

    const totalSpeciesReports = filtered.reduce((sum, r) => sum + r.species.length, 0);
    const avgDeathRate = totalSpeciesReports > 0 ? totalDeathRateSum / totalSpeciesReports : 0;

    // 总种群
    const lastPopulation = lastAlive.reduce((sum, s) => sum + s.population, 0);
    const firstPopulation = firstAlive.reduce((sum, s) => sum + s.population, 0);

    return {
      temp: last.global_temperature ?? 0,
      seaLevel: last.sea_level ?? 0,
      species: lastAlive.length,
      population: lastPopulation,
      tempDelta: (last.global_temperature ?? 0) - (first.global_temperature ?? 0),
      seaLevelDelta: (last.sea_level ?? 0) - (first.sea_level ?? 0),
      speciesDelta: lastAlive.length - firstAlive.length,
      populationDelta: lastPopulation - firstPopulation,
      turnSpan: filtered.length,
      latestTurn: last.turn_index,
      baselineTurn: first.turn_index,
      extinctions,
      branchingCount,
      migrationCount,
      avgDeathRate,
      totalDeaths,
      mapChanges,
      tectonicStage: last.tectonic_stage ?? "unknown",
    };
  }, [reports, range]);
}

/**
 * 环境数据图表数据
 */
export function useEnvironmentChartData(reports: TurnReport[], range: TimeRange): EnvironmentChartData[] {
  return useMemo(() => {
    const filtered = filterReportsByRange(reports, range);
    return filtered.map((r) => ({
      turn: r.turn_index,
      temperature: r.global_temperature ?? 0,
      seaLevel: r.sea_level ?? 0,
    }));
  }, [reports, range]);
}

/**
 * 生物多样性图表数据
 */
export function useBiodiversityChartData(reports: TurnReport[], range: TimeRange): BiodiversityChartData[] {
  return useMemo(() => {
    const filtered = filterReportsByRange(reports, range);
    return filtered.map((r) => {
      const alive = r.species.filter((s) => s.status === "alive");
      return {
        turn: r.turn_index,
        speciesCount: alive.length,
        totalPopulation: alive.reduce((sum, s) => sum + s.population, 0),
        extinctions: r.extinction_count ?? 0,
        branches: r.branching_events?.length ?? 0,
      };
    });
  }, [reports, range]);
}

/**
 * 计算趋势方向
 */
export function getTrendDirection(delta: number, threshold = 0): "up" | "down" | "neutral" {
  if (delta > threshold) return "up";
  if (delta < -threshold) return "down";
  return "neutral";
}

/**
 * 格式化数字
 */
export function formatNumber(n: number, decimals = 1): string {
  if (Math.abs(n) >= 1_000_000) {
    return `${(n / 1_000_000).toFixed(decimals)}M`;
  }
  if (Math.abs(n) >= 1_000) {
    return `${(n / 1_000).toFixed(decimals)}K`;
  }
  return n.toFixed(decimals);
}

/**
 * 格式化增量文本
 */
export function formatDelta(delta: number, unit = ""): string {
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${formatNumber(delta)}${unit}`;
}

