/**
 * EcologicalRealismSummary - 回合级生态拟真汇总组件
 *
 * 显示整体生态系统的 Allee 效应、疾病压力、共生关系等统计
 */

import type { EcologicalRealismSummary as EcoSummaryType } from "@/services/api.types";
import "./EcologicalRealismSummary.css";

interface EcologicalRealismSummaryProps {
  data: EcoSummaryType | null | undefined;
  className?: string;
}

export function EcologicalRealismSummary({ data, className = "" }: EcologicalRealismSummaryProps) {
  if (!data) {
    return null;
  }

  const hasIssues = data.allee_affected_count > 0 || data.disease_affected_count > 0 || data.adaptation_stressed_count > 0;

  return (
    <div className={`eco-summary ${className}`}>
      <div className="eco-summary-header">
        <span className="eco-summary-icon">🌍</span>
        <h3>生态拟真系统</h3>
        {hasIssues && <span className="eco-summary-alert">需要关注</span>}
      </div>

      <div className="eco-summary-grid">
        {/* Allee 效应 */}
        <div className={`eco-summary-card ${data.allee_affected_count > 0 ? "warning" : ""}`}>
          <div className="eco-summary-card-icon">👥</div>
          <div className="eco-summary-card-content">
            <div className="eco-summary-card-title">Allee 效应</div>
            <div className="eco-summary-card-value">
              {data.allee_affected_count > 0 ? (
                <span className="danger">{data.allee_affected_count} 个物种</span>
              ) : (
                <span className="safe">无影响</span>
              )}
            </div>
            {data.allee_affected_species.length > 0 && (
              <div className="eco-summary-card-detail">
                受影响: {data.allee_affected_species.slice(0, 3).join(", ")}
                {data.allee_affected_species.length > 3 && " ..."}
              </div>
            )}
          </div>
        </div>

        {/* 疾病压力 */}
        <div className={`eco-summary-card ${data.disease_affected_count > 0 ? "warning" : ""}`}>
          <div className="eco-summary-card-icon">🦠</div>
          <div className="eco-summary-card-content">
            <div className="eco-summary-card-title">疾病压力</div>
            <div className="eco-summary-card-value">
              {data.disease_affected_count > 0 ? (
                <span className="danger">{data.disease_affected_count} 个物种</span>
              ) : (
                <span className="safe">健康</span>
              )}
            </div>
            <div className="eco-summary-card-detail">
              平均压力: {Math.round(data.avg_disease_pressure * 100)}%
            </div>
          </div>
        </div>

        {/* 互利共生 */}
        <div className={`eco-summary-card ${data.mutualism_links_count > 0 ? "positive" : ""}`}>
          <div className="eco-summary-card-icon">🤝</div>
          <div className="eco-summary-card-content">
            <div className="eco-summary-card-title">互利共生</div>
            <div className="eco-summary-card-value">
              {data.mutualism_links_count > 0 ? (
                <span className="positive">{data.mutualism_links_count} 对关系</span>
              ) : (
                <span className="neutral">无共生网络</span>
              )}
            </div>
            {data.mutualism_species_count > 0 && (
              <div className="eco-summary-card-detail">
                涉及 {data.mutualism_species_count} 个物种
              </div>
            )}
          </div>
        </div>

        {/* 适应压力 */}
        <div className={`eco-summary-card ${data.adaptation_stressed_count > 0 ? "warning" : ""}`}>
          <div className="eco-summary-card-icon">🔄</div>
          <div className="eco-summary-card-content">
            <div className="eco-summary-card-title">适应滞后</div>
            <div className="eco-summary-card-value">
              {data.adaptation_stressed_count > 0 ? (
                <span className="danger">{data.adaptation_stressed_count} 个物种</span>
              ) : (
                <span className="safe">适应良好</span>
              )}
            </div>
            <div className="eco-summary-card-detail">
              环境系数: ×{data.avg_env_modifier.toFixed(2)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EcologicalRealismSummary;









