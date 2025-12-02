/**
 * ConnectionSection - 服务商连接配置 (全新设计)
 */

import { memo, useCallback, useState, type Dispatch } from "react";
import type { ProviderConfig, ProviderType } from "@/services/api.types";
import type { SettingsAction, TestResult } from "../types";
import { testApiConnection, fetchProviderModels, type ModelInfo } from "@/services/api";
import { PROVIDER_API_TYPES } from "../constants";
import { getProviderLogo, getProviderTypeBadge, generateId } from "../reducer";
import { SectionHeader, ActionButton } from "../common/Controls";

interface Props {
  providers: Record<string, ProviderConfig>;
  selectedProviderId: string | null;
  testResults: Record<string, TestResult>;
  testingProviderId: string | null;
  showApiKeys: Record<string, boolean>;
  dispatch: Dispatch<SettingsAction>;
}

export const ConnectionSection = memo(function ConnectionSection({
  providers,
  selectedProviderId,
  testResults,
  testingProviderId,
  showApiKeys,
  dispatch,
}: Props) {
  const providerList = Object.values(providers);
  const selectedProvider = selectedProviderId ? providers[selectedProviderId] : null;

  const [fetchingModels, setFetchingModels] = useState<string | null>(null);
  const [providerModels, setProviderModels] = useState<Record<string, ModelInfo[]>>({});
  const [modelFetchError, setModelFetchError] = useState<Record<string, string>>({});

  // 添加自定义服务商
  const handleAddCustom = useCallback((apiType: ProviderType, typeName: string) => {
    const newId = `custom_${apiType}_${generateId()}`;
    const baseUrls: Record<ProviderType, string> = {
      openai: "https://api.example.com/v1",
      anthropic: "https://api.anthropic.com/v1",
      google: "https://generativelanguage.googleapis.com/v1beta",
    };
    dispatch({
      type: "ADD_PROVIDER",
      provider: {
        id: newId,
        name: `自定义 ${typeName}`,
        type: apiType,
        provider_type: apiType,
        base_url: baseUrls[apiType],
        api_key: "",
        models: [],
      },
    });
    dispatch({ type: "SELECT_PROVIDER", id: newId });
  }, [dispatch]);

  // 测试连接
  const handleTest = useCallback(async (provider: ProviderConfig) => {
    if (!provider.api_key || !provider.base_url) {
      dispatch({
        type: "SET_TEST_RESULT",
        providerId: provider.id,
        result: { success: false, message: "请填写 API Key 和 Base URL" },
      });
      return;
    }

    dispatch({ type: "SET_TESTING_PROVIDER", id: provider.id });

    try {
      const result = await testApiConnection({
        type: "chat",
        base_url: provider.base_url,
        api_key: provider.api_key,
        model: provider.models?.[0] || "gpt-3.5-turbo",
        provider_type: provider.provider_type || "openai",
      });
      dispatch({ type: "SET_TEST_RESULT", providerId: provider.id, result });
    } catch (err: unknown) {
      dispatch({
        type: "SET_TEST_RESULT",
        providerId: provider.id,
        result: { success: false, message: err instanceof Error ? err.message : "测试失败" },
      });
    } finally {
      dispatch({ type: "SET_TESTING_PROVIDER", id: null });
    }
  }, [dispatch]);

  // 删除服务商
  const handleDelete = useCallback((id: string) => {
    dispatch({
      type: "SET_CONFIRM_DIALOG",
      dialog: {
        isOpen: true,
        title: "删除服务商",
        message: "确定要删除这个服务商配置吗？此操作不可撤销。",
        variant: "danger",
        onConfirm: () => {
          dispatch({ type: "REMOVE_PROVIDER", id });
          if (selectedProviderId === id) {
            dispatch({ type: "SELECT_PROVIDER", id: null });
          }
        },
      },
    });
  }, [dispatch, selectedProviderId]);

  // 获取模型列表
  const handleFetchModels = useCallback(async (provider: ProviderConfig) => {
    if (!provider.api_key || !provider.base_url) {
      setModelFetchError((prev) => ({
        ...prev,
        [provider.id]: "请先填写 API Key 和 Base URL",
      }));
      return;
    }

    setFetchingModels(provider.id);
    setModelFetchError((prev) => {
      const newErrors = { ...prev };
      delete newErrors[provider.id];
      return newErrors;
    });

    try {
      const result = await fetchProviderModels({
        base_url: provider.base_url,
        api_key: provider.api_key,
        provider_type: provider.provider_type || "openai",
      });

      if (result.success && result.models.length > 0) {
        // 只存储到临时状态，不自动添加到收藏
        setProviderModels((prev) => ({
          ...prev,
          [provider.id]: result.models,
        }));
      } else {
        setModelFetchError((prev) => ({
          ...prev,
          [provider.id]: result.message || "未获取到模型列表",
        }));
      }
    } catch (err: unknown) {
      setModelFetchError((prev) => ({
        ...prev,
        [provider.id]: err instanceof Error ? err.message : "获取模型列表失败",
      }));
    } finally {
      setFetchingModels(null);
    }
  }, [dispatch]);

  return (
    <div className="section-page">
      <SectionHeader
        icon="🔌"
        title="服务商配置"
        subtitle="管理 AI API 服务商连接，配置 API Key 和端点地址"
      />

      <div className="connection-layout">
        {/* 左侧：服务商列表 */}
        <div className="provider-list-panel">
          <div className="provider-list-header">
            <span className="provider-list-title">已配置服务商</span>
            <span className="provider-count-badge">{providerList.length} 个</span>
          </div>

          <div className="provider-list-scroll">
            {providerList.length === 0 ? (
              <div className="empty-state" style={{ padding: "24px 16px" }}>
                <div className="empty-state-icon">🔌</div>
                <div className="empty-state-title">暂无服务商</div>
                <div className="empty-state-desc">点击下方按钮添加</div>
              </div>
            ) : (
              providerList.map((provider) => {
                const isSelected = selectedProviderId === provider.id;
                const testResult = testResults[provider.id];
                const badge = getProviderTypeBadge(provider.provider_type || "openai");

                return (
                  <div
                    key={provider.id}
                    className={`provider-item ${isSelected ? "active" : ""}`}
                    onClick={() => dispatch({ type: "SELECT_PROVIDER", id: provider.id })}
                  >
                    <div className="provider-logo">{getProviderLogo(provider)}</div>
                    <div className="provider-info">
                      <div className="provider-name">{provider.name}</div>
                      <div className="provider-type-badge" style={{ color: badge.color }}>
                        {badge.text}
                      </div>
                    </div>
                    {testResult && (
                      <div className={`provider-status ${testResult.success ? "success" : "error"}`} />
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* 添加服务商 */}
          <div className="add-provider-section">
            <div className="add-provider-label">添加服务商</div>
            <div className="preset-btns">
              <button className="preset-btn" onClick={() => handleAddCustom("openai", "OpenAI")}>
                <span>🤖</span>
                <span>OpenAI 兼容</span>
              </button>
              <button className="preset-btn" onClick={() => handleAddCustom("anthropic", "Claude")}>
                <span>🎭</span>
                <span>Claude</span>
              </button>
              <button className="preset-btn" onClick={() => handleAddCustom("google", "Gemini")}>
                <span>💎</span>
                <span>Gemini</span>
              </button>
            </div>
          </div>
        </div>

        {/* 右侧：编辑面板 */}
        <div className="provider-edit-panel">
          {selectedProvider ? (
            <>
              <div className="edit-panel-header">
                <div className="edit-panel-title">
                  <span className="edit-panel-logo">{getProviderLogo(selectedProvider)}</span>
                  <div>
                    <div className="edit-panel-name">{selectedProvider.name}</div>
                    <div className="edit-panel-type">
                      {getProviderTypeBadge(selectedProvider.provider_type || "openai").text}
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-ghost danger"
                  onClick={() => handleDelete(selectedProvider.id)}
                >
                  🗑️ 删除
                </button>
              </div>

              <div className="edit-panel-body">
                {/* 服务商名称 */}
                <div className="form-row">
                  <div className="form-label">
                    <div className="form-label-text">服务商名称</div>
                  </div>
                  <div className="form-control" style={{ flex: 1 }}>
                    <input
                      type="text"
                      className="text-input"
                      value={selectedProvider.name}
                      onChange={(e) =>
                        dispatch({
                          type: "UPDATE_PROVIDER",
                          id: selectedProvider.id,
                          field: "name",
                          value: e.target.value,
                        })
                      }
                      placeholder="输入便于识别的名称"
                      style={{
                        width: "100%",
                        padding: "10px 14px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-md)",
                        color: "var(--s-text)",
                        fontSize: "0.9rem",
                      }}
                    />
                  </div>
                </div>

                {/* API 类型选择 */}
                <div style={{ marginTop: "16px" }}>
                  <div className="form-label-text" style={{ marginBottom: "10px" }}>
                    API 类型
                  </div>
                  <div className="api-type-grid">
                    {PROVIDER_API_TYPES.map((t) => (
                      <button
                        key={t.value}
                        className={`api-type-btn ${selectedProvider.provider_type === t.value ? "active" : ""}`}
                        onClick={() =>
                          dispatch({
                            type: "UPDATE_PROVIDER",
                            id: selectedProvider.id,
                            field: "provider_type",
                            value: t.value as ProviderType,
                          })
                        }
                      >
                        <span className="api-type-label">{t.label}</span>
                        <span className="api-type-desc">{t.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Base URL */}
                <div className="form-row" style={{ marginTop: "16px" }}>
                  <div className="form-label">
                    <div className="form-label-text">Base URL</div>
                    <div className="form-label-desc">API 端点地址，通常以 /v1 结尾</div>
                  </div>
                  <div className="form-control" style={{ flex: 1 }}>
                    <input
                      type="text"
                      value={selectedProvider.base_url || ""}
                      onChange={(e) =>
                        dispatch({
                          type: "UPDATE_PROVIDER",
                          id: selectedProvider.id,
                          field: "base_url",
                          value: e.target.value,
                        })
                      }
                      placeholder="https://api.example.com/v1"
                      style={{
                        width: "100%",
                        padding: "10px 14px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-md)",
                        color: "var(--s-text)",
                        fontSize: "0.9rem",
                        fontFamily: "var(--s-font-mono)",
                      }}
                    />
                  </div>
                </div>

                {/* API Key */}
                <div className="form-row" style={{ marginTop: "16px" }}>
                  <div className="form-label">
                    <div className="form-label-text">API Key</div>
                  </div>
                  <div className="form-control" style={{ flex: 1, position: "relative" }}>
                    <input
                      type={showApiKeys[selectedProvider.id] ? "text" : "password"}
                      value={selectedProvider.api_key || ""}
                      onChange={(e) =>
                        dispatch({
                          type: "UPDATE_PROVIDER",
                          id: selectedProvider.id,
                          field: "api_key",
                          value: e.target.value,
                        })
                      }
                      placeholder="sk-..."
                      style={{
                        width: "100%",
                        padding: "10px 48px 10px 14px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-md)",
                        color: "var(--s-text)",
                        fontSize: "0.9rem",
                        fontFamily: "var(--s-font-mono)",
                      }}
                    />
                    <button
                      type="button"
                      onClick={() =>
                        dispatch({ type: "TOGGLE_API_KEY_VISIBILITY", providerId: selectedProvider.id })
                      }
                      style={{
                        position: "absolute",
                        right: "8px",
                        top: "50%",
                        transform: "translateY(-50%)",
                        background: "transparent",
                        border: "none",
                        color: "var(--s-text-muted)",
                        cursor: "pointer",
                        fontSize: "1.1rem",
                        padding: "4px",
                      }}
                    >
                      {showApiKeys[selectedProvider.id] ? "🙈" : "👁️"}
                    </button>
                  </div>
                </div>

                {/* 收藏的模型 */}
                <div style={{ marginTop: "16px" }}>
                  <div className="form-label-text" style={{ marginBottom: "10px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span>收藏模型</span>
                    <span style={{ fontSize: "0.72rem", color: "var(--s-text-muted)", fontWeight: 400 }}>
                      {(selectedProvider.models || []).length} 个收藏，
                      {(selectedProvider.models || []).filter(m => !(selectedProvider.disabled_models || []).includes(m)).length} 个启用
                    </span>
                  </div>
                  
                  {(selectedProvider.models || []).length === 0 ? (
                    <div style={{
                      padding: "16px",
                      background: "var(--s-bg-deep)",
                      border: "1px dashed var(--s-border)",
                      borderRadius: "var(--s-radius-md)",
                      textAlign: "center",
                      color: "var(--s-text-muted)",
                      fontSize: "0.82rem",
                    }}>
                      暂无收藏模型，点击下方"获取模型列表"添加
                    </div>
                  ) : (
                    <div style={{
                      background: "var(--s-bg-deep)",
                      border: "1px solid var(--s-border)",
                      borderRadius: "var(--s-radius-md)",
                      maxHeight: "200px",
                      overflowY: "auto",
                    }}>
                      {(selectedProvider.models || []).map((modelId) => {
                        const isEnabled = !(selectedProvider.disabled_models || []).includes(modelId);
                        return (
                          <div
                            key={modelId}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              padding: "8px 12px",
                              borderBottom: "1px solid var(--s-border)",
                              opacity: isEnabled ? 1 : 0.5,
                            }}
                          >
                            {/* 启用/禁用开关 */}
                            <button
                              onClick={() => {
                                const disabledModels = selectedProvider.disabled_models || [];
                                if (isEnabled) {
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "disabled_models",
                                    value: [...disabledModels, modelId],
                                  });
                                } else {
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "disabled_models",
                                    value: disabledModels.filter(m => m !== modelId),
                                  });
                                }
                              }}
                              style={{
                                width: "36px",
                                height: "20px",
                                borderRadius: "10px",
                                border: "none",
                                background: isEnabled ? "var(--s-success)" : "var(--s-bg-glass)",
                                cursor: "pointer",
                                position: "relative",
                                marginRight: "10px",
                                flexShrink: 0,
                                transition: "all 0.2s",
                              }}
                              title={isEnabled ? "点击禁用" : "点击启用"}
                            >
                              <div style={{
                                width: "16px",
                                height: "16px",
                                borderRadius: "50%",
                                background: "#fff",
                                position: "absolute",
                                top: "2px",
                                left: isEnabled ? "18px" : "2px",
                                transition: "left 0.2s",
                              }} />
                            </button>
                            
                            {/* 模型名称 */}
                            <span style={{
                              flex: 1,
                              fontSize: "0.82rem",
                              color: isEnabled ? "var(--s-text)" : "var(--s-text-muted)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}>
                              {modelId}
                            </span>
                            
                            {/* 删除按钮 */}
                            <button
                              onClick={() => {
                                dispatch({
                                  type: "UPDATE_PROVIDER",
                                  id: selectedProvider.id,
                                  field: "models",
                                  value: (selectedProvider.models || []).filter(m => m !== modelId),
                                });
                                // 同时从禁用列表中移除
                                if ((selectedProvider.disabled_models || []).includes(modelId)) {
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "disabled_models",
                                    value: (selectedProvider.disabled_models || []).filter(m => m !== modelId),
                                  });
                                }
                              }}
                              style={{
                                width: "24px",
                                height: "24px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                background: "transparent",
                                border: "none",
                                color: "var(--s-text-muted)",
                                cursor: "pointer",
                                fontSize: "0.9rem",
                                opacity: 0.6,
                                transition: "opacity 0.15s",
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
                              onMouseLeave={(e) => e.currentTarget.style.opacity = "0.6"}
                              title="移除收藏"
                            >
                              ✕
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  
                  {/* 手动添加模型 */}
                  <div style={{ marginTop: "10px", display: "flex", gap: "8px" }}>
                    <input
                      type="text"
                      placeholder="输入模型名称手动添加..."
                      id={`manual-model-${selectedProvider.id}`}
                      style={{
                        flex: 1,
                        padding: "8px 12px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-sm)",
                        color: "var(--s-text)",
                        fontSize: "0.82rem",
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          const input = e.currentTarget;
                          const value = input.value.trim();
                          if (value && !(selectedProvider.models || []).includes(value)) {
                            dispatch({
                              type: "UPDATE_PROVIDER",
                              id: selectedProvider.id,
                              field: "models",
                              value: [...(selectedProvider.models || []), value],
                            });
                            input.value = "";
                          }
                        }
                      }}
                    />
                    <button
                      onClick={() => {
                        const input = document.getElementById(`manual-model-${selectedProvider.id}`) as HTMLInputElement;
                        const value = input?.value.trim();
                        if (value && !(selectedProvider.models || []).includes(value)) {
                          dispatch({
                            type: "UPDATE_PROVIDER",
                            id: selectedProvider.id,
                            field: "models",
                            value: [...(selectedProvider.models || []), value],
                          });
                          if (input) input.value = "";
                        }
                      }}
                      style={{
                        padding: "8px 14px",
                        background: "var(--s-primary)",
                        border: "none",
                        borderRadius: "var(--s-radius-sm)",
                        color: "#fff",
                        fontSize: "0.82rem",
                        cursor: "pointer",
                      }}
                    >
                      添加
                    </button>
                  </div>
                </div>

                {/* 操作按钮 */}
                <div style={{ display: "flex", gap: "12px", marginTop: "20px", paddingTop: "16px", borderTop: "1px solid var(--s-border)" }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => handleTest(selectedProvider)}
                    disabled={testingProviderId !== null}
                  >
                    {testingProviderId === selectedProvider.id ? (
                      <>
                        <span className="spinner" /> 测试中...
                      </>
                    ) : (
                      "🔍 测试连接"
                    )}
                  </button>
                  <button
                    className="btn btn-outline"
                    onClick={() => handleFetchModels(selectedProvider)}
                    disabled={fetchingModels !== null || !selectedProvider.api_key || !selectedProvider.base_url}
                  >
                    {fetchingModels === selectedProvider.id ? (
                      <>
                        <span className="spinner" /> 获取中...
                      </>
                    ) : (
                      "📋 获取模型列表"
                    )}
                  </button>
                </div>

                {/* 测试结果 */}
                {testResults[selectedProvider.id] && (
                  <div className={`test-result ${testResults[selectedProvider.id].success ? "success" : "error"}`}>
                    <span>{testResults[selectedProvider.id].success ? "✓" : "✗"}</span>
                    <span>{testResults[selectedProvider.id].message}</span>
                  </div>
                )}

                {modelFetchError[selectedProvider.id] && (
                  <div className="test-result error">
                    <span>✗</span>
                    <span>{modelFetchError[selectedProvider.id]}</span>
                  </div>
                )}

                {/* 已获取的模型列表 */}
                {providerModels[selectedProvider.id] && providerModels[selectedProvider.id].length > 0 && (
                  <div style={{ marginTop: "16px", padding: "12px", background: "var(--s-info-bg)", border: "1px solid rgba(96, 165, 250, 0.3)", borderRadius: "var(--s-radius-md)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", fontSize: "0.85rem", color: "var(--s-info)" }}>
                      <span>✓</span>
                      <span>已获取 {providerModels[selectedProvider.id].length} 个模型</span>
                      <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "var(--s-text-muted)" }}>
                        点击 + 添加到收藏
                      </span>
                    </div>
                    <div style={{ maxHeight: "200px", overflowY: "auto" }}>
                      {providerModels[selectedProvider.id].map((model) => {
                        const isAdded = (selectedProvider.models || []).includes(model.id);
                        return (
                          <div
                            key={model.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              padding: "6px 8px",
                              fontSize: "0.78rem",
                              color: isAdded ? "var(--s-success)" : "var(--s-text-secondary)",
                              background: isAdded ? "rgba(16, 185, 129, 0.08)" : "transparent",
                              borderRadius: "var(--s-radius-sm)",
                              marginBottom: "4px",
                              transition: "all 0.15s",
                            }}
                          >
                            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {isAdded && <span style={{ marginRight: "6px" }}>✓</span>}
                              {model.name || model.id}
                            </span>
                            {model.context_window && (
                              <span style={{ fontSize: "0.68rem", color: "var(--s-text-muted)", marginLeft: "8px", marginRight: "8px" }}>
                                {model.context_window >= 1000000
                                  ? `${(model.context_window / 1000000).toFixed(1)}M`
                                  : `${Math.round(model.context_window / 1000)}K`}
                              </span>
                            )}
                            <button
                              onClick={() => {
                                const currentModels = selectedProvider.models || [];
                                if (isAdded) {
                                  // 移除模型
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "models",
                                    value: currentModels.filter((m) => m !== model.id),
                                  });
                                } else {
                                  // 添加模型
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "models",
                                    value: [...currentModels, model.id],
                                  });
                                }
                              }}
                              style={{
                                width: "24px",
                                height: "24px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                background: isAdded ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)",
                                border: `1px solid ${isAdded ? "rgba(239, 68, 68, 0.3)" : "rgba(16, 185, 129, 0.3)"}`,
                                borderRadius: "50%",
                                color: isAdded ? "var(--s-danger)" : "var(--s-success)",
                                cursor: "pointer",
                                fontSize: "0.9rem",
                                fontWeight: 700,
                                flexShrink: 0,
                                transition: "all 0.15s",
                              }}
                              title={isAdded ? "移除模型" : "添加模型"}
                            >
                              {isAdded ? "−" : "+"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">👈</div>
              <div className="empty-state-title">选择左侧服务商进行编辑</div>
              <div className="empty-state-desc">或点击添加按钮创建新的服务商配置</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
