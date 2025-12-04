/**
 * EcologicalRealismDisplay - 生态拟真数据展示组件
 *
 * 显示物种的 Allee 效应、疾病压力、共生关系等生态拟真状态
 */

import type { EcologicalRealismSnapshot } from "@/services/api.types";
import "./EcologicalRealismDisplay.css";

interface EcologicalRealismDisplayProps {
  data: EcologicalRealismSnapshot | null | undefined;
  compact?: boolean;
}

/**
 * 格式化百分比数值
 */
function formatPercent(value: number, showSign = false): string {
  const percent = Math.round(value * 100);
  if (showSign && percent > 0) return `+${percent}%`;
  return `${percent}%`;
}

/**
 * 获取健康状态标签
 */
function getHealthStatus(data: EcologicalRealismSnapshot): {
  level: "healthy" | "warning" | "danger";
  label: string;
} {
  // 检查危险信号
  if (data.is_below_mvp) {
    return { level: "danger", label: "MVP 危机" };
  }
  if (data.disease_pressure > 0.3) {
    return { level: "danger", label: "疾病肆虐" };
  }
  if (data.adaptation_penalty > 0.15) {
    return { level: "danger", label: "适应困难" };
  }
  
  // 检查警告信号
  if (data.disease_pressure > 0.1 || data.adaptation_penalty > 0.05) {
    return { level: "warning", label: "生态压力" };
  }
  if (data.allee_reproduction_modifier < 0.8) {
    return { level: "warning", label: "繁殖受限" };
  }
  
  // 检查共生关系
  if (data.mutualism_benefit > 0.1) {
    return { level: "healthy", label: "共生繁荣" };
  }
  
  return { level: "healthy", label: "生态稳定" };
}

export function EcologicalRealismDisplay({ data, compact = false }: EcologicalRealismDisplayProps) {
  if (!data) {
    return null;
  }

  const healthStatus = getHealthStatus(data);

  // 紧凑模式 - 用于列表项
  if (compact) {
    // 只显示关键指标
    const indicators: { icon: string; label: string; color: string }[] = [];
    
    if (data.is_below_mvp) {
      indicators.push({ icon: "⚠️", label: "MVP", color: "#ef4444" });
    }
    if (data.disease_pressure > 0.1) {
      indicators.push({ icon: "🦠", label: formatPercent(data.disease_pressure), color: "#f97316" });
    }
    if (data.mutualism_partners.length > 0) {
      indicators.push({ icon: "🤝", label: `${data.mutualism_partners.length}`, color: "#22c55e" });
    }
    if (data.adaptation_penalty > 0.05) {
      indicators.push({ icon: "🔄", label: formatPercent(data.adaptation_penalty), color: "#eab308" });
    }

    if (indicators.length === 0) return null;

    return (
      <div className="eco-compact">
        {indicators.slice(0, 3).map((ind, i) => (
          <span key={i} className="eco-indicator" style={{ color: ind.color }} title={ind.label}>
            {ind.icon}
          </span>
        ))}
      </div>
    );
  }

  // 完整模式 - 用于详情页
  return (
    <div className="eco-realism-display">
      <div className="eco-header">
        <h4>🌍 生态拟真状态</h4>
        <span className={`eco-status eco-${healthStatus.level}`}>{healthStatus.label}</span>
      </div>

      <div className="eco-grid">
        {/* Allee 效应 */}
        <div className={`eco-card ${data.is_below_mvp ? "danger" : ""}`}>
          <div className="eco-card-header">
            <span className="eco-icon">👥</span>
            <span className="eco-title">Allee 效应</span>
          </div>
          <div className="eco-card-body">
            {data.is_below_mvp ? (
              <div className="eco-alert danger">
                <span className="alert-icon">⚠️</span>
                <span>低于最小可存活种群！</span>
              </div>
            ) : (
              <div className="eco-metric">
                <span className="label">繁殖修正</span>
                <span className={`value ${data.allee_reproduction_modifier < 1 ? "warning" : ""}`}>
                  ×{data.allee_reproduction_modifier.toFixed(2)}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* 密度依赖疾病 */}
        <div className={`eco-card ${data.disease_pressure > 0.2 ? "danger" : data.disease_pressure > 0.1 ? "warning" : ""}`}>
          <div className="eco-card-header">
            <span className="eco-icon">🦠</span>
            <span className="eco-title">疾病压力</span>
          </div>
          <div className="eco-card-body">
            <div className="eco-bar-container">
              <div
                className="eco-bar"
                style={{
                  width: `${Math.min(data.disease_pressure * 100, 100)}%`,
                  background: data.disease_pressure > 0.2 ? "#ef4444" : data.disease_pressure > 0.1 ? "#f97316" : "#22c55e",
                }}
              />
            </div>
            <div className="eco-metric">
              <span className="label">死亡率增加</span>
              <span className={`value ${data.disease_mortality_modifier > 0.1 ? "danger" : ""}`}>
                {formatPercent(data.disease_mortality_modifier, true)}
              </span>
            </div>
          </div>
        </div>

        {/* 环境波动 */}
        <div className={`eco-card ${data.env_fluctuation_modifier < 0.8 ? "warning" : ""}`}>
          <div className="eco-card-header">
            <span className="eco-icon">🌡️</span>
            <span className="eco-title">环境波动</span>
          </div>
          <div className="eco-card-body">
            <div className="eco-metric">
              <span className="label">适应系数</span>
              <span className={`value ${data.env_fluctuation_modifier < 0.8 ? "warning" : "healthy"}`}>
                ×{data.env_fluctuation_modifier.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* 同化效率 */}
        <div className="eco-card">
          <div className="eco-card-header">
            <span className="eco-icon">⚡</span>
            <span className="eco-title">同化效率</span>
          </div>
          <div className="eco-card-body">
            <div className="eco-bar-container">
              <div
                className="eco-bar efficiency"
                style={{
                  width: `${(data.assimilation_efficiency / 0.35) * 100}%`,
                }}
              />
            </div>
            <div className="eco-metric">
              <span className="label">能量转化</span>
              <span className="value">{formatPercent(data.assimilation_efficiency)}</span>
            </div>
          </div>
        </div>

        {/* 适应滞后 */}
        <div className={`eco-card ${data.adaptation_penalty > 0.1 ? "warning" : ""}`}>
          <div className="eco-card-header">
            <span className="eco-icon">🔄</span>
            <span className="eco-title">适应滞后</span>
          </div>
          <div className="eco-card-body">
            <div className="eco-metric">
              <span className="label">死亡率惩罚</span>
              <span className={`value ${data.adaptation_penalty > 0.1 ? "danger" : data.adaptation_penalty > 0 ? "warning" : "healthy"}`}>
                {data.adaptation_penalty > 0 ? formatPercent(data.adaptation_penalty, true) : "无"}
              </span>
            </div>
          </div>
        </div>

        {/* 互利共生 */}
        <div className={`eco-card ${data.mutualism_benefit > 0 ? "healthy" : data.mutualism_benefit < 0 ? "danger" : ""}`}>
          <div className="eco-card-header">
            <span className="eco-icon">🤝</span>
            <span className="eco-title">互利共生</span>
          </div>
          <div className="eco-card-body">
            {data.mutualism_partners.length > 0 ? (
              <>
                <div className="eco-metric">
                  <span className="label">共生收益</span>
                  <span className={`value ${data.mutualism_benefit > 0 ? "healthy" : data.mutualism_benefit < 0 ? "danger" : ""}`}>
                    {formatPercent(data.mutualism_benefit, true)}
                  </span>
                </div>
                <div className="eco-partners">
                  <span className="partners-label">伙伴：</span>
                  <div className="partners-list">
                    {data.mutualism_partners.slice(0, 3).map((code, i) => (
                      <span key={i} className="partner-code">{code}</span>
                    ))}
                    {data.mutualism_partners.length > 3 && (
                      <span className="partner-more">+{data.mutualism_partners.length - 3}</span>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="eco-metric">
                <span className="label">状态</span>
                <span className="value neutral">无共生关系</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default EcologicalRealismDisplay;

