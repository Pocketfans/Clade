/**
 * ConnectionSection - 服务商连接配置 (全新设计)
 */

import { memo, useCallback, useEffect, useMemo, useState, type Dispatch } from "react";
import type { ProviderConfig, ProviderType } from "@/services/api.types";
import type { SettingsAction, TestResult } from "../types";
import { testApiConnection, fetchProviderModels, type ModelInfo } from "@/services/api";
import { PROVIDER_API_TYPES } from "../constants";
import {
  canonicalizeProviderRecords,
  generateId,
  getCanonicalProviderId,
  getProviderLogo,
  getProviderTypeBadge,
} from "../reducer";
import { SectionHeader, ActionButton, InfoBox, ConfigGroup } from "../common/Controls";

interface Props {
  providers: Record<string, ProviderConfig>;
  selectedProviderId: string | null;
  testResults: Record<string, TestResult>;
  testingProviderId: string | null;
  showApiKeys: Record<string, boolean>;
  dispatch: Dispatch<SettingsAction>;
}

const hasUsableApiKey = (provider: ProviderConfig) =>
  Boolean(provider.api_key || provider.api_key_configured) && !provider.api_key_clear_requested;

export const ConnectionSection = memo(function ConnectionSection({
  providers,
  selectedProviderId,
  testResults,
  testingProviderId,
  showApiKeys,
  dispatch,
}: Props) {
  const canonicalProviders = useMemo(() => canonicalizeProviderRecords(providers), [providers]);
  const canonicalSelectedProviderId = getCanonicalProviderId(providers, selectedProviderId);
  const providerList = Object.values(canonicalProviders);
  const selectedProvider = canonicalSelectedProviderId
    ? canonicalProviders[canonicalSelectedProviderId]
    : null;
  const selectedProviderDefaultModel = selectedProvider?.selected_models?.[0] || "";

  const [fetchingModels, setFetchingModels] = useState<string | null>(null);
  const [providerModels, setProviderModels] = useState<Record<string, ModelInfo[]>>({});
  const [modelFetchError, setModelFetchError] = useState<Record<string, string>>({});

  const handleDefaultModelChange = useCallback(
    (providerId: string, value: string) => {
      const trimmed = value.trim();
      dispatch({
        type: "UPDATE_PROVIDER",
        id: providerId,
        field: "selected_models",
        value: trimmed ? [trimmed] : [],
      });
    },
    [dispatch],
  );

  useEffect(() => {
    if (!selectedProvider) return;
    const models = selectedProvider.models || [];
    const selected = selectedProvider.selected_models || [];

    if (models.length === 1 && selected[0] !== models[0]) {
      handleDefaultModelChange(selectedProvider.id, models[0]);
    } else if (selected.length && !models.includes(selected[0])) {
      handleDefaultModelChange(selectedProvider.id, "");
    }
  }, [selectedProvider, handleDefaultModelChange]);

  const removeModel = useCallback(
    (provider: ProviderConfig, modelId: string) => {
      dispatch({
        type: "UPDATE_PROVIDER",
        id: provider.id,
        field: "models",
        value: (provider.models || []).filter((m) => m !== modelId),
      });

      if ((provider.disabled_models || []).includes(modelId)) {
        dispatch({
          type: "UPDATE_PROVIDER",
          id: provider.id,
          field: "disabled_models",
          value: (provider.disabled_models || []).filter((m) => m !== modelId),
        });
      }

      if ((provider.selected_models || [])[0] === modelId) {
        handleDefaultModelChange(provider.id, "");
      }
    },
    [dispatch, handleDefaultModelChange],
  );

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
    if (!hasUsableApiKey(provider) || !provider.base_url) {
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
        provider_id: provider.id,
        base_url: provider.base_url,
        api_key: provider.api_key || "",
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

  const handleClearApiKey = useCallback((providerId: string, provider: ProviderConfig) => {
    dispatch({
      type: "SET_CONFIRM_DIALOG",
      dialog: {
        isOpen: true,
        title: "清除已保存密钥",
        message: `确定要清除 ${provider.name} 已保存的 API Key 吗？保存配置后生效。`,
        variant: "danger",
        onConfirm: () => {
          dispatch({ type: "CLEAR_PROVIDER_API_KEY", providerId });
        },
      },
    });
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
          if (canonicalSelectedProviderId === id) {
            dispatch({ type: "SELECT_PROVIDER", id: null });
          }
        },
      },
    });
  }, [canonicalSelectedProviderId, dispatch]);

  // 获取模型列表
  const handleFetchModels = useCallback(async (provider: ProviderConfig) => {
    if (!hasUsableApiKey(provider) || !provider.base_url) {
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
        provider_id: provider.id,
        base_url: provider.base_url,
        api_key: provider.api_key || "",
        provider_type: provider.provider_type || "openai",
      });

      if (result.success && result.models.length > 0) {
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
  }, []);

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
              <div className="empty-state">
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
                    className={`provider-item ${isSelected ? "selected" : ""}`}
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
                <span>OpenAI</span>
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
            <div className="edit-panel">
              <div className="edit-header">
                <div className="edit-title">
                  <div className="edit-logo">{getProviderLogo(selectedProvider)}</div>
                  <div>
                    <h3>{selectedProvider.name}</h3>
                    <div className="edit-type">
                      {getProviderTypeBadge(selectedProvider.provider_type || "openai").text}
                    </div>
                  </div>
                </div>
                <button
                  className="btn-delete"
                  onClick={() => handleDelete(selectedProvider.id)}
                >
                  🗑️ 删除
                </button>
              </div>

              <div className="edit-form">
                {/* 服务商名称 */}
                <div className="form-group">
                  <label>服务商名称</label>
                  <input
                    type="text"
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
                  />
                </div>

                {/* API 类型选择 */}
                <div className="form-group">
                  <label>API 类型</label>
                  <div className="api-type-selector">
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
                        <span className="type-label">{t.label}</span>
                        <span className="type-desc">{t.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Base URL */}
                <div className="form-group">
                  <label>Base URL <span className="field-hint">API 端点地址，通常以 /v1 结尾</span></label>
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
                    style={{ fontFamily: "monospace" }}
                  />
                </div>

                {/* API Key */}
                <div className="form-group">
                  <label>API Key</label>
                  <div className="api-key-input">
                    <input
                      type={showApiKeys[selectedProvider.id] ? "text" : "password"}
                      value={selectedProvider.api_key || ""}
                      onChange={(e) =>
                        dispatch({
                          type: "UPDATE_PROVIDER_API_KEY",
                          providerId: selectedProvider.id,
                          apiKey: e.target.value,
                        })
                      }
                      placeholder={selectedProvider.api_key_configured ? "已配置；留空会保留现有密钥" : "sk-..."}
                    />
                    <button
                      type="button"
                      className="toggle-visibility"
                      onClick={() =>
                        dispatch({ type: "TOGGLE_API_KEY_VISIBILITY", providerId: selectedProvider.id })
                      }
                    >
                      {showApiKeys[selectedProvider.id] ? "🙈" : "👁️"}
                    </button>
                    {selectedProvider.api_key_configured && !selectedProvider.api_key && (
                      <button
                        type="button"
                        className="btn btn-outline danger"
                        onClick={() => handleClearApiKey(selectedProviderId!, selectedProvider)}
                      >
                        清除已保存密钥
                      </button>
                    )}
                  </div>
                </div>

                {/* 收藏的模型 */}
                <ConfigGroup title={`收藏模型 (${(selectedProvider.models || []).length})`}>
                  {(selectedProvider.models || []).length === 0 ? (
                    <div className="empty-notice">
                      <p>暂无收藏模型</p>
                      <p className="hint">点击下方"获取模型列表"添加</p>
                    </div>
                  ) : (
                    <div className="model-list-container">
                      {(selectedProvider.models || []).map((modelId) => {
                        const isEnabled = !(selectedProvider.disabled_models || []).includes(modelId);
                        const isDefault = selectedProviderDefaultModel === modelId;
                        return (
                          <div
                            key={modelId}
                            className={`model-item ${!isEnabled ? "disabled" : ""}`}
                          >
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
                              className={`model-toggle-btn ${isEnabled ? "enabled" : ""}`}
                              title={isEnabled ? "点击禁用" : "点击启用"}
                            >
                              <div className="model-toggle-thumb" />
                            </button>
                            
                            <span className="model-info">
                              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '180px' }}>
                                {modelId}
                              </span>
                              {isDefault && (
                                <span className="model-default-badge">
                                  默认
                                </span>
                              )}
                            </span>
                            
                            <button
                              className="model-remove-btn"
                              onClick={() => removeModel(selectedProvider, modelId)}
                              title="移除收藏"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                              </svg>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  
                  {/* 手动添加模型 */}
                  <div className="add-model-group">
                    <input
                      type="text"
                      className="add-model-input"
                      placeholder="输入模型名称..."
                      id={`manual-model-${selectedProvider.id}`}
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
                      className="btn-icon-add"
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
                      title="添加模型"
                    >
                      +
                    </button>
                  </div>
                </ConfigGroup>

                {/* 默认模型 */}
                <div className="form-group">
                  <label>默认模型 <span className="field-hint">优先作为该服务商的默认调用模型，未设置时退回全局默认</span></label>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <input
                      type="text"
                      list={`default-model-options-${selectedProvider.id}`}
                      value={selectedProviderDefaultModel}
                      onChange={(e) => handleDefaultModelChange(selectedProvider.id, e.target.value)}
                      placeholder="未设置则使用全局默认"
                      style={{ flex: 1, fontFamily: "monospace" }}
                    />
                    <button
                      className="btn btn-outline"
                      onClick={() => handleDefaultModelChange(selectedProvider.id, "")}
                      disabled={!selectedProviderDefaultModel}
                    >
                      清除
                    </button>
                  </div>
                  <datalist id={`default-model-options-${selectedProvider.id}`}>
                    {(selectedProvider.models || []).map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </div>

                {/* 操作按钮 */}
                <div className="form-actions">
                  <ActionButton
                    label={testingProviderId === selectedProvider.id ? "测试中..." : "测试连接"}
                    onClick={() => handleTest(selectedProvider)}
                    variant="primary"
                    loading={testingProviderId === selectedProvider.id}
                    disabled={testingProviderId !== null || !hasUsableApiKey(selectedProvider) || !selectedProvider.base_url}
                    icon="🔍"
                  />
                  <ActionButton
                    label={fetchingModels === selectedProvider.id ? "获取中..." : "获取模型列表"}
                    onClick={() => handleFetchModels(selectedProvider)}
                    variant="secondary"
                    loading={fetchingModels === selectedProvider.id}
                    disabled={fetchingModels !== null || !hasUsableApiKey(selectedProvider) || !selectedProvider.base_url}
                    icon="📋"
                  />
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
                  <div className="fetched-models-section">
                    <div className="fetched-models-header">
                      <span>✓ 已获取 {providerModels[selectedProvider.id].length} 个模型</span>
                    </div>
                    <div className="fetched-models-list">
                      {providerModels[selectedProvider.id].map((model) => {
                        const isAdded = (selectedProvider.models || []).includes(model.id);
                        return (
                          <div
                            key={model.id}
                            className={`model-item ${isAdded ? "added" : ""}`}
                          >
                            <span className="model-name" title={model.id}>
                              {isAdded && <span style={{ marginRight: "4px" }}>✓</span>}
                              {model.name || model.id}
                            </span>
                            {model.context_window && (
                              <span className="model-context">
                                {model.context_window >= 1000000
                                  ? `${(model.context_window / 1000000).toFixed(1)}M`
                                  : `${Math.round(model.context_window / 1000)}K`}
                              </span>
                            )}
                            <button
                              className={`add-model-btn ${isAdded ? "remove" : ""}`}
                              onClick={() => {
                                const currentModels = selectedProvider.models || [];
                                if (isAdded) {
                                  removeModel(selectedProvider, model.id);
                                } else {
                                  dispatch({
                                    type: "UPDATE_PROVIDER",
                                    id: selectedProvider.id,
                                    field: "models",
                                    value: [...currentModels, model.id],
                                  });
                                  if (!(selectedProvider.selected_models || []).length) {
                                    handleDefaultModelChange(selectedProvider.id, model.id);
                                  }
                                }
                              }}
                              title={isAdded ? "移除模型" : "添加模型"}
                            >
                              {isAdded ? (
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                  <line x1="18" y1="6" x2="6" y2="18"></line>
                                  <line x1="6" y1="6" x2="18" y2="18"></line>
                                </svg>
                              ) : (
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                  <line x1="12" y1="5" x2="12" y2="19"></line>
                                  <line x1="5" y1="12" x2="19" y2="12"></line>
                                </svg>
                              )}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
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
