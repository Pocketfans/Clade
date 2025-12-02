/**
 * FoodWebGraph 模块导出
 */

// 主组件 - 使用重构版本
export { FoodWebGraph } from "./FoodWebGraphNew";

// 类型
export type {
  GraphNode,
  GraphLink,
  GraphData,
  FilterMode,
  FoodWebGraphProps,
  TrophicColor,
} from "./types";

export { TROPHIC_COLORS, KEYSTONE_COLOR } from "./types";

// Hooks
export { useFoodWebData } from "./hooks/useFoodWebData";

