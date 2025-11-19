import { useState } from "react";

import type { UIConfig, CapabilityModelConfig } from "../services/api.types";
import { testApiConnection } from "../services/api";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => void;
}

const providers = ["openai", "deepseek", "anthropic", "custom"];
type Tab = "primary" | "embedding" | "capabilities";

// AI 能力列表定义
const AI_CAPABILITIES = [
  { key: "turn_report", label: "主推演叙事", priority: "high" },
  { key: "focus_batch", label: "重点批次推演", priority: "high" },
  { key: "critical_detail", label: "关键物种分析", priority: "high" },
  { key: "speciation", label: "物种分化", priority: "medium" },
  { key: "migration", label: "迁徙建议", priority: "low" },
  { key: "pressure_escalation", label: "压力升级", priority: "low" },
  { key: "reemergence", label: "物种重现/起名", priority: "low" },
] as const;

export function SettingsDrawer({ config, onClose, onSave }: Props) {
  const [form, setForm] = useState(config);
  const [tab, setTab] = useState<Tab>("primary");
  const [testingMain, setTestingMain] = useState(false);
  const [testResultMain, setTestResultMain] = useState<{ success: boolean; message: string; details?: string } | null>(null);
  const [testingCapability, setTestingCapability] = useState<string | null>(null);
  const [testResultCapability, setTestResultCapability] = useState<Record<string, { success: boolean; message: string; details?: string }>>({});
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [testResultEmbedding, setTestResultEmbedding] = useState<{ success: boolean; message: string; details?: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  function handleChange<T extends keyof UIConfig>(field: T, value: UIConfig[T]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateCapability(key: string, field: keyof CapabilityModelConfig, value: string | number) {
    setForm((prev) => {
      const configs = prev.capability_configs || {};
      const current = configs[key] || { provider: "openai", model: "gpt-4o", timeout: 60 };
      return {
        ...prev,
        capability_configs: {
          ...configs,
          [key]: { ...current, [field]: value },
        },
      };
    });
  }

  async function handleTestMain() {
    if (!form.ai_base_url || !form.ai_api_key) {
      setTestResultMain({ success: false, message: "请先填写 API Base URL 和 API Key" });
      return;
    }
    setTestingMain(true);
    setTestResultMain(null);
    try {
      const result = await testApiConnection({
        type: "chat",
        base_url: form.ai_base_url,
        api_key: form.ai_api_key?.trim() || "", // 去除首尾空格
        model: form.ai_model || "gpt-3.5-turbo",
      });
      setTestResultMain(result);
    } catch (error) {
      setTestResultMain({ success: false, message: "测试失败：" + String(error) });
    } finally {
      setTestingMain(false);
    }
  }

  async function handleTestCapability(capKey: string) {
    const capConfig = form.capability_configs?.[capKey];
    const baseUrl = capConfig?.base_url || form.ai_base_url;
    const apiKey = capConfig?.api_key || form.ai_api_key;
    const model = capConfig?.model || form.ai_model || "gpt-3.5-turbo";

    if (!baseUrl || !apiKey) {
      setTestResultCapability((prev) => ({
        ...prev,
        [capKey]: { success: false, message: "请先填写 API Base URL 和 API Key" },
      }));
      return;
    }

    setTestingCapability(capKey);
    setTestResultCapability((prev) => {
      const newResults = { ...prev };
      delete newResults[capKey];
      return newResults;
    });

    try {
      const result = await testApiConnection({
        type: "chat",
        base_url: baseUrl,
        api_key: apiKey?.trim() || "", // 去除首尾空格
        model: model,
      });
      setTestResultCapability((prev) => ({ ...prev, [capKey]: result }));
    } catch (error) {
      setTestResultCapability((prev) => ({
        ...prev,
        [capKey]: { success: false, message: "测试失败：" + String(error) },
      }));
    } finally {
      setTestingCapability(null);
    }
  }

  async function handleTestEmbedding() {
    if (!form.embedding_base_url || !form.embedding_api_key) {
      setTestResultEmbedding({ success: false, message: "请先填写 API Base URL 和 API Key" });
      return;
    }
    setTestingEmbedding(true);
    setTestResultEmbedding(null);
    try {
      const result = await testApiConnection({
        type: "embedding",
        base_url: form.embedding_base_url,
        api_key: form.embedding_api_key?.trim() || "", // 去除首尾空格
        model: form.embedding_model || "text-embedding-ada-002",
      });
      setTestResultEmbedding(result);
    } catch (error) {
      setTestResultEmbedding({ success: false, message: "测试失败：" + String(error) });
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
      // 3秒后自动隐藏成功提示
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error("保存配置失败:", error);
      alert("保存配置失败：" + String(error));
    } finally {
      setSaving(false);
    }
  }


  return (
    <div className="drawer-overlay">
      <div className="drawer-panel settings-panel settings-redesign">
        <header className="settings-header">
          <div>
            <h2>🔧 模型与 API 设置</h2>
            <p>配置 AI 模型以驱动演化推演，支持分功能精细化成本控制</p>
          </div>
          <button onClick={onClose} className="close-btn">✕</button>
        </header>
        <div className="settings-tabs">
          <button 
            className={`settings-tab ${tab === "primary" ? "active" : ""}`} 
            onClick={() => setTab("primary")}
          >
            <span className="tab-icon">⚙️</span>
            <span className="tab-label">主模型</span>
          </button>
          <button 
            className={`settings-tab ${tab === "capabilities" ? "active" : ""}`} 
            onClick={() => setTab("capabilities")}
          >
            <span className="tab-icon">🎯</span>
            <span className="tab-label">分功能配置</span>
          </button>
          <button 
            className={`settings-tab ${tab === "embedding" ? "active" : ""}`} 
            onClick={() => setTab("embedding")}
          >
            <span className="tab-icon">🧬</span>
            <span className="tab-label">向量模型</span>
          </button>
        </div>
        <div className="settings-content">
          {tab === "primary" && (
            <div className="settings-section">
              <div className="section-intro">
                <h3>全局默认配置</h3>
                <p>该配置将应用于所有 AI 功能，除非在"分功能配置"中单独设置</p>
              </div>
              <div className="form-grid">
                <label className="form-field">
                  <span className="field-label">服务商</span>
                  <select
                    className="field-input"
                    value={form.ai_provider ?? ""}
                    onChange={(e) => handleChange("ai_provider", e.target.value || null)}
                  >
                    <option value="">未选择</option>
                    {providers.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span className="field-label">模型名称</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.ai_model ?? ""}
                    onChange={(e) => handleChange("ai_model", e.target.value)}
                    placeholder="gpt-4o, deepseek-chat …"
                  />
                </label>
                <label className="form-field full-width">
                  <span className="field-label">API Base URL</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.ai_base_url ?? ""}
                    onChange={(e) => handleChange("ai_base_url", e.target.value)}
                    placeholder="https://api.openai.com/v1"
                  />
                </label>
                <label className="form-field full-width">
                  <span className="field-label">API Key</span>
                  <input
                    className="field-input"
                    type="password"
                    value={form.ai_api_key ?? ""}
                    onChange={(e) => handleChange("ai_api_key", e.target.value)}
                    placeholder="请输入您的 API Key"
                  />
                </label>
                <label className="form-field">
                  <span className="field-label">超时时间（秒）</span>
                  <input
                    className="field-input"
                    type="number"
                    min={5}
                    max={300}
                    value={form.ai_timeout}
                    onChange={(e) => handleChange("ai_timeout", parseInt(e.target.value, 10))}
                  />
                </label>
              </div>
              
              <div className="test-section">
                <button
                  type="button"
                  onClick={handleTestMain}
                  disabled={testingMain}
                  className="test-btn"
                >
                  {testingMain ? "🔄 测试中..." : "🧪 测试连接"}
                </button>
                {testResultMain && (
                  <div className={`test-result ${testResultMain.success ? "success" : "error"}`}>
                    <div className="test-message">{testResultMain.message}</div>
                    {testResultMain.details && (
                      <div className="test-details">{testResultMain.details}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
          {tab === "capabilities" && (
            <div className="settings-section capabilities-section">
              <div className="section-intro">
                <h3>分功能精细配置</h3>
                <p>为不同 AI 能力单独配置模型，优化成本与性能。留空的配置项将使用"主模型"中的设置。</p>
              </div>

              <div className="capabilities-list">
                {AI_CAPABILITIES.map((cap) => {
                  const capConfig = form.capability_configs?.[cap.key] || {
                    provider: "",
                    model: "",
                    base_url: "",
                    api_key: "",
                    timeout: 60,
                  };
                  return (
                    <div key={cap.key} className={`capability-card priority-${cap.priority}`}>
                      <div className="capability-header">
                        <h4 className="capability-title">{cap.label}</h4>
                        <span className={`priority-tag priority-${cap.priority}`}>
                          {cap.priority === "high" ? "🔴 高" : cap.priority === "medium" ? "🟡 中" : "🟢 低"}
                        </span>
                      </div>
                      <div className="capability-form">
                        <div className="form-row">
                          <label className="form-field compact">
                            <span className="field-label">服务商</span>
                            <select
                              className="field-input"
                              value={capConfig.provider}
                              onChange={(e) => updateCapability(cap.key, "provider", e.target.value)}
                            >
                              <option value="">未选择</option>
                              {providers.map((p) => (
                                <option key={p} value={p}>
                                  {p}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="form-field compact">
                            <span className="field-label">模型</span>
                            <input
                              className="field-input"
                              type="text"
                              placeholder="gpt-4o, gpt-4o-mini ..."
                              value={capConfig.model}
                              onChange={(e) => updateCapability(cap.key, "model", e.target.value)}
                            />
                          </label>
                        </div>
                        <label className="form-field compact">
                          <span className="field-label">API Base URL</span>
                          <input
                            className="field-input"
                            type="text"
                            placeholder="https://api.openai.com/v1"
                            value={capConfig.base_url || ""}
                            onChange={(e) => updateCapability(cap.key, "base_url", e.target.value)}
                          />
                        </label>
                        <label className="form-field compact">
                          <span className="field-label">API Key</span>
                          <input
                            className="field-input"
                            type="password"
                            placeholder="留空使用主模型配置"
                            value={capConfig.api_key || ""}
                            onChange={(e) => updateCapability(cap.key, "api_key", e.target.value)}
                          />
                        </label>
                        <div className="capability-test">
                          <button
                            type="button"
                            onClick={() => handleTestCapability(cap.key)}
                            disabled={testingCapability === cap.key}
                            className="test-btn-small"
                          >
                            {testingCapability === cap.key ? "🔄 测试中..." : "🧪 测试"}
                          </button>
                          {testResultCapability[cap.key] && (
                            <div className={`test-result-inline ${testResultCapability[cap.key].success ? "success" : "error"}`}>
                              {testResultCapability[cap.key].message}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {tab === "embedding" && (
            <div className="settings-section">
              <div className="section-intro">
                <h3>向量模型配置</h3>
                <p>配置远程 Embedding API 以提供更精准的生态位向量计算。留空将使用本地近似向量。</p>
              </div>

              <div className="form-grid">
                <label className="form-field">
                  <span className="field-label">提供商</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.embedding_provider ?? ""}
                    onChange={(e) => handleChange("embedding_provider", e.target.value)}
                    placeholder="openai"
                  />
                </label>
                <label className="form-field">
                  <span className="field-label">模型名称</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.embedding_model ?? ""}
                    onChange={(e) => handleChange("embedding_model", e.target.value)}
                    placeholder="text-embedding-3-small"
                  />
                </label>
                <label className="form-field full-width">
                  <span className="field-label">API Base URL</span>
                  <input
                    className="field-input"
                    type="text"
                    value={form.embedding_base_url ?? ""}
                    onChange={(e) => handleChange("embedding_base_url", e.target.value)}
                    placeholder="https://api.siliconflow.cn/v1"
                  />
                </label>
                <label className="form-field full-width">
                  <span className="field-label">API Key</span>
                  <input
                    className="field-input"
                    type="password"
                    value={form.embedding_api_key ?? ""}
                    onChange={(e) => handleChange("embedding_api_key", e.target.value)}
                    placeholder="请输入您的 API Key"
                  />
                </label>
              </div>
              
              <div className="test-section">
                <button
                  type="button"
                  onClick={handleTestEmbedding}
                  disabled={testingEmbedding}
                  className="test-btn"
                >
                  {testingEmbedding ? "🔄 测试中..." : "🧪 测试连接"}
                </button>
                {testResultEmbedding && (
                  <div className={`test-result ${testResultEmbedding.success ? "success" : "error"}`}>
                    <div className="test-message">{testResultEmbedding.message}</div>
                    {testResultEmbedding.details && (
                      <div className="test-details">{testResultEmbedding.details}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
        
        <footer className="settings-footer">
          <div className="save-status">
            {saveSuccess && (
              <div className="save-success-message">
                ✅ 配置已保存成功！
              </div>
            )}
          </div>
          <button onClick={handleSave} disabled={saving} className="save-btn">
            {saving ? "💾 保存中..." : "💾 保存配置"}
          </button>
        </footer>
      </div>
    </div>
  );
}
