/**
 * SettingsDrawer 模块导出
 * 
 * 重构后的结构:
 * - types.ts: 类型定义
 * - constants.ts: 常量和预设
 * - reducer.ts: 状态管理
 * - common/: 通用 UI 组件
 * - sections/: Tab 内容组件
 */

// 主组件 - 使用重构版本
export { SettingsDrawer } from "./SettingsDrawerNew";

// 类型
export type {
  SettingsTab,
  SettingsState,
  SettingsAction,
  ConfirmState,
  TestResult,
  CapabilityDef,
  ParallelMode,
  ProviderPreset,
} from "./types";

// 常量
export {
  PROVIDER_API_TYPES,
  PROVIDER_PRESETS,
  AI_CAPABILITIES,
  ALL_CAPABILITIES,
  CAPABILITY_DEFS,
  EMBEDDING_PRESETS,
  DEFAULT_SPECIATION_CONFIG,
  DEFAULT_REPRODUCTION_CONFIG,
  DEFAULT_MORTALITY_CONFIG,
  DEFAULT_ECOLOGY_BALANCE_CONFIG,
  DEFAULT_MAP_ENVIRONMENT_CONFIG,
} from "./constants";

// Reducer
export {
  settingsReducer,
  createInitialState,
  createDefaultConfig,
  getInitialProviders,
  getProviderLogo,
  getProviderTypeBadge,
  supportsThinking,
  generateId,
} from "./reducer";

// 通用组件
export * from "./common";
