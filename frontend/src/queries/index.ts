/**
 * 查询 Hooks 统一导出
 *
 * 这些 hooks 封装了数据获取逻辑，提供：
 * - 自动加载
 * - 加载状态
 * - 错误处理
 * - 缓存管理
 *
 * React Query 版 hooks 提供更强大的缓存和状态管理
 */

// 原有的手写 hooks（逐步迁移到 React Query）
export { useMapData } from "./useMapData";
export { useLineage } from "./useLineage";
export { useQueueStatus } from "./useQueueStatus";
export { useHints } from "./useHints";

// React Query 版 hooks
export {
  useSpeciesListQuery,
  useSpeciesDetailQuery,
  useEditSpeciesMutation,
  useGenerateSpeciesMutation,
  useGenerateSpeciesAdvancedMutation,
} from "./useSpeciesQuery";

export {
  useFoodWebQuery,
  useFoodWebAnalysisQuery,
  useFoodWebDataWithAnalysis,
  useRepairFoodWebMutation,
} from "./useFoodWebQuery";
