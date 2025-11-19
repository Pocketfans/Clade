import type { ViewMode } from "./MapViewSelector";

interface Props {
  viewMode: ViewMode;
  seaLevel?: number;
  temperature?: number;
}

export function MapLegend({ viewMode, seaLevel = 0, temperature = 15 }: Props) {
  const legends: Record<ViewMode, Array<{ color: string; label: string }>> = {
    terrain: [
      { color: "#000d1f", label: "海沟 (<-6000m)" },
      { color: "#001f3f", label: "深海 (-6000~-3000m)" },
      { color: "#0074D9", label: "浅海 (-3000~-200m)" },
      { color: "#7FDBFF", label: "海岸 (-200~0m)" },
      { color: "#7CB342", label: "平原 (0~200m)" },
      { color: "#C0A853", label: "丘陵 (200~1000m)" },
      { color: "#8B7355", label: "山地 (1000~2500m)" },
      { color: "#B0B0B0", label: "高山 (2500~5000m)" },
      { color: "#FFFFFF", label: "极高山 (>5000m)" },
      { color: "#2ECC40", label: "森林" },
      { color: "#D2B48C", label: "沙漠" },
      { color: "#F0F8FF", label: "冰川" },
    ],
    terrain_type: [
      { color: "#00050f", label: "海沟 (<-6000m)" },
      { color: "#001f3f", label: "深海 (-6000~-3000m)" },
      { color: "#0074D9", label: "浅海 (-3000~-200m)" },
      { color: "#7FDBFF", label: "海岸 (-200~0m)" },
      { color: "#66BB6A", label: "平原 (0~200m)" },
      { color: "#FDD835", label: "丘陵 (200~1000m)" },
      { color: "#A1887F", label: "山地 (1000~3000m)" },
      { color: "#BDBDBD", label: "高山 (3000~5000m)" },
      { color: "#FFFFFF", label: "极高山 (>5000m)" },
    ],
    elevation: [
      { color: "#1a0033", label: "-8000m 深海沟" },
      { color: "#000066", label: "-6000m" },
      { color: "#0066ff", label: "-2000m" },
      { color: "#00ccff", label: "-500m" },
      { color: "#00ff99", label: "0m 海平面" },
      { color: "#66ff66", label: "+500m" },
      { color: "#ffff00", label: "+2000m" },
      { color: "#ff9900", label: "+4000m" },
      { color: "#cc9999", label: "+6000m" },
      { color: "#ffffff", label: "+8000m 极高山" },
    ],
    biodiversity: [
      { color: "#081d58", label: "极低" },
      { color: "#225ea8", label: "低" },
      { color: "#41b6c4", label: "中等" },
      { color: "#c7e9b4", label: "较高" },
      { color: "#fd8d3c", label: "高" },
      { color: "#e31a1c", label: "极高" },
    ],
    climate: [
      { color: "#e0f3ff", label: "极地 (<-5°C)" },
      { color: "#a8d8ea", label: "寒带 (-5~5°C)" },
      { color: "#66bb6a", label: "温带 (5~15°C)" },
      { color: "#fdd835", label: "亚热带 (15~20°C)" },
      { color: "#ff6f00", label: "热带 (>20°C)" },
    ],
  };

  const currentLegend = legends[viewMode];

  return (
    <div className="map-legend">
      <div className="legend-header">
        <strong>图例</strong>
        {viewMode === "terrain" && (
          <small style={{ marginLeft: "8px", opacity: 0.8 }}>
            海平面: {seaLevel.toFixed(0)}m
          </small>
        )}
        {viewMode === "elevation" && (
          <small style={{ marginLeft: "8px", opacity: 0.8 }}>
            相对海拔 (海平面: {seaLevel.toFixed(0)}m)
          </small>
        )}
      </div>
      <div className="legend-items">
        {currentLegend.map((item, index) => (
          <div key={index} className="legend-item">
            <div className="legend-color" style={{ backgroundColor: item.color }} />
            <span className="legend-label">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

