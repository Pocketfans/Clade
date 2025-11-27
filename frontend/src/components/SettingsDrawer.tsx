import { useState, useEffect, useCallback, useReducer, useMemo } from "react";
import type { UIConfig, ProviderConfig, CapabilityRouteConfig } from "../services/api.types";
import { testApiConnection } from "../services/api";
import { GamePanel } from "./common/GamePanel";
import { ConfirmDialog } from "./common/ConfirmDialog";
import { Tooltip } from "./common/Tooltip";
import "./SettingsDrawer.css";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => void;
}

type Tab = "connection" | "models" | "memory";

// ========== 常量定义 ==========

const PROVIDER_TYPES = ["openai", "deepseek", "anthropic", "custom", "local"] as const;

// 服务商预设配置（含 Logo）
const PROVIDER_PRESETS = [
  {
    id: "deepseek_official",
    name: "DeepSeek 官方",
    type: "openai",
    base_url: "https://api.deepseek.com",
    description: "DeepSeek 官方 API（支持 deepseek-chat, deepseek-reasoner 等模型）",
    models: ["deepseek-chat", "deepseek-reasoner"],
    logo: "🔮",
    color: "#6366f1",
  },
  {
    id: "siliconflow",
    name: "硅基流动",
    type: "openai",
    base_url: "https://api.siliconflow.cn/v1",
    description: "硅基流动 API（支持多种开源模型，支持思维链功能）",
    models: ["Pro/deepseek-ai/DeepSeek-V3.2-Exp"],
    logo: "⚡",
    color: "#f59e0b",
    supportsThinking: true,
  },
  {
    id: "volcengine",
    name: "火山引擎（豆包）",
    type: "openai",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    description: "火山引擎 API（支持思维链功能，需要填写端点ID作为模型名）",
    models: [],
    logo: "🌋",
    color: "#ef4444",
    supportsThinking: true,
  },
  {
    id: "openai_official",
    name: "OpenAI 官方",
    type: "openai",
    base_url: "https://api.openai.com/v1",
    description: "OpenAI 官方 API（ChatGPT）",
    models: ["gpt-4.1"],
    logo: "🤖",
    color: "#10b981",
  },
  {
    id: "anthropic_proxy",
    name: "Claude (OpenAI 兼容)",
    type: "openai",
    base_url: "https://api.anthropic.com/v1",
    description: "Claude API（需使用支持 OpenAI 格式的代理）",
    models: ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
    logo: "🎭",
    color: "#8b5cf6",
  },
  {
    id: "gemini_proxy",
    name: "Gemini (OpenAI 兼容)",
    type: "openai",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    description: "Google Gemini API（OpenAI 兼容格式）",
    models: ["gemini-2.5-flash", "gemini-2.5-pro"],
    logo: "💎",
    color: "#3b82f6",
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

// 服务商模型预设（用于功能路由）
const PROVIDER_MODEL_PRESETS: Record<string, Array<{ model: string; label: string; hint?: string }>> = {
  deepseek_official: [
    { model: "deepseek-chat", label: "deepseek-chat", hint: "通用对话模型" },
    { model: "deepseek-reasoner", label: "deepseek-reasoner 🧠", hint: "带思考功能，更强推理能力" },
  ],
  siliconflow: [
    { model: "deepseek-ai/DeepSeek-V3", label: "DeepSeek-V3 (免费)", hint: "可使用免费额度" },
    { model: "Pro/deepseek-ai/DeepSeek-V3", label: "DeepSeek-V3 Pro (付费)", hint: "付费，并行量更大" },
  ],
};

// 根据服务商 URL 获取模型预设
function getModelPresetsForProvider(provider: ProviderConfig | null): Array<{ model: string; label: string; hint?: string }> {
  if (!provider?.base_url) return [];
  
  if (provider.base_url.includes("deepseek.com")) {
    return PROVIDER_MODEL_PRESETS.deepseek_official || [];
  }
  if (provider.base_url.includes("siliconflow")) {
    return PROVIDER_MODEL_PRESETS.siliconflow || [];
  }
  
  return [];
}

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
  | { type: 'RESET_TO_DEFAULT' };

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
    default:
      return state;
  }
}

// ========== 工具函数 ==========

const generateId = () => Math.random().toString(36).substr(2, 9);

function createDefaultConfig(): UIConfig {
  const providers: Record<string, ProviderConfig> = {};
  PROVIDER_PRESETS.forEach(preset => {
    providers[preset.id] = {
      id: preset.id,
      name: preset.name,
      type: preset.type,
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
  };
}

function getInitialProviders(config: UIConfig): Record<string, ProviderConfig> {
  const providers = config.providers || {};
  if (Object.keys(providers).length === 0) {
    return createDefaultConfig().providers;
  }
  return providers;
}

function getProviderLogo(provider: ProviderConfig): string {
  const preset = PROVIDER_PRESETS.find(p => p.id === provider.id);
  if (preset) return preset.logo;
  
  // 根据 URL 猜测
  const url = provider.base_url || '';
  if (url.includes('deepseek')) return '🔮';
  if (url.includes('siliconflow')) return '⚡';
  if (url.includes('volces')) return '🌋';
  if (url.includes('openai')) return '🤖';
  if (url.includes('anthropic')) return '🎭';
  if (url.includes('google')) return '💎';
  return '🔧';
}

function supportsThinking(provider: ProviderConfig | null): boolean {
  if (!provider?.base_url) return false;
  return provider.base_url.includes("siliconflow") || provider.base_url.includes("volces.com");
}

function validateConfig(form: UIConfig): Record<string, string> {
  const errors: Record<string, string> = {};
  
  // 检查是否有默认服务商
  if (!form.default_provider_id) {
    errors.default_provider = "请选择默认服务商";
  } else {
    const defaultProvider = form.providers[form.default_provider_id];
    if (!defaultProvider?.api_key) {
      errors.default_provider = "默认服务商缺少 API Key";
    }
  }
  
  // 检查默认模型
  if (!form.default_model) {
    errors.default_model = "请设置默认模型";
  }
  
  return errors;
}

// ========== 主组件 ==========

export function SettingsDrawer({ config, onClose, onSave }: Props) {
  const initialConfig = useMemo(() => ({
    ...config,
    providers: getInitialProviders(config),
    capability_routes: config.capability_routes || {},
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
  });

  const { form, tab, selectedProviderId, testResults, testingProviderId, 
          testingEmbedding, testResultEmbedding, saving, saveSuccess, 
          showApiKeys, confirmDialog, validationErrors } = state;

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

  const addCustomProvider = useCallback(() => {
    const newProvider: ProviderConfig = {
      id: generateId(),
      name: "自定义服务商",
      type: "openai",
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

    dispatch({ type: 'SET_TESTING_PROVIDER', id: providerId });

    try {
      const testModel = form.default_model || "gpt-3.5-turbo";
      const result = await testApiConnection({
        type: "chat",
        base_url: provider.base_url,
        api_key: provider.api_key,
        provider: provider.type,
        model: testModel
      });
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
    // 验证配置
    const errors = validateConfig(form);
    dispatch({ type: 'SET_VALIDATION_ERRORS', errors });
    
    if (Object.keys(errors).length > 0) {
      // 有验证错误，但仍允许保存（只是警告）
    }

    dispatch({ type: 'SET_SAVING', saving: true });
    dispatch({ type: 'SET_SAVE_SUCCESS', success: false });
    
    try {
      await onSave(form);
      dispatch({ type: 'SET_SAVE_SUCCESS', success: true });
    } catch (error) {
      console.error("保存配置失败:", error);
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
      title="系统设置"
      onClose={onClose}
      variant="modal"
      width="clamp(700px, 85vw, 1300px)"
      height="clamp(550px, 85vh, 950px)"
      icon={<span>⚙️</span>}
    >
      <div className="settings-container">
        {/* 侧边导航 */}
        <nav className="settings-nav">
          <div className="nav-items">
            <NavButton 
              active={tab === "connection"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'connection' })} 
              icon="🔌" 
              label="服务商管理" 
              desc="配置 AI 接入点"
            />
            <NavButton 
              active={tab === "models"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'models' })} 
              icon="🧠" 
              label="功能路由" 
              desc="分配模型任务"
            />
            <NavButton 
              active={tab === "memory"} 
              onClick={() => dispatch({ type: 'SET_TAB', tab: 'memory' })} 
              icon="🧬" 
              label="向量记忆" 
              desc="Embedding 设置"
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
                  <h4 className="panel-title">服务商列表</h4>
                  
                  <div className="provider-list">
                    {providerList.map(p => {
                      const hasApiKey = !!p.api_key;
                      const hasThinking = supportsThinking(p);
                      const testResult = testResults[p.id];
                      
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
                              {hasThinking && <span className="badge-thinking" title="支持思维链">🧠</span>}
                              {/* 连接状态指示 */}
                              {testResult && (
                                <span 
                                  className={`status-dot ${testResult.success ? 'success' : 'error'}`}
                                  title={testResult.success ? "连接正常" : "连接失败"}
                                />
                              )}
                            </div>
                          </div>
                          {!hasApiKey && (
                            <div className="provider-warning">
                              <span>⚠️</span>
                              <span>需要配置 API Key</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    
                  </div>
                  
                  <button onClick={addCustomProvider} className="btn-add-provider">
                    + 添加自定义服务商
                  </button>

                  <div className="global-defaults">
                    <label className="form-field">
                      <span className="field-label">
                        全局默认服务商
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
                        <option value="">未选择</option>
                        {Object.values(form.providers).map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
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
                      <input
                        className={`field-input ${validationErrors.default_model ? 'has-error' : ''}`}
                        value={form.default_model ?? ""}
                        onChange={(e) => dispatch({ type: 'UPDATE_GLOBAL', field: 'default_model', value: e.target.value })}
                        placeholder="Pro/deepseek-ai/DeepSeek-V3.2-Exp"
                        aria-invalid={!!validationErrors.default_model}
                      />
                    </label>
                  </div>
                </div>

                {/* 右侧：编辑表单 */}
                <div className="provider-edit-panel">
                  {selectedProvider ? (
                    <>
                      <div className="edit-header">
                        <div className="edit-title-row">
                          <span className="edit-logo">{getProviderLogo(selectedProvider)}</span>
                          <div>
                            <h3>编辑服务商</h3>
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
                          🗑️ 删除
                        </button>
                      </div>

                      {selectedProvider.base_url && (
                        <div className="tip-box">
                          💡 <strong>配置提示：</strong>
                          {getProviderTip(selectedProvider.base_url)}
                        </div>
                      )}

                      <div className="form-fields">
                        <label className="form-field">
                          <span className="field-label">名称</span>
                          <input
                            className="field-input"
                            value={selectedProvider.name}
                            onChange={(e) => selectedProviderId && dispatch({ 
                              type: 'UPDATE_PROVIDER', 
                              id: selectedProviderId, 
                              field: 'name', 
                              value: e.target.value 
                            })}
                            placeholder="My AI Provider"
                          />
                        </label>

                        <label className="form-field">
                          <span className="field-label">类型</span>
                          <select
                            className="field-input"
                            value={selectedProvider.type}
                            onChange={(e) => selectedProviderId && dispatch({ 
                              type: 'UPDATE_PROVIDER', 
                              id: selectedProviderId, 
                              field: 'type', 
                              value: e.target.value 
                            })}
                          >
                            {PROVIDER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                          </select>
                        </label>

                        <label className="form-field">
                          <span className="field-label">Base URL</span>
                          <input
                            className="field-input"
                            value={selectedProvider.base_url ?? ""}
                            onChange={(e) => selectedProviderId && dispatch({ 
                              type: 'UPDATE_PROVIDER', 
                              id: selectedProviderId, 
                              field: 'base_url', 
                              value: e.target.value 
                            })}
                            placeholder="https://api.openai.com/v1"
                          />
                        </label>

                        <label className="form-field">
                          <span className="field-label">API Key</span>
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
                              placeholder="sk-..."
                            />
                            <button
                              type="button"
                              className="toggle-visibility"
                              onClick={() => selectedProviderId && dispatch({ 
                                type: 'TOGGLE_API_KEY_VISIBILITY', 
                                providerId: selectedProviderId 
                              })}
                              aria-label={showApiKeys[selectedProviderId || ''] ? "隐藏 API Key" : "显示 API Key"}
                            >
                              {showApiKeys[selectedProviderId || ''] ? '🙈' : '👁️'}
                            </button>
                          </div>
                        </label>
                      </div>

                      <div className="test-section">
                        <div className="test-row">
                          <button
                            onClick={() => selectedProviderId && handleTestProvider(selectedProviderId)}
                            disabled={testingProviderId === selectedProviderId}
                            className="btn-primary btn-test"
                          >
                            {testingProviderId === selectedProviderId ? (
                              <><span className="spinner-small"></span> 连接中...</>
                            ) : "🔌 测试连接"}
                          </button>
                          <span className="test-hint">(使用默认模型)</span>
                        </div>
                        
                        {selectedProviderId && testResults[selectedProviderId] && (
                          <div className={`test-result ${testResults[selectedProviderId].success ? 'success' : 'error'}`}>
                            <span>{testResults[selectedProviderId].success ? "✅" : "❌"}</span>
                            <span>{testResults[selectedProviderId].message}</span>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-icon">🔌</span>
                      <p>请选择或添加一个服务商</p>
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
                <h3>🧠 大脑皮层：功能路由</h3>
                <p>为每个具体的认知功能指定专用服务商与模型，可单独设置超时时间。</p>
              </div>
              
              {/* 高优先级 */}
              <div className="capability-group">
                <div className="group-header high">
                  <span className="group-icon">🔴</span>
                  <span className="group-title">高优先级</span>
                  <span className="group-desc">核心推演功能，建议使用高性能模型</span>
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
                    />
                  ))}
                </div>
              </div>

              {/* 中优先级 */}
              <div className="capability-group">
                <div className="group-header medium">
                  <span className="group-icon">🟡</span>
                  <span className="group-title">中优先级</span>
                  <span className="group-desc">物种生成相关功能</span>
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
                    />
                  ))}
                </div>
              </div>

              {/* 低优先级 */}
              <div className="capability-group">
                <div className="group-header low">
                  <span className="group-icon">🟢</span>
                  <span className="group-title">普通优先级</span>
                  <span className="group-desc">辅助功能，可使用轻量模型</span>
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
  onUpdate 
}: {
  cap: { key: string; label: string; desc: string; defaultTimeout: number };
  priority: 'high' | 'medium' | 'low';
  route: Partial<CapabilityRouteConfig>;
  providers: Record<string, ProviderConfig>;
  defaultProviderId?: string | null;
  defaultModel?: string | null;
  onUpdate: (field: keyof CapabilityRouteConfig, value: any) => void;
}) {
  const routeProvider = route.provider_id 
    ? providers[route.provider_id] 
    : (defaultProviderId ? providers[defaultProviderId] : null);
  
  const hasThinking = supportsThinking(routeProvider);
  const modelPresets = getModelPresetsForProvider(routeProvider);

  return (
    <div className={`capability-card ${priority}`}>
      <div className="capability-header">
        <strong>{cap.label}</strong>
      </div>
      <p className="capability-desc">{cap.desc}</p>
      
      <div className="capability-controls">
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
            默认 ({defaultProviderId ? (providers[defaultProviderId]?.name || "Unknown") : "未设置"})
          </option>
          {Object.values(providers).map(p => (
            <option key={p.id} value={p.id}>{getProviderLogo(p)} {p.name}</option>
          ))}
        </select>

        {/* 模型选择：有预设时显示下拉+输入，否则只显示输入 */}
        {modelPresets.length > 0 ? (
          <div className="model-select-group">
            <select
              className="field-input model-select"
              value={modelPresets.some(p => p.model === route.model) ? (route.model || "") : ""}
              onChange={(e) => onUpdate("model", e.target.value)}
              aria-label={`${cap.label} 模型预设`}
            >
              <option value="">选择模型...</option>
              {modelPresets.map(preset => (
                <option key={preset.model} value={preset.model} title={preset.hint}>
                  {preset.label}
                </option>
              ))}
              <option value="__custom__">自定义...</option>
            </select>
            {(!modelPresets.some(p => p.model === route.model) && route.model) && (
              <input
                className="field-input model-custom-input"
                type="text"
                placeholder="输入模型名称"
                value={route.model || ""}
                onChange={(e) => onUpdate("model", e.target.value)}
              />
            )}
            {/* 显示当前模型的提示 */}
            {route.model && modelPresets.find(p => p.model === route.model)?.hint && (
              <span className="model-hint">
                💡 {modelPresets.find(p => p.model === route.model)?.hint}
              </span>
            )}
          </div>
        ) : (
          <input
            className="field-input"
            type="text"
            placeholder={`模型 (默认: ${defaultModel || "未设置"})`}
            value={route.model || ""}
            onChange={(e) => onUpdate("model", e.target.value)}
            aria-label={`${cap.label} 模型`}
          />
        )}

        <div className="timeout-row">
          <label className="timeout-label">超时</label>
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
            <span>开启思考模式 🧠</span>
          </label>
        )}
      </div>
    </div>
  );
}

// 工具函数
function getProviderTip(baseUrl: string): string {
  if (baseUrl.includes("deepseek.com")) return "DeepSeek 官方 API，支持 deepseek-chat 和 deepseek-reasoner 模型。";
  if (baseUrl.includes("siliconflow")) return "硅基流动支持多种开源模型。✨ 支持思维链功能，可在功能路由中开启。";
  if (baseUrl.includes("volces.com")) return "火山引擎需要在模型名处填写端点 ID（如 ep-xxxxx）。✨ 支持思维链功能。";
  if (baseUrl.includes("openai.com")) return "OpenAI 官方 API，支持 GPT 系列模型。";
  if (baseUrl.includes("anthropic.com")) return "Claude API，需确保代理支持 OpenAI 格式。";
  if (baseUrl.includes("generativelanguage.googleapis.com")) return "Google Gemini API，使用 OpenAI 兼容端点。";
  return "请确保 API 端点支持 OpenAI 兼容格式。";
}
