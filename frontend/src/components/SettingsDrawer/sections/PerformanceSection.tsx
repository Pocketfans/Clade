/**
 * PerformanceSection - AI 推演性能调优
 * 
 * 控制 AI 调用的超时、并发、降级策略等
 */

import { memo, type Dispatch } from "react";
import type { UIConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SliderRow, ToggleRow, NumberInput } from "../common";

interface PerformanceSectionProps {
  config: UIConfig;
  dispatch: Dispatch<SettingsAction>;
}

// 预设配置
const PERFORMANCE_PRESETS = [
  {
    id: "speed",
    name: "极速模式",
    icon: "⚡",
    desc: "快速降级，适合测试",
    values: {
      ai_timeout: 30,
      enable_species_narrative: false,
      enable_turn_report: true,
      max_concurrent_requests: 5,
      enable_load_balance: false,
    },
  },
  {
    id: "balanced",
    name: "默认模式",
    icon: "⚖️",
    desc: "平衡速度与质量",
    values: {
      ai_timeout: 60,
      enable_species_narrative: false,
      enable_turn_report: true,
      max_concurrent_requests: 3,
      enable_load_balance: false,
    },
  },
  {
    id: "thinking",
    name: "思考模式",
    icon: "🧠",
    desc: "适合DeepSeek-R1等",
    values: {
      ai_timeout: 180,
      enable_species_narrative: true,
      enable_turn_report: true,
      max_concurrent_requests: 2,
      enable_thinking: true,
    },
  },
  {
    id: "patient",
    name: "耐心模式",
    icon: "🐢",
    desc: "最大等待，减少降级",
    values: {
      ai_timeout: 300,
      enable_species_narrative: true,
      enable_turn_report: true,
      max_concurrent_requests: 2,
      enable_load_balance: true,
    },
  },
];

export const PerformanceSection = memo(function PerformanceSection({
  config,
  dispatch,
}: PerformanceSectionProps) {
  const handleUpdate = (field: string, value: unknown) => {
    dispatch({ type: "UPDATE_GLOBAL", field, value });
  };

  const applyPreset = (preset: typeof PERFORMANCE_PRESETS[0]) => {
    Object.entries(preset.values).forEach(([field, value]) => {
      handleUpdate(field, value);
    });
  };

  return (
    <div className="settings-section performance-section">
      <div className="section-header-bar">
        <div>
          <h2>⚡ AI 推演性能调优</h2>
          <p className="section-subtitle">调整 AI 调用的超时时间，平衡响应速度与推演质量。</p>
        </div>
      </div>

      {/* AI 功能开关 */}
      <div className="config-panel">
        <div className="config-header">
          <h3>🎛️ AI 功能开关</h3>
        </div>

        <div className="toggle-cards">
          <div className="toggle-card">
            <div className="toggle-card-header">
              <span className="toggle-icon">📝</span>
              <div className="toggle-info">
                <h4>回合报告（LLM）</h4>
                <p>生成每回合的整体生态总结与演化叙事</p>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={config.enable_turn_report !== false}
                  onChange={(e) => handleUpdate("enable_turn_report", e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>
          </div>

          <div className="toggle-card">
            <div className="toggle-card-header">
              <span className="toggle-icon">📖</span>
              <div className="toggle-info">
                <h4>AI 物种叙事</h4>
                <p>为每个物种单独生成演化故事和行为描述</p>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={config.enable_species_narrative === true}
                  onChange={(e) => handleUpdate("enable_species_narrative", e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>
            <div className="toggle-hint warning">
              💡 关闭后可节省 API 调用，推演速度更快
            </div>
          </div>
        </div>

        {/* 两个开关的区别说明 */}
        <div className="info-card">
          <h4>💡 两个开关的区别：</h4>
          <ul>
            <li><strong>回合报告（LLM）</strong>：控制整回合的宏观总结，汇总所有物种的生态变化</li>
            <li><strong>AI 物种叙事</strong>：控制单个物种的微观描述，生成个体行为和适应故事</li>
          </ul>
        </div>
      </div>

      {/* 超时配置 */}
      <div className="config-panel">
        <div className="config-header">
          <h3>⏱️ 超时设置</h3>
        </div>

        <div className="timeout-info">
          💡 超时时间决定了系统等待 AI 响应的最长时间。如果 AI 在超时前未能完成，系统将使用规则降级处理。
        </div>

        <div className="timeout-controls">
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
            desc="同时处理的AI请求数量，过高可能触发API限流"
            value={config.max_concurrent_requests || 3}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate("max_concurrent_requests", v)}
          />
        </div>
      </div>

      {/* 负载均衡 */}
      <div className="config-panel">
        <div className="config-header">
          <h3>⚖️ 多服务商负载均衡</h3>
        </div>

        <div className="lb-intro">
          💡 启用后可为每个AI能力配置多个服务商，并行请求会自动分散到不同服务商，提高整体吞吐量并避免单一服务商限流。
        </div>

        <div className="toggle-card">
          <div className="toggle-card-header">
            <span className="toggle-icon">⚖️</span>
            <div className="toggle-info">
              <h4>启用负载均衡</h4>
              <p>在「智能路由」页面为每个能力选择多个服务商</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={config.enable_load_balance === true}
                onChange={(e) => handleUpdate("enable_load_balance", e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          </div>
        </div>
      </div>

      {/* 快速配置预设 */}
      <div className="config-panel">
        <div className="config-header">
          <h3>🚀 快速配置</h3>
        </div>

        <div className="preset-grid">
          {PERFORMANCE_PRESETS.map((preset) => (
            <button
              key={preset.id}
              className="preset-card"
              onClick={() => applyPreset(preset)}
            >
              <span className="preset-icon">{preset.icon}</span>
              <div className="preset-info">
                <h4>{preset.name}</h4>
                <p>{preset.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 超时机制说明 */}
      <div className="config-panel info-panel">
        <div className="config-header">
          <h3>📋 超时机制说明</h3>
        </div>

        <div className="mechanism-list">
          <div className="mechanism-item">
            <span className="mechanism-icon">⏱️</span>
            <div>
              <h4>超时降级</h4>
              <p>当AI超时后，系统将使用基于规则的快速评估代替</p>
            </div>
          </div>
          <div className="mechanism-item">
            <span className="mechanism-icon">🔄</span>
            <div>
              <h4>并行处理</h4>
              <p>多个物种的评估会并行进行，提高整体效率</p>
            </div>
          </div>
          <div className="mechanism-item">
            <span className="mechanism-icon">💓</span>
            <div>
              <h4>流式心跳</h4>
              <p>AI处理中会发送心跳信号，前端可实时感知进度</p>
            </div>
          </div>
          <div className="mechanism-item warning">
            <span className="mechanism-icon">⚠️</span>
            <div>
              <h4>注意</h4>
              <p>过短的超时会导致更多规则降级，叙事质量可能下降</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

