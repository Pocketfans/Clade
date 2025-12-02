/**
 * SettingsDrawer Reducer
 */

import type { UIConfig, ProviderConfig, ProviderType } from "@/services/api.types";
import type { SettingsState, SettingsAction } from "./types";
import {
  PROVIDER_PRESETS,
  DEFAULT_SPECIATION_CONFIG,
  DEFAULT_REPRODUCTION_CONFIG,
  DEFAULT_MORTALITY_CONFIG,
  DEFAULT_ECOLOGY_BALANCE_CONFIG,
  DEFAULT_MAP_ENVIRONMENT_CONFIG,
} from "./constants";

// ============ 工具函数 ============

export const generateId = () => Math.random().toString(36).substr(2, 9);

export function createDefaultConfig(): UIConfig {
  const providers: Record<string, ProviderConfig> = {};
  PROVIDER_PRESETS.forEach((preset) => {
    providers[preset.id] = {
      id: preset.id,
      name: preset.name,
      type: preset.provider_type,
      provider_type: preset.provider_type,
      base_url: preset.base_url,
      api_key: "",
      models: [...preset.models],
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
    // AI 功能开关
    turn_report_llm_enabled: true,      // 默认开启 LLM 回合报告
    ai_narrative_enabled: false,        // 默认关闭物种叙事
    load_balance_enabled: false,        // 默认关闭负载均衡
  };
}

export function getInitialProviders(config: UIConfig): Record<string, ProviderConfig> {
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

export function getProviderLogo(provider: ProviderConfig): string {
  const preset = PROVIDER_PRESETS.find((p) => p.id === provider.id);
  if (preset) return preset.logo;

  if (provider.provider_type === "anthropic") return "🎭";
  if (provider.provider_type === "google") return "💎";

  const url = provider.base_url || "";
  if (url.includes("deepseek")) return "🔮";
  if (url.includes("siliconflow")) return "⚡";
  if (url.includes("volces")) return "🌋";
  if (url.includes("openai")) return "🤖";
  if (url.includes("anthropic")) return "🎭";
  if (url.includes("google")) return "💎";
  if (url.includes("openrouter")) return "🔀";
  return "🔧";
}

export function getProviderTypeBadge(providerType: ProviderType): { text: string; color: string } {
  switch (providerType) {
    case "anthropic":
      return { text: "Claude", color: "#d97706" };
    case "google":
      return { text: "Gemini", color: "#3b82f6" };
    default:
      return { text: "OpenAI", color: "#10b981" };
  }
}

export function supportsThinking(provider: ProviderConfig | null): boolean {
  if (!provider?.base_url) return false;
  return provider.base_url.includes("siliconflow") || provider.base_url.includes("volces.com");
}

// ============ Reducer ============

export function settingsReducer(state: SettingsState, action: SettingsAction): SettingsState {
  switch (action.type) {
    case "SET_TAB":
      return { ...state, tab: action.tab };

    case "SELECT_PROVIDER":
      return { ...state, selectedProviderId: action.id };

    case "SET_FORM":
      return { ...state, form: action.form };

    case "UPDATE_PROVIDER":
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.id]: { ...state.form.providers[action.id], [action.field]: action.value },
          },
        },
      };

    case "ADD_PROVIDER":
      return {
        ...state,
        form: {
          ...state.form,
          providers: { ...state.form.providers, [action.provider.id]: action.provider },
        },
        selectedProviderId: action.provider.id,
      };

    case "REMOVE_PROVIDER": {
      const newProviders = { ...state.form.providers };
      delete newProviders[action.id];
      return {
        ...state,
        form: { ...state.form, providers: newProviders },
        selectedProviderId: state.selectedProviderId === action.id ? null : state.selectedProviderId,
      };
    }

    case "UPDATE_GLOBAL":
      return { ...state, form: { ...state.form, [action.field]: action.value } };

    case "UPDATE_ROUTE": {
      const currentRoute = state.form.capability_routes[action.capKey] || { timeout: 60 };
      return {
        ...state,
        form: {
          ...state.form,
          capability_routes: {
            ...state.form.capability_routes,
            [action.capKey]: { ...currentRoute, [action.field]: action.value },
          },
        },
      };
    }

    case "SET_TEST_RESULT":
      return { ...state, testResults: { ...state.testResults, [action.providerId]: action.result } };

    case "SET_TESTING_PROVIDER":
      return { ...state, testingProviderId: action.id };

    case "SET_TESTING_EMBEDDING":
      return { ...state, testingEmbedding: action.testing };

    case "SET_EMBEDDING_RESULT":
      return { ...state, testResultEmbedding: action.result };

    case "SET_SAVING":
      return { ...state, saving: action.saving };

    case "SET_SAVE_SUCCESS":
      return { ...state, saveSuccess: action.success };

    case "TOGGLE_API_KEY_VISIBILITY":
      return {
        ...state,
        showApiKeys: {
          ...state.showApiKeys,
          [action.providerId]: !state.showApiKeys[action.providerId],
        },
      };

    case "SET_CONFIRM_DIALOG":
      return { ...state, confirmDialog: action.dialog };

    case "CLOSE_CONFIRM":
      return { ...state, confirmDialog: { ...state.confirmDialog, isOpen: false } };

    case "SET_VALIDATION_ERRORS":
      return { ...state, validationErrors: action.errors };

    case "RESET_TO_DEFAULT":
      return { ...state, form: createDefaultConfig() };

    // 模型列表相关
    case "SET_FETCHING_MODELS":
      return { ...state, fetchingModels: action.providerId };

    case "SET_PROVIDER_MODELS":
      return {
        ...state,
        providerModels: { ...state.providerModels, [action.providerId]: action.models },
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: {
              ...state.form.providers[action.providerId],
              models: action.models.map((m) => m.id),
            },
          },
        },
      };

    case "SET_MODEL_FETCH_ERROR":
      return { ...state, modelFetchError: { ...state.modelFetchError, [action.providerId]: action.error } };

    case "CLEAR_MODEL_FETCH_ERROR": {
      const newErrors = { ...state.modelFetchError };
      delete newErrors[action.providerId];
      return { ...state, modelFetchError: newErrors };
    }

    case "TOGGLE_MODEL_SELECTION": {
      const provider = state.form.providers[action.providerId];
      if (!provider) return state;
      const currentSelected = provider.selected_models || [];
      const isSelected = currentSelected.includes(action.modelId);
      const newSelected = isSelected
        ? currentSelected.filter((m) => m !== action.modelId)
        : [...currentSelected, action.modelId];
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: newSelected },
          },
        },
      };
    }

    case "SELECT_ALL_MODELS": {
      const provider = state.form.providers[action.providerId];
      const models = state.providerModels[action.providerId] || [];
      if (!provider || models.length === 0) return state;
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: models.map((m) => m.id) },
          },
        },
      };
    }

    case "DESELECT_ALL_MODELS": {
      const provider = state.form.providers[action.providerId];
      if (!provider) return state;
      return {
        ...state,
        form: {
          ...state.form,
          providers: {
            ...state.form.providers,
            [action.providerId]: { ...provider, selected_models: [] },
          },
        },
      };
    }

    case "TOGGLE_ROUTE_PROVIDER": {
      const currentRoute = state.form.capability_routes[action.capKey] || { timeout: 60 };
      const currentIds = currentRoute.provider_ids || [];
      const isSelected = currentIds.includes(action.providerId);
      const newIds = isSelected
        ? currentIds.filter((id) => id !== action.providerId)
        : [...currentIds, action.providerId];
      return {
        ...state,
        form: {
          ...state.form,
          capability_routes: {
            ...state.form.capability_routes,
            [action.capKey]: { ...currentRoute, provider_ids: newIds },
          },
        },
      };
    }

    // 各配置模块更新
    case "UPDATE_SPECIATION":
      return {
        ...state,
        form: {
          ...state.form,
          speciation: { ...(state.form.speciation || {}), ...action.updates },
        },
      };

    case "RESET_SPECIATION":
      return {
        ...state,
        form: { ...state.form, speciation: { ...DEFAULT_SPECIATION_CONFIG } },
      };

    case "UPDATE_REPRODUCTION":
      return {
        ...state,
        form: {
          ...state.form,
          reproduction: { ...(state.form.reproduction || {}), ...action.updates },
        },
      };

    case "RESET_REPRODUCTION":
      return {
        ...state,
        form: { ...state.form, reproduction: { ...DEFAULT_REPRODUCTION_CONFIG } },
      };

    case "UPDATE_MORTALITY":
      return {
        ...state,
        form: {
          ...state.form,
          mortality: { ...(state.form.mortality || {}), ...action.updates },
        },
      };

    case "RESET_MORTALITY":
      return {
        ...state,
        form: { ...state.form, mortality: { ...DEFAULT_MORTALITY_CONFIG } },
      };

    case "UPDATE_ECOLOGY":
      return {
        ...state,
        form: {
          ...state.form,
          ecology_balance: { ...(state.form.ecology_balance || {}), ...action.updates },
        },
      };

    case "RESET_ECOLOGY":
      return {
        ...state,
        form: { ...state.form, ecology_balance: { ...DEFAULT_ECOLOGY_BALANCE_CONFIG } },
      };

    case "UPDATE_GAMEPLAY":
      return {
        ...state,
        form: {
          ...state.form,
          gameplay: { ...(state.form.gameplay || {}), ...action.updates },
        },
      };

    case "UPDATE_MAP_ENV":
      return {
        ...state,
        form: {
          ...state.form,
          map_environment: { ...(state.form.map_environment || {}), ...action.updates },
        },
      };

    case "RESET_MAP_ENV":
      return {
        ...state,
        form: { ...state.form, map_environment: { ...DEFAULT_MAP_ENVIRONMENT_CONFIG } },
      };

    default:
      return state;
  }
}

// ============ 创建初始状态 ============

export function createInitialState(config: UIConfig): SettingsState {
  const initialConfig = {
    ...config,
    providers: getInitialProviders(config),
    capability_routes: config.capability_routes || {},
    speciation: { ...DEFAULT_SPECIATION_CONFIG, ...(config.speciation || {}) },
  };

  return {
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
    confirmDialog: {
      isOpen: false,
      title: "",
      message: "",
      variant: "warning",
      onConfirm: () => {},
    },
    validationErrors: {},
    fetchingModels: null,
    providerModels: {},
    modelFetchError: {},
  };
}

