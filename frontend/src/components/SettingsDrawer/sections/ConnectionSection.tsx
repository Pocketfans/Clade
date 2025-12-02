/**
 * ConnectionSection - 服务商连接配置
 * 
 * 左右分栏布局：
 * - 左侧：服务商列表 + 添加按钮
 * - 右侧：选中服务商的编辑表单
 */

import { memo, useCallback, type Dispatch } from "react";
import type { ProviderConfig, ProviderType } from "@/services/api.types";
import type { SettingsAction, TestResult } from "../types";
import { testApiConnection } from "@/services/api";
import { PROVIDER_PRESETS, PROVIDER_API_TYPES } from "../constants";
import { getProviderLogo, getProviderTypeBadge, generateId } from "../reducer";

interface ConnectionSectionProps {
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
}: ConnectionSectionProps) {
  const providerList = Object.values(providers);
  const selectedProvider = selectedProviderId ? providers[selectedProviderId] : null;

  // 添加预设服务商
  const handleAddProvider = useCallback((preset: typeof PROVIDER_PRESETS[0]) => {
    const newId = `${preset.id}_${generateId()}`;
    dispatch({
      type: "ADD_PROVIDER",
      provider: {
        id: newId,
        name: `${preset.name}`,
        type: preset.provider_type,
        provider_type: preset.provider_type,
        base_url: preset.base_url,
        api_key: "",
        models: [...preset.models],
      },
    });
    dispatch({ type: "SELECT_PROVIDER", id: newId });
  }, [dispatch]);

  // 添加自定义服务商（指定 API 类型）
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

  return (
    <div className="settings-section connection-section">
      <div className="section-header-bar">
        <div>
          <h2>🔌 服务商配置</h2>
          <p className="section-subtitle">管理 AI API 服务商连接</p>
        </div>
      </div>

      {/* 左右分栏布局 */}
      <div className="connection-layout">
        {/* 左侧：服务商列表 */}
        <div className="provider-panel">
          <div className="panel-header">
            <h3>已配置服务商</h3>
            <span className="provider-count">{providerList.length} 个</span>
          </div>

          <div className="provider-list">
            {providerList.length === 0 ? (
              <div className="empty-state small">
                <p>暂无服务商</p>
                <p className="hint">点击下方按钮添加</p>
              </div>
            ) : (
              providerList.map((provider) => {
                const isSelected = selectedProviderId === provider.id;
                const isTesting = testingProviderId === provider.id;
                const testResult = testResults[provider.id];
                const badge = getProviderTypeBadge(provider.provider_type || "openai");

                return (
                  <div
                    key={provider.id}
                    className={`provider-item ${isSelected ? "selected" : ""}`}
                    onClick={() => dispatch({ type: "SELECT_PROVIDER", id: provider.id })}
                  >
                    <div className="provider-info">
                      <span className="provider-logo">{getProviderLogo(provider)}</span>
                      <div className="provider-details">
                        <span className="provider-name">{provider.name}</span>
                        <span className="provider-type" style={{ color: badge.color }}>
                          {badge.text}
                        </span>
                      </div>
                    </div>
                    <div className="provider-status">
                      {isTesting && <span className="status testing">...</span>}
                      {testResult && !isTesting && (
                        <span className={`status-dot ${testResult.success ? "success" : "error"}`} />
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* 添加预设服务商 */}
          <div className="add-section">
            <div className="add-label">快速添加</div>
            <div className="preset-buttons">
              {PROVIDER_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  className="preset-btn-small"
                  onClick={() => handleAddProvider(preset)}
                  title={preset.description}
                >
                  <span>{preset.logo}</span>
                  <span>{preset.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 添加自定义服务商 */}
          <div className="add-section">
            <div className="add-label">自定义（选择 API 格式）</div>
            <div className="custom-buttons">
              <button
                className="custom-btn openai"
                onClick={() => handleAddCustom("openai", "OpenAI兼容")}
              >
                <span className="btn-icon">🤖</span>
                <span>OpenAI 兼容</span>
              </button>
              <button
                className="custom-btn anthropic"
                onClick={() => handleAddCustom("anthropic", "Claude")}
              >
                <span className="btn-icon">🎭</span>
                <span>Claude API</span>
              </button>
              <button
                className="custom-btn google"
                onClick={() => handleAddCustom("google", "Gemini")}
              >
                <span className="btn-icon">💎</span>
                <span>Gemini API</span>
              </button>
            </div>
          </div>
        </div>

        {/* 右侧：编辑面板 */}
        <div className="edit-panel">
          {selectedProvider ? (
            <>
              <div className="edit-header">
                <div className="edit-title">
                  <span className="edit-logo">{getProviderLogo(selectedProvider)}</span>
                  <div>
                    <h3>{selectedProvider.name}</h3>
                    <span className="edit-type">
                      {getProviderTypeBadge(selectedProvider.provider_type || "openai").text}
                    </span>
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
                    placeholder="输入一个便于识别的名称"
                  />
                </div>

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

                <div className="form-group">
                  <label>Base URL</label>
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
                  />
                  <p className="field-hint">API 端点地址，通常以 /v1 结尾</p>
                </div>

                <div className="form-group">
                  <label>API Key</label>
                  <div className="api-key-input">
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
                  </div>
                </div>

                <div className="form-group">
                  <label>可用模型（每行一个）</label>
                  <textarea
                    value={(selectedProvider.models || []).join("\n")}
                    onChange={(e) =>
                      dispatch({
                        type: "UPDATE_PROVIDER",
                        id: selectedProvider.id,
                        field: "models",
                        value: e.target.value.split("\n").filter(Boolean),
                      })
                    }
                    placeholder="gpt-4o&#10;gpt-4o-mini&#10;claude-3-5-sonnet-20241022"
                    rows={4}
                  />
                  <p className="field-hint">手动填写或通过测试连接自动获取</p>
                </div>

                <div className="form-actions">
                  <button
                    className="btn primary"
                    onClick={() => handleTest(selectedProvider)}
                    disabled={testingProviderId !== null}
                  >
                    {testingProviderId === selectedProvider.id ? "测试中..." : "🔍 测试连接"}
                  </button>
                </div>

                {testResults[selectedProvider.id] && (
                  <div
                    className={`test-result ${testResults[selectedProvider.id].success ? "success" : "error"}`}
                  >
                    <span className="result-icon">
                      {testResults[selectedProvider.id].success ? "✓" : "✗"}
                    </span>
                    <span>{testResults[selectedProvider.id].message}</span>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">👈</div>
              <p>选择左侧服务商进行编辑</p>
              <p className="hint">或点击添加按钮创建新的服务商配置</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
