/**
 * GlobalTrendsPanel 模块导出
 */

// 主组件 - 使用重构版本
export { GlobalTrendsPanel } from "./GlobalTrendsPanelNew";

// 类型
export type {
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
  GlobalTrendsPanelProps,
  ChartConfig,
} from "./types";

export { CHART_COLORS, ROLE_COLORS } from "./types";

// Hooks
export { useTrendsData } from "./hooks/useTrendsData";
