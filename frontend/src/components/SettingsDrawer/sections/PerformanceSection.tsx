/**
 * PerformanceSection - AI 推演性能调优 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { UIConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, SliderRow, NumberInput, ToggleRow, InfoBox } from "../common/Controls";

interface Props {
  config: UIConfig;
  dispatch: Dispatch<SettingsAction>;
}

// 预设配置
const PRESETS = [
  {
    id: "speed",
    name: "极速模式",
    icon: "⚡",
    desc: "快速降级，适合测试",
    values: {
      ai_timeout: 30,
      ai_narrative_enabled: false,
      turn_report_llm_enabled: true,
      max_concurrent_requests: 5,
    },
  },
  {
    id: "balanced",
    name: "默认模式",
    icon: "⚖️",
    desc: "平衡速度与质量",
    values: {
      ai_timeout: 60,
      ai_narrative_enabled: false,
      turn_report_llm_enabled: true,
      max_concurrent_requests: 3,
    },
  },
  {
    id: "thinking",
    name: "思考模式",
    icon: "🧠",
    desc: "适合 DeepSeek-R1 等",
    values: {
      ai_timeout: 180,
      ai_narrative_enabled: true,
      turn_report_llm_enabled: true,
      max_concurrent_requests: 2,
    },
  },
  {
    id: "patient",
    name: "耐心模式",
    icon: "🐢",
    desc: "最大等待，减少降级",
    values: {
      ai_timeout: 300,
      ai_narrative_enabled: true,
      turn_report_llm_enabled: true,
      max_concurrent_requests: 2,
    },
  },
];

export const PerformanceSection = memo(function PerformanceSection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (field: string, value: unknown) => {
    dispatch({ type: "UPDATE_GLOBAL", field, value });
  };

  const applyPreset = (preset: (typeof PRESETS)[0]) => {
    Object.entries(preset.values).forEach(([field, value]) => {
      handleUpdate(field, value);
    });
  };

  return (
    <div className="section-page">
      <SectionHeader
        icon="⚡"
        title="AI 推演性能调优"
        subtitle="调整 AI 调用的超时时间、并发控制，平衡响应速度与推演质量"
      />

      {/* 快速配置预设 */}
      <Card title="快速配置" icon="🚀" desc="一键应用预设">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px" }}>
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => applyPreset(preset)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "14px",
                padding: "16px",
                background: "var(--s-bg-glass)",
                border: "1px solid var(--s-border)",
                borderRadius: "var(--s-radius-md)",
                cursor: "pointer",
                transition: "all 0.2s",
                textAlign: "left",
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = "var(--s-bg-active)";
                e.currentTarget.style.borderColor = "var(--s-primary)";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = "var(--s-bg-glass)";
                e.currentTarget.style.borderColor = "var(--s-border)";
              }}
            >
              <span style={{ fontSize: "1.8rem" }}>{preset.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "var(--s-text)" }}>
                  {preset.name}
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--s-text-muted)", marginTop: "2px" }}>
                  {preset.desc}
                </div>
              </div>
            </button>
          ))}
        </div>
      </Card>

      {/* AI 功能开关 */}
      <Card title="AI 功能开关" icon="🎛️">
        <ToggleRow
          label="回合报告（LLM）"
          desc="生成每回合的整体生态总结与演化叙事"
          checked={config.turn_report_llm_enabled !== false}
          onChange={(v) => handleUpdate("turn_report_llm_enabled", v)}
        />
        <ToggleRow
          label="AI 物种叙事"
          desc="为每个物种单独生成演化故事和行为描述（关闭可节省 API）"
          checked={config.ai_narrative_enabled === true}
          onChange={(v) => handleUpdate("ai_narrative_enabled", v)}
        />
      </Card>

      {/* 超时配置 */}
      <Card title="超时设置" icon="⏱️">
        <InfoBox>
          超时时间决定了系统等待 AI 响应的最长时间。如果 AI 在超时前未能完成，系统将使用规则降级处理。
        </InfoBox>

        <SliderRow
          label="全局 AI 超时"
          desc="单次 AI 请求的最大等待时间"
          value={config.ai_timeout || 60}
          min={15}
          max={300}
          step={15}
          onChange={(v) => handleUpdate("ai_timeout", v)}
          formatValue={(v) => `${v} 秒`}
        />

        <NumberInput
          label="最大并发请求数"
          desc="同时处理的 AI 请求数量，过高可能触发限流"
          value={config.max_concurrent_requests || 3}
          min={1}
          max={10}
          step={1}
          onChange={(v) => handleUpdate("max_concurrent_requests", v)}
          suffix="个"
        />
      </Card>

      {/* 负载均衡 */}
      <Card title="多服务商负载均衡" icon="⚖️">
        <InfoBox>
          启用后可为每个 AI 能力配置多个服务商，并行请求会自动分散，提高整体吞吐量并避免单一服务商限流。
        </InfoBox>

        <ToggleRow
          label="启用负载均衡"
          desc="在「智能路由」页面为每个能力选择多个服务商"
          checked={config.load_balance_enabled === true}
          onChange={(v) => handleUpdate("load_balance_enabled", v)}
        />
      </Card>

      {/* 超时机制说明 */}
      <Card title="超时机制说明" icon="📋">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px" }}>
          {[
            { icon: "⏱️", title: "超时降级", desc: "AI 超时后使用基于规则的快速评估代替" },
            { icon: "🔄", title: "并行处理", desc: "多个物种的评估会并行进行，提高效率" },
            { icon: "💓", title: "流式心跳", desc: "AI 处理中发送心跳，前端实时感知进度" },
            { icon: "⚠️", title: "注意事项", desc: "过短的超时会导致更多规则降级，质量下降" },
          ].map((item, idx) => (
            <div
              key={idx}
              style={{
                display: "flex",
                gap: "12px",
                padding: "14px",
                background: idx === 3 ? "var(--s-warning-bg)" : "var(--s-bg-glass)",
                border: `1px solid ${idx === 3 ? "rgba(251, 191, 36, 0.3)" : "var(--s-border)"}`,
                borderRadius: "var(--s-radius-md)",
              }}
            >
              <span style={{ fontSize: "1.4rem", flexShrink: 0 }}>{item.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--s-text)" }}>
                  {item.title}
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--s-text-muted)", marginTop: "4px", lineHeight: 1.5 }}>
                  {item.desc}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
});
