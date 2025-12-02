/**
 * SpeciesListItem - 物种列表项组件
 */

import { memo } from "react";
import { TrendingUp, TrendingDown, Minus, Skull } from "lucide-react";
import type { SpeciesSnapshot } from "@/services/api.types";
import type { PopulationTrend } from "../types";
import { getRoleConfig, STATUS_COLORS, TREND_COLORS } from "../constants";

interface SpeciesListItemProps {
  species: SpeciesSnapshot;
  isSelected: boolean;
  trend: PopulationTrend;
  populationChange: number;
  onClick: () => void;
}

export const SpeciesListItem = memo(function SpeciesListItem({
  species,
  isSelected,
  trend,
  populationChange,
  onClick,
}: SpeciesListItemProps) {
  const role = getRoleConfig(species.ecological_role || "unknown");
  const isExtinct = species.status === "extinct";
  const statusConfig = STATUS_COLORS[isExtinct ? "extinct" : "alive"];

  // 格式化人口数
  const formatPopulation = (pop: number): string => {
    if (pop >= 1000000) return `${(pop / 1000000).toFixed(1)}M`;
    if (pop >= 1000) return `${(pop / 1000).toFixed(1)}K`;
    return pop.toString();
  };

  // 趋势图标
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  return (
    <div
      className={`species-list-item ${isSelected ? "selected" : ""} ${isExtinct ? "extinct" : ""}`}
      onClick={onClick}
      style={{
        borderLeft: `3px solid ${role.color}`,
        background: isSelected ? role.bgGradient : undefined,
      }}
    >
      {/* 角色图标 */}
      <div className="species-icon" style={{ background: role.gradient }}>
        <span>{role.icon}</span>
      </div>

      {/* 物种信息 */}
      <div className="species-info">
        <div className="species-name">
          {species.common_name || species.lineage_code}
          {isExtinct && <Skull size={14} className="extinct-icon" />}
        </div>
        <div className="species-meta">
          <span className="species-code">{species.lineage_code}</span>
          <span className="species-role" style={{ color: role.color }}>
            {role.label}
          </span>
        </div>
      </div>

      {/* 种群信息 */}
      <div className="species-population">
        <div className="population-value">
          {formatPopulation(species.population || 0)}
        </div>
        {!isExtinct && populationChange !== 0 && (
          <div
            className="population-trend"
            style={{ color: TREND_COLORS[trend].color }}
          >
            <TrendIcon size={12} />
            <span>{Math.abs(populationChange)}</span>
          </div>
        )}
      </div>
    </div>
  );
});
