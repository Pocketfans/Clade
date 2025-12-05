/**
 * SettingsDrawer 类型定义
 */

import type {
  UIConfig,
  ProviderConfig,
  CapabilityRouteConfig,
  ProviderType,
  SpeciationConfig,
  ReproductionConfig,
  MortalityConfig,
  EcologyBalanceConfig,
  GameplayConfig,
  MapEnvironmentConfig,
  PressureIntensityConfig,
} from "@/services/api.types";
import type { ModelInfo } from "@/services/api";

// ============ Tab 类型 ============
export type SettingsTab =
  | "connection"
  | "embedding"
  | "memory"
  | "autosave"
  | "performance"
  | "speciation"
  | "reproduction"
  | "mortality"
  | "pressure"
  | "ecology"
  | "map";

// ============ 确认对话框状态 ============
export interface ConfirmState {
  isOpen: boolean;
  title: string;
  message: string;
  variant: "danger" | "warning" | "info";
  onConfirm: () => void;
}

// ============ 测试结果 ============
export interface TestResult {
  success: boolean;
  message: string;
  details?: string;
}

// ============ 组件状态 ============
export interface SettingsState {
  form: UIConfig;
  tab: SettingsTab;
  selectedProviderId: string | null;
  testResults: Record<string, TestResult>;
  testingProviderId: string | null;
  testingEmbedding: boolean;
  testResultEmbedding: TestResult | null;
  saving: boolean;
  saveSuccess: boolean;
  showApiKeys: Record<string, boolean>;
  confirmDialog: ConfirmState;
  validationErrors: Record<string, string>;
  // 模型列表相关
  fetchingModels: string | null;
  providerModels: Record<string, ModelInfo[]>;
  modelFetchError: Record<string, string>;
}

// ============ Actions ============
export type SettingsAction =
  | { type: "SET_TAB"; tab: SettingsTab }
  | { type: "SELECT_PROVIDER"; id: string | null }
  | { type: "SET_FORM"; form: UIConfig }
  | { type: "UPDATE_PROVIDER"; id: string; field: keyof ProviderConfig; value: unknown }
  | { type: "ADD_PROVIDER"; provider: ProviderConfig }
  | { type: "REMOVE_PROVIDER"; id: string }
  | { type: "UPDATE_GLOBAL"; field: string; value: unknown }
  | { type: "UPDATE_ROUTE"; capKey: string; field: keyof CapabilityRouteConfig; value: unknown }
  | { type: "SET_TEST_RESULT"; providerId: string; result: TestResult }
  | { type: "SET_TESTING_PROVIDER"; id: string | null }
  | { type: "SET_TESTING_EMBEDDING"; testing: boolean }
  | { type: "SET_EMBEDDING_RESULT"; result: TestResult | null }
  | { type: "SET_SAVING"; saving: boolean }
  | { type: "SET_SAVE_SUCCESS"; success: boolean }
  | { type: "TOGGLE_API_KEY_VISIBILITY"; providerId: string }
  | { type: "SET_CONFIRM_DIALOG"; dialog: ConfirmState }
  | { type: "CLOSE_CONFIRM" }
  | { type: "SET_VALIDATION_ERRORS"; errors: Record<string, string> }
  | { type: "RESET_TO_DEFAULT" }
  // 模型列表相关
  | { type: "SET_FETCHING_MODELS"; providerId: string | null }
  | { type: "SET_PROVIDER_MODELS"; providerId: string; models: ModelInfo[] }
  | { type: "SET_MODEL_FETCH_ERROR"; providerId: string; error: string }
  | { type: "CLEAR_MODEL_FETCH_ERROR"; providerId: string }
  | { type: "TOGGLE_MODEL_SELECTION"; providerId: string; modelId: string }
  | { type: "SELECT_ALL_MODELS"; providerId: string }
  | { type: "DESELECT_ALL_MODELS"; providerId: string }
  // 多服务商负载均衡
  | { type: "TOGGLE_ROUTE_PROVIDER"; capKey: string; providerId: string }
  // 各配置模块
  | { type: "UPDATE_SPECIATION"; updates: Partial<SpeciationConfig> }
  | { type: "RESET_SPECIATION" }
  | { type: "UPDATE_REPRODUCTION"; updates: Partial<ReproductionConfig> }
  | { type: "RESET_REPRODUCTION" }
  | { type: "UPDATE_MORTALITY"; updates: Partial<MortalityConfig> }
  | { type: "RESET_MORTALITY" }
  | { type: "UPDATE_ECOLOGY"; updates: Partial<EcologyBalanceConfig> }
  | { type: "RESET_ECOLOGY" }
  | { type: "UPDATE_GAMEPLAY"; updates: Partial<GameplayConfig> }
  | { type: "UPDATE_MAP_ENV"; updates: Partial<MapEnvironmentConfig> }
  | { type: "RESET_MAP_ENV" }
  | { type: "UPDATE_PRESSURE"; updates: Partial<PressureIntensityConfig> }
  | { type: "RESET_PRESSURE" };

// ============ 能力定义 ============
export type ParallelMode = "batch" | "concurrent" | "single";

export interface CapabilityDef {
  key: string;
  label: string;
  desc: string;
  defaultTimeout: number;
  parallel: ParallelMode;
  parallelNote?: string;
}

// ============ Provider 预设 ============
export interface ProviderPreset {
  id: string;
  name: string;
  provider_type: ProviderType;
  base_url: string;
  description: string;
  models: string[];
  logo: string;
  color: string;
  category: "openai" | "anthropic" | "google";
  supportsThinking?: boolean;
}

