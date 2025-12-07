/**
 * SpeciesPanel 模块导出
 *
 * 重构后的模块化结构：
 * - SpeciesPanel: 新版组件 (~280 行) ← 默认使用
 * - SpeciesPanelLegacy: 原版组件 (已冻结，将移除)
 */

// 主组件 - 新版（默认）
export { SpeciesPanelNew as SpeciesPanel } from "./SpeciesPanelNew";
// 原版组件（冻结，计划移除）
export { SpeciesPanel as SpeciesPanelLegacy } from "../SpeciesPanel";

// 类型
export type {
  SpeciesPanelProps,
  DetailTab,
  SortField,
  SortOrder,
  FilterOptions,
  RoleConfig,
  PopulationTrend,
  EditState,
  TrendInfo,
} from "./types";

// 常量
export { ROLE_CONFIGS, getRoleConfig, STATUS_COLORS, TREND_COLORS, DETAIL_TABS } from "./constants";

// 工具函数
export { formatPopulation, formatNumber, getTrend, calculateChangePercent, formatChangePercent } from "./utils";

// Hooks
export { useSpeciesList } from "./hooks/useSpeciesList";
export { useSpeciesDetail } from "./hooks/useSpeciesDetail";
export { useSpeciesFilter } from "./hooks/useSpeciesFilter";

// 子组件
export { SpeciesListItem } from "./components/SpeciesListItem";
export { SpeciesListHeader } from "./components/SpeciesListHeader";
