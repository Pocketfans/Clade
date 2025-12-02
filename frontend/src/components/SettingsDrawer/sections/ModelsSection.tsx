/**
 * ModelsSection - 智能路由配置
 * 
 * 分组展示 AI 能力，支持为每个能力配置专用模型
 */

import { memo, type Dispatch } from "react";
import type { ProviderConfig, CapabilityRouteConfig } from "@/services/api.types";
import type { SettingsAction, CapabilityDef } from "../types";
import { AI_CAPABILITIES } from "../constants";
import { getProviderLogo } from "../reducer";
import { SliderRow } from "../common";

interface ModelsSectionProps {
  providers: Record<string, ProviderConfig>;
  capabilityRoutes: Record<string, CapabilityRouteConfig>;
  aiProvider: string | null;
  aiModel: string | null;
  aiTimeout: number;
  dispatch: Dispatch<SettingsAction>;
}

// 能力分组配置
const CAPABILITY_GROUPS = [
  { 
    key: "core", 
    title: "核心能力", 
    icon: "⚡", 
    level: "high",
    desc: "影响整体推演质量的关键能力"
  },
  { 
    key: "speciation", 
    title: "物种分化", 
    icon: "🧬", 
    level: "high",
    desc: "控制物种演化与分化的 AI 能力"
  },
  { 
    key: "narrative", 
    title: "叙事生成", 
    icon: "📖", 
    level: "medium",
    desc: "生成物种故事与描述的能力"
  },
  { 
    key: "advanced", 
    title: "高级功能", 
    icon: "🔬", 
    level: "low",
    desc: "杂交、智能体评估等进阶功能"
  },
];

export const ModelsSection = memo(function ModelsSection({
  providers,
  capabilityRoutes,
  aiProvider,
  aiModel,
  aiTimeout,
  dispatch,
}: ModelsSectionProps) {
  const providerList = Object.values(providers).filter((p) => p.api_key);

  // 获取服务商的模型列表
  const getProviderModels = (providerId: string): string[] => {
    const provider = providers[providerId];
    if (!provider) return [];
    return provider.models || [];
  };

  // 获取当前生效的配置
  const getEffectiveConfig = (cap: CapabilityDef) => {
    const route = capabilityRoutes[cap.key];
    if (route?.provider) {
      const provider = providers[route.provider];
      return {
        provider: provider?.name || route.provider,
        model: route.model || "默认",
        isCustom: true,
      };
    }
    if (aiProvider) {
      const provider = providers[aiProvider];
      return {
        provider: provider?.name || aiProvider,
        model: aiModel || "默认",
        isCustom: false,
      };
    }
    return null;
  };

  // 渲染单个能力卡片
  const renderCapabilityCard = (cap: CapabilityDef, groupLevel: string) => {
    const route = capabilityRoutes[cap.key] || {
      provider: null,
      model: null,
      timeout: cap.defaultTimeout,
      enabled: true,
    };

    const currentProviderId = route.provider || "";
    const models = currentProviderId ? getProviderModels(currentProviderId) : [];
    const effective = getEffectiveConfig(cap);

    return (
      <div key={cap.key} className={`capability-card ${groupLevel}`}>
        <div className="capability-header">
          <div className="capability-title">
            <strong>{cap.label}</strong>
            <span className={`parallel-badge ${cap.parallel}`}>
              {cap.parallel === "batch" ? "批量" : cap.parallel === "concurrent" ? "并发" : "单次"}
            </span>
          </div>
          <label className="toggle-switch small">
            <input
              type="checkbox"
              checked={route.enabled !== false}
              onChange={(e) =>
                dispatch({
                  type: "UPDATE_ROUTE",
                  capKey: cap.key,
                  field: "enabled",
                  value: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>

        <p className="capability-desc">{cap.desc}</p>

        {/* 当前生效配置预览 */}
        {effective && route.enabled !== false && (
          <div className="capability-effective">
            <span className="effective-label">当前:</span>
            <span className="effective-value">
              <span className="effective-provider">{effective.provider}</span>
              <span className="effective-separator">/</span>
              <span className="effective-model">{effective.model}</span>
            </span>
            {!effective.isCustom && <span className="effective-badge">默认</span>}
          </div>
        )}

        {route.enabled !== false && (
          <div className="capability-config">
            <div className="config-row">
              <span className="config-label">服务商</span>
              <select
                className="config-select"
                value={currentProviderId}
                onChange={(e) =>
                  dispatch({
                    type: "UPDATE_ROUTE",
                    capKey: cap.key,
                    field: "provider",
                    value: e.target.value || null,
                  })
                }
              >
                <option value="">使用全局默认</option>
                {providerList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {getProviderLogo(p)} {p.name}
                  </option>
                ))}
              </select>
            </div>

            {currentProviderId && (
              <div className="config-row">
                <span className="config-label">模型</span>
                <select
                  className="config-select"
                  value={route.model || ""}
                  onChange={(e) =>
                    dispatch({
                      type: "UPDATE_ROUTE",
                      capKey: cap.key,
                      field: "model",
                      value: e.target.value || null,
                    })
                  }
                >
                  <option value="">使用默认</option>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="config-row timeout">
              <span className="config-label">超时</span>
              <input
                type="number"
                className="timeout-input"
                value={route.timeout || cap.defaultTimeout}
                min={10}
                max={300}
                step={10}
                onChange={(e) =>
                  dispatch({
                    type: "UPDATE_ROUTE",
                    capKey: cap.key,
                    field: "timeout",
                    value: parseInt(e.target.value) || cap.defaultTimeout,
                  })
                }
              />
              <span className="timeout-unit">秒</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="settings-section models-section">
      <div className="section-header-bar">
        <div>
          <h2>🤖 智能路由</h2>
          <p className="section-subtitle">为不同 AI 能力分配专用模型，优化性能与成本</p>
        </div>
      </div>

      {/* 全局默认配置 */}
      <div className="global-config-panel">
        <div className="panel-header">
          <h3>🌐 全局默认</h3>
          <p>未单独配置的能力将使用此设置</p>
        </div>

        <div className="global-config-grid">
          <div className="form-group">
            <label>默认服务商</label>
            <select
              value={aiProvider || ""}
              onChange={(e) =>
                dispatch({ type: "UPDATE_GLOBAL", field: "ai_provider", value: e.target.value || null })
              }
            >
              <option value="">请选择服务商</option>
              {providerList.map((p) => (
                <option key={p.id} value={p.id}>
                  {getProviderLogo(p)} {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>默认模型</label>
            <select
              value={aiModel || ""}
              onChange={(e) =>
                dispatch({ type: "UPDATE_GLOBAL", field: "ai_model", value: e.target.value || null })
              }
              disabled={!aiProvider}
            >
              <option value="">请选择模型</option>
              {aiProvider &&
                getProviderModels(aiProvider).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
            </select>
          </div>

          <div className="form-group">
            <label>默认超时</label>
            <div className="timeout-inline">
              <input
                type="number"
                value={aiTimeout}
                min={10}
                max={300}
                step={10}
                onChange={(e) =>
                  dispatch({ type: "UPDATE_GLOBAL", field: "ai_timeout", value: parseInt(e.target.value) || 60 })
                }
              />
              <span>秒</span>
            </div>
          </div>
        </div>

        {!aiProvider && (
          <div className="config-warning">
            ⚠️ 请先选择默认服务商，否则 AI 功能将无法正常使用
          </div>
        )}
      </div>

      {/* 能力分组 */}
      {CAPABILITY_GROUPS.map((group) => {
        const capabilities = AI_CAPABILITIES[group.key] || [];
        if (capabilities.length === 0) return null;

        return (
          <div key={group.key} className="capability-group">
            <div className={`group-header ${group.level}`}>
              <span className="group-icon">{group.icon}</span>
              <div className="group-title-area">
                <h3 className="group-title">{group.title}</h3>
                <p className="group-desc">{group.desc}</p>
              </div>
              <span className="group-count">{capabilities.length} 项</span>
            </div>

            <div className="capabilities-grid">
              {capabilities.map((cap) => renderCapabilityCard(cap, group.level))}
            </div>
          </div>
        );
      })}

      {/* 使用提示 */}
      <div className="usage-tips compact">
        <h4>💡 配置建议</h4>
        <ul>
          <li><strong>核心能力</strong>：建议使用高质量模型（如 GPT-4o、Claude-3.5）</li>
          <li><strong>批量任务</strong>：可使用性价比高的模型（如 DeepSeek、Qwen）</li>
          <li><strong>超时设置</strong>：思考模型（R1等）建议 120-180 秒</li>
        </ul>
      </div>
    </div>
  );
});
