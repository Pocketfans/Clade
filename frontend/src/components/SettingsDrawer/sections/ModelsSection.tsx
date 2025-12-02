/**
 * ModelsSection - 智能路由配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { ProviderConfig, CapabilityRouteConfig } from "@/services/api.types";
import type { SettingsAction, CapabilityDef } from "../types";
import { AI_CAPABILITIES } from "../constants";
import { getProviderLogo } from "../reducer";
import { SectionHeader, Card, SliderRow, InfoBox } from "../common/Controls";

interface Props {
  providers: Record<string, ProviderConfig>;
  capabilityRoutes: Record<string, CapabilityRouteConfig>;
  aiProvider: string | null;
  aiModel: string | null;
  aiTimeout: number;
  dispatch: Dispatch<SettingsAction>;
}

// 能力分组配置
const CAPABILITY_GROUPS = [
  { key: "core", title: "核心能力", icon: "⚡", color: "#ef4444", desc: "影响整体推演质量的关键能力" },
  { key: "speciation", title: "物种分化", icon: "🧬", color: "#f59e0b", desc: "控制物种演化与分化的 AI 能力" },
  { key: "narrative", title: "叙事生成", icon: "📖", color: "#10b981", desc: "生成物种故事与描述的能力" },
  { key: "advanced", title: "高级功能", icon: "🔬", color: "#3b82f6", desc: "杂交、智能体评估等进阶功能" },
];

export const ModelsSection = memo(function ModelsSection({
  providers,
  capabilityRoutes,
  aiProvider,
  aiModel,
  aiTimeout,
  dispatch,
}: Props) {
  const providerList = Object.values(providers).filter((p) => p.api_key);

  const getProviderModels = (providerId: string): string[] => {
    const provider = providers[providerId];
    if (!provider?.models) return [];
    // 只返回启用的模型（不在 disabled_models 中的）
    const disabledModels = provider.disabled_models || [];
    return provider.models.filter(m => !disabledModels.includes(m));
  };

  const getEffectiveConfig = (cap: CapabilityDef) => {
    const route = capabilityRoutes[cap.key];
    if (route?.provider_id) {
      const provider = providers[route.provider_id];
      return {
        provider: provider?.name || route.provider_id,
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

  const renderCapabilityCard = (cap: CapabilityDef, groupColor: string) => {
    const route = capabilityRoutes[cap.key] || {
      provider_id: null,
      provider_ids: null,
      model: null,
      timeout: cap.defaultTimeout,
    };

    // 获取已选中的服务商列表
    const selectedProviderIds = route.provider_ids || (route.provider_id ? [route.provider_id] : []);
    const effective = getEffectiveConfig(cap);

    // 切换服务商选择
    const toggleProvider = (providerId: string) => {
      const current = [...selectedProviderIds];
      const index = current.indexOf(providerId);
      if (index >= 0) {
        current.splice(index, 1);
      } else {
        current.push(providerId);
      }
      dispatch({
        type: "UPDATE_ROUTE",
        capKey: cap.key,
        field: "provider_ids",
        value: current.length > 0 ? current : null,
      });
      // 同时清空单选字段
      if (route.provider_id) {
        dispatch({
          type: "UPDATE_ROUTE",
          capKey: cap.key,
          field: "provider_id",
          value: null,
        });
      }
    };

    return (
      <div
        key={cap.key}
        style={{
          background: "var(--s-bg-glass)",
          border: "1px solid var(--s-border)",
          borderTop: `2px solid ${groupColor}`,
          borderRadius: "var(--s-radius-md)",
          padding: "14px",
          transition: "all 0.2s",
        }}
      >
        {/* 头部 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <strong style={{ fontSize: "0.9rem", color: "var(--s-text)" }}>{cap.label}</strong>
            <span
              style={{
                fontSize: "0.65rem",
                padding: "2px 6px",
                borderRadius: "4px",
                fontWeight: 500,
                background:
                  cap.parallel === "batch"
                    ? "rgba(245, 158, 11, 0.15)"
                    : cap.parallel === "concurrent"
                    ? "rgba(99, 102, 241, 0.15)"
                    : "rgba(100, 116, 139, 0.15)",
                color:
                  cap.parallel === "batch"
                    ? "#fbbf24"
                    : cap.parallel === "concurrent"
                    ? "#a5b4fc"
                    : "#94a3b8",
              }}
            >
              {cap.parallel === "batch" ? "批量" : cap.parallel === "concurrent" ? "并发" : "单次"}
            </span>
          </div>
        </div>

        <p style={{ fontSize: "0.78rem", color: "var(--s-text-muted)", margin: "0 0 10px", lineHeight: 1.4 }}>
          {cap.desc}
        </p>

        {/* 当前生效配置 */}
        {(selectedProviderIds.length > 0 || effective) && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 10px",
              background: "rgba(0, 0, 0, 0.2)",
              borderRadius: "var(--s-radius-sm)",
              fontSize: "0.72rem",
              marginBottom: "10px",
              flexWrap: "wrap",
            }}
          >
            <span style={{ color: "var(--s-text-muted)" }}>当前:</span>
            {selectedProviderIds.length > 0 ? (
              selectedProviderIds.map((pid, idx) => {
                const p = providers[pid];
                return (
                  <span key={pid} style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                    {idx > 0 && <span style={{ color: "var(--s-text-muted)", margin: "0 2px" }}>+</span>}
                    <span style={{ color: "var(--s-primary-light)" }}>{p?.name || pid}</span>
                  </span>
                );
              })
            ) : effective ? (
              <>
                <span style={{ color: "var(--s-primary-light)" }}>{effective.provider}</span>
                <span style={{ color: "var(--s-text-muted)" }}>/</span>
                <span style={{ color: "var(--s-accent)", maxWidth: "80px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {effective.model}
                </span>
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: "0.62rem",
                    background: "rgba(100, 116, 139, 0.2)",
                    color: "#94a3b8",
                    padding: "1px 5px",
                    borderRadius: "3px",
                  }}
                >
                  默认
                </span>
              </>
            ) : null}
          </div>
        )}

        {/* 配置选项 */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", paddingTop: "8px", borderTop: "1px solid rgba(255, 255, 255, 0.05)" }}>
          {/* 可用服务商池 - 多选 */}
          <div>
            <div style={{ fontSize: "0.72rem", color: "var(--s-text-muted)", marginBottom: "6px" }}>
              可用服务商（点击选择，可多选）
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {providerList.length === 0 ? (
                <span style={{ fontSize: "0.75rem", color: "var(--s-text-muted)", fontStyle: "italic" }}>
                  请先配置服务商
                </span>
              ) : (
                providerList.map((p) => {
                  const isSelected = selectedProviderIds.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      onClick={() => toggleProvider(p.id)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "5px 10px",
                        background: isSelected ? "rgba(245, 158, 11, 0.15)" : "var(--s-bg-deep)",
                        border: `1px solid ${isSelected ? "var(--s-primary)" : "var(--s-border)"}`,
                        borderRadius: "var(--s-radius-sm)",
                        color: isSelected ? "var(--s-primary)" : "var(--s-text-secondary)",
                        fontSize: "0.75rem",
                        cursor: "pointer",
                        transition: "all 0.15s",
                      }}
                    >
                      {isSelected && <span style={{ fontSize: "0.7rem" }}>✓</span>}
                      <span>{getProviderLogo(p)}</span>
                      <span>{p.name}</span>
                    </button>
                  );
                })
              )}
            </div>
            {selectedProviderIds.length === 0 && providerList.length > 0 && (
              <div style={{ fontSize: "0.68rem", color: "var(--s-text-muted)", marginTop: "4px", fontStyle: "italic" }}>
                未选择则使用全局默认
              </div>
            )}
          </div>

          {/* 模型选择 - 当只选择一个服务商时显示 */}
          {selectedProviderIds.length === 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "0.72rem", color: "var(--s-text-muted)", minWidth: "45px" }}>模型</span>
              <select
                value={route.model || ""}
                onChange={(e) =>
                  dispatch({
                    type: "UPDATE_ROUTE",
                    capKey: cap.key,
                    field: "model",
                    value: e.target.value || null,
                  })
                }
                style={{
                  flex: 1,
                  padding: "4px 8px",
                  background: "var(--s-bg-deep)",
                  border: "1px solid var(--s-border)",
                  borderRadius: "var(--s-radius-sm)",
                  color: "var(--s-text)",
                  fontSize: "0.78rem",
                }}
              >
                <option value="">使用服务商默认</option>
                {getProviderModels(selectedProviderIds[0]).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 超时设置 */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--s-text-muted)", minWidth: "45px" }}>超时</span>
            <input
              type="number"
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
              style={{
                width: "60px",
                padding: "4px 8px",
                background: "var(--s-bg-deep)",
                border: "1px solid var(--s-border)",
                borderRadius: "var(--s-radius-sm)",
                color: "var(--s-text)",
                fontSize: "0.78rem",
                textAlign: "center",
              }}
            />
            <span style={{ fontSize: "0.72rem", color: "var(--s-text-muted)" }}>秒</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🤖"
        title="智能路由"
        subtitle="为不同 AI 能力分配专用模型，优化性能与成本"
      />

      {/* 全局默认配置 */}
      <Card title="全局默认" icon="🌐" desc="未单独配置的能力将使用此设置">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
          {/* 默认服务商 */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--s-text-secondary)", marginBottom: "8px" }}>
              默认服务商
            </label>
            <select
              value={aiProvider || ""}
              onChange={(e) =>
                dispatch({ type: "UPDATE_GLOBAL", field: "ai_provider", value: e.target.value || null })
              }
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "var(--s-bg-deep)",
                border: "1px solid var(--s-border)",
                borderRadius: "var(--s-radius-md)",
                color: "var(--s-text)",
                fontSize: "0.88rem",
              }}
            >
              <option value="">请选择服务商</option>
              {providerList.map((p) => (
                <option key={p.id} value={p.id}>
                  {getProviderLogo(p)} {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* 默认模型 */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--s-text-secondary)", marginBottom: "8px" }}>
              默认模型
            </label>
            <select
              value={aiModel || ""}
              onChange={(e) =>
                dispatch({ type: "UPDATE_GLOBAL", field: "ai_model", value: e.target.value || null })
              }
              disabled={!aiProvider}
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "var(--s-bg-deep)",
                border: "1px solid var(--s-border)",
                borderRadius: "var(--s-radius-md)",
                color: "var(--s-text)",
                fontSize: "0.88rem",
                opacity: aiProvider ? 1 : 0.5,
              }}
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

          {/* 默认超时 */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--s-text-secondary)", marginBottom: "8px" }}>
              默认超时
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="number"
                value={aiTimeout}
                min={10}
                max={300}
                step={10}
                onChange={(e) =>
                  dispatch({ type: "UPDATE_GLOBAL", field: "ai_timeout", value: parseInt(e.target.value) || 60 })
                }
                style={{
                  width: "100px",
                  padding: "10px 14px",
                  background: "var(--s-bg-deep)",
                  border: "1px solid var(--s-border)",
                  borderRadius: "var(--s-radius-md)",
                  color: "var(--s-text)",
                  fontSize: "0.88rem",
                  textAlign: "center",
                }}
              />
              <span style={{ color: "var(--s-text-muted)", fontSize: "0.88rem" }}>秒</span>
            </div>
          </div>
        </div>

        {!aiProvider && (
          <div
            style={{
              marginTop: "16px",
              padding: "12px 16px",
              background: "var(--s-warning-bg)",
              border: "1px solid rgba(251, 191, 36, 0.3)",
              borderRadius: "var(--s-radius-md)",
              color: "var(--s-warning)",
              fontSize: "0.88rem",
            }}
          >
            ⚠️ 请先选择默认服务商，否则 AI 功能将无法正常使用
          </div>
        )}
      </Card>

      {/* 能力分组 */}
      {CAPABILITY_GROUPS.map((group) => {
        const capabilities = AI_CAPABILITIES[group.key] || [];
        if (capabilities.length === 0) return null;

        return (
          <Card
            key={group.key}
            title={group.title}
            icon={group.icon}
            desc={`${capabilities.length} 项能力`}
          >
            <p style={{ fontSize: "0.82rem", color: "var(--s-text-muted)", margin: "0 0 14px" }}>
              {group.desc}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
              {capabilities.map((cap) => renderCapabilityCard(cap, group.color))}
            </div>
          </Card>
        );
      })}

      {/* 配置建议 */}
      <InfoBox variant="warning" title="配置建议">
        <ul style={{ margin: 0, paddingLeft: "18px", lineHeight: 1.8 }}>
          <li><strong>核心能力</strong>：建议使用高质量模型（如 GPT-4o、Claude-3.5）</li>
          <li><strong>批量任务</strong>：可使用性价比高的模型（如 DeepSeek、Qwen）</li>
          <li><strong>超时设置</strong>：思考模型（R1等）建议 120-180 秒</li>
        </ul>
      </InfoBox>
    </div>
  );
});
