import { useState, useRef, useEffect } from "react";
import { ViewMode } from "../MapViewSelector";

interface HintsInfo {
  count: number;
  criticalCount: number;
  highCount: number;
}

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
  onCreateSpecies?: () => void;
  onOpenHybridization?: () => void;
  onOpenAIAssistant?: () => void;
  onOpenAchievements?: () => void;
  onToggleHints?: () => void;
  showHints?: boolean;
  hintsInfo?: HintsInfo;
}

// Tooltip 组件
function ToolTooltip({ title, description, color }: { title: string; description: string; color?: string }) {
  return (
    <div className="tool-tooltip-v2" style={{ '--tooltip-color': color || '#2dd4bf' } as React.CSSProperties}>
      <div className="tooltip-title">{title}</div>
      <div className="tooltip-desc">{description}</div>
    </div>
  );
}

// 视图模式分组
const VIEW_GROUPS = {
  terrain: {
    label: "地形",
    icon: "🗺️",
    modes: [
      { id: "terrain" as ViewMode, label: "实景地图", icon: "🌍", description: "综合地形、覆盖物与气候的真实世界风格" },
      { id: "terrain_type" as ViewMode, label: "地形分类", icon: "🏔️", description: "纯地形分类（深海/浅海/平原/丘陵/山地）" },
      { id: "elevation" as ViewMode, label: "海拔高度", icon: "📐", description: "海拔高度渐变色阶（-11000m 至 8848m）" },
    ]
  },
  climate: {
    label: "气候",
    icon: "🌡️",
    modes: [
      { id: "climate" as ViewMode, label: "气候带", icon: "🌡️", description: "气候带与温度分布" },
    ]
  },
  ecology: {
    label: "生态",
    icon: "🌿",
    modes: [
      { id: "biodiversity" as ViewMode, label: "生物热力", icon: "🧬", description: "物种分布与多样性热力图" },
      { id: "suitability" as ViewMode, label: "适宜度", icon: "🎯", description: "当前选中物种的生存适宜度分布" },
    ]
  }
};

// 分析工具定义
const ANALYSIS_TOOLS = [
  { id: "create", label: "创建物种", icon: "✨", description: "设计并投放新物种", color: "#f59e0b" },
  { id: "hybridize", label: "物种杂交", icon: "🧬", description: "诱导两个物种杂交产生后代", color: "#10b981" },
  { id: "genealogy", label: "演化族谱", icon: "🌳", description: "查看物种演化关系树", color: "#c084fc" },
  { id: "foodweb", label: "食物网", icon: "🕸️", description: "分析捕食与被捕食关系", color: "#f43f5e" },
  { id: "niche", label: "生态位对比", icon: "📊", description: "对比不同物种的生态位", color: "#38bdf8" },
  { id: "trends", label: "全球趋势", icon: "📈", description: "查看环境与生物量变化趋势", color: "#4ade80" },
  { id: "ai", label: "AI 助手", icon: "🤖", description: "智能搜索、问答与演化预测", color: "#a855f7" },
  { id: "achievements", label: "成就", icon: "🏆", description: "查看成就进度与解锁奖励", color: "#fbbf24" },
  { id: "hints", label: "提示", icon: "💡", description: "智能游戏建议与提示", color: "#22d3ee" },
];

// 历史工具
const HISTORY_TOOLS = [
  { id: "maphistory", label: "地质变迁", icon: "🌋", description: "回顾地图的地质变化历史", color: "#a78bfa" },
  { id: "history", label: "演化年鉴", icon: "📜", description: "查看完整的演化历史记录", color: "#fbbf24" },
  { id: "logs", label: "系统日志", icon: "🖥️", description: "查看详细的系统运行日志", color: "#94a3b8" },
];

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
  onOpenHybridization,
  onOpenAIAssistant,
  onOpenAchievements,
  onToggleHints,
  showHints = false,
  hintsInfo,
}: Props) {
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [hoveredTool, setHoveredTool] = useState<string | null>(null);
  const [hoveredViewGroup, setHoveredViewGroup] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setActiveDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 获取当前模式所在的分组
  const getCurrentGroupKey = () => {
    for (const [key, group] of Object.entries(VIEW_GROUPS)) {
      if (group.modes.some(m => m.id === currentMode)) {
        return key;
      }
    }
    return "terrain";
  };

  // 获取当前模式的信息
  const getCurrentModeInfo = () => {
    for (const group of Object.values(VIEW_GROUPS)) {
      const mode = group.modes.find(m => m.id === currentMode);
      if (mode) return mode;
    }
    return VIEW_GROUPS.terrain.modes[0];
  };

  const handleToolClick = (toolId: string) => {
    switch (toolId) {
      case "create": onCreateSpecies?.(); break;
      case "hybridize": onOpenHybridization?.(); break;
      case "genealogy": onToggleGenealogy(); break;
      case "foodweb": onToggleFoodWeb(); break;
      case "niche": onToggleNiche(); break;
      case "trends": onOpenTrends(); break;
      case "maphistory": onOpenMapHistory?.(); break;
      case "history": onToggleHistory(); break;
      case "logs": onOpenLogs?.(); break;
      case "ai": onOpenAIAssistant?.(); break;
      case "achievements": onOpenAchievements?.(); break;
      case "hints": onToggleHints?.(); break;
    }
  };

  const currentModeInfo = getCurrentModeInfo();
  const currentGroupKey = getCurrentGroupKey();

  return (
    <div className="lensbar-v2" ref={dropdownRef}>
      {/* ===== 左侧：地图视图选择 ===== */}
      <div className="lensbar-section lensbar-views">
        <div className="section-label">视图</div>
        <div className="view-controls">
          {/* 视图分组按钮 */}
          {Object.entries(VIEW_GROUPS).map(([groupKey, group]) => {
            const isActiveGroup = currentGroupKey === groupKey;
            const isDropdownOpen = activeDropdown === groupKey;
            const groupModes = group.modes;
            const activeModeInGroup = groupModes.find(m => m.id === currentMode);
            const isHovered = hoveredViewGroup === groupKey && !isDropdownOpen;
            
            // 视图分组的颜色
            const groupColors: Record<string, string> = {
              terrain: "#10b981",
              climate: "#f59e0b", 
              ecology: "#a78bfa"
            };

            return (
              <div key={groupKey} className="view-group-wrapper">
                <button
                  className={`view-group-btn ${isActiveGroup ? 'active' : ''} ${isDropdownOpen ? 'open' : ''}`}
                  onClick={() => {
                    if (groupModes.length === 1) {
                      // 只有一个模式，直接切换
                      onModeChange(groupModes[0].id);
                      setActiveDropdown(null);
                    } else {
                      // 多个模式，展开下拉菜单
                      setActiveDropdown(isDropdownOpen ? null : groupKey);
                    }
                  }}
                  onMouseEnter={() => setHoveredViewGroup(groupKey)}
                  onMouseLeave={() => setHoveredViewGroup(null)}
                >
                  <span className="view-icon">{activeModeInGroup?.icon || group.icon}</span>
                  <span className="view-label">
                    {activeModeInGroup?.label || group.label}
                  </span>
                  {groupModes.length > 1 && (
                    <span className="dropdown-arrow">{isDropdownOpen ? '▲' : '▼'}</span>
                  )}
                  {/* 悬浮提示 - 只在没有打开下拉菜单时显示 */}
                  {isHovered && (
                    <ToolTooltip 
                      title={activeModeInGroup?.label || group.label}
                      description={activeModeInGroup?.description || `切换${group.label}视图模式`}
                      color={groupColors[groupKey]}
                    />
                  )}
                </button>

                {/* 下拉菜单 */}
                {isDropdownOpen && groupModes.length > 1 && (
                  <div className="view-dropdown">
                    {groupModes.map(mode => (
                      <button
                        key={mode.id}
                        className={`dropdown-item ${currentMode === mode.id ? 'active' : ''}`}
                        onClick={() => {
                          onModeChange(mode.id);
                          setActiveDropdown(null);
                        }}
                      >
                        <span className="item-icon">{mode.icon}</span>
                        <div className="item-content">
                          <span className="item-label">{mode.label}</span>
                          <span className="item-desc">{mode.description}</span>
                        </div>
                        {currentMode === mode.id && <span className="item-check">✓</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ===== 分隔线 ===== */}
      <div className="lensbar-divider-v2" />

      {/* ===== 中间：分析工具 ===== */}
      <div className="lensbar-section lensbar-analysis">
        <div className="section-label">分析</div>
        <div className="tool-row">
          {ANALYSIS_TOOLS.filter(t => {
            if (t.id === "create") return !!onCreateSpecies;
            if (t.id === "hybridize") return !!onOpenHybridization;
            if (t.id === "ai") return !!onOpenAIAssistant;
            if (t.id === "achievements") return !!onOpenAchievements;
            if (t.id === "hints") return !!onToggleHints;
            return true;
          }).map(tool => (
            <div
              key={tool.id}
              className="tool-btn-wrapper"
              onMouseEnter={() => setHoveredTool(tool.id)}
              onMouseLeave={() => setHoveredTool(null)}
            >
              <button
                className={`tool-btn-v2 ${hoveredTool === tool.id ? 'hovered' : ''} ${tool.id === 'hints' && showHints ? 'active' : ''}`}
                style={{ '--tool-color': tool.color } as React.CSSProperties}
                onClick={() => handleToolClick(tool.id)}
                title={`${tool.label} - ${tool.description}`}
              >
                <span className="tool-icon-v2">{tool.icon}</span>
                {/* 提示按钮的徽章 */}
                {tool.id === 'hints' && hintsInfo && hintsInfo.count > 0 && (
                  <span className={`hints-badge ${
                    hintsInfo.criticalCount > 0 ? 'critical' : 
                    hintsInfo.highCount > 0 ? 'high' : 'normal'
                  }`}>
                    {hintsInfo.criticalCount > 0 ? hintsInfo.criticalCount : 
                     hintsInfo.highCount > 0 ? hintsInfo.highCount : hintsInfo.count}
                  </span>
                )}
              </button>
              {hoveredTool === tool.id && (
                <ToolTooltip 
                  title={tool.label} 
                  description={tool.description} 
                  color={tool.color}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ===== 分隔线 ===== */}
      <div className="lensbar-divider-v2" />

      {/* ===== 右侧：历史与系统 ===== */}
      <div className="lensbar-section lensbar-history">
        <div className="section-label">历史</div>
        <div className="tool-row">
          {HISTORY_TOOLS.filter(t => {
            if (t.id === "maphistory") return !!onOpenMapHistory;
            if (t.id === "logs") return !!onOpenLogs;
            return true;
          }).map(tool => (
            <div
              key={tool.id}
              className="tool-btn-wrapper"
              onMouseEnter={() => setHoveredTool(tool.id)}
              onMouseLeave={() => setHoveredTool(null)}
            >
              <button
                className={`tool-btn-v2 ${hoveredTool === tool.id ? 'hovered' : ''}`}
                style={{ '--tool-color': tool.color } as React.CSSProperties}
                onClick={() => handleToolClick(tool.id)}
                title={`${tool.label} - ${tool.description}`}
              >
                <span className="tool-icon-v2">{tool.icon}</span>
              </button>
              {hoveredTool === tool.id && (
                <ToolTooltip 
                  title={tool.label} 
                  description={tool.description} 
                  color={tool.color}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
