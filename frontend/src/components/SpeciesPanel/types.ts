/**
 * SpeciesPanel 类型定义
 */

import type { SpeciesDetail, SpeciesSnapshot } from "@/services/api.types";

// ============ 组件 Props ============
export interface SpeciesPanelProps {
  speciesList: SpeciesSnapshot[];
  selectedSpeciesId: string | null;
  onSelectSpecies: (id: string | null) => void;
  onCollapse?: () => void;
  refreshTrigger?: number;
  previousPopulations?: Map<string, number>;
}

// ============ 详情标签页 ============
export type DetailTab = "overview" | "stats" | "ai" | "history";

// ============ 列表排序 ============
export type SortField = "name" | "population" | "role" | "status";
export type SortOrder = "asc" | "desc";

// ============ 过滤选项 ============
export interface FilterOptions {
  searchQuery: string;
  roleFilter: string | null;
  statusFilter: "all" | "alive" | "extinct" | null;
  sortBy?: "population" | "name" | "trend";
  sortOrder?: "asc" | "desc";
}

// ============ 生态角色配置 ============
export interface RoleConfig {
  color: string;
  gradient: string;
  bgGradient: string;
  icon: string;
  label: string;
  description: string;
}

// ============ 种群趋势 ============
export type PopulationTrend = "up" | "down" | "stable";

// ============ 编辑状态 ============
export interface EditState {
  isEditing: boolean;
  description: string;
  morphology: string;
  traits: string;
}

// ============ 趋势信息 ============
export interface TrendInfo {
  icon: React.ComponentType<{ size?: number | string }>;
  color: string;
  label: string;
  bg: string;
  emoji: string;
}
