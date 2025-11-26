import { useState, useEffect } from "react";
import type { UIConfig, ProviderConfig, CapabilityRouteConfig } from "../services/api.types";
import { testApiConnection } from "../services/api";
import { GamePanel } from "./common/GamePanel";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => void;
}

const PROVIDER_TYPES = ["openai", "deepseek", "anthropic", "custom", "local"];
type Tab = "connection" | "models" | "memory";

// 预设服务商模板
const PROVIDER_PRESETS = [
  {
    id: "deepseek_official",
    name: "DeepSeek 官方",
    type: "openai",
    base_url: "https://api.deepseek.com",
    description: "DeepSeek 官方 API（支持 deepseek-chat, deepseek-reasoner 等模型）",
    models: ["deepseek-chat", "deepseek-reasoner"],
  },
  {
    id: "siliconflow",
    name: "硅基流动 ⚡",
    type: "openai",
    base_url: "https://api.siliconflow.cn/v1",
    description: "硅基流动 API（支持多种开源模型，支持思维链功能 🧠）",
    models: ["Pro/deepseek-ai/DeepSeek-V3.2-Exp"],
  },
  {
    id: "volcengine",
    name: "火山引擎（豆包）⚡",
    type: "openai",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    description: "火山引擎 API（支持思维链功能 🧠，需要填写端点ID作为模型名）",
    models: [],
  },
  {
    id: "openai_official",
    name: "OpenAI 官方",
    type: "openai",
    base_url: "https://api.openai.com/v1",
    description: "OpenAI 官方 API（ChatGPT）",
    models: ["gpt-5.1"],
  },
  {
    id: "anthropic_proxy",
    name: "Claude (OpenAI 兼容)",
    type: "openai",
    base_url: "https://api.anthropic.com/v1",
    description: "Claude API（需使用支持 OpenAI 格式的代理）",
    models: ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
  },
  {
    id: "gemini_proxy",
    name: "Gemini (OpenAI 兼容)",
    type: "openai",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    description: "Google Gemini API（OpenAI 兼容格式）",
    models: ["gemini-2.5-flash", "gemini-3-pro"],
  },
] as const;

// AI 能力列表定义
const AI_CAPABILITIES = [
  { key: "turn_report", label: "主推演叙事", priority: "high", desc: "负责生成每个回合的总体生态演化报告" },
  { key: "focus_batch", label: "重点批次推演", priority: "high", desc: "处理关键物种的具体生存判定" },
  { key: "critical_detail", label: "关键物种分析", priority: "high", desc: "分析濒危或优势物种的详细状态" },
  { key: "speciation", label: "物种分化", priority: "medium", desc: "判定新物种的诞生条件与特征" },
  { key: "migration", label: "迁徙建议", priority: "low", desc: "计算物种在不同地块间的移动" },
  { key: "pressure_escalation", label: "压力升级", priority: "low", desc: "动态调整环境生存压力" },
  { key: "reemergence", label: "物种重现/起名", priority: "low", desc: "为新物种生成名称与描述" },
  { key: "species_generation", label: "物种生成", priority: "medium", desc: "生成初始物种或新物种" },
] as const;

// 简单的 ID 生成器
const generateId = () => Math.random().toString(36).substr(2, 9);

export function SettingsDrawer({ config, onClose, onSave }: Props) {
  // 确保 providers 即使为空也是对象，并添加默认预设服务商
  const getInitialProviders = () => {
    const providers = config.providers || {};
    
    // 如果没有任何服务商，添加预设服务商
    if (Object.keys(providers).length === 0) {
      const presetProviders: Record<string, ProviderConfig> = {};
      
      PROVIDER_PRESETS.forEach((preset, index) => {
        presetProviders[preset.id] = {
          id: preset.id,
          name: preset.name,
          type: preset.type,
          base_url: preset.base_url,
          api_key: "", // 需要用户填写
          models: [...preset.models]
        };
      });
      
      return presetProviders;
    }
    
    return providers;
  };
  
  const initialConfig = {
    ...config,
    providers: getInitialProviders(),
    capability_routes: config.capability_routes || {},
  };

  const [form, setForm] = useState<UIConfig>(initialConfig);
  const [tab, setTab] = useState<Tab>("connection");
  
  // UI States
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(
    Object.keys(initialConfig.providers)[0] || null
  );

  // Testing States
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({});
  
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [testResultEmbedding, setTestResultEmbedding] = useState<{ success: boolean; message: string; details?: string } | null>(null);
  
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // --- Actions ---

  // 1. Provider Management
  function addCustomProvider() {
    const newId = generateId();
    const newProvider: ProviderConfig = {
      id: newId,
      name: "自定义服务商",
      type: "openai",
      models: []
    };
    setForm(prev => ({
      ...prev,
      providers: { ...prev.providers, [newId]: newProvider }
    }));
    setSelectedProviderId(newId);
  }

  function removeProvider(id: string) {
    // 检查是否是预设服务商
    const isPreset = PROVIDER_PRESETS.some(preset => preset.id === id);
    
    if (isPreset) {
      if (!confirm("这是预设服务商，删除后下次打开设置将重新出现。确定要删除吗？")) return;
    } else {
      if (!confirm("确定要删除这个服务商吗？相关的路由配置将失效。")) return;
    }
    
    setForm(prev => {
      const newProviders = { ...prev.providers };
      delete newProviders[id];
      return { ...prev, providers: newProviders };
    });
    
    if (selectedProviderId === id) {
      setSelectedProviderId(null);
    }
    
    // 可以在这里清理相关的 routes，或者留给后端清理
  }

  function updateProvider(id: string, field: keyof ProviderConfig, value: any) {
    setForm(prev => ({
      ...prev,
      providers: {
        ...prev.providers,
        [id]: { ...prev.providers[id], [field]: value }
      }
    }));
  }

  // 2. Global Settings
  function updateGlobalDefault(field: "default_provider_id" | "default_model", value: string) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  // 3. Routing
  function updateRoute(capKey: string, field: keyof CapabilityRouteConfig, value: any) {
    setForm(prev => {
      const currentRoute = prev.capability_routes[capKey] || { timeout: 60 };
      return {
        ...prev,
        capability_routes: {
          ...prev.capability_routes,
          [capKey]: { ...currentRoute, [field]: value }
        }
      };
    });
  }

  // 4. Testing
  async function handleTestProvider(providerId: string) {
    const provider = form.providers[providerId];
    if (!provider || !provider.base_url || !provider.api_key) {
      setTestResults(prev => ({ ...prev, [providerId]: { success: false, message: "请先填写完整配置" } }));
      return;
    }

    setTestingProviderId(providerId);
    setTestResults(prev => {
      const next = { ...prev };
      delete next[providerId];
      return next;
    });

    try {
      // 优先使用全局默认模型，或者 prompt 用户 (这里简单起见使用 'gpt-3.5-turbo' 或 provider 列表里的第一个，或者让用户填写)
      // 改进：使用 form.default_model 作为 fallback，再不行 gpt-3.5-turbo
      const testModel = form.default_model || "Pro/deepseek-ai/DeepSeek-V3.2-Exp";
      
      const result = await testApiConnection({
        type: "chat",
        base_url: provider.base_url,
        api_key: provider.api_key,
        provider: provider.type,
        model: testModel
      });
      setTestResults(prev => ({ ...prev, [providerId]: { success: result.success, message: result.message } }));
    } catch (e) {
      setTestResults(prev => ({ ...prev, [providerId]: { success: false, message: String(e) } }));
    } finally {
      setTestingProviderId(null);
    }
  }

  async function handleTestEmbedding() {
    const providerId = form.embedding_provider_id;
    // 查找 Embedding 配置：
    // 1. 如果指定了 provider_id，从 providers 中找
    // 2. 如果没指定，回退到 default_provider_id
    const effectiveProviderId = providerId || form.default_provider_id;
    const provider = effectiveProviderId ? form.providers[effectiveProviderId] : null;
    
    // 兼容旧字段 (embedding_base_url/api_key)
    const baseUrl = provider?.base_url || form.embedding_base_url;
    const apiKey = provider?.api_key || form.embedding_api_key;
    const model = form.embedding_model || "Qwen/Qwen3-Embedding-4B";

    if (!baseUrl || !apiKey) {
      setTestResultEmbedding({ success: false, message: "请先填写配置或选择有效的服务商" });
      return;
    }
    
    setTestingEmbedding(true);
    setTestResultEmbedding(null);
    
    try {
      const result = await testApiConnection({
        type: "embedding",
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
      });
      setTestResultEmbedding(result);
    } catch (error) {
      setTestResultEmbedding({ success: false, message: "失败：" + String(error) });
    } finally {
      setTestingEmbedding(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    try {
      await onSave(form);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error("保存配置失败:", error);
      alert("保存配置失败：" + String(error));
    } finally {
      setSaving(false);
    }
  }

  const providerList = Object.values(form.providers);

  return (
    <GamePanel
      title="系统设置 (System Configuration)"
      onClose={onClose}
      variant="modal"
      width="900px"
      height="700px"
    >
      <div style={{ display: "flex", height: "100%" }}>
        {/* Sidebar Navigation */}
        <div style={{ 
          width: "200px", 
          borderRight: "1px solid rgba(255,255,255,0.1)", 
          padding: "16px 0",
          background: "rgba(0,0,0,0.2)"
        }}>
          <NavButton 
            active={tab === "connection"} 
            onClick={() => setTab("connection")} 
            icon="🔌" 
            label="服务商管理" 
            desc="配置 AI 接入点"
          />
          <NavButton 
            active={tab === "models"} 
            onClick={() => setTab("models")} 
            icon="🧠" 
            label="功能路由" 
            desc="分配模型任务"
          />
          <NavButton 
            active={tab === "memory"} 
            onClick={() => setTab("memory")} 
            icon="🧬" 
            label="向量记忆" 
            desc="Embedding 设置"
          />
        </div>

        {/* Content Area */}
        <div style={{ flex: 1, padding: "24px", overflowY: "auto", display: "flex", flexDirection: "column" }}>
          
          {/* TAB 1: PROVIDERS */}
          {tab === "connection" && (
            <div className="fade-in" style={{ display: "flex", gap: "24px", height: "100%" }}>
              {/* Left: Provider List */}
              <div style={{ width: "200px", display: "flex", flexDirection: "column", gap: "8px" }}>
                <h4 style={{ margin: "0 0 8px 0", color: "#ccc" }}>服务商列表</h4>
                <div style={{ maxHeight: "400px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "6px" }}>
                  {providerList.map(p => {
                    // 检查是否是预设服务商（没有 API Key）
                    const isPreset = !p.api_key;
                    const supportsThinking = p.base_url && (
                      p.base_url.includes("siliconflow") || 
                      p.base_url.includes("volces.com")
                    );
                    
                    return (
                      <div 
                        key={p.id}
                        onClick={() => setSelectedProviderId(p.id)}
                        style={{
                          padding: "10px",
                          background: selectedProviderId === p.id ? "rgba(59, 130, 246, 0.2)" : "rgba(255,255,255,0.05)",
                          border: selectedProviderId === p.id ? "1px solid #3b82f6" : "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "6px",
                          cursor: "pointer",
                          position: "relative"
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                            {p.name}
                          </span>
                          {supportsThinking && <span style={{ fontSize: "0.9rem" }}>🧠</span>}
                        </div>
                        {isPreset && (
                          <div style={{ 
                            fontSize: "0.7rem", 
                            color: "rgba(255, 193, 7, 0.8)", 
                            marginTop: "4px",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px"
                          }}>
                            <span>⚠️</span>
                            <span>需要配置 API Key</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                
                {/* 添加自定义服务商按钮 */}
                <button 
                  onClick={addCustomProvider}
                  className="btn-secondary"
                  style={{ marginTop: "8px", width: "100%", fontSize: "0.85rem" }}
                >
                  + 添加自定义服务商
                </button>

                <div style={{ marginTop: "auto", borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "16px" }}>
                   <label className="form-field">
                    <span className="field-label" style={{ fontSize: "0.8rem" }}>全局默认服务商</span>
                    <select
                      className="field-input"
                      value={form.default_provider_id ?? ""}
                      onChange={(e) => updateGlobalDefault("default_provider_id", e.target.value)}
                      style={{ fontSize: "0.85rem" }}
                    >
                      <option value="">未选择</option>
                      {providerList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                   </label>
                   <label className="form-field">
                    <span className="field-label" style={{ fontSize: "0.8rem" }}>默认模型</span>
                    <input
                      className="field-input"
                      value={form.default_model ?? ""}
                      onChange={(e) => updateGlobalDefault("default_model", e.target.value)}
                      placeholder="Pro/deepseek-ai/DeepSeek-V3.2-Exp"
                      style={{ fontSize: "0.85rem" }}
                    />
                   </label>
                </div>
              </div>

              {/* Right: Edit Form */}
              <div style={{ flex: 1, background: "rgba(0,0,0,0.2)", padding: "16px", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.05)" }}>
                {selectedProviderId && form.providers[selectedProviderId] ? (
                  <div className="form-grid" style={{ gridTemplateColumns: "1fr", gap: "16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                      <div>
                        <h3 style={{ margin: 0 }}>编辑服务商</h3>
                        {PROVIDER_PRESETS.some(p => p.id === selectedProviderId) && (
                          <p style={{ fontSize: "0.75rem", color: "rgba(34, 197, 94, 0.8)", margin: "4px 0 0 0" }}>
                            ⭐ 预设服务商
                          </p>
                        )}
                      </div>
                      <button 
                        onClick={() => removeProvider(selectedProviderId)}
                        style={{ color: "#ff5252", background: "transparent", border: "none", cursor: "pointer", fontSize: "0.9rem" }}
                      >
                        🗑️ 删除
                      </button>
                    </div>

                    {/* 提示信息：根据服务商类型显示 */}
                    {form.providers[selectedProviderId].base_url && (
                      <div style={{
                        background: "rgba(59, 130, 246, 0.1)",
                        border: "1px solid rgba(59, 130, 246, 0.3)",
                        borderRadius: "6px",
                        padding: "12px",
                        fontSize: "0.85rem",
                        color: "#93c5fd"
                      }}>
                        💡 <strong>配置提示：</strong>
                        {form.providers[selectedProviderId].base_url.includes("deepseek.com") && " DeepSeek 官方 API，支持 deepseek-chat 和 deepseek-reasoner 模型。"}
                        {form.providers[selectedProviderId].base_url.includes("siliconflow") && " 硅基流动支持多种开源模型，如 DeepSeek-V3、Qwen2.5 等。✨ 支持思维链功能，可在功能路由中开启。"}
                        {form.providers[selectedProviderId].base_url.includes("volces.com") && " 火山引擎需要在模型名处填写端点 ID（如 ep-xxxxx）。✨ 支持思维链功能，可在功能路由中开启。"}
                        {form.providers[selectedProviderId].base_url.includes("openai.com") && " OpenAI 官方 API，支持 GPT 系列模型。"}
                        {form.providers[selectedProviderId].base_url.includes("anthropic.com") && " Claude API，需确保代理支持 OpenAI 格式。"}
                        {form.providers[selectedProviderId].base_url.includes("generativelanguage.googleapis.com") && " Google Gemini API，使用 OpenAI 兼容端点。"}
                        {!form.providers[selectedProviderId].base_url.includes("deepseek") &&
                         !form.providers[selectedProviderId].base_url.includes("siliconflow") &&
                         !form.providers[selectedProviderId].base_url.includes("volces") &&
                         !form.providers[selectedProviderId].base_url.includes("openai") &&
                         !form.providers[selectedProviderId].base_url.includes("anthropic") &&
                         !form.providers[selectedProviderId].base_url.includes("google") && 
                         " 请确保 API 端点支持 OpenAI 兼容格式。"}
                      </div>
                    )}

                    <label className="form-field">
                      <span className="field-label">名称 (Display Name)</span>
                      <input
                        className="field-input"
                        value={form.providers[selectedProviderId].name}
                        onChange={(e) => updateProvider(selectedProviderId, "name", e.target.value)}
                        placeholder="My AI Provider"
                      />
                    </label>

                    <label className="form-field">
                      <span className="field-label">类型 (Type)</span>
                      <select
                        className="field-input"
                        value={form.providers[selectedProviderId].type}
                        onChange={(e) => updateProvider(selectedProviderId, "type", e.target.value)}
                      >
                        {PROVIDER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </label>

                    <label className="form-field">
                      <span className="field-label">Base URL</span>
                      <input
                        className="field-input"
                        value={form.providers[selectedProviderId].base_url ?? ""}
                        onChange={(e) => updateProvider(selectedProviderId, "base_url", e.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </label>

                    <label className="form-field">
                      <span className="field-label">API Key</span>
                      <input
                        className="field-input"
                        type="password"
                        value={form.providers[selectedProviderId].api_key ?? ""}
                        onChange={(e) => updateProvider(selectedProviderId, "api_key", e.target.value)}
                        placeholder="sk-..."
                      />
                    </label>

                    <div style={{ marginTop: "24px", paddingTop: "16px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                          <button
                            onClick={() => handleTestProvider(selectedProviderId)}
                            disabled={testingProviderId === selectedProviderId}
                            className="btn-primary"
                            style={{ 
                              flex: 1,
                              background: testingProviderId === selectedProviderId ? "#4b5563" : "#3b82f6",
                              borderColor: testingProviderId === selectedProviderId ? "#4b5563" : "#3b82f6",
                              opacity: testingProviderId === selectedProviderId ? 0.7 : 1
                            }}
                          >
                            {testingProviderId === selectedProviderId ? (
                              <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
                                <span className="spinner-small"></span> 连接中...
                              </span>
                            ) : "🔌 测试连接"}
                          </button>
                          
                          <span style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.4)", flexShrink: 0 }}>
                            (使用默认模型)
                          </span>
                        </div>
                        
                        {testResults[selectedProviderId] && (
                          <div style={{ 
                            marginTop: "12px", 
                            padding: "10px", 
                            borderRadius: "6px",
                            background: testResults[selectedProviderId].success ? "rgba(76, 175, 80, 0.1)" : "rgba(244, 67, 54, 0.1)",
                            border: `1px solid ${testResults[selectedProviderId].success ? "rgba(76, 175, 80, 0.3)" : "rgba(244, 67, 54, 0.3)"}`,
                            color: testResults[selectedProviderId].success ? "#81c784" : "#e57373",
                            fontSize: "0.9rem",
                            display: "flex",
                            alignItems: "flex-start",
                            gap: "8px"
                          }}>
                            <span>{testResults[selectedProviderId].success ? "✅" : "❌"}</span>
                            <span>{testResults[selectedProviderId].message}</span>
                          </div>
                        )}
                    </div>
                  </div>
                ) : (
                  <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.3)" }}>
                    请选择或添加一个服务商
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: MODELS (Routing) */}
          {tab === "models" && (
            <div className="fade-in">
              <h3 style={{ marginTop: 0, borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "12px", marginBottom: "20px" }}>
                大脑皮层：功能路由
              </h3>
              <p style={{ fontSize: "0.9rem", color: "rgba(255,255,255,0.6)", marginBottom: "16px" }}>
                为每个具体的认知功能指定专用服务商与模型。
              </p>
              
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "16px" }}>
                {AI_CAPABILITIES.map((cap) => {
                  const route = form.capability_routes[cap.key] || {};
                  
                  // 判断当前选择的服务商是否支持思维链
                  const selectedProvider = route.provider_id 
                    ? form.providers[route.provider_id] 
                    : (form.default_provider_id ? form.providers[form.default_provider_id] : null);
                  
                  const supportsThinking = selectedProvider?.base_url && (
                    selectedProvider.base_url.includes("siliconflow") || 
                    selectedProvider.base_url.includes("volces.com")
                  );
                  
                  return (
                    <div key={cap.key} style={{ 
                      background: "rgba(255,255,255,0.03)", 
                      border: "1px solid rgba(255,255,255,0.1)", 
                      borderRadius: "8px",
                      padding: "12px"
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                        <strong style={{ color: "#e2ecff" }}>{cap.label}</strong>
                        <span style={{ 
                          fontSize: "0.7rem", 
                          padding: "2px 6px", 
                          borderRadius: "4px", 
                          background: cap.priority === "high" ? "rgba(244,67,54,0.2)" : "rgba(76,175,80,0.2)",
                          color: cap.priority === "high" ? "#ff8a80" : "#a5d6a7"
                        }}>
                          {cap.priority === "high" ? "高优" : "普通"}
                        </span>
                      </div>
                      <p style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.4)", margin: "0 0 12px 0" }}>{cap.desc}</p>
                      
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        {/* Provider Select */}
                        <select
                          className="field-input"
                          style={{ fontSize: "0.85rem", padding: "6px 8px" }}
                          value={route.provider_id ?? ""}
                          onChange={(e) => {
                            const newProviderId = e.target.value || null;
                            updateRoute(cap.key, "provider_id", newProviderId);
                            
                            // 检查新选择的服务商是否支持思维链
                            const newProvider = newProviderId 
                              ? form.providers[newProviderId] 
                              : (form.default_provider_id ? form.providers[form.default_provider_id] : null);
                            
                            const newSupportsThinking = newProvider?.base_url && (
                              newProvider.base_url.includes("siliconflow") || 
                              newProvider.base_url.includes("volces.com")
                            );
                            
                            // 如果不支持思维链，自动关闭该功能
                            if (!newSupportsThinking && route.enable_thinking) {
                              updateRoute(cap.key, "enable_thinking", false);
                            }
                          }}
                        >
                          <option value="">默认 ({form.default_provider_id ? (form.providers[form.default_provider_id]?.name || "Unknown") : "未设置"})</option>
                          {providerList.map(p => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                          ))}
                        </select>

                        {/* Model Input */}
                        <input
                          className="field-input"
                          style={{ fontSize: "0.85rem", padding: "6px 8px" }}
                          type="text"
                          placeholder={`模型 (默认: ${form.default_model || "未设置"})`}
                          value={route.model || ""}
                          onChange={(e) => updateRoute(cap.key, "model", e.target.value)}
                        />

                        {/* Thinking Toggle - 仅在支持思维链的服务商时显示 */}
                        {supportsThinking && (
                          <>
                            {/* 思维链提示 */}
                            {!route.enable_thinking && (
                              <div style={{
                                background: "rgba(255, 193, 7, 0.1)",
                                border: "1px solid rgba(255, 193, 7, 0.3)",
                                borderRadius: "4px",
                                padding: "6px 8px",
                                fontSize: "0.75rem",
                                color: "#ffd54f",
                                display: "flex",
                                alignItems: "center",
                                gap: "6px"
                              }}>
                                <span>💡</span>
                                <span>此服务商支持思维链，开启可得到更加精准的结果，但耗时更长</span>
                              </div>
                            )}
                            
                            <label style={{ 
                              display: "flex", 
                              alignItems: "center", 
                              gap: "8px", 
                              cursor: "pointer", 
                              fontSize: "0.85rem", 
                              color: "rgba(255,255,255,0.8)",
                              background: "rgba(255, 193, 7, 0.05)",
                              padding: "6px 8px",
                              borderRadius: "4px",
                              border: "1px solid rgba(255, 193, 7, 0.2)"
                            }}>
                              <input
                                type="checkbox"
                                checked={route.enable_thinking || false}
                                onChange={(e) => updateRoute(cap.key, "enable_thinking", e.target.checked)}
                                style={{ cursor: "pointer" }}
                              />
                              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                                开启思考模式 (Thinking Mode)
                                <span style={{ fontSize: "1rem" }}>🧠</span>
                              </span>
                            </label>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* TAB 3: MEMORY */}
          {tab === "memory" && (
            <div className="fade-in">
              <h3 style={{ marginTop: 0, borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "12px", marginBottom: "20px" }}>
                海马体：向量记忆
              </h3>
               <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
                 <div style={{ background: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)", padding: "16px", borderRadius: "8px", marginBottom: "16px" }}>
                  <p style={{ margin: 0, fontSize: "0.9rem", color: "#93c5fd" }}>
                    向量服务通常需要 Qwen/Qwen3-Embedding-4B 或类似模型。请确保选择的服务商支持 Embedding 接口。
                  </p>
                </div>

                <label className="form-field">
                  <span className="field-label">服务商 (Provider)</span>
                  <select
                    className="field-input"
                    value={form.embedding_provider_id ?? ""}
                    onChange={(e) => setForm(prev => ({ ...prev, embedding_provider_id: e.target.value || null }))}
                  >
                    <option value="">使用全局默认</option>
                    {providerList.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </label>

                <label className="form-field">
                  <span className="field-label">Embedding 模型</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.embedding_model ?? ""}
                    onChange={(e) => setForm(prev => ({ ...prev, embedding_model: e.target.value }))}
                    placeholder="Qwen/Qwen3-Embedding-4B
"
                  />
                </label>
                
                <div style={{ marginTop: "24px", paddingTop: "16px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                   <button
                    type="button"
                    onClick={handleTestEmbedding}
                    disabled={testingEmbedding}
                    className="btn-primary"
                    style={{
                        width: "100%",
                        background: testingEmbedding ? "#4b5563" : "#3b82f6",
                        borderColor: testingEmbedding ? "#4b5563" : "#3b82f6",
                        opacity: testingEmbedding ? 0.7 : 1
                    }}
                  >
                    {testingEmbedding ? "🔄 连接中..." : "🧬 测试向量服务"}
                  </button>
                  
                  {testResultEmbedding && (
                    <div style={{ 
                        marginTop: "12px", 
                        padding: "10px", 
                        borderRadius: "6px",
                        background: testResultEmbedding.success ? "rgba(76, 175, 80, 0.1)" : "rgba(244, 67, 54, 0.1)",
                        border: `1px solid ${testResultEmbedding.success ? "rgba(76, 175, 80, 0.3)" : "rgba(244, 67, 54, 0.3)"}`,
                        color: testResultEmbedding.success ? "#81c784" : "#e57373",
                        fontSize: "0.9rem"
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600 }}>
                        <span>{testResultEmbedding.success ? "✅ 连接成功" : "❌ 连接失败"}</span>
                      </div>
                      {testResultEmbedding.details && (
                          <div style={{ marginTop: "4px", fontSize: "0.8rem", opacity: 0.8 }}>
                              {testResultEmbedding.details}
                          </div>
                      )}
                      {!testResultEmbedding.success && testResultEmbedding.message && (
                          <div style={{ marginTop: "4px", fontSize: "0.8rem" }}>
                              {testResultEmbedding.message}
                          </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          
          {/* Footer Actions */}
          <div style={{ marginTop: "auto", paddingTop: "24px", borderTop: "1px solid rgba(255,255,255,0.1)", display: "flex", justifyContent: "flex-end", gap: "12px" }}>
            <button onClick={onClose} className="btn-secondary" style={{ padding: "8px 24px" }}>取消</button>
            <button onClick={handleSave} className="btn-primary" disabled={saving} style={{ padding: "8px 24px" }}>
              {saving ? "保存中..." : "保存配置"}
            </button>
          </div>
          {saveSuccess && (
             <div style={{ 
               position: "absolute", 
               bottom: "24px", 
               left: "224px", 
               color: "#4caf50", 
               background: "rgba(76, 175, 80, 0.1)", 
               padding: "8px 16px", 
               borderRadius: "4px",
               border: "1px solid rgba(76, 175, 80, 0.3)"
             }}>
               ✅ 配置已保存
             </div>
          )}
        </div>
      </div>
    </GamePanel>
  );
}

function NavButton({ active, onClick, icon, label, desc }: { active: boolean; onClick: () => void; icon: string; label: string; desc: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "12px 24px",
        background: active ? "rgba(255,255,255,0.08)" : "transparent",
        border: "none",
        borderLeft: active ? "3px solid #3b82f6" : "3px solid transparent",
        color: active ? "#fff" : "rgba(255,255,255,0.6)",
        cursor: "pointer",
        transition: "all 0.2s",
        display: "flex",
        alignItems: "center",
        gap: "12px"
      }}
    >
      <span style={{ fontSize: "1.2rem" }}>{icon}</span>
      <div>
        <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{label}</div>
        <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>{desc}</div>
      </div>
    </button>
  );
}
