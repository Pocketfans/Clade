/**
 * PerformanceSection - AI 配置与性能调优
 * 单列布局，清晰的卡片分组
 */

import { memo, useMemo, useState, type Dispatch } from "react";
import type { UIConfig, ProviderConfig, CapabilityRouteConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, SliderRow, NumberInput, ToggleRow, InfoBox, SelectRow } from "../common/Controls";
import {
  canonicalizeProviderRecords,
  getCanonicalProviderId,
  getProviderLogo,
} from "../reducer";

interface Props {
  config: UIConfig;
  providers: Record<string, ProviderConfig>;
  dispatch: Dispatch<SettingsAction>;
}

const hasUsableApiKey = (provider: ProviderConfig) =>
  Boolean(provider.api_key || provider.api_key_configured) && !provider.api_key_clear_requested;

// 预设配置
const PRESETS = [
  {
    id: "speed",
    name: "极速模式",
    icon: "⚡",
    desc: "快速降级，适合测试",
    values: {
      ai_timeout: 30,
      turn_report_llm_enabled: true,
      ai_concurrency_limit: 5,
    },
  },
  {
    id: "balanced",
    name: "默认模式",
    icon: "⚖️",
    desc: "平衡速度与质量",
    values: {
      ai_timeout: 60,
      turn_report_llm_enabled: true,
      ai_concurrency_limit: 3,
    },
  },
  {
    id: "thinking",
    name: "思考模式",
    icon: "🧠",
    desc: "适合 DeepSeek-R1 等",
    values: {
      ai_timeout: 180,
      turn_report_llm_enabled: true,
      ai_concurrency_limit: 2,
    },
  },
  {
    id: "patient",
    name: "耐心模式",
    icon: "🐢",
    desc: "最大等待，减少降级",
    values: {
      ai_timeout: 300,
      turn_report_llm_enabled: true,
      ai_concurrency_limit: 2,
    },
  },
];

// 正在使用的 LLM 功能定义
// 注意：biological_assessment_a/b 已被张量系统替代，默认禁用
const LLM_CAPABILITIES = [
  {
    key: "speciation",
    name: "物种分化",
    icon: "🧬",
    desc: "AI 生成新物种的特征、名称和描述",
    category: "evolution",
  },
  {
    key: "speciation_batch",
    name: "批量分化（动物）",
    icon: "🦎",
    desc: "批量处理多个动物物种的分化",
    category: "evolution",
  },
  {
    key: "plant_speciation_batch",
    name: "批量分化（植物）",
    icon: "🌿",
    desc: "批量处理多个植物物种的分化",
    category: "evolution",
  },
  {
    key: "hybridization",
    name: "杂交生成",
    icon: "🔀",
    desc: "AI 生成杂交物种的特征和描述",
    category: "evolution",
  },
  {
    key: "forced_hybridization",
    name: "强行杂交",
    icon: "⚗️",
    desc: "创造嵌合体，消耗更多神力",
    category: "evolution",
  },
  {
    key: "turn_report",
    name: "回合叙事",
    icon: "📝",
    desc: "生成每回合的生态叙事和总结",
    category: "narrative",
  },
];

// 分类名称
const CATEGORY_NAMES: Record<string, string> = {
  evolution: "演化与分化",
  narrative: "叙事生成",
};

export const PerformanceSection = memo(function PerformanceSection({
  config,
  providers,
  dispatch,
}: Props) {
  const [expandedCapability, setExpandedCapability] = useState<string | null>(null);

  const handleUpdate = (field: string, value: unknown) => {
    dispatch({ type: "UPDATE_GLOBAL", field, value });
  };

  const handleRouteUpdate = (capKey: string, field: keyof CapabilityRouteConfig, value: unknown) => {
    dispatch({ type: "UPDATE_ROUTE", capKey, field, value });
  };

  const applyPreset = (preset: (typeof PRESETS)[0]) => {
    Object.entries(preset.values).forEach(([field, value]) => {
      handleUpdate(field, value);
    });
  };

  // 获取可用的服务商列表
  const canonicalProviders = useMemo(() => canonicalizeProviderRecords(providers), [providers]);
  const providerList = Object.values(canonicalProviders).filter(hasUsableApiKey);

  // 获取服务商的模型列表（排除禁用的）
  const getProviderModels = (providerId: string): string[] => {
    const provider = canonicalProviders[providerId];
    if (!provider?.models) return [];
    const disabledModels = provider.disabled_models || [];
    return provider.models.filter(m => !disabledModels.includes(m));
  };

  // 获取功能路由配置
  const getCapabilityRoute = (capKey: string): CapabilityRouteConfig => {
    const route = config.capability_routes?.[capKey] || { timeout: 60 };
    return {
      ...route,
      provider_id: getCanonicalProviderId(providers, route.provider_id),
    };
  };

  // 判断功能是否使用自定义配置
  const hasCustomRoute = (capKey: string): boolean => {
    const route = config.capability_routes?.[capKey];
    return !!(route?.provider_id || route?.model);
  };

  const defaultProviderId = getCanonicalProviderId(
    providers,
    config.default_provider_id || config.ai_provider
  ) || null;
  const defaultModel = config.default_model || config.ai_model || null;
  const aiTimeout = config.ai_timeout || 60;

  // 按分类分组功能
  const groupedCapabilities = LLM_CAPABILITIES.reduce((acc, cap) => {
    if (!acc[cap.category]) acc[cap.category] = [];
    acc[cap.category].push(cap);
    return acc;
  }, {} as Record<string, typeof LLM_CAPABILITIES>);

  return (
    <div className="section-page">
      <SectionHeader
        icon="⚡"
        title="AI 配置"
        subtitle="配置 AI 服务商、模型选择与性能参数"
      />

      {/* 全局默认配置 */}
      <Card title="默认服务商" icon="🌐" desc="AI 功能将使用此服务商和模型">
        <SelectRow
          label="服务商"
          desc="选择用于 AI 功能的服务商"
          value={defaultProviderId || ""}
          options={[
            { value: "", label: "请选择服务商" },
            ...providerList.map(p => ({ value: p.id, label: `${getProviderLogo(p)} ${p.name}` }))
          ]}
          onChange={(v) => {
            handleUpdate("default_provider_id", v || null);
            handleUpdate("ai_provider", v || null);
          }}
        />

        <SelectRow
          label="模型"
          desc="选择用于 AI 功能的模型"
          value={defaultModel || ""}
          options={[
            { value: "", label: defaultProviderId ? "请选择模型" : "需先选择服务商" },
            ...(defaultProviderId ? getProviderModels(defaultProviderId).map(m => ({ value: m, label: m })) : [])
          ]}
          onChange={(v) => {
            handleUpdate("default_model", v || null);
            handleUpdate("ai_model", v || null);
          }}
          disabled={!defaultProviderId}
        />

        {!defaultProviderId && (
          <div className="config-warning">
            ⚠️ 请先在「服务商配置」中添加服务商，并在此处选择默认服务商
          </div>
        )}
      </Card>

      {/* 正在使用的 LLM 功能 */}
      <Card title="LLM 功能模块" icon="🤖" desc="当前正在使用的 AI 功能列表">
        <InfoBox>
          以下功能使用 LLM 生成内容。默认使用全局服务商配置，点击可为特定功能指定独立的服务商和模型。
        </InfoBox>
        
        <div className="llm-capabilities-list">
          {Object.entries(groupedCapabilities).map(([category, caps]) => (
            <div key={category} className="capability-category">
              <div className="capability-category-header">
                {CATEGORY_NAMES[category] || category}
              </div>
              {caps.map((cap) => {
                const route = getCapabilityRoute(cap.key);
                const isExpanded = expandedCapability === cap.key;
                const isCustom = hasCustomRoute(cap.key);
                
                return (
                  <div 
                    key={cap.key} 
                    className={`capability-item ${isCustom ? 'has-custom' : ''} ${isExpanded ? 'expanded' : ''}`}
                  >
                    <div 
                      className="capability-item-header"
                      onClick={() => setExpandedCapability(isExpanded ? null : cap.key)}
                    >
                      <span className="capability-icon">{cap.icon}</span>
                      <div className="capability-info">
                        <div className="capability-name">
                          {cap.name}
                          {isCustom && <span className="custom-badge">自定义</span>}
                        </div>
                        <div className="capability-desc">{cap.desc}</div>
                      </div>
                      <span className="capability-expand-icon">
                        {isExpanded ? '▼' : '▶'}
                      </span>
                    </div>
                    
                    {isExpanded && (
                      <div className="capability-config">
                        <SelectRow
                          label="服务商"
                          desc="留空则使用默认服务商"
                          value={route.provider_id || ""}
                          options={[
                            { value: "", label: `使用默认 ${defaultProviderId ? `(${canonicalProviders[defaultProviderId]?.name || defaultProviderId})` : ''}` },
                            ...providerList.map(p => ({ value: p.id, label: `${getProviderLogo(p)} ${p.name}` }))
                          ]}
                          onChange={(v) => handleRouteUpdate(cap.key, "provider_id", v || null)}
                        />
                        
                        <SelectRow
                          label="模型"
                          desc="留空则使用默认模型"
                          value={route.model || ""}
                          options={[
                            { value: "", label: `使用默认 ${defaultModel ? `(${defaultModel})` : ''}` },
                            ...((route.provider_id || defaultProviderId) 
                              ? getProviderModels(route.provider_id || defaultProviderId!).map(m => ({ value: m, label: m })) 
                              : [])
                          ]}
                          onChange={(v) => handleRouteUpdate(cap.key, "model", v || null)}
                        />
                        
                        <NumberInput
                          label="超时时间"
                          desc="此功能的请求超时（秒）"
                          value={route.timeout || 60}
                          min={15}
                          max={300}
                          step={15}
                          onChange={(v) => handleRouteUpdate(cap.key, "timeout", v)}
                          suffix="秒"
                        />

                        {(cap.key === "speciation" || cap.key === "speciation_batch" || cap.key === "plant_speciation_batch") && (
                          <ToggleRow
                            label="启用思考模式"
                            desc="开启后使用更长的推理时间（适合 DeepSeek-R1）"
                            checked={route.enable_thinking || false}
                            onChange={(v) => handleRouteUpdate(cap.key, "enable_thinking", v)}
                          />
                        )}

                        {isCustom && (
                          <button 
                            className="btn-ghost btn-sm"
                            onClick={() => {
                              handleRouteUpdate(cap.key, "provider_id", null);
                              handleRouteUpdate(cap.key, "model", null);
                            }}
                          >
                            ↻ 恢复默认
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Card>

      {/* 快速配置预设 */}
      <Card title="快速配置" icon="🚀" desc="根据场景一键切换 AI 参数组合">
        <InfoBox>
          预设会同步调整超时时间、并发限制以及回合报告开关，方便在速度与质量之间快速切换。
        </InfoBox>
        <div className="preset-grid">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => applyPreset(preset)}
              className="preset-card"
            >
              <span className="preset-icon">{preset.icon}</span>
              <div className="preset-info">
                <div className="preset-name">{preset.name}</div>
                <div className="preset-desc">{preset.desc}</div>
                <div className="preset-meta">
                  <span>超时 {preset.values.ai_timeout}s</span>
                  <span>并发 {preset.values.ai_concurrency_limit}</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </Card>

      {/* AI 功能开关 */}
      <Card title="功能开关" icon="🎛️" desc="控制 AI 生成功能">
        <InfoBox>
          关闭功能后将使用规则系统替代 LLM，可节省 API 调用费用。
        </InfoBox>

        <ToggleRow
          label="回合报告（LLM）"
          desc="每回合结束时生成整体生态总结与演化叙事，让报告更生动有趣"
          checked={config.turn_report_llm_enabled !== false}
          onChange={(v) => handleUpdate("turn_report_llm_enabled", v)}
        />
      </Card>

      {/* 超时配置 */}
      <Card title="超时与并发" icon="⏱️">
        <InfoBox>
          普通 AI 请求从排队到获得完整结果共用一个端到端总时限；流式生成时，此处设置的是等待下一段 AI 内容的最长时间，整段流式生成总计最多运行 10 分钟。超时后系统会使用规则生成的备用结果。
        </InfoBox>

        <SliderRow
          label="全局超时时间"
          desc="普通请求的端到端总时限；流式请求等待新内容的时限（可在功能模块中单独覆盖）"
          value={aiTimeout}
          min={15}
          max={300}
          step={15}
          onChange={(v) => handleUpdate("ai_timeout", v)}
          formatValue={(v) => `${v} 秒`}
        />

        <NumberInput
          label="最大并发数"
          desc="同时处理的 AI 请求数量，过高可能触发限流"
          value={config.ai_concurrency_limit || 3}
          min={1}
          max={10}
          step={1}
          onChange={(v) => handleUpdate("ai_concurrency_limit", v)}
          suffix="个"
        />
      </Card>
    </div>
  );
});
