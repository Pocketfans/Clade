import { useState } from "react";
import { ViewMode } from "../MapViewSelector";

interface Props {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  onToggleGenealogy: () => void;
  onToggleHistory: () => void;
  onToggleNiche: () => void;
  onToggleFoodWeb: () => void;
  onOpenTrends: () => void;
  onOpenMapHistory?: () => void;
  onOpenLogs?: () => void;
  onCreateSpecies?: () => void;  // 新增：创建物种入口
  is3D?: boolean;
  onToggle3D?: () => void;
}

export function LensBar({ 
  currentMode, 
  onModeChange, 
  onToggleGenealogy,
  onToggleHistory,
  onToggleNiche,
  onToggleFoodWeb,
  onOpenTrends,
  onOpenMapHistory,
  onOpenLogs,
  onCreateSpecies,
  is3D = false,
  onToggle3D
}: Props) {
  const [hoveredTool, setHoveredTool] = useState<string | null>(null);

  const lenses: Array<{ id: ViewMode; label: string; icon: string; color: string }> = [
    { id: "terrain", label: "实景", icon: "🌍", color: "#22c55e" },
    { id: "terrain_type", label: "地形", icon: "🏔️", color: "#a78bfa" },
    { id: "elevation", label: "海拔", icon: "📏", color: "#fb923c" },
    { id: "climate", label: "气候", icon: "🌡️", color: "#f43f5e" },
    { id: "biodiversity", label: "生态", icon: "🌿", color: "#4ade80" },
    { id: "suitability", label: "适宜", icon: "🎯", color: "#2dd4bf" },
  ];

  const tools = [
    { id: "create", label: "创建物种", icon: "✨", action: onCreateSpecies, color: "#f59e0b" },
    { id: "genealogy", label: "族谱", icon: "🧬", action: onToggleGenealogy, color: "#c084fc" },
    { id: "trends", label: "全球趋势", icon: "📈", action: onOpenTrends, color: "#4ade80" },
    { id: "niche", label: "生态位", icon: "📊", action: onToggleNiche, color: "#38bdf8" },
    { id: "foodweb", label: "食物网", icon: "🕸️", action: onToggleFoodWeb, color: "#f43f5e" },
    { id: "maphistory", label: "地图变迁", icon: "🗺️", action: onOpenMapHistory, color: "#a78bfa" },
    { id: "logs", label: "系统日志", icon: "🖥️", action: onOpenLogs, color: "#94a3b8" },
    { id: "history", label: "年鉴", icon: "📜", action: onToggleHistory, color: "#fbbf24" },
  ].filter(tool => tool.action);

  return (
    <div className="lensbar-container">
      {/* Map Lenses Group */}
      <div className="lensbar-group lensbar-lenses">
        {lenses.map(lens => {
          const isActive = currentMode === lens.id;
          return (
            <button
              key={lens.id}
              onClick={() => onModeChange(lens.id)}
              title={`切换至${lens.label}视图`}
              className={`lens-btn ${isActive ? 'active' : ''}`}
              style={{
                '--lens-color': lens.color,
              } as React.CSSProperties}
            >
              <span className="lens-icon">{lens.icon}</span>
              <span className="lens-label">{lens.label}</span>
              {isActive && <div className="lens-active-indicator" />}
            </button>
          );
        })}
      </div>

      {/* Functional Tools Group */}
      <div className="lensbar-group lensbar-tools">
        {/* 3D Toggle */}
        {onToggle3D && (
          <button
            onClick={onToggle3D}
            title={is3D ? "切换回2D视图" : "切换至3D视图"}
            className={`tool-btn tool-3d ${is3D ? 'active' : ''}`}
          >
            <span className="tool-3d-text">{is3D ? "3D" : "2D"}</span>
          </button>
        )}

        <div className="lensbar-divider" />

        {tools.map(tool => (
          <button
            key={tool.id}
            onClick={tool.action}
            title={tool.label}
            className={`tool-btn ${hoveredTool === tool.id ? 'hovered' : ''}`}
            style={{
              '--tool-color': tool.color,
            } as React.CSSProperties}
            onMouseEnter={() => setHoveredTool(tool.id)}
            onMouseLeave={() => setHoveredTool(null)}
          >
            <span className="tool-icon">{tool.icon}</span>
            <div className="tool-glow" />
            {hoveredTool === tool.id && (
              <div className="tool-tooltip">{tool.label}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
