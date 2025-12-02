/**
 * API 模块统一导出
 * 
 * 使用方式：
 * import { fetchMapOverview, runTurn, fetchSpeciesList } from "@/services/api";
 * 
 * 或按模块导入：
 * import * as TurnsAPI from "@/services/api/turns";
 */

// 基础设施
export { http, createEventSource } from "./base";
export type { ApiError, RequestConfig, SSEEventHandler } from "./base";

// 回合相关
export {
  runTurn,
  runBatchTurns,
  fetchPressureTemplates,
  fetchHistory,
  fetchQueueStatus,
  addQueue,
  clearQueue,
} from "./turns";

// 地图相关
export {
  fetchMapOverview,
  fetchHeightMap,
  fetchWaterMask,
  fetchErosionMap,
} from "./map";

// 物种相关
export {
  fetchSpeciesList,
  fetchSpeciesDetail,
  editSpecies,
  generateSpecies,
  generateSpeciesAdvanced,
  compareNiche,
  fetchLineageTree,
  invalidateLineageCache,
  updateWatchlist,
} from "./species";
export type { GenerateSpeciesAdvancedParams } from "./species";

// 配置相关
export {
  fetchUIConfig,
  updateUIConfig,
  testApiConnection,
  fetchProviderModels,
} from "./config";
export type { ApiTestParams, ApiTestResult, ModelInfo, FetchModelsResult } from "./config";

// 存档相关
export {
  fetchGameState,
  listSaves,
  createSave,
  saveGame,
  loadGame,
  deleteSave,
} from "./saves";
export type { GameState } from "./saves";

// 生态系统相关
export {
  fetchFoodWeb,
  fetchSpeciesFoodChain,
  analyzeExtinctionImpact,
  fetchFoodWebAnalysis,
  repairFoodWeb,
} from "./ecosystem";

// 管理相关
export {
  checkHealth,
  resetWorld,
  dropDatabase,
  fetchLogs,
  fetchAIDiagnostics,
  resetAIDiagnostics,
  abortCurrentTasks,
  skipCurrentAIStep,
  getTaskDiagnostics,
} from "./admin";
export type { AIDiagnostics, TaskDiagnostics, AbortTasksResult } from "./admin";

// 事件流
export {
  connectToEventStream,
  isTurnStartedEvent,
  isTurnCompletedEvent,
  isSpeciesCreatedEvent,
  isSpeciesExtinctEvent,
  isAchievementUnlockedEvent,
  isEnergyChangedEvent,
} from "./events";
export type {
  EventType,
  GameEvent,
  TurnStartedEvent,
  TurnCompletedEvent,
  SpeciesCreatedEvent,
  SpeciesExtinctEvent,
  AchievementUnlockedEvent,
  EnergyChangedEvent,
} from "./events";

