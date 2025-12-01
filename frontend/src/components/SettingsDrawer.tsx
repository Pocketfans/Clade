import { useState, useEffect, useCallback, useReducer, useMemo } from "react";
import type { UIConfig, ProviderConfig, CapabilityRouteConfig, ProviderType, SpeciationConfig } from "../services/api.types";
import { testApiConnection, fetchProviderModels, type ModelInfo } from "../services/api";
import { GamePanel } from "./common/GamePanel";
import { ConfirmDialog } from "./common/ConfirmDialog";
import { Tooltip } from "./common/Tooltip";
import "./SettingsDrawer.css";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => Promise<void>;
}

type Tab = "connection" | "models" | "memory" | "autosave" | "performance" | "speciation";

// ========== 常量定义 ==========

// API 类型：决定如何调用 API
const PROVIDER_API_TYPES: { value: ProviderType; label: string; desc: string }[] = [
  { value: "openai", label: "OpenAI 兼容", desc: "适用于 OpenAI、DeepSeek、硅基流动等" },
  { value: "anthropic", label: "Claude 原生", desc: "Anthropic Claude 官方 API" },
  { value: "google", label: "Gemini 原生", desc: "Google Gemini 官方 API" },
];

// 服务商预设配置（含 Logo）- 分组展示
const PROVIDER_PRESETS = [
  // ===== OpenAI 兼容格式 =====
  {
    id: "deepseek_official",
    name: "DeepSeek",
    provider_type: "openai" as ProviderType,
    base_url: "https://api.deepseek.com/v1",
    description: "DeepSeek 官方 API",
    models: [],
    logo: "🔮",
    color: "#6366f1",
    category: "openai",
  },
  {
    id: "siliconflow",
    name: "硅基流动",
    provider_type: "openai" as ProviderType,
    base_url: "https://api.siliconflow.cn/v1",
    description: "硅基流动 API，支持思维链",
    models: [],
    logo: "⚡",
    color: "#f59e0b",
    supportsThinking: true,
    category: "openai",
  },
  {
    id: "volcengine",
    name: "火山引擎（豆包）",
    provider_type: "openai" as ProviderType,
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    description: "火山引擎 API，需填写端点ID作为模型名",
    models: [],
    logo: "🌋",
    color: "#ef4444",
    supportsThinking: true,
    category: "openai",
  },
  {
    id: "openai_official",
    name: "OpenAI",
    provider_type: "openai" as ProviderType,
    base_url: "https://api.openai.com/v1",
    description: "OpenAI 官方 API",
    models: [],
    logo: "🤖",
    color: "#10b981",
    category: "openai",
  },
  // ===== Claude 原生 API =====
  {
    id: "claude_official",
    name: "Claude",
    provider_type: "anthropic" as ProviderType,
    base_url: "https://api.anthropic.com/v1",
    description: "Anthropic Claude 官方 API",
    models: [],
    logo: "🎭",
    color: "#d97706",
    category: "anthropic",
  },
  // ===== Gemini 原生 API =====
  {
    id: "gemini_official",
    name: "Gemini",
    provider_type: "google" as ProviderType,
    base_url: "https://generativelanguage.googleapis.com/v1beta",
    description: "Google Gemini 官方 API",
    models: [],
    logo: "💎",
    color: "#3b82f6",
    category: "google",
  },
  // ===== 聚合服务 =====
  {
    id: "openrouter",
    name: "OpenRouter",
    provider_type: "openai" as ProviderType,
    base_url: "https://openrouter.ai/api/v1",
    description: "聚合 API，一个 Key 访问多种模型",
    models: [],
    logo: "🔀",
    color: "#8b5cf6",
    category: "openai",
  },
] as const;

// AI 能力列表定义（分组）
const AI_CAPABILITIES = {
  high: [
    { key: "turn_report", label: "主推演叙事", desc: "负责生成每个回合的总体生态演化报告", defaultTimeout: 120 },
    { key: "focus_batch", label: "重点批次推演", desc: "处理关键物种的具体生存判定", defaultTimeout: 90 },
    { key: "critical_detail", label: "关键物种分析", desc: "分析濒危或优势物种的详细状态", defaultTimeout: 90 },
  ],
  medium: [
    { key: "speciation", label: "物种分化", desc: "判定新物种的诞生条件与特征", defaultTimeout: 60 },
    { key: "species_generation", label: "物种生成", desc: "生成初始物种或新物种", defaultTimeout: 60 },
  ],
  low: [
    { key: "migration", label: "迁徙建议", desc: "计算物种在不同地块间的移动", defaultTimeout: 45 },
    { key: "pressure_escalation", label: "压力升级", desc: "动态调整环境生存压力", defaultTimeout: 45 },
    { key: "reemergence", label: "物种重现/起名", desc: "为新物种生成名称与描述", defaultTimeout: 45 },
  ],
} as const;

const ALL_CAPABILITIES = [...AI_CAPABILITIES.high, ...AI_CAPABILITIES.medium, ...AI_CAPABILITIES.low];

// 向量模型预设
const EMBEDDING_PRESETS = [
  { id: "qwen3", name: "Qwen/Qwen3-Embedding-4B", dimensions: 4096 },
  { id: "bge-m3", name: "BAAI/bge-m3", dimensions: 1024 },
  { id: "text-embedding-3-small", name: "text-embedding-3-small", dimensions: 1536 },
];

// ========== 状态管理 ==========

type ConfirmState = {
  isOpen: boolean;
  title: string;
  message: string;
  variant: 'danger' | 'warning' | 'info';
  onConfirm: () => void;
};

type TestResult = { success: boolean; message: string; details?: string };

interface State {
  form: UIConfig;
  tab: Tab;
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
  fetchingModels: string | null;  // 正在获取模型的服务商 ID
  providerModels: Record<string, ModelInfo[]>;  // 各服务商的模型列表
  modelFetchError: Record<string, string>;  // 获取模型错误信息
}

type Action =
  | { type: 'SET_TAB'; tab: Tab }
  | { type: 'SELECT_PROVIDER'; id: string | null }
  | { type: 'SET_FORM'; form: UIConfig }
  | { type: 'UPDATE_PROVIDER'; id: string; field: keyof ProviderConfig; value: any }
  | { type: 'ADD_PROVIDER'; provider: ProviderConfig }
  | { type: 'REMOVE_PROVIDER'; id: string }
  | { type: 'UPDATE_GLOBAL'; field: string; value: any }
  | { type: 'UPDATE_ROUTE'; capKey: string; field: keyof CapabilityRouteConfig; value: any }
  | { type: 'SET_TEST_RESULT'; providerId: string; result: TestResult }
  | { type: 'SET_TESTING_PROVIDER'; id: string | null }
  | { type: 'SET_TESTING_EMBEDDING'; testing: boolean }
  | { type: 'SET_EMBEDDING_RESULT'; result: TestResult | null }
  | { type: 'SET_SAVING'; saving: boolean }
  | { type: 'SET_SAVE_SUCCESS'; success: boolean }
  | { type: 'TOGGLE_API_KEY_VISIBILITY'; providerId: string }
  | { type: 'SET_CONFIRM_DIALOG'; dialog: ConfirmState }
  | { type: 'CLOSE_CONFIRM' }
  | { type: 'SET_VALIDATION_ERRORS'; errors: Record<string, string> }
  | { type: 'RESET_TO_DEFAULT' }
  // 模型列表相关
  | { type: 'SET_FETCHING_MODELS'; providerId: string | null }
  | { type: 'SET_PROVIDER_MODELS'; providerId: string; models: ModelInfo[] }
  | { type: 'SET_MODEL_FETCH_ERROR'; providerId: string; error: string }
  | { type: 'CLEAR_MODEL_FETCH_ERROR'; providerId: string }
  | { type: 'TOGGLE_MODEL_SELECTION'; providerId: string; modelId: string }
  | { type: 'SELECT_ALL_MODELS'; providerId: string }
  | { type: 'DESELECT_ALL_MODELS'; providerId: string }
  // 多服务商负载均衡
  | { type: 'TOGGLE_ROUTE_PROVIDER'; capKey: string; providerId: string }
  // 分化配置
  | { type: 'UPDATE_SPECIATION'; updates: Partial<SpeciationConfig> };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_TAB':
      return { ...state, tab: action.tab };
    case 'SELECT_PROVIDER':
      return { ...state, selectedProviderId: action.id };
    case 'SET_FORM':
      return { ...state, form: action.form };
    case 'UPDATE_PROVIDER':
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.id]: { ...state.form.providers[action.id], [action.field]: action.value }
          }
        }
      };
    case 'ADD_PROVIDER':
      return {
        ...state,
        form: {
          ...state.form,
          providers: { ...state.form.providers, [action.provider.id]: action.provider }
        },
        selectedProviderId: action.provider.id
      };
    case 'REMOVE_PROVIDER': {
      const newProviders = { ...state.form.providers };
      delete newProviders[action.id];
      return {
        ...state,
        form: { ...state.form, providers: newProviders },
        selectedProviderId: state.selectedProviderId === action.id ? null : state.selectedProviderId
      };
    }
    case 'UPDATE_GLOBAL':
      return { ...state, form: { ...state.form, [action.field]: action.value } };
    case 'UPDATE_ROUTE': {
      const currentRoute = state.form.capability_routes[action.capKey] || { timeout: 60 };
      return {
        ...state,
        form: {
          ...state.form,
          capability_routes: {
            ...state.form.capability_routes,
            [action.capKey]: { ...currentRoute, [action.field]: action.value }
          }
        }
      };
    }
    case 'SET_TEST_RESULT':
      return { ...state, testResults: { ...state.testResults, [action.providerId]: action.result } };
    case 'SET_TESTING_PROVIDER':
      return { ...state, testingProviderId: action.id };
    case 'SET_TESTING_EMBEDDING':
      return { ...state, testingEmbedding: action.testing };
    case 'SET_EMBEDDING_RESULT':
      return { ...state, testResultEmbedding: action.result };
    case 'SET_SAVING':
      return { ...state, saving: action.saving };
    case 'SET_SAVE_SUCCESS':
      return { ...state, saveSuccess: action.success };
    case 'TOGGLE_API_KEY_VISIBILITY':
      return {
        ...state,
        showApiKeys: {
          ...state.showApiKeys,
          [action.providerId]: !state.showApiKeys[action.providerId]
        }
      };
    case 'SET_CONFIRM_DIALOG':
      return { ...state, confirmDialog: action.dialog };
    case 'CLOSE_CONFIRM':
      return { ...state, confirmDialog: { ...state.confirmDialog, isOpen: false } };
    case 'SET_VALIDATION_ERRORS':
      return { ...state, validationErrors: action.errors };
    case 'RESET_TO_DEFAULT':
      return { ...state, form: createDefaultConfig() };
    // 模型列表相关
    case 'SET_FETCHING_MODELS':
      return { ...state, fetchingModels: action.providerId };
    case 'SET_PROVIDER_MODELS':
      return { 
        ...state, 
        providerModels: { ...state.providerModels, [action.providerId]: action.models },
        // 同时更新 provider 的 models 字段
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: {
              ...state.form.providers[action.providerId],
              models: action.models.map(m => m.id)
            }
          }
        }
      };
    case 'SET_MODEL_FETCH_ERROR':
      return { ...state, modelFetchError: { ...state.modelFetchError, [action.providerId]: action.error } };
    case 'CLEAR_MODEL_FETCH_ERROR': {
      const newErrors = { ...state.modelFetchError };
      delete newErrors[action.providerId];
      return { ...state, modelFetchError: newErrors };
    }
    case 'TOGGLE_MODEL_SELECTION': {
      const provider = state.form.providers[action.providerId];
      if (!provider) return state;
      const currentSelected = provider.selected_models || [];
      const isSelected = currentSelected.includes(action.modelId);
      const newSelected = isSelected
        ? currentSelected.filter(m => m !== action.modelId)
        : [...currentSelected, action.modelId];
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: newSelected }
          }
        }
      };
    }
    case 'SELECT_ALL_MODELS': {
      const provider = state.form.providers[action.providerId];
      const models = state.providerModels[action.providerId] || [];
      if (!provider || models.length === 0) return state;
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: models.map(m => m.id) }
          }
        }
      };
    }
    case 'DESELECT_ALL_MODELS': {
      const provider = state.form.providers[action.providerId];
      if (!provider) return state;
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: [] }
          }
        }
      };
    }
    case 'TOGGLE_ROUTE_PROVIDER': {
      const currentRoute = state.form.capability_routes[action.capKey] || { timeout: 60 };
      const currentIds = currentRoute.provider_ids || [];
      const isSelected = currentIds.includes(action.providerId);
      const newIds = isSelected
        ? currentIds.filter(id => id !== action.providerId)
        : [...currentIds, action.providerId];
      return {
        ...state,
        form: {
          ...state.form,
          capability_routes: {
            ...state.form.capability_routes,
            [action.capKey]: { ...currentRoute, provider_ids: newIds }
          }
        }
      };
    }
    case 'UPDATE_SPECIATION': {
      return {
        ...state,
        form: {
          ...state.form,
          speciation: {
            ...(state.form.speciation || {}),
            ...action.updates
          }
        }
      };
    }
    default:
      return state;
  }
}

// ========== 工具函数 ==========

const generateId = () => Math.random().toString(36).substr(2, 9);

// 默认分化配置
const DEFAULT_SPECIATION_CONFIG: SpeciationConfig = {
  cooldown_turns: 0,
  species_soft_cap: 60,
  base_speciation_rate: 0.5,
  max_offspring_count: 6,
  early_game_turns: 10,
  early_threshold_min_factor: 0.3,
  early_threshold_decay_rate: 0.07,
  early_skip_cooldown_turns: 5,
  pressure_threshold_late: 0.7,
  pressure_threshold_early: 0.4,
  resource_threshold_late: 0.6,
  resource_threshold_early: 0.35,
  evo_potential_threshold_late: 0.7,
  evo_potential_threshold_early: 0.5,
  candidate_tile_min_pop: 50,
  candidate_tile_death_rate_min: 0.02,
  candidate_tile_death_rate_max: 0.75,
  radiation_base_chance: 0.05,
  radiation_early_bonus: 0.15,
  radiation_pop_ratio_early: 1.2,
  radiation_pop_ratio_late: 1.5,
  radiation_max_chance_early: 0.35,
  radiation_max_chance_late: 0.25,
  no_isolation_penalty_early: 0.8,
  no_isolation_penalty_late: 0.5,
  threshold_multiplier_no_isolation: 1.8,
  threshold_multiplier_high_overlap: 1.2,
  threshold_multiplier_high_saturation: 1.2,
};

function createDefaultConfig(): UIConfig {
  const providers: Record<string, ProviderConfig> = {};
  PROVIDER_PRESETS.forEach(preset => {
    providers[preset.id] = {
      id: preset.id,
      name: preset.name,
      type: preset.provider_type,  // 兼容旧字段
      provider_type: preset.provider_type,
      base_url: preset.base_url,
      api_key: "",
      models: [...preset.models]
    };
  });
  return {
    providers,
    capability_routes: {},
    ai_provider: null,
    ai_model: null,
    ai_timeout: 60,
    embedding_provider: null,
    speciation: { ...DEFAULT_SPECIATION_CONFIG },
  };
}

function getInitialProviders(config: UIConfig): Record<string, ProviderConfig> {
  const providers = config.providers || {};
  if (Object.keys(providers).length === 0) {
    return createDefaultConfig().providers;
  }
  // 确保所有 provider 都有 provider_type 字段（兼容旧数据）
  const updated: Record<string, ProviderConfig> = {};
  for (const [id, p] of Object.entries(providers)) {
    updated[id] = {
      ...p,
      provider_type: p.provider_type || (p.type as ProviderType) || "openai",
    };
  }
  return updated;
}

function getProviderLogo(provider: ProviderConfig): string {
  const preset = PROVIDER_PRESETS.find(p => p.id === provider.id);
  if (preset) return preset.logo;
  
  // 根据 provider_type 或 URL 猜测
  if (provider.provider_type === "anthropic") return '🎭';
  if (provider.provider_type === "google") return '💎';
  
  const url = provider.base_url || '';
  if (url.includes('deepseek')) return '🔮';
  if (url.includes('siliconflow')) return '⚡';
  if (url.includes('volces')) return '🌋';
  if (url.includes('openai')) return '🤖';
  if (url.includes('anthropic')) return '🎭';
  if (url.includes('google')) return '💎';
  if (url.includes('openrouter')) return '🔀';
  return '🔧';
}

function getProviderTypeBadge(providerType: ProviderType): { text: string; color: string } {
  switch (providerType) {
    case "anthropic": return { text: "Claude", color: "#d97706" };
    case "google": return { text: "Gemini", color: "#3b82f6" };
    default: return { text: "OpenAI", color: "#10b981" };
  }
}

function supportsThinking(provider: ProviderConfig | null): boolean {
  if (!provider?.base_url) return false;
  return provider.base_url.includes("siliconflow") || provider.base_url.includes("volces.com");
}

function validateConfig(_form: UIConfig): Record<string, string> {
  // 不再强制要求默认服务商和默认模型，只保存服务商列表信息即可
  return {};
}

// ========== 主组件 ==========

export function SettingsDrawer({ config, onClose, onSave }: Props) {
  const initialConfig = useMemo(() => ({
    ...config,
    providers: getInitialProviders(config),
    capability_routes: config.capability_routes || {},
    speciation: { ...DEFAULT_SPECIATION_CONFIG, ...(config.speciation || {}) },
  }), []);

  const [state, dispatch] = useReducer(reducer, {
    form: initialConfig,
    tab: "connection",
    selectedProviderId: Object.keys(initialConfig.providers)[0] || null,
    testResults: {},
    testingProviderId: null,
    testingEmbedding: false,
    testResultEmbedding: null,
    saving: false,
    saveSuccess: false,
    showApiKeys: {},
    confirmDialog: { isOpen: false, title: '', message: '', variant: 'warning', onConfirm: () => {} },
    validationErrors: {},
    fetchingModels: null,
    providerModels: {},
    modelFetchError: {},
  });

  const { form, tab, selectedProviderId, testResults, testingProviderId, 
          testingEmbedding, testResultEmbedding, saving, saveSuccess, 
          showApiKeys, confirmDialog, validationErrors,
          fetchingModels, providerModels, modelFetchError } = state;

  const selectedProvider = selectedProviderId ? form.providers[selectedProviderId] : null;
  
  const providerList = useMemo(() => Object.values(form.providers), [form.providers]);

  // 快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
      if (e.key === 'Escape' && !confirmDialog.isOpen) {
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [confirmDialog.isOpen, form]);

  // 保存成功提示自动消失
  useEffect(() => {
    if (saveSuccess) {
      const timer = setTimeout(() => dispatch({ type: 'SET_SAVE_SUCCESS', success: false }), 3000);
      return () => clearTimeout(timer);
    }
  }, [saveSuccess]);

  // ========== 操作函数 ==========

  const showConfirm = useCallback((
    title: string, 
    message: string, 
    onConfirm: () => void, 
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    dispatch({
      type: 'SET_CONFIRM_DIALOG',
      dialog: { isOpen: true, title, message, variant, onConfirm }
    });
  }, []);

  const addCustomProvider = useCallback((providerType: ProviderType = "openai") => {
    const typeNames: Record<ProviderType, string> = {
      openai: "OpenAI 兼容",
      anthropic: "Claude",
      google: "Gemini"
    };
    const newProvider: ProviderConfig = {
      id: generateId(),
      name: `自定义 ${typeNames[providerType]}`,
      type: providerType,
      provider_type: providerType,
      models: []
    };
    dispatch({ type: 'ADD_PROVIDER', provider: newProvider });
  }, []);

  const removeProvider = useCallback((id: string) => {
    const isPreset = PROVIDER_PRESETS.some(p => p.id === id);
    const title = isPreset ? "删除预设服务商" : "删除服务商";
    const message = isPreset 
      ? "这是预设服务商，删除后下次打开设置将重新出现。确定要删除吗？"
      : "确定要删除这个服务商吗？相关的路由配置将失效。";
    
    showConfirm(title, message, () => {
      dispatch({ type: 'REMOVE_PROVIDER', id });
      dispatch({ type: 'CLOSE_CONFIRM' });
    }, 'danger');
  }, [showConfirm]);

  const handleTestProvider = useCallback(async (providerId: string) => {
    const provider = form.providers[providerId];
    if (!provider?.base_url || !provider?.api_key) {
      dispatch({ 
        type: 'SET_TEST_RESULT', 
        providerId, 
        result: { success: false, message: "请先填写 Base URL 和 API Key" } 
      });
      return;
    }

    const providerType = provider.provider_type || "openai";
    
    // 优先使用该服务商的已收藏模型，否则根据服务商类型选择默认模型
    let testModel = provider.selected_models?.[0];
    
    if (!testModel) {
      if (providerType === "anthropic") {
        testModel = "claude-3-5-sonnet-20241022";
      } else if (providerType === "google") {
        testModel = "gemini-2.0-flash";
      } else if (provider.base_url?.includes("deepseek.com")) {
        testModel = "deepseek-chat";
      } else if (provider.base_url?.includes("siliconflow")) {
        testModel = "deepseek-ai/DeepSeek-V3";
      } else if (provider.base_url?.includes("openai.com")) {
        testModel = "gpt-4o-mini";
      } else if (provider.base_url?.includes("openrouter")) {
        testModel = "openai/gpt-4o-mini";
      } else if (provider.base_url?.includes("volces.com")) {
        // 火山引擎需要端点ID，提示用户
        dispatch({ 
          type: 'SET_TEST_RESULT', 
          providerId, 
          result: { success: false, message: "火山引擎需要先添加端点ID作为模型名" } 
        });
        return;
      } else {
        testModel = "gpt-3.5-turbo";
      }
    }

    dispatch({ type: 'SET_TESTING_PROVIDER', id: providerId });
    
    // 获取默认的备用测试模型
    const getDefaultModel = () => {
      if (providerType === "anthropic") return "claude-3-5-sonnet-20241022";
      if (providerType === "google") return "gemini-2.0-flash";
      if (provider.base_url?.includes("deepseek.com")) return "deepseek-chat";
      if (provider.base_url?.includes("siliconflow")) return "deepseek-ai/DeepSeek-V3";
      if (provider.base_url?.includes("openai.com")) return "gpt-4o-mini";
      if (provider.base_url?.includes("openrouter")) return "openai/gpt-4o-mini";
      return "gpt-3.5-turbo";
    };
    
    const defaultModel = getDefaultModel();
    const isUsingCustomModel = testModel !== defaultModel;
    
    console.log(`[测试连接] 服务商: ${provider.name}, 模型: ${testModel}`);

    try {
      let result = await testApiConnection({
        type: "chat",
        base_url: provider.base_url,
        api_key: provider.api_key,
        provider_type: providerType,
        model: testModel
      });
      
      // 如果使用收藏模型失败且是400错误，尝试用默认模型重试
      if (!result.success && isUsingCustomModel && result.message?.includes("400")) {
        console.log(`[测试连接] 收藏模型失败，尝试默认模型: ${defaultModel}`);
        const retryResult = await testApiConnection({
          type: "chat",
          base_url: provider.base_url,
          api_key: provider.api_key,
          provider_type: providerType,
          model: defaultModel
        });
        
        if (retryResult.success) {
          result = {
            ...retryResult,
            message: `${retryResult.message}\n⚠️ 注意：收藏的模型 "${testModel}" 测试失败，建议检查模型名称`,
          };
        }
      }
      
      dispatch({ type: 'SET_TEST_RESULT', providerId, result });
    } catch (e) {
      dispatch({ 
        type: 'SET_TEST_RESULT', 
        providerId, 
        result: { success: false, message: String(e) } 
      });
    } finally {
      dispatch({ type: 'SET_TESTING_PROVIDER', id: null });
    }
  }, [form]);

  // 获取服务商的模型列表
  const handleFetchModels = useCallback(async (providerId: string) => {
    const provider = form.providers[providerId];
    if (!provider?.base_url || !provider?.api_key) {
      dispatch({ 
        type: 'SET_MODEL_FETCH_ERROR', 
        providerId, 
        error: "请先填写 Base URL 和 API Key" 
      });
      return;
    }

    dispatch({ type: 'SET_FETCHING_MODELS', providerId });
    dispatch({ type: 'CLEAR_MODEL_FETCH_ERROR', providerId });

    try {
      const result = await fetchProviderModels({
        base_url: provider.base_url,
        api_key: provider.api_key,
        provider_type: provider.provider_type || "openai",
      });
      
      if (result.success && result.models.length > 0) {
        dispatch({ type: 'SET_PROVIDER_MODELS', providerId, models: result.models });
      } else {
        dispatch({ 
          type: 'SET_MODEL_FETCH_ERROR', 
          providerId, 
          error: result.message || "未获取到模型" 
        });
      }
    } catch (e) {
      dispatch({ 
        type: 'SET_MODEL_FETCH_ERROR', 
        providerId, 
        error: String(e) 
      });
    } finally {
      dispatch({ type: 'SET_FETCHING_MODELS', providerId: null });
    }
  }, [form]);

  const handleTestEmbedding = useCallback(async () => {
    const providerId = form.embedding_provider_id;
    const effectiveProviderId = providerId || form.default_provider_id;
    const provider = effectiveProviderId ? form.providers[effectiveProviderId] : null;
    
    const baseUrl = provider?.base_url || form.embedding_base_url;
    const apiKey = provider?.api_key || form.embedding_api_key;
    const model = form.embedding_model || "Qwen/Qwen3-Embedding-4B";

    if (!baseUrl || !apiKey) {
      dispatch({ 
        type: 'SET_EMBEDDING_RESULT', 
        result: { success: false, message: "请先填写配置或选择有效的服务商" } 
      });
      return;
    }
    
    dispatch({ type: 'SET_TESTING_EMBEDDING', testing: true });
    dispatch({ type: 'SET_EMBEDDING_RESULT', result: null });
    
    try {
      const result = await testApiConnection({
        type: "embedding",
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
      });
      dispatch({ type: 'SET_EMBEDDING_RESULT', result });
    } catch (error) {
      dispatch({ 
        type: 'SET_EMBEDDING_RESULT', 
        result: { success: false, message: "失败：" + String(error) } 
      });
    } finally {
      dispatch({ type: 'SET_TESTING_EMBEDDING', testing: false });
    }
  }, [form]);

  const handleSave = useCallback(async () => {
    console.log("[设置] 开始保存配置...");
    
    // 验证配置（已移除强制验证）
    const errors = validateConfig(form);
    dispatch({ type: 'SET_VALIDATION_ERRORS', errors });

    dispatch({ type: 'SET_SAVING', saving: true });
    dispatch({ type: 'SET_SAVE_SUCCESS', success: false });
    
    try {
      console.log("[设置] 调用 onSave...");
      await onSave(form);
      console.log("[设置] 保存成功！");
      dispatch({ type: 'SET_SAVE_SUCCESS', success: true });
    } catch (error) {
      console.error("[设置] 保存配置失败:", error);
      showConfirm("保存失败", String(error), () => dispatch({ type: 'CLOSE_CONFIRM' }), 'danger');
    } finally {
      dispatch({ type: 'SET_SAVING', saving: false });
    }
  }, [form, onSave, showConfirm]);

  const handleExport = useCallback(() => {
    const exportData = {
      version: 1,
      exportedAt: new Date().toISOString(),
      config: form,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `clade-settings-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [form]);

  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        
        if (data.config && data.config.providers) {
          showConfirm(
            "导入配置",
            "导入将覆盖当前所有设置，确定要继续吗？",
            () => {
              dispatch({ type: 'SET_FORM', form: data.config });
              dispatch({ type: 'CLOSE_CONFIRM' });
            },
            'warning'
          );
        } else {
          showConfirm("导入失败", "无效的配置文件格式", () => dispatch({ type: 'CLOSE_CONFIRM' }), 'danger');
        }
      } catch (err) {
        showConfirm("导入失败", "解析文件失败: " + String(err), () => dispatch({ type: 'CLOSE_CONFIRM' }), 'danger');
      }
    };
    input.click();
  }, [showConfirm]);

  const handleReset = useCallback(() => {
    showConfirm(
      "重置为默认",
      "这将清除所有自定义配置并恢复默认设置，确定要继续吗？",
      () => {
        dispatch({ type: 'RESET_TO_DEFAULT' });
        dispatch({ type: 'CLOSE_CONFIRM' });
      },
      'danger'
    );
  }, [showConfirm]);

  // ========== 渲染 ==========

  return (
    <GamePanel
      title="⚙️ 系统设置"
      onClose={onClose}
      variant="modal"
      width="clamp(800px, 88vw, 1400px)"
      height="clamp(600px, 88vh, 1000px)"
      icon={<span style={{ filter: 'drop-shadow(0 0 8px rgba(99, 102, 241, 0.5))' }}>⚙️</span>}
    >
      <div className="settings-container">
        {/* 侧边导航 */}
        <nav className="settings-nav">
          <div className="nav-items">
            <NavButton 
              active={tab === "connection"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'connection' })} 
              icon="🔌" 
              label="服务商配置" 
              desc="管理 AI API 接入"
            />
            <NavButton 
              active={tab === "models"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'models' })} 
              icon="🧠" 
              label="智能路由" 
              desc="分配模型能力"
            />
            <NavButton 
              active={tab === "memory"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'memory' })} 
              icon="🧬" 
              label="向量记忆" 
              desc="语义搜索引擎"
            />
            <NavButton 
              active={tab === "autosave"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'autosave' })} 
              icon="💾" 
              label="自动存档" 
              desc="进度保护策略"
            />
            <NavButton 
              active={tab === "performance"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'performance' })} 
              icon="⚡" 
              label="性能调优" 
              desc="超时与并发控制"
            />
            <NavButton 
              active={tab === "speciation"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'speciation' })} 
              icon="🧬" 
              label="分化设置" 
              desc="物种演化参数"
            />
          </div>
          
        </nav>

        {/* 内容区域 */}
        <div className="settings-content">
          
          {/* TAB 1: 服务商管理 */}
          {tab === "connection" && (
            <div className="tab-content fade-in">
              <div className="providers-layout">
                {/* 左侧：服务商列表 */}
                <div className="provider-list-panel">
                  <h4 className="panel-title">AI 服务商</h4>
                  
                  <div className="provider-list">
                    {providerList.map(p => {
                      const hasApiKey = !!p.api_key;
                      const hasThinking = supportsThinking(p);
                      const testResult = testResults[p.id];
                      const typeBadge = getProviderTypeBadge(p.provider_type || "openai");
                      
                      return (
                        <div 
                          key={p.id}
                          className={`provider-item ${selectedProviderId === p.id ? 'active' : ''}`}
                          onClick={() => dispatch({ type: 'SELECT_PROVIDER', id: p.id })}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => e.key === 'Enter' && dispatch({ type: 'SELECT_PROVIDER', id: p.id })}
                          aria-selected={selectedProviderId === p.id}
                        >
                          <div className="provider-item-header">
                            <span className="provider-logo">{getProviderLogo(p)}</span>
                            <span className="provider-name">{p.name}</span>
                            <div className="provider-badges">
                              <span 
                                className="badge-type" 
                                style={{ backgroundColor: `${typeBadge.color}18`, color: typeBadge.color, borderColor: `${typeBadge.color}40` }}
                              >
                                {typeBadge.text}
                              </span>
                              {hasThinking && <span className="badge-thinking" title="支持思维链推理">🧠</span>}
                              {testResult && (
                                <span 
                                  className={`status-dot ${testResult.success ? 'success' : 'error'}`}
                                  title={testResult.success ? "✓ 连接正常" : "✗ 连接失败"}
                                />
                              )}
                            </div>
                          </div>
                          {!hasApiKey && (
                            <div className="provider-warning">
                              <span>🔑</span>
                              <span>需要配置 API Key</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    
                  </div>
                  
                  <div className="add-provider-group">
                    <span className="add-label">➕ 添加自定义服务商</span>
                    <div className="add-provider-buttons">
                      <button onClick={() => addCustomProvider("openai")} className="btn-add-mini" title="OpenAI 兼容格式（大多数服务商）">
                        <span>🤖</span>
                        <span>OpenAI</span>
                      </button>
                      <button onClick={() => addCustomProvider("anthropic")} className="btn-add-mini" title="Anthropic Claude 原生API">
                        <span>🎭</span>
                        <span>Claude</span>
                      </button>
                      <button onClick={() => addCustomProvider("google")} className="btn-add-mini" title="Google Gemini 原生API">
                        <span>💎</span>
                        <span>Gemini</span>
                      </button>
                    </div>
                  </div>

                  <div className="global-defaults">
                    <label className="form-field">
                      <span className="field-label">
                        默认服务商
                        {validationErrors.default_provider && (
                          <span className="field-error"> ⚠️</span>
                        )}
                      </span>
                      <select
                        className={`field-input ${validationErrors.default_provider ? 'has-error' : ''}`}
                        value={form.default_provider_id ?? ""}
                        onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'default_provider_id', value: e.target.value })}
                        aria-invalid={!!validationErrors.default_provider}
                      >
                        <option value="">-- 请选择 --</option>
                        {Object.values(form.providers).filter(p => !!p.api_key).map(p => (
                          <option key={p.id} value={p.id}>{getProviderLogo(p)} {p.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span className="field-label">
                        默认模型
                        {validationErrors.default_model && (
                          <span className="field-error"> ⚠️</span>
                        )}
                      </span>
                      <GlobalModelSelect 
                        value={form.default_model ?? ""}
                        onChange={(value) => dispatch({ type: 'UPDATE_GLOBAL', field: 'default_model', value })}
                        hasError={!!validationErrors.default_model}
                        fetchedModels={form.default_provider_id ? providerModels[form.default_provider_id] : undefined}
                        selectedModels={form.default_provider_id ? form.providers[form.default_provider_id]?.selected_models : undefined}
                      />
                    </label>
                  </div>
                </div>

                {/* 右侧：编辑表单 */}
                <div className="provider-edit-panel">
                  {selectedProvider ? (
                    <div className="provider-edit-content">
                      <div className="edit-header">
                        <div className="edit-title-row">
                          <span className="edit-logo">{getProviderLogo(selectedProvider)}</span>
                          <div>
                            <h3>{selectedProvider.name}</h3>
                            {PROVIDER_PRESETS.some(p => p.id === selectedProviderId) && (
                              <span className="badge-preset">⭐ 预设服务商</span>
                            )}
                          </div>
                        </div>
                        <button 
                          onClick={() => selectedProviderId && removeProvider(selectedProviderId)}
                          className="btn-delete"
                          aria-label="删除服务商"
                        >
                          🗑️ 移除
                        </button>
                      </div>

                      <div className="tip-box">
                        <strong>💡 配置指南</strong>
                        <br/>
                        {getProviderTip(selectedProvider.base_url || "", selectedProvider.provider_type || "openai")}
                      </div>

                      <div className="form-fields">
                        <label className="form-field">
                          <span className="field-label">📝 显示名称</span>
                          <input
                            className="field-input"
                            value={selectedProvider.name}
                            onChange={(e) => selectedProviderId && dispatch({ 
                              type: 'UPDATE_PROVIDER', 
                              id: selectedProviderId, 
                              field: 'name', 
                              value: e.target.value 
                            })}
                            placeholder="自定义名称..."
                          />
                        </label>

                        <div className="form-field">
                          <span className="field-label">🔧 API 协议 <span className="field-hint-inline">（决定调用方式）</span></span>
                          <div className="api-type-selector">
                            {PROVIDER_API_TYPES.map(t => (
                              <button
                                key={t.value}
                                type="button"
                                className={`api-type-btn ${selectedProvider.provider_type === t.value ? 'active' : ''}`}
                                onClick={() => selectedProviderId && dispatch({ 
                                  type: 'UPDATE_PROVIDER', 
                                  id: selectedProviderId, 
                                  field: 'provider_type', 
                                  value: t.value 
                                })}
                                title={t.desc}
                              >
                                {t.value === "openai" && "🤖"}
                                {t.value === "anthropic" && "🎭"}
                                {t.value === "google" && "💎"}
                                <span>{t.label}</span>
                              </button>
                            ))}
                          </div>
                        </div>

                        <label className="form-field">
                          <span className="field-label">🌐 API 地址</span>
                          <input
                            className="field-input"
                            value={selectedProvider.base_url ?? ""}
                            onChange={(e) => selectedProviderId && dispatch({ 
                              type: 'UPDATE_PROVIDER', 
                              id: selectedProviderId, 
                              field: 'base_url', 
                              value: e.target.value 
                            })}
                            placeholder={
                              selectedProvider.provider_type === "anthropic" 
                                ? "https://api.anthropic.com/v1"
                                : selectedProvider.provider_type === "google"
                                ? "https://generativelanguage.googleapis.com/v1beta"
                                : "https://api.openai.com/v1"
                            }
                          />
                          <span className="field-hint">一般以 /v1 结尾，不需要添加 /chat/completions</span>
                        </label>

                        <label className="form-field">
                          <span className="field-label">🔑 API 密钥</span>
                          <div className="input-with-toggle">
                            <input
                              className="field-input"
                              type={showApiKeys[selectedProviderId || ''] ? "text" : "password"}
                              value={selectedProvider.api_key ?? ""}
                              onChange={(e) => selectedProviderId && dispatch({ 
                                type: 'UPDATE_PROVIDER', 
                                id: selectedProviderId, 
                                field: 'api_key', 
                                value: e.target.value 
                              })}
                              placeholder={
                                selectedProvider.provider_type === "anthropic" 
                                  ? "sk-ant-api03-..."
                                  : selectedProvider.provider_type === "google"
                                  ? "AIzaSy..."
                                  : "sk-..."
                              }
                            />
                            <button
                              type="button"
                              className="toggle-visibility"
                              onClick={() => selectedProviderId && dispatch({ 
                                type: 'TOGGLE_API_KEY_VISIBILITY', 
                                providerId: selectedProviderId 
                              })}
                              aria-label={showApiKeys[selectedProviderId || ''] ? "隐藏密钥" : "显示密钥"}
                            >
                              {showApiKeys[selectedProviderId || ''] ? '🙈' : '👁️'}
                            </button>
                          </div>
                        </label>
                      </div>

                      {/* 已收藏模型列表 */}
                      <div className="models-section">
                        <div className="models-header">
                          <span className="field-label">⭐ 已收藏模型</span>
                          <span className="models-count">{selectedProvider.selected_models?.length || 0} 个</span>
                        </div>
                        
                        {selectedProvider.selected_models && selectedProvider.selected_models.length > 0 && selectedProviderId ? (
                          <div className="saved-models-list">
                            {selectedProvider.selected_models.map(modelId => {
                              const modelInfo = providerModels[selectedProviderId]?.find((m: ModelInfo) => m.id === modelId);
                              return (
                                <div key={modelId} className="saved-model-item">
                                  <span className="saved-model-name" title={modelId}>
                                    {modelInfo?.name || modelId}
                                  </span>
                                  {modelInfo?.context_window && (
                                    <span className="model-context">
                                      {modelInfo.context_window >= 1000000 
                                        ? `${(modelInfo.context_window / 1000000).toFixed(1)}M` 
                                        : `${Math.round(modelInfo.context_window / 1000)}K`}
                                    </span>
                                  )}
                                  <button
                                    className="btn-remove-model"
                                    onClick={() => dispatch({ type: 'TOGGLE_MODEL_SELECTION', providerId: selectedProviderId, modelId })}
                                    title="移除收藏"
                                  >
                                    ✕
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="saved-models-empty">
                            暂无收藏，从下方列表添加常用模型
                          </div>
                        )}
                      </div>

                      {/* 可用模型列表 */}
                      <div className="models-section available-models">
                        <div className="models-header">
                          <span className="field-label">📦 可用模型</span>
                          <button
                            onClick={() => selectedProviderId && handleFetchModels(selectedProviderId)}
                            disabled={fetchingModels === selectedProviderId || !selectedProvider.api_key}
                            className="btn-fetch-models"
                            title={!selectedProvider.api_key ? "请先填写 API Key" : "从服务商获取模型列表"}
                          >
                            {fetchingModels === selectedProviderId ? (
                              <><span className="spinner-small"></span> 加载中...</>
                            ) : "🔄 获取列表"}
                          </button>
                        </div>
                        
                        {/* 错误提示 */}
                        {selectedProviderId && modelFetchError[selectedProviderId] && (
                          <div className="models-error">
                            ⚠️ {modelFetchError[selectedProviderId]}
                          </div>
                        )}
                        
                        {/* 模型列表 */}
                        {selectedProviderId && providerModels[selectedProviderId] && providerModels[selectedProviderId].length > 0 && (
                          <div className="models-list">
                            {providerModels[selectedProviderId].map(model => {
                              const isAdded = selectedProvider.selected_models?.includes(model.id) || false;
                              return (
                                <div 
                                  key={model.id} 
                                  className={`model-item ${isAdded ? 'added' : ''}`}
                                  title={model.description || model.id}
                                >
                                  <span className="model-name">{model.name}</span>
                                  {model.context_window && (
                                    <span className="model-context">
                                      {model.context_window >= 1000000 
                                        ? `${(model.context_window / 1000000).toFixed(1)}M` 
                                        : `${Math.round(model.context_window / 1000)}K`}
                                    </span>
                                  )}
                                  <button
                                    className={`btn-add-model ${isAdded ? 'added' : ''}`}
                                    onClick={() => !isAdded && dispatch({ type: 'TOGGLE_MODEL_SELECTION', providerId: selectedProviderId, modelId: model.id })}
                                    disabled={isAdded}
                                    title={isAdded ? "已添加" : "添加到收藏"}
                                  >
                                    {isAdded ? '✓' : '+'}
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                        
                        {/* 未获取提示 */}
                        {selectedProviderId && (!providerModels[selectedProviderId] || providerModels[selectedProviderId].length === 0) && !modelFetchError[selectedProviderId] && (
                          <div className="models-empty">
                            {selectedProvider.api_key 
                              ? "💡 点击「获取列表」按钮加载可用模型" 
                              : "🔒 填写 API Key 后可获取模型列表"}
                          </div>
                        )}
                      </div>

                      <div className="test-section">
                        <div className="test-row">
                          <button
                            onClick={() => selectedProviderId && handleTestProvider(selectedProviderId)}
                            disabled={testingProviderId === selectedProviderId || !selectedProvider.api_key}
                            className="btn-primary btn-test"
                          >
                            {testingProviderId === selectedProviderId ? (
                              <><span className="spinner-small"></span> 测试中...</>
                            ) : "⚡ 测试连接"}
                          </button>
                          <span className="test-hint">发送简单请求验证配置</span>
                        </div>
                        
                        {selectedProviderId && testResults[selectedProviderId] && (
                          <div className={`test-result ${testResults[selectedProviderId].success ? 'success' : 'error'}`}>
                            <div className="result-header">
                              {testResults[selectedProviderId].success ? "✅ 连接成功" : "❌ 连接失败"}
                            </div>
                            <div className="result-details">{testResults[selectedProviderId].message}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-icon">🔌</span>
                      <p>从左侧选择或添加一个 AI 服务商</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: 功能路由 */}
          {tab === "models" && (
            <div className="tab-content fade-in">
              <div className="section-header">
                <h3>🧠 AI 能力路由配置</h3>
                <p>为不同的 AI 功能分配专属模型。未配置的功能将使用全局默认服务商。每个功能可独立设置超时时间和思考模式。</p>
              </div>
              
              {/* 高优先级 */}
              <div className="capability-group">
                <div className="group-header high">
                  <span className="group-icon">🔴</span>
                  <span className="group-title">核心推演</span>
                  <span className="group-desc">主要叙事与关键决策，推荐使用高性能模型</span>
                </div>
                <div className="capabilities-grid">
                  {AI_CAPABILITIES.high.map(cap => (
                    <CapabilityCard 
                      key={cap.key}
                      cap={cap}
                      priority="high"
                      route={form.capability_routes[cap.key] || {}}
                      providers={form.providers}
                      defaultProviderId={form.default_provider_id}
                      defaultModel={form.default_model}
                      onUpdate={(field, value) => dispatch({ type: 'UPDATE_ROUTE', capKey: cap.key, field, value })}
                      providerModels={providerModels}
                      loadBalanceEnabled={form.load_balance_enabled}
                      onToggleProvider={(providerId) => dispatch({ type: 'TOGGLE_ROUTE_PROVIDER', capKey: cap.key, providerId })}
                    />
                  ))}
                </div>
              </div>

              {/* 中优先级 */}
              <div className="capability-group">
                <div className="group-header medium">
                  <span className="group-icon">🟡</span>
                  <span className="group-title">物种演化</span>
                  <span className="group-desc">新物种诞生与基因分化判定</span>
                </div>
                <div className="capabilities-grid">
                  {AI_CAPABILITIES.medium.map(cap => (
                    <CapabilityCard 
                      key={cap.key}
                      cap={cap}
                      priority="medium"
                      route={form.capability_routes[cap.key] || {}}
                      providers={form.providers}
                      defaultProviderId={form.default_provider_id}
                      defaultModel={form.default_model}
                      onUpdate={(field, value) => dispatch({ type: 'UPDATE_ROUTE', capKey: cap.key, field, value })}
                      providerModels={providerModels}
                      loadBalanceEnabled={form.load_balance_enabled}
                      onToggleProvider={(providerId) => dispatch({ type: 'TOGGLE_ROUTE_PROVIDER', capKey: cap.key, providerId })}
                    />
                  ))}
                </div>
              </div>

              {/* 低优先级 */}
              <div className="capability-group">
                <div className="group-header low">
                  <span className="group-icon">🟢</span>
                  <span className="group-title">辅助功能</span>
                  <span className="group-desc">迁徙、命名等轻量任务，可使用经济模型</span>
                </div>
                <div className="capabilities-grid">
                  {AI_CAPABILITIES.low.map(cap => (
                    <CapabilityCard 
                      key={cap.key}
                      cap={cap}
                      priority="low"
                      route={form.capability_routes[cap.key] || {}}
                      providers={form.providers}
                      defaultProviderId={form.default_provider_id}
                      defaultModel={form.default_model}
                      onUpdate={(field, value) => dispatch({ type: 'UPDATE_ROUTE', capKey: cap.key, field, value })}
                      providerModels={providerModels}
                      loadBalanceEnabled={form.load_balance_enabled}
                      onToggleProvider={(providerId) => dispatch({ type: 'TOGGLE_ROUTE_PROVIDER', capKey: cap.key, providerId })}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: 向量记忆 */}
          {tab === "memory" && (
            <div className="tab-content fade-in">
              <div className="section-header">
                <h3>🧬 海马体：向量记忆</h3>
                <p>配置文本向量化服务，用于语义搜索和记忆检索。</p>
              </div>
              
              <div className="memory-layout">
                <div className="memory-main">
                  <div className="tip-box info">
                    💡 向量服务将文本转换为高维向量，用于语义相似度匹配。请确保选择的服务商支持 Embedding API。
                  </div>

                  <div className="form-fields">
                    <label className="form-field">
                      <span className="field-label">服务商</span>
                      <select
                        className="field-input"
                        value={form.embedding_provider_id ?? ""}
                        onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'embedding_provider_id', value: e.target.value || null })}
                      >
                        <option value="">使用全局默认</option>
                        {Object.values(form.providers).map(p => (
                          <option key={p.id} value={p.id}>{getProviderLogo(p)} {p.name}</option>
                        ))}
                      </select>
                    </label>

                    <label className="form-field">
                      <span className="field-label">Embedding 模型</span>
                      <div className="input-with-presets">
                        <input
                          className="field-input"
                          type="text"
                          value={form.embedding_model ?? ""}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'embedding_model', value: e.target.value })}
                          placeholder="Qwen/Qwen3-Embedding-4B"
                        />
                        <div className="preset-buttons">
                          {EMBEDDING_PRESETS.map(preset => (
                            <Tooltip key={preset.id} content={`${preset.dimensions} 维向量`}>
                              <button
                                type="button"
                                className={`preset-btn ${form.embedding_model === preset.name ? 'active' : ''}`}
                                onClick={() => dispatch({ type: 'UPDATE_GLOBAL', field: 'embedding_model', value: preset.name })}
                              >
                                {preset.id}
                              </button>
                            </Tooltip>
                          ))}
                        </div>
                      </div>
                    </label>

                    <label className="form-field">
                      <span className="field-label">向量维度 (可选)</span>
                      <input
                        className="field-input"
                        type="number"
                        value={form.embedding_dimensions ?? ""}
                        onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'embedding_dimensions', value: e.target.value ? parseInt(e.target.value) : null })}
                        placeholder="自动检测"
                      />
                    </label>
                  </div>
                  
                  <div className="test-section">
                    <button
                      type="button"
                      onClick={handleTestEmbedding}
                      disabled={testingEmbedding}
                      className="btn-primary btn-test full-width"
                    >
                      {testingEmbedding ? "🔄 连接中..." : "🧬 测试向量服务"}
                    </button>
                    
                    {testResultEmbedding && (
                      <div className={`test-result ${testResultEmbedding.success ? 'success' : 'error'}`}>
                        <div className="result-header">
                          <span>{testResultEmbedding.success ? "✅ 连接成功" : "❌ 连接失败"}</span>
                        </div>
                        {testResultEmbedding.details && (
                          <div className="result-details">{testResultEmbedding.details}</div>
                        )}
                        {!testResultEmbedding.success && testResultEmbedding.message && (
                          <div className="result-details">{testResultEmbedding.message}</div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* 向量记忆统计 */}
                <div className="memory-stats">
                  <h4>📊 缓存状态</h4>
                  <div className="stats-grid">
                    <div className="stat-item">
                      <span className="stat-label">缓存条目</span>
                      <span className="stat-value">--</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">占用空间</span>
                      <span className="stat-value">--</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">命中率</span>
                      <span className="stat-value">--</span>
                    </div>
                  </div>
                  <button className="btn-secondary btn-clear-cache" disabled>
                    🗑️ 清理缓存
                  </button>
                  <p className="stats-hint">统计功能开发中...</p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: 自动保存 */}
          {tab === "autosave" && (
            <div className="tab-content fade-in">
              <div className="section-header">
                <h3>💾 自动保存设置</h3>
                <p>配置游戏自动保存功能，确保您的进度不会丢失。</p>
              </div>
              
              <div className="memory-layout">
                <div className="memory-main">
                  <div className="tip-box info">
                    💡 自动保存会在每个回合结束后自动创建存档，存档名称格式为 <code>autosave_存档名_时间戳</code>。旧的自动保存会被自动清理。
                  </div>

                  <div className="form-fields">
                    {/* 启用自动保存 */}
                    <div className="form-field toggle-field">
                      <label className="toggle-container">
                        <input
                          type="checkbox"
                          checked={form.autosave_enabled ?? true}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_enabled', value: e.target.checked })}
                        />
                        <span className="toggle-slider"></span>
                        <span className="toggle-label">启用自动保存</span>
                      </label>
                      <span className="field-hint">每回合结束后自动保存游戏进度</span>
                    </div>

                    {/* 保存间隔 */}
                    <label className="form-field">
                      <span className="field-label">保存间隔</span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="1"
                          max="100"
                          value={form.autosave_interval ?? 1}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_interval', value: parseInt(e.target.value) || 1 })}
                          disabled={!(form.autosave_enabled ?? true)}
                        />
                        <span className="unit-label">回合</span>
                      </div>
                      <span className="field-hint">每隔多少回合自动保存一次（默认：每回合）</span>
                    </label>

                    {/* 最大保存槽位 */}
                    <label className="form-field">
                      <span className="field-label">最大保存数量</span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="1"
                          max="50"
                          value={form.autosave_max_slots ?? 5}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_max_slots', value: parseInt(e.target.value) || 5 })}
                          disabled={!(form.autosave_enabled ?? true)}
                        />
                        <span className="unit-label">个</span>
                      </div>
                      <span className="field-hint">保留最近的自动保存数量，超出后自动删除旧存档</span>
                    </label>
                  </div>

                  {/* 预设配置 */}
                  <div className="preset-section">
                    <h4>快速配置</h4>
                    <div className="preset-buttons autosave-presets">
                      <button
                        type="button"
                        className={`preset-btn ${(form.autosave_interval ?? 1) === 1 && (form.autosave_max_slots ?? 5) === 5 ? 'active' : ''}`}
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_enabled', value: true });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_interval', value: 1 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_max_slots', value: 5 });
                        }}
                      >
                        🔒 安全模式
                        <span className="preset-desc">每回合保存，保留5个</span>
                      </button>
                      <button
                        type="button"
                        className={`preset-btn ${(form.autosave_interval ?? 1) === 5 && (form.autosave_max_slots ?? 5) === 3 ? 'active' : ''}`}
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_enabled', value: true });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_interval', value: 5 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_max_slots', value: 3 });
                        }}
                      >
                        ⚖️ 平衡模式
                        <span className="preset-desc">每5回合保存，保留3个</span>
                      </button>
                      <button
                        type="button"
                        className={`preset-btn ${(form.autosave_interval ?? 1) === 10 && (form.autosave_max_slots ?? 5) === 2 ? 'active' : ''}`}
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_enabled', value: true });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_interval', value: 10 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_max_slots', value: 2 });
                        }}
                      >
                        🚀 性能模式
                        <span className="preset-desc">每10回合保存，保留2个</span>
                      </button>
                      <button
                        type="button"
                        className={`preset-btn ${!(form.autosave_enabled ?? true) ? 'active' : ''}`}
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'autosave_enabled', value: false });
                        }}
                      >
                        ❌ 关闭
                        <span className="preset-desc">禁用自动保存</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 自动保存说明 */}
                <div className="memory-stats">
                  <h4>📝 说明</h4>
                  <div className="info-list">
                    <div className="info-item">
                      <span className="info-icon">📁</span>
                      <div>
                        <strong>存档位置</strong>
                        <p>data/saves/autosave_*</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">🔄</span>
                      <div>
                        <strong>自动清理</strong>
                        <p>超出数量限制的旧存档会被自动删除</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">⏱️</span>
                      <div>
                        <strong>保存时机</strong>
                        <p>在每回合AI推演完成后执行</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">📊</span>
                      <div>
                        <strong>当前状态</strong>
                        <p style={{ color: (form.autosave_enabled ?? true) ? '#10b981' : '#ef4444' }}>
                          {(form.autosave_enabled ?? true) ? '✅ 已启用' : '❌ 已禁用'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: 性能调优 */}
          {tab === "performance" && (
            <div className="tab-content fade-in">
              <div className="section-header">
                <h3>⚡ AI 推演性能调优</h3>
                <p>调整 AI 调用的超时时间，平衡响应速度与推演质量。</p>
              </div>
              
              <div className="memory-layout">
                <div className="memory-main">
                  {/* 回合报告 LLM 开关 */}
                  <div className="feature-toggle-card">
                    <div className="toggle-card-content">
                      <div className="toggle-info">
                        <span className="toggle-icon">📜</span>
                        <div className="toggle-text">
                          <span className="toggle-title">回合报告（LLM）</span>
                          <span className="toggle-desc">生成每回合的整体生态总结与演化叙事</span>
                        </div>
                      </div>
                      <label className="toggle-switch">
                        <input 
                          type="checkbox" 
                          checked={form.turn_report_llm_enabled ?? true}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'turn_report_llm_enabled', value: e.target.checked })}
                        />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>
                    {!(form.turn_report_llm_enabled ?? true) && (
                      <div className="toggle-hint">
                        💡 关闭后使用简单模板生成回合摘要，节省 Token
                      </div>
                    )}
                  </div>

                  {/* AI 物种叙事开关 */}
                  <div className="feature-toggle-card">
                    <div className="toggle-card-content">
                      <div className="toggle-info">
                        <span className="toggle-icon">📖</span>
                        <div className="toggle-text">
                          <span className="toggle-title">AI 物种叙事</span>
                          <span className="toggle-desc">为每个物种单独生成演化故事和行为描述</span>
                        </div>
                      </div>
                      <label className="toggle-switch">
                        <input 
                          type="checkbox" 
                          checked={form.ai_narrative_enabled ?? false}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_enabled', value: e.target.checked })}
                        />
                        <span className="toggle-slider"></span>
                      </label>
                    </div>
                    {!form.ai_narrative_enabled && (
                      <div className="toggle-hint">
                        💡 关闭后可节省 API 调用，推演速度更快
                      </div>
                    )}
                  </div>
                  
                  {/* 开关区别说明 */}
                  <div className="tip-box" style={{ marginTop: '8px' }}>
                    <strong>💡 两个开关的区别：</strong>
                    <ul style={{ margin: '8px 0 0 16px', padding: 0, fontSize: '0.85rem', opacity: 0.9 }}>
                      <li><strong>回合报告（LLM）</strong>：控制整回合的宏观总结，汇总所有物种的生态变化</li>
                      <li><strong>AI 物种叙事</strong>：控制单个物种的微观描述，生成个体行为和适应故事</li>
                    </ul>
                  </div>

                  <div className="tip-box info">
                    💡 超时时间决定了系统等待 AI 响应的最长时间。如果 AI 在超时前未能完成，系统将使用规则降级处理。
                    <br/><br/>
                    <strong>建议配置：</strong>
                    <ul style={{ margin: '8px 0 0 16px', padding: 0 }}>
                      <li>网络稳定时可设置较短的超时（30-60秒）</li>
                      <li>使用 DeepSeek-R1 等思考模型时建议增加超时（90-180秒）</li>
                      <li>物种数量多时建议增加整体批量超时</li>
                    </ul>
                  </div>

                  <div className="form-fields">
                    {/* 单物种评估超时 */}
                    <label className="form-field">
                      <span className="field-label">
                        🦎 单物种评估超时
                        <span className="field-hint-inline">（每个物种的AI分析时间上限）</span>
                      </span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="10"
                          max="300"
                          value={form.ai_species_eval_timeout ?? 60}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_species_eval_timeout', value: parseInt(e.target.value) || 60 })}
                        />
                        <span className="unit-label">秒</span>
                      </div>
                      <span className="field-hint">单个物种状态评估的最长等待时间，超时后使用规则降级</span>
                    </label>

                    {/* 批量评估总超时 */}
                    <label className="form-field">
                      <span className="field-label">
                        🦋 批量评估总超时
                        <span className="field-hint-inline">（所有物种评估的总时间上限）</span>
                      </span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="30"
                          max="600"
                          value={form.ai_batch_eval_timeout ?? 180}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_batch_eval_timeout', value: parseInt(e.target.value) || 180 })}
                        />
                        <span className="unit-label">秒</span>
                      </div>
                      <span className="field-hint">整体 AI 综合状态评估的最长等待时间</span>
                    </label>

                    {/* 叙事生成超时 */}
                    <label className="form-field">
                      <span className="field-label">
                        📖 叙事生成超时
                        <span className="field-hint-inline">（物种故事生成时间上限）</span>
                      </span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="10"
                          max="300"
                          value={form.ai_narrative_timeout ?? 60}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_timeout', value: parseInt(e.target.value) || 60 })}
                        />
                        <span className="unit-label">秒</span>
                      </div>
                      <span className="field-hint">每个物种叙事/故事生成的最长等待时间</span>
                    </label>

                    {/* 物种分化超时 */}
                    <label className="form-field">
                      <span className="field-label">
                        🧬 物种分化超时
                        <span className="field-hint-inline">（新物种诞生判定时间上限）</span>
                      </span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="30"
                          max="300"
                          value={form.ai_speciation_timeout ?? 120}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_speciation_timeout', value: parseInt(e.target.value) || 120 })}
                        />
                        <span className="unit-label">秒</span>
                      </div>
                      <span className="field-hint">AI判定物种分化的最长等待时间</span>
                    </label>

                    {/* AI 并发限制 */}
                    <label className="form-field">
                      <span className="field-label">
                        🔀 AI 并发数量
                        <span className="field-hint-inline">（同时进行的AI请求数）</span>
                      </span>
                      <div className="input-with-unit">
                        <input
                          className="field-input"
                          type="number"
                          min="1"
                          max="50"
                          value={form.ai_concurrency_limit ?? 15}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_concurrency_limit', value: parseInt(e.target.value) || 15 })}
                        />
                        <span className="unit-label">个</span>
                      </div>
                      <span className="field-hint">同时处理的AI请求数量，过高可能触发API限流</span>
                    </label>
                  </div>

                  {/* 负载均衡配置 */}
                  <div className="load-balance-section">
                    <h4>⚖️ 多服务商负载均衡</h4>
                    <div className="tip-box info">
                      💡 启用后可为每个AI能力配置多个服务商，并行请求会自动分散到不同服务商，提高整体吞吐量并避免单一服务商限流。
                    </div>
                    
                    <div className="form-field toggle-field">
                      <label className="toggle-container">
                        <input
                          type="checkbox"
                          checked={form.load_balance_enabled ?? false}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'load_balance_enabled', value: e.target.checked })}
                        />
                        <span className="toggle-label">启用负载均衡</span>
                      </label>
                      <span className="field-hint">在「智能路由」页面为每个能力选择多个服务商</span>
                    </div>

                    {form.load_balance_enabled && (
                      <label className="form-field">
                        <span className="field-label">负载均衡策略</span>
                        <select
                          className="field-input"
                          value={form.load_balance_strategy ?? "round_robin"}
                          onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'load_balance_strategy', value: e.target.value })}
                        >
                          <option value="round_robin">🔄 轮询 - 依次使用每个服务商</option>
                          <option value="random">🎲 随机 - 随机选择服务商</option>
                          <option value="least_latency">⚡ 最低延迟 - 优先使用响应最快的服务商</option>
                        </select>
                        <span className="field-hint">选择如何在多个服务商之间分配请求</span>
                      </label>
                    )}
                  </div>

                  {/* 快速预设 */}
                  <div className="preset-section">
                    <h4>快速配置</h4>
                    <div className="preset-buttons autosave-presets">
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_species_eval_timeout', value: 30 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_batch_eval_timeout', value: 90 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_timeout', value: 30 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_speciation_timeout', value: 60 });
                        }}
                      >
                        🚀 极速模式
                        <span className="preset-desc">快速降级，适合测试</span>
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_species_eval_timeout', value: 60 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_batch_eval_timeout', value: 180 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_timeout', value: 60 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_speciation_timeout', value: 120 });
                        }}
                      >
                        ⚖️ 默认模式
                        <span className="preset-desc">平衡速度与质量</span>
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_species_eval_timeout', value: 120 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_batch_eval_timeout', value: 360 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_timeout', value: 120 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_speciation_timeout', value: 180 });
                        }}
                      >
                        🧠 思考模式
                        <span className="preset-desc">适合DeepSeek-R1等</span>
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_species_eval_timeout', value: 180 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_batch_eval_timeout', value: 600 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_narrative_timeout', value: 180 });
                          dispatch({ type: 'UPDATE_GLOBAL', field: 'ai_speciation_timeout', value: 300 });
                        }}
                      >
                        🐢 耐心模式
                        <span className="preset-desc">最大等待，减少降级</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 右侧说明 */}
                <div className="memory-stats">
                  <h4>📝 超时机制说明</h4>
                  <div className="info-list">
                    <div className="info-item">
                      <span className="info-icon">⏱️</span>
                      <div>
                        <strong>超时降级</strong>
                        <p>当AI超时后，系统将使用基于规则的快速评估代替</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">🔄</span>
                      <div>
                        <strong>并行处理</strong>
                        <p>多个物种的评估会并行进行，提高整体效率</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">💡</span>
                      <div>
                        <strong>流式心跳</strong>
                        <p>AI处理中会发送心跳信号，前端可实时感知进度</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">⚠️</span>
                      <div>
                        <strong>注意</strong>
                        <p>过短的超时会导致更多规则降级，叙事质量可能下降</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: 分化设置 */}
          {tab === "speciation" && (
            <div className="tab-content fade-in">
              <div className="section-header">
                <h3>🧬 物种分化参数</h3>
                <p>调整新物种产生的频率与时机。数值越低 = 分化越容易发生。</p>
              </div>
              
              <div className="memory-layout">
                <div className="memory-main">
                  {/* 快速预设 */}
                  <div className="preset-section">
                    <h4>🎮 快速配置</h4>
                    <div className="preset-buttons autosave-presets">
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_SPECIATION', updates: {
                            early_game_turns: 15,
                            early_threshold_min_factor: 0.2,
                            early_threshold_decay_rate: 0.1,
                            pressure_threshold_early: 0.3,
                            resource_threshold_early: 0.25,
                            radiation_early_bonus: 0.2,
                            no_isolation_penalty_early: 0.9,
                          }});
                        }}
                      >
                        🌱 爆发模式
                        <span className="preset-desc">前15回合疯狂分化，快速建立生态多样性</span>
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_SPECIATION', updates: {
                            early_game_turns: 10,
                            early_threshold_min_factor: 0.3,
                            early_threshold_decay_rate: 0.07,
                            pressure_threshold_early: 0.4,
                            resource_threshold_early: 0.35,
                            radiation_early_bonus: 0.15,
                            no_isolation_penalty_early: 0.8,
                          }});
                        }}
                      >
                        ⚖️ 平衡模式
                        <span className="preset-desc">推荐设置，前10回合适度鼓励分化</span>
                      </button>
                      <button
                        type="button"
                        className="preset-btn"
                        onClick={() => {
                          dispatch({ type: 'UPDATE_SPECIATION', updates: {
                            early_game_turns: 5,
                            early_threshold_min_factor: 0.5,
                            early_threshold_decay_rate: 0.03,
                            pressure_threshold_early: 0.6,
                            resource_threshold_early: 0.5,
                            radiation_early_bonus: 0.05,
                            no_isolation_penalty_early: 0.6,
                          }});
                        }}
                      >
                        🔬 写实模式
                        <span className="preset-desc">分化困难，需要真正的环境压力才会演化</span>
                      </button>
                    </div>
                  </div>

                  <div className="tip-box info">
                    💡 <strong>什么是分化？</strong> 一个物种分裂成两个或多个新物种的过程。游戏早期会自动降低分化门槛，让生态系统快速多样化。后期条件会收紧，需要真正的环境压力才能触发分化。
                  </div>

                  {/* 基础参数 */}
                  <div className="speciation-section">
                    <h4>🎯 基础参数</h4>
                    <div className="form-fields">
                      <label className="form-field">
                        <span className="field-label">
                          分化冷却期
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="10"
                            value={form.speciation?.cooldown_turns ?? 0}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { cooldown_turns: parseInt(e.target.value) || 0 } })}
                          />
                          <span className="unit-label">回合</span>
                        </div>
                        <span className="field-hint">物种分化后，需等待N回合才能再次分化。设为0表示无冷却限制。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          生态系统物种上限
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="10"
                            max="200"
                            value={form.speciation?.species_soft_cap ?? 60}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { species_soft_cap: parseInt(e.target.value) || 60 } })}
                          />
                          <span className="unit-label">种</span>
                        </div>
                        <span className="field-hint">当物种数量接近此值时，新分化会越来越困难。防止物种爆炸式增长。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          基础分化成功率
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.base_speciation_rate ?? 0.5}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { base_speciation_rate: parseFloat(e.target.value) || 0.5 } })}
                          />
                          <span className="unit-label">（0-1）</span>
                        </div>
                        <span className="field-hint">满足所有条件后，分化实际发生的概率。0.5 = 50%成功率。</span>
                      </label>
                    </div>
                  </div>

                  {/* 早期优化参数 */}
                  <div className="speciation-section">
                    <h4>🌅 早期阶段设置</h4>
                    <div className="tip-box">
                      💡 游戏初期物种较少，这些设置会暂时降低分化难度，帮助快速建立多样化的生态系统。
                    </div>
                    <div className="form-fields">
                      <label className="form-field">
                        <span className="field-label">
                          早期阶段持续时间
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="50"
                            value={form.speciation?.early_game_turns ?? 10}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { early_game_turns: parseInt(e.target.value) || 10 } })}
                          />
                          <span className="unit-label">回合</span>
                        </div>
                        <span className="field-hint">前N回合视为"早期阶段"，使用更宽松的分化规则。之后恢复正常难度。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          种群门槛最低倍率
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0.1"
                            max="1"
                            step="0.05"
                            value={form.speciation?.early_threshold_min_factor ?? 0.3}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { early_threshold_min_factor: parseFloat(e.target.value) || 0.3 } })}
                          />
                          <span className="unit-label">（0-1）</span>
                        </div>
                        <span className="field-hint">早期阶段种群要求最低可降至正常值的多少倍。例如0.3表示门槛最低降到30%。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          门槛每回合恢复速度
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0.01"
                            max="0.2"
                            step="0.01"
                            value={form.speciation?.early_threshold_decay_rate ?? 0.07}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { early_threshold_decay_rate: parseFloat(e.target.value) || 0.07 } })}
                          />
                          <span className="unit-label">（0-0.2）</span>
                        </div>
                        <span className="field-hint">每回合门槛恢复多少。0.07表示：第1回合门槛=93%，第5回合=65%，第10回合=30%。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          无冷却期回合数
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="20"
                            value={form.speciation?.early_skip_cooldown_turns ?? 5}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { early_skip_cooldown_turns: parseInt(e.target.value) || 5 } })}
                          />
                          <span className="unit-label">回合</span>
                        </div>
                        <span className="field-hint">前N回合完全忽略分化冷却期，允许物种连续分化。</span>
                      </label>
                    </div>
                  </div>

                  {/* 触发阈值 */}
                  <div className="speciation-section">
                    <h4>📊 环境压力触发阈值</h4>
                    <div className="tip-box">
                      💡 只有当环境压力超过阈值时，才可能触发分化。数值越低 = 越容易达到分化条件。
                    </div>
                    <div className="form-fields two-column">
                      <div className="column">
                        <h5 style={{margin: '0 0 8px', color: 'var(--accent-color)'}}>🌅 早期阶段（更宽松）</h5>
                        <label className="form-field compact">
                          <span className="field-label">环境压力</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.pressure_threshold_early ?? 0.4}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { pressure_threshold_early: parseFloat(e.target.value) || 0.4 } })}
                          />
                        </label>
                        <label className="form-field compact">
                          <span className="field-label">资源竞争</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.resource_threshold_early ?? 0.35}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { resource_threshold_early: parseFloat(e.target.value) || 0.35 } })}
                          />
                        </label>
                        <label className="form-field compact">
                          <span className="field-label">演化潜力</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.evo_potential_threshold_early ?? 0.5}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { evo_potential_threshold_early: parseFloat(e.target.value) || 0.5 } })}
                          />
                        </label>
                      </div>
                      <div className="column">
                        <h5 style={{margin: '0 0 8px', color: 'var(--text-secondary)'}}>🌙 后期阶段（更严格）</h5>
                        <label className="form-field compact">
                          <span className="field-label">环境压力</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.pressure_threshold_late ?? 0.7}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { pressure_threshold_late: parseFloat(e.target.value) || 0.7 } })}
                          />
                        </label>
                        <label className="form-field compact">
                          <span className="field-label">资源竞争</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.resource_threshold_late ?? 0.6}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { resource_threshold_late: parseFloat(e.target.value) || 0.6 } })}
                          />
                        </label>
                        <label className="form-field compact">
                          <span className="field-label">演化潜力</span>
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.evo_potential_threshold_late ?? 0.7}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { evo_potential_threshold_late: parseFloat(e.target.value) || 0.7 } })}
                          />
                        </label>
                      </div>
                    </div>
                    <span className="field-hint" style={{display: 'block', marginTop: '8px'}}>
                      <strong>环境压力</strong>：气候变化、灾难等外部因素 | <strong>资源竞争</strong>：食物/栖息地争夺程度 | <strong>演化潜力</strong>：物种本身的变异能力
                    </span>
                  </div>

                  {/* 辐射演化 */}
                  <div className="speciation-section">
                    <h4>☀️ 辐射演化（繁荣分化）</h4>
                    <div className="tip-box">
                      💡 当物种非常繁荣、没有明显压力时，也可能自然分化出新种。这是一种"太成功导致分裂"的机制。
                    </div>
                    <div className="form-fields">
                      <label className="form-field">
                        <span className="field-label">
                          辐射演化基础概率
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="0.5"
                            step="0.01"
                            value={form.speciation?.radiation_base_chance ?? 0.05}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { radiation_base_chance: parseFloat(e.target.value) || 0.05 } })}
                          />
                          <span className="unit-label">（0-0.5）</span>
                        </div>
                        <span className="field-hint">即使没有环境压力，繁荣物种每回合也有此概率触发分化。0.05 = 5%。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          早期额外加成
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="0.5"
                            step="0.01"
                            value={form.speciation?.radiation_early_bonus ?? 0.15}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { radiation_early_bonus: parseFloat(e.target.value) || 0.15 } })}
                          />
                          <span className="unit-label">（0-0.5）</span>
                        </div>
                        <span className="field-hint">早期阶段额外增加的辐射演化概率。0.15 = 额外+15%概率。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          无地理隔离时的概率衰减（早期）
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.no_isolation_penalty_early ?? 0.8}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { no_isolation_penalty_early: parseFloat(e.target.value) || 0.8 } })}
                          />
                          <span className="unit-label">（0-1）</span>
                        </div>
                        <span className="field-hint">物种分布连续（无地理隔离）时，分化概率乘以此系数。0.8表示概率降为80%。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          无地理隔离时的概率衰减（后期）
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={form.speciation?.no_isolation_penalty_late ?? 0.5}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { no_isolation_penalty_late: parseFloat(e.target.value) || 0.5 } })}
                          />
                          <span className="unit-label">（0-1）</span>
                        </div>
                        <span className="field-hint">后期阶段无隔离时的衰减更严重。0.5表示概率降为50%。</span>
                      </label>
                    </div>
                  </div>

                  {/* 候选地块筛选 */}
                  <div className="speciation-section">
                    <h4>🗺️ 分化候选条件</h4>
                    <div className="tip-box">
                      💡 只有满足这些条件的栖息地才会被考虑作为分化发生地。过于稀疏或死亡率极端的地区不适合产生新物种。
                    </div>
                    <div className="form-fields">
                      <label className="form-field">
                        <span className="field-label">
                          地块最低种群数
                        </span>
                        <div className="input-with-unit">
                          <input
                            className="field-input"
                            type="number"
                            min="10"
                            max="500"
                            value={form.speciation?.candidate_tile_min_pop ?? 50}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { candidate_tile_min_pop: parseInt(e.target.value) || 50 } })}
                          />
                          <span className="unit-label">个体</span>
                        </div>
                        <span className="field-hint">地块上至少要有这么多个体，才能成为分化候选地。数值越低，小种群也能分化。</span>
                      </label>

                      <label className="form-field">
                        <span className="field-label">
                          允许分化的死亡率区间
                        </span>
                        <div className="range-inputs">
                          <input
                            className="field-input small"
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={form.speciation?.candidate_tile_death_rate_min ?? 0.02}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { candidate_tile_death_rate_min: parseFloat(e.target.value) || 0.02 } })}
                          />
                          <span className="range-separator">~</span>
                          <input
                            className="field-input small"
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={form.speciation?.candidate_tile_death_rate_max ?? 0.75}
                            onChange={(e) => dispatch({ type: 'UPDATE_SPECIATION', updates: { candidate_tile_death_rate_max: parseFloat(e.target.value) || 0.75 } })}
                          />
                        </div>
                        <span className="field-hint">死亡率太低（太安逸）或太高（濒临灭绝）都不利于分化。默认2%-75%。</span>
                      </label>
                    </div>
                  </div>
                </div>

                {/* 右侧说明 */}
                <div className="memory-stats">
                  <h4>📖 名词解释</h4>
                  <div className="info-list">
                    <div className="info-item">
                      <span className="info-icon">🌍</span>
                      <div>
                        <strong>地理隔离分化</strong>
                        <p>山脉、海洋等物理屏障将种群分开，各自演化成新物种。最常见的分化方式。</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">🌿</span>
                      <div>
                        <strong>生态隔离分化</strong>
                        <p>同一区域内，因食物、作息等生态位差异导致的分化。如白天/夜间活动的物种分化。</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">☀️</span>
                      <div>
                        <strong>辐射演化</strong>
                        <p>繁荣物种自然分化，就像企业做大后会分拆子公司。概率较低但持续进行。</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">📈</span>
                      <div>
                        <strong>环境压力</strong>
                        <p>气候变化、灾难、栖息地变化等。高压力促进演化，但过高会导致灭绝。</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">⚔️</span>
                      <div>
                        <strong>资源竞争</strong>
                        <p>食物和栖息地的争夺程度。激烈竞争促使物种寻找新的生态位。</p>
                      </div>
                    </div>
                    <div className="info-item">
                      <span className="info-icon">🧬</span>
                      <div>
                        <strong>演化潜力</strong>
                        <p>物种本身的遗传多样性和变异能力。高潜力的物种更容易产生新变种。</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* 底部操作栏 */}
          <div className="settings-footer">
            <div className="footer-left">
              <button onClick={handleExport} className="btn-secondary btn-small">
                📤 导出
              </button>
              <button onClick={handleImport} className="btn-secondary btn-small">
                📥 导入
              </button>
              <button onClick={handleReset} className="btn-secondary btn-small btn-danger-text">
                🔄 重置
              </button>
            </div>
            
            {saveSuccess && (
              <div className="save-success">✅ 配置已保存</div>
            )}
            {Object.keys(validationErrors).length > 0 && (
              <div className="validation-warning">
                ⚠️ 部分配置未完成
              </div>
            )}
            
            <div className="footer-buttons">
              <span className="shortcut-hint">Ctrl+S</span>
              <button onClick={onClose} className="btn-secondary">取消</button>
              <button onClick={handleSave} className="btn-primary" disabled={saving}>
                {saving ? "保存中..." : "保存配置"}
              </button>
            </div>
          </div>
        </div>
      </div>
      
      {/* 确认对话框 */}
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => dispatch({ type: 'CLOSE_CONFIRM' })}
      />
    </GamePanel>
  );
}

// ========== 子组件 ==========

function NavButton({ active, onClick, icon, label, desc }: { 
  active: boolean; 
  onClick: () => void; 
  icon: string; 
  label: string; 
  desc: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`nav-button ${active ? 'active' : ''}`}
      aria-current={active ? 'page' : undefined}
    >
      <span className="nav-icon">{icon}</span>
      <div className="nav-text">
        <div className="nav-label">{label}</div>
        <div className="nav-desc">{desc}</div>
      </div>
    </button>
  );
}

function CapabilityCard({ 
  cap, 
  priority,
  route, 
  providers, 
  defaultProviderId,
  defaultModel,
  onUpdate,
  providerModels,
  loadBalanceEnabled,
  onToggleProvider,
}: {
  cap: { key: string; label: string; desc: string; defaultTimeout: number };
  priority: 'high' | 'medium' | 'low';
  route: Partial<CapabilityRouteConfig>;
  providers: Record<string, ProviderConfig>;
  defaultProviderId?: string | null;
  defaultModel?: string | null;
  onUpdate: (field: keyof CapabilityRouteConfig, value: any) => void;
  providerModels?: Record<string, ModelInfo[]>;
  loadBalanceEnabled?: boolean;
  onToggleProvider?: (providerId: string) => void;
}) {
  const effectiveProviderId = route.provider_id || defaultProviderId;
  const routeProvider = effectiveProviderId ? providers[effectiveProviderId] : null;
  
  const hasThinking = supportsThinking(routeProvider);
  const poolProviderIds = route.provider_ids || [];
  
  // 获取已获取的模型列表
  const fetchedModels = effectiveProviderId && providerModels ? providerModels[effectiveProviderId] : undefined;
  const hasFetchedModels = fetchedModels && fetchedModels.length > 0;
  const isKnownModel = hasFetchedModels && fetchedModels.some(m => m.id === route.model);

  // 有效的服务商列表（有API Key的）
  const validProviders = Object.values(providers).filter(p => !!p.api_key);

  // 获取用户已选择的模型
  const selectedModels = routeProvider?.selected_models || [];
  const hasSelectedModels = selectedModels.length > 0;
  
  // 分离已选模型和其他模型
  const selectedModelInfos = hasFetchedModels 
    ? fetchedModels.filter(m => selectedModels.includes(m.id)) 
    : [];
  const otherModels = hasFetchedModels 
    ? fetchedModels.filter(m => !selectedModels.includes(m.id)).slice(0, 30) 
    : [];

  return (
    <div className={`capability-card ${priority}`}>
      <div className="capability-header">
        <strong>{cap.label}</strong>
        <div className="capability-provider-badges">
          {loadBalanceEnabled && poolProviderIds.length > 1 ? (
            <span className="badge-lb" title={`负载均衡: ${poolProviderIds.length}个服务商`}>
              ⚖️ {poolProviderIds.length}
            </span>
          ) : route.provider_id && (
            <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>
              {getProviderLogo(providers[route.provider_id])}
            </span>
          )}
        </div>
      </div>
      <p className="capability-desc">{cap.desc}</p>
      
      <div className="capability-controls">
        {/* 负载均衡模式：多选服务商 */}
        {loadBalanceEnabled ? (
          <div className="provider-pool-select">
            <span className="pool-label">⚖️ 服务商池（多选）:</span>
            <div className="pool-checkboxes">
              {validProviders.map(p => (
                <label key={p.id} className={`pool-checkbox ${poolProviderIds.includes(p.id) ? 'selected' : ''}`}>
                  <input
                    type="checkbox"
                    checked={poolProviderIds.includes(p.id)}
                    onChange={() => onToggleProvider?.(p.id)}
                  />
                  <span className="pool-provider-logo">{getProviderLogo(p)}</span>
                  <span className="pool-provider-name">{p.name}</span>
                </label>
              ))}
            </div>
            {poolProviderIds.length === 0 && (
              <span className="pool-hint">请选择至少一个服务商</span>
            )}
          </div>
        ) : (
          /* 单服务商模式 */
          <select
            className="field-input"
            value={route.provider_id ?? ""}
            onChange={(e) => {
              const newProviderId = e.target.value || null;
              onUpdate("provider_id", newProviderId);
              
              const newProvider = newProviderId 
                ? providers[newProviderId] 
                : (defaultProviderId ? providers[defaultProviderId] : null);
              
              if (!supportsThinking(newProvider) && route.enable_thinking) {
                onUpdate("enable_thinking", false);
              }
              
              // 切换服务商时清空模型选择
              onUpdate("model", "");
            }}
            aria-label={`${cap.label} 服务商`}
          >
            <option value="">
              🌐 使用默认 {defaultProviderId ? `(${providers[defaultProviderId]?.name || ""})` : "(未设置)"}
            </option>
            {validProviders.map(p => (
              <option key={p.id} value={p.id}>{getProviderLogo(p)} {p.name}</option>
            ))}
          </select>
        )}

        {/* 模型选择 - 只显示已收藏的模型 */}
        {hasSelectedModels ? (
          <div className="model-select-group">
            <select
              className="field-input model-select"
              value={isKnownModel ? (route.model || "") : (route.model ? "__custom__" : "")}
              onChange={(e) => {
                if (e.target.value !== "__custom__") {
                  onUpdate("model", e.target.value);
                }
              }}
              aria-label={`${cap.label} 模型`}
            >
              <option value="">选择模型...</option>
              {selectedModelInfos.map(model => (
                <option key={model.id} value={model.id}>
                  {model.name}
                  {model.context_window ? ` (${model.context_window >= 1000000 ? `${(model.context_window/1000000).toFixed(1)}M` : `${Math.round(model.context_window / 1000)}K`})` : ''}
                </option>
              ))}
              {/* 如果有收藏但没有模型信息（未获取），显示原始ID */}
              {selectedModels.filter(id => !selectedModelInfos.some(m => m.id === id)).map(modelId => (
                <option key={modelId} value={modelId}>{modelId}</option>
              ))}
              <option value="__custom__">✏️ 手动输入...</option>
            </select>
            {(!isKnownModel && route.model) && (
              <input
                className="field-input model-custom-input"
                type="text"
                placeholder="模型名称"
                value={route.model || ""}
                onChange={(e) => onUpdate("model", e.target.value)}
              />
            )}
          </div>
        ) : (
          <div className="model-input-group">
            <input
              className="field-input"
              type="text"
              placeholder={defaultModel ? `默认: ${defaultModel}` : "输入模型名称..."}
              value={route.model || ""}
              onChange={(e) => onUpdate("model", e.target.value)}
              aria-label={`${cap.label} 模型`}
            />
            <span className="model-input-hint">在服务商页面收藏模型</span>
          </div>
        )}

        <div className="timeout-row">
          <span className="timeout-label">⏱️ 超时</span>
          <input
            className="field-input timeout-input"
            type="number"
            min="10"
            max="600"
            value={route.timeout ?? cap.defaultTimeout}
            onChange={(e) => onUpdate("timeout", parseInt(e.target.value) || cap.defaultTimeout)}
            aria-label={`${cap.label} 超时时间`}
          />
          <span className="timeout-unit">秒</span>
        </div>

        {hasThinking && (
          <label className="thinking-toggle">
            <input
              type="checkbox"
              checked={route.enable_thinking || false}
              onChange={(e) => onUpdate("enable_thinking", e.target.checked)}
            />
            <span>🧠 深度思考模式</span>
          </label>
        )}
      </div>
    </div>
  );
}

// 全局默认模型选择组件
function GlobalModelSelect({ 
  value, 
  onChange, 
  hasError,
  fetchedModels,
  selectedModels,
}: { 
  value: string;
  onChange: (value: string) => void;
  hasError: boolean;
  fetchedModels?: ModelInfo[];
  selectedModels?: string[];
}) {
  const hasFetchedModels = fetchedModels && fetchedModels.length > 0;
  const hasSelectedModels = selectedModels && selectedModels.length > 0;
  
  // 获取已收藏模型的详情
  const selectedModelInfos = hasFetchedModels && hasSelectedModels
    ? fetchedModels.filter(m => selectedModels.includes(m.id))
    : [];
  
  // 检查当前值是否在收藏列表中
  const isInSelected = hasSelectedModels && selectedModels.includes(value);
  
  if (!hasSelectedModels) {
    // 没有收藏模型时显示普通输入框
    return (
      <div className="global-model-select">
        <input
          className={`field-input ${hasError ? 'has-error' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="输入模型名称"
        />
        <span className="model-input-hint">在服务商页面收藏模型后可下拉选择</span>
      </div>
    );
  }

  return (
    <div className="global-model-select">
      <select
        className={`field-input ${hasError ? 'has-error' : ''}`}
        value={isInSelected ? value : (value ? "__custom__" : "")}
        onChange={(e) => {
          if (e.target.value !== "__custom__") {
            onChange(e.target.value);
          }
        }}
      >
        <option value="">选择模型...</option>
        {selectedModelInfos.map(model => (
          <option key={model.id} value={model.id}>
            {model.name}
            {model.context_window ? ` (${model.context_window >= 1000000 ? `${(model.context_window/1000000).toFixed(1)}M` : `${Math.round(model.context_window / 1000)}K`})` : ''}
          </option>
        ))}
        {/* 如果有收藏但没有模型信息（未获取），显示原始ID */}
        {selectedModels.filter(id => !selectedModelInfos.some(m => m.id === id)).map(modelId => (
          <option key={modelId} value={modelId}>{modelId}</option>
        ))}
        <option value="__custom__">✏️ 手动输入...</option>
      </select>
      {(!isInSelected && value !== "") && (
        <input
          className="field-input global-model-custom"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="输入模型名称"
        />
      )}
    </div>
  );
}

// 工具函数
function getProviderTip(baseUrl: string, providerType: ProviderType = "openai"): string {
  // 根据 API 类型给出不同提示
  if (providerType === "anthropic") {
    return "Claude 原生 API，直接连接 Anthropic 服务。支持 claude-sonnet-4、claude-3.5-sonnet 等模型。";
  }
  if (providerType === "google") {
    return "Gemini 原生 API，直接连接 Google AI。支持 gemini-2.5-flash、gemini-2.5-pro 等模型。";
  }
  
  // OpenAI 兼容格式，根据 URL 细分
  if (baseUrl.includes("deepseek.com")) return "DeepSeek 官方 API，支持 deepseek-chat 和 deepseek-reasoner 模型。";
  if (baseUrl.includes("siliconflow")) return "硅基流动支持多种开源模型。✨ 支持思维链功能，可在功能路由中开启。";
  if (baseUrl.includes("volces.com")) return "火山引擎需要在模型名处填写端点 ID（如 ep-xxxxx）。✨ 支持思维链功能。";
  if (baseUrl.includes("openai.com")) return "OpenAI 官方 API，支持 GPT-4o、GPT-4 等模型。";
  if (baseUrl.includes("openrouter")) return "OpenRouter 聚合 API，一个 Key 可访问多家模型（包括 Claude、Gemini）。";
  return "OpenAI 兼容格式 API。大多数 LLM 服务商都支持此格式。";
}
