/**
 * GlobalTrendsPanel 类型定义
 * 全球趋势面板 - 展示环境、生物多样性、进化、地质、健康数据
 */

import type { TurnReport, SpeciesSnapshot, BranchingEvent, MigrationEvent, MapChange } from "@/services/api.types";

// ============ 标签页类型 ============
export type Tab = "environment" | "biodiversity" | "evolution" | "geology" | "health";
export type ChartType = "line" | "area" | "bar";
export type TimeRange = "all" | "10" | "20" | "50";
export type TrendDirection = "up" | "down" | "neutral";

// ============ 统计摘要 ============
export interface SummaryStats {
  temp: number;
  seaLevel: number;
  species: number;
  population: number;
  tempDelta: number;
  seaLevelDelta: number;
  speciesDelta: number;
  populationDelta: number;
}

// ============ 环境数据 ============
export interface EnvironmentDataPoint {
  turn: number;
  temperature: number;
  humidity: number;
  sea_level: number;
}

// ============ 物种时间线数据 ============
export interface SpeciesTimelineData {
  turn: number;
  alive: number;
  extinct: number;
  total: number;
  branching: number;
}

// ============ 种群数据 ============
export interface PopulationData {
  turn: number;
  total: number;
  [speciesCode: string]: number;
}

// ============ 生态角色分布 ============
export interface RoleDistribution {
  name: string;
  value: number;
  color: string;
}

// ============ 进化事件 ============
export interface EvolutionEvent {
  turn: number;
  type: "branching" | "extinction" | "migration" | "hybridization";
  description: string;
  species?: string;
}

// ============ 地质事件 ============
export interface GeologyData {
  turn: number;
  events: MapChange[];
  terrain_changes: number;
}

// ============ 健康指标 ============
export interface HealthMetrics {
  turn: number;
  biodiversity_index: number;
  ecosystem_stability: number;
  extinction_rate: number;
  speciation_rate: number;
}

// ============ 组件 Props ============
export interface GlobalTrendsPanelProps {
  reports: TurnReport[];
  onClose: () => void;
}

export interface ChartConfig {
  type: ChartType;
  timeRange: TimeRange;
  showLegend: boolean;
  animate: boolean;
}

// ============ 图表颜色 ============
export const CHART_COLORS = {
  temperature: "#ef4444",
  humidity: "#3b82f6",
  seaLevel: "#06b6d4",
  population: "#22c55e",
  species: "#8b5cf6",
  extinction: "#f97316",
  producer: "#10b981",
  herbivore: "#fbbf24",
  carnivore: "#f43f5e",
  omnivore: "#f97316",
  decomposer: "#a78bfa",
} as const;

// ============ 角色颜色映射 ============
export const ROLE_COLORS: Record<string, string> = {
  producer: "#10b981",
  herbivore: "#fbbf24",
  carnivore: "#f43f5e",
  omnivore: "#f97316",
  decomposer: "#a78bfa",
  scavenger: "#64748b",
  mixotroph: "#22d3ee",
};
