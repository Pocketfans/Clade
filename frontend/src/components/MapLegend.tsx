import { useState } from "react";
import type { ViewMode } from "./MapViewSelector";

interface Props {
  viewMode: ViewMode;
  seaLevel?: number;
  temperature?: number;
  visible?: boolean;
  hasSelectedSpecies?: boolean;
}

// 图例数据定义
const LEGENDS: Record<ViewMode, { 
  title: string;
  subtitle?: string;
  items: Array<{ color: string; label: string; range?: string }> 
}> = {
  terrain: {
    title: "实景地图",
    subtitle: "综合地形与生态",
    items: [
      { color: "#000d1f", label: "海沟", range: "< -6000m" },
      { color: "#001f3f", label: "深海", range: "-6000 ~ -3000m" },
      { color: "#0074D9", label: "浅海", range: "-3000 ~ -200m" },
      { color: "#7FDBFF", label: "海岸", range: "-200 ~ 0m" },
      { color: "#7CB342", label: "平原", range: "0 ~ 200m" },
      { color: "#C0A853", label: "丘陵", range: "200 ~ 1000m" },
      { color: "#8B7355", label: "山地", range: "1000 ~ 2500m" },
      { color: "#B0B0B0", label: "高山", range: "2500 ~ 5000m" },
      { color: "#FFFFFF", label: "极高山", range: "> 5000m" },
      { color: "#2ECC40", label: "森林" },
      { color: "#D2B48C", label: "沙漠" },
      { color: "#F0F8FF", label: "冰川" },
    ],
  },
  terrain_type: {
    title: "地形分类",
    subtitle: "纯海拔分类",
    items: [
      { color: "#00050f", label: "海沟", range: "< -6000m" },
      { color: "#001f3f", label: "深海", range: "-6000 ~ -3000m" },
      { color: "#0074D9", label: "浅海", range: "-3000 ~ -200m" },
      { color: "#7FDBFF", label: "海岸", range: "-200 ~ 0m" },
      { color: "#66BB6A", label: "平原", range: "0 ~ 200m" },
      { color: "#FDD835", label: "丘陵", range: "200 ~ 1000m" },
      { color: "#A1887F", label: "山地", range: "1000 ~ 3000m" },
      { color: "#BDBDBD", label: "高山", range: "3000 ~ 5000m" },
      { color: "#FFFFFF", label: "极高山", range: "> 5000m" },
    ],
  },
  elevation: {
    title: "海拔高度",
    subtitle: "相对海平面",
    items: [
      { color: "#1a0033", label: "深海沟", range: "-8000m" },
      { color: "#000066", label: "深海", range: "-6000m" },
      { color: "#0066ff", label: "浅海", range: "-2000m" },
      { color: "#00ccff", label: "近海", range: "-500m" },
      { color: "#00ff99", label: "海平面", range: "0m" },
      { color: "#66ff66", label: "低地", range: "+500m" },
      { color: "#ffff00", label: "丘陵", range: "+2000m" },
      { color: "#ff9900", label: "山地", range: "+4000m" },
      { color: "#cc9999", label: "高山", range: "+6000m" },
      { color: "#ffffff", label: "极高山", range: "+8000m" },
    ],
  },
  biodiversity: {
    title: "生物热力",
    subtitle: "物种多样性分布",
    items: [
      { color: "#081d58", label: "极低", range: "0-10%" },
      { color: "#225ea8", label: "低", range: "10-25%" },
      { color: "#41b6c4", label: "中等", range: "25-50%" },
      { color: "#c7e9b4", label: "较高", range: "50-70%" },
      { color: "#fd8d3c", label: "高", range: "70-90%" },
      { color: "#e31a1c", label: "极高", range: "90-100%" },
    ],
  },
  climate: {
    title: "气候带",
    subtitle: "温度分布",
    items: [
      { color: "#e0f3ff", label: "极地", range: "< -5°C" },
      { color: "#a8d8ea", label: "寒带", range: "-5 ~ 5°C" },
      { color: "#66bb6a", label: "温带", range: "5 ~ 15°C" },
      { color: "#fdd835", label: "亚热带", range: "15 ~ 20°C" },
      { color: "#ff6f00", label: "热带", range: "> 20°C" },
    ],
  },
  suitability: {
    title: "生存适宜度",
    subtitle: "选中物种",
    items: [
      { color: "#00ff00", label: "极高", range: "0.8 - 1.0" },
      { color: "#76ff03", label: "高", range: "0.6 - 0.8" },
      { color: "#ffff00", label: "中", range: "0.4 - 0.6" },
      { color: "#ff9800", label: "低", range: "0.2 - 0.4" },
      { color: "#f44336", label: "极低", range: "0 - 0.2" },
    ],
  },
};

export function MapLegend({ viewMode, seaLevel = 0, temperature = 15, visible = true, hasSelectedSpecies = false }: Props) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const legend = LEGENDS[viewMode];

  if (!visible) return null;

  return (
    <div className={`map-legend-v2 ${isCollapsed ? 'collapsed' : ''}`}>
      {/* 折叠按钮 */}
      <button 
        className="legend-toggle"
        onClick={() => setIsCollapsed(!isCollapsed)}
        title={isCollapsed ? "展开图例" : "折叠图例"}
      >
        {isCollapsed ? '◀' : '▶'}
      </button>

      {!isCollapsed && (
        <>
          {/* 标题区 */}
          <div className="legend-header-v2">
            <div className="legend-title">{legend.title}</div>
            {legend.subtitle && (
              <div className="legend-subtitle">{legend.subtitle}</div>
            )}
            
            {/* 环境信息 */}
            {(viewMode === "terrain" || viewMode === "elevation") && (
              <div className="legend-env-info">
                <span className="env-item">
                  <span className="env-icon">🌊</span>
                  <span className="env-value">{seaLevel.toFixed(0)}m</span>
                </span>
              </div>
            )}
            {viewMode === "climate" && (
              <div className="legend-env-info">
                <span className="env-item">
                  <span className="env-icon">🌡️</span>
                  <span className="env-value">{temperature.toFixed(1)}°C</span>
                </span>
              </div>
            )}
          </div>

          {/* 图例项 */}
          <div className="legend-items-v2">
            {legend.items.map((item, index) => (
              <div key={index} className="legend-item-v2">
                <div 
                  className="legend-color-v2" 
                  style={{ backgroundColor: item.color }}
                />
                <div className="legend-text-v2">
                  <span className="legend-label-v2">{item.label}</span>
                  {item.range && (
                    <span className="legend-range">{item.range}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* 生物栖息指示器说明 */}
          <div className="legend-section-divider" />
          <div className="legend-habitat-section">
            <div className="legend-subtitle">生物分布</div>
            <div className="legend-habitat-items">
              {hasSelectedSpecies && (
                <div className="legend-item-v2">
                  <div className="legend-indicator" style={{ backgroundColor: "#2dd4bf" }} />
                  <span className="legend-label-v2">选中物种存在</span>
                </div>
              )}
              <div className="legend-item-v2">
                <div className="legend-indicator" style={{ backgroundColor: "#22c55e" }} />
                <span className="legend-label-v2">多物种 (5+)</span>
              </div>
              <div className="legend-item-v2">
                <div className="legend-indicator" style={{ backgroundColor: "#86efac" }} />
                <span className="legend-label-v2">少量物种 (2-4)</span>
              </div>
              <div className="legend-item-v2">
                <div className="legend-indicator" style={{ backgroundColor: "#fbbf24" }} />
                <span className="legend-label-v2">单一物种</span>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 折叠状态下显示当前视图图标 */}
      {isCollapsed && (
        <div className="legend-collapsed-hint">
          <span className="collapsed-icon">
            {viewMode === "terrain" ? "🌍" : 
             viewMode === "terrain_type" ? "🏔️" :
             viewMode === "elevation" ? "📐" :
             viewMode === "climate" ? "🌡️" :
             viewMode === "biodiversity" ? "🧬" : "🎯"}
          </span>
        </div>
      )}
    </div>
  );
}
