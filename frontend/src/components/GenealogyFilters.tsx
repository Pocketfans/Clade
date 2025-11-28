import { Filter, Search, ChevronDown, RotateCcw, Leaf, Skull, Crosshair, Star } from "lucide-react";
import { useState } from "react";

export interface FilterOptions {
  states: string[];
  ecologicalRoles: string[];
  tiers: string[];
  turnRange: [number, number];
  searchTerm: string;
}

interface Props {
  filters: FilterOptions;
  maxTurn: number;
  onChange: (filters: FilterOptions) => void;
}

export function GenealogyFilters({ filters, maxTurn, onChange }: Props) {
  const [showFilters, setShowFilters] = useState(false);

  const stateOptions = [
    { value: "alive", label: "存活", icon: <Leaf size={12} />, color: "#22c55e" },
    { value: "extinct", label: "灭绝", icon: <Skull size={12} />, color: "#ef4444" },
  ];

  const roleOptions = [
    { value: "producer", label: "生产者", color: "#10b981", emoji: "🌿" },
    { value: "herbivore", label: "食草", color: "#fbbf24", emoji: "🦌" },
    { value: "carnivore", label: "食肉", color: "#f43f5e", emoji: "🦁" },
    { value: "omnivore", label: "杂食", color: "#f97316", emoji: "🐻" },
    { value: "unknown", label: "未知", color: "#64748b", emoji: "❓" },
  ];

  const tierOptions = [
    { value: "focus", label: "重点", icon: <Star size={12} />, color: "#fbbf24" },
    { value: "important", label: "重要", icon: <Crosshair size={12} />, color: "#3b82f6" },
    { value: "background", label: "背景", color: "#64748b" },
  ];

  const toggleState = (state: string) => {
    const newStates = filters.states.includes(state)
      ? filters.states.filter(s => s !== state)
      : [...filters.states, state];
    onChange({ ...filters, states: newStates });
  };

  const toggleRole = (role: string) => {
    const newRoles = filters.ecologicalRoles.includes(role)
      ? filters.ecologicalRoles.filter(r => r !== role)
      : [...filters.ecologicalRoles, role];
    onChange({ ...filters, ecologicalRoles: newRoles });
  };

  const toggleTier = (tier: string) => {
    const newTiers = filters.tiers.includes(tier)
      ? filters.tiers.filter(t => t !== tier)
      : [...filters.tiers, tier];
    onChange({ ...filters, tiers: newTiers });
  };

  const resetFilters = () => {
    onChange({
      states: [],
      ecologicalRoles: [],
      tiers: [],
      turnRange: [0, maxTurn],
      searchTerm: "",
    });
  };

  const hasActiveFilters = filters.states.length > 0 || 
    filters.ecologicalRoles.length > 0 || 
    filters.tiers.length > 0 || 
    filters.searchTerm.length > 0 ||
    filters.turnRange[0] > 0 || 
    filters.turnRange[1] < maxTurn;

  const activeFilterCount = 
    filters.states.length + 
    filters.ecologicalRoles.length + 
    filters.tiers.length + 
    (filters.searchTerm ? 1 : 0) +
    (filters.turnRange[0] > 0 || filters.turnRange[1] < maxTurn ? 1 : 0);

  return (
    <div className="genealogy-filters">
      <div className="filters-bar">
        {/* 筛选器切换按钮 */}
        <button 
          className={`filter-toggle ${showFilters ? "active" : ""} ${hasActiveFilters ? "has-filters" : ""}`}
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter size={16} />
          <span>筛选器</span>
          {activeFilterCount > 0 && (
            <span className="filter-count">{activeFilterCount}</span>
          )}
          <ChevronDown 
            size={14} 
            className={`chevron ${showFilters ? "rotated" : ""}`}
          />
        </button>

        {/* 搜索框 */}
        <div className="search-wrapper">
          <Search size={14} className="search-icon" />
          <input
            type="text"
            placeholder="搜索物种名称、代码..."
            value={filters.searchTerm}
            onChange={(e) => onChange({ ...filters, searchTerm: e.target.value })}
          />
          {filters.searchTerm && (
            <button 
              className="search-clear"
              onClick={() => onChange({ ...filters, searchTerm: "" })}
            >
              ×
            </button>
          )}
        </div>

        {/* 快速筛选标签 */}
        <div className="quick-filters">
          {stateOptions.map(opt => (
            <button
              key={opt.value}
              className={`quick-chip ${filters.states.includes(opt.value) ? "active" : ""}`}
              onClick={() => toggleState(opt.value)}
              style={{ 
                "--chip-color": opt.color,
                "--chip-bg": `${opt.color}15`,
                "--chip-border": `${opt.color}30`,
              } as React.CSSProperties}
            >
              {opt.icon}
              <span>{opt.label}</span>
            </button>
          ))}
        </div>

        {/* 重置按钮 */}
        {hasActiveFilters && (
          <button className="reset-btn" onClick={resetFilters} title="重置筛选">
            <RotateCcw size={14} />
          </button>
        )}
      </div>

      {/* 展开的筛选面板 */}
      {showFilters && (
        <div className="filters-panel">
          {/* 生态角色筛选 */}
          <div className="filter-group">
            <label className="group-label">
              <span className="label-icon">🎭</span>
              <span>生态角色</span>
            </label>
            <div className="chips-row">
              {roleOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`role-chip ${filters.ecologicalRoles.includes(opt.value) ? "active" : ""}`}
                  onClick={() => toggleRole(opt.value)}
                  style={{ 
                    "--chip-color": opt.color,
                  } as React.CSSProperties}
                >
                  <span className="role-emoji">{opt.emoji}</span>
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 层级筛选 */}
          <div className="filter-group">
            <label className="group-label">
              <span className="label-icon">📊</span>
              <span>重要性层级</span>
            </label>
            <div className="chips-row">
              {tierOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`tier-chip ${filters.tiers.includes(opt.value) ? "active" : ""}`}
                  onClick={() => toggleTier(opt.value)}
                  style={{ 
                    "--chip-color": opt.color,
                  } as React.CSSProperties}
                >
                  {opt.icon}
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 回合范围筛选 */}
          <div className="filter-group range-group">
            <label className="group-label">
              <span className="label-icon">⏱️</span>
              <span>诞生回合</span>
              <span className="range-display">
                T{filters.turnRange[0] + 1} — T{filters.turnRange[1] + 1}
              </span>
            </label>
            <div className="range-slider-container">
              <div className="range-track">
                <div 
                  className="range-fill"
                  style={{
                    left: `${(filters.turnRange[0] / maxTurn) * 100}%`,
                    right: `${100 - (filters.turnRange[1] / maxTurn) * 100}%`,
                  }}
                />
              </div>
              <input
                type="range"
                className="range-input min"
                min={0}
                max={maxTurn}
                value={filters.turnRange[0]}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (val < filters.turnRange[1]) {
                    onChange({ ...filters, turnRange: [val, filters.turnRange[1]] });
                  }
                }}
              />
              <input
                type="range"
                className="range-input max"
                min={0}
                max={maxTurn}
                value={filters.turnRange[1]}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (val > filters.turnRange[0]) {
                    onChange({ ...filters, turnRange: [filters.turnRange[0], val] });
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}

      <style>{`
        .genealogy-filters {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .filters-bar {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        /* 筛选器切换按钮 */
        .filter-toggle {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 16px;
          background: rgba(30, 41, 59, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: rgba(148, 163, 184, 0.9);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-toggle:hover {
          background: rgba(59, 130, 246, 0.1);
          border-color: rgba(59, 130, 246, 0.2);
          color: #e2e8f0;
        }

        .filter-toggle.active {
          background: rgba(59, 130, 246, 0.15);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }

        .filter-toggle.has-filters {
          border-color: rgba(59, 130, 246, 0.4);
        }

        .filter-count {
          min-width: 18px;
          height: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #3b82f6;
          border-radius: 9px;
          font-size: 0.7rem;
          font-weight: 700;
          color: white;
          padding: 0 5px;
        }

        .chevron {
          transition: transform 0.2s;
        }

        .chevron.rotated {
          transform: rotate(180deg);
        }

        /* 搜索框 */
        .search-wrapper {
          position: relative;
          flex: 1;
          max-width: 280px;
        }

        .search-icon {
          position: absolute;
          left: 14px;
          top: 50%;
          transform: translateY(-50%);
          color: rgba(148, 163, 184, 0.5);
          pointer-events: none;
        }

        .search-wrapper input {
          width: 100%;
          padding: 10px 36px 10px 38px;
          background: rgba(15, 23, 42, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.85rem;
          transition: all 0.2s;
        }

        .search-wrapper input::placeholder {
          color: rgba(148, 163, 184, 0.5);
        }

        .search-wrapper input:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.4);
          background: rgba(15, 23, 42, 0.8);
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .search-clear {
          position: absolute;
          right: 10px;
          top: 50%;
          transform: translateY(-50%);
          width: 20px;
          height: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.1);
          border: none;
          border-radius: 50%;
          color: rgba(148, 163, 184, 0.8);
          font-size: 14px;
          cursor: pointer;
          transition: all 0.15s;
        }

        .search-clear:hover {
          background: rgba(239, 68, 68, 0.2);
          color: #f87171;
        }

        /* 快速筛选标签 */
        .quick-filters {
          display: flex;
          gap: 6px;
        }

        .quick-chip {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 7px 12px;
          background: var(--chip-bg);
          border: 1px solid var(--chip-border);
          border-radius: 8px;
          color: var(--chip-color);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .quick-chip:hover {
          background: color-mix(in srgb, var(--chip-color) 20%, transparent);
          border-color: color-mix(in srgb, var(--chip-color) 50%, transparent);
        }

        .quick-chip.active {
          background: color-mix(in srgb, var(--chip-color) 25%, transparent);
          border-color: var(--chip-color);
          box-shadow: 0 0 12px color-mix(in srgb, var(--chip-color) 30%, transparent);
        }

        /* 重置按钮 */
        .reset-btn {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 8px;
          color: #f87171;
          cursor: pointer;
          transition: all 0.2s;
        }

        .reset-btn:hover {
          background: rgba(239, 68, 68, 0.2);
          transform: rotate(-90deg);
        }

        /* 筛选面板 */
        .filters-panel {
          display: flex;
          gap: 20px;
          padding: 16px 20px;
          background: rgba(15, 23, 42, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          animation: slideDown 0.2s ease;
        }

        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateY(-8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .filter-group {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .group-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          color: rgba(148, 163, 184, 0.8);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .label-icon {
          font-size: 0.85rem;
        }

        .chips-row {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }

        /* 角色筛选标签 */
        .role-chip {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: rgba(30, 41, 59, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: rgba(148, 163, 184, 0.9);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .role-chip:hover {
          background: color-mix(in srgb, var(--chip-color) 15%, transparent);
          border-color: color-mix(in srgb, var(--chip-color) 30%, transparent);
          color: var(--chip-color);
        }

        .role-chip.active {
          background: color-mix(in srgb, var(--chip-color) 20%, transparent);
          border-color: var(--chip-color);
          color: var(--chip-color);
          box-shadow: 0 2px 8px color-mix(in srgb, var(--chip-color) 25%, transparent);
        }

        .role-emoji {
          font-size: 0.9rem;
        }

        /* 层级筛选标签 */
        .tier-chip {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 8px 12px;
          background: rgba(30, 41, 59, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: rgba(148, 163, 184, 0.9);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .tier-chip:hover {
          background: color-mix(in srgb, var(--chip-color) 15%, transparent);
          border-color: color-mix(in srgb, var(--chip-color) 30%, transparent);
          color: var(--chip-color);
        }

        .tier-chip.active {
          background: color-mix(in srgb, var(--chip-color) 20%, transparent);
          border-color: var(--chip-color);
          color: var(--chip-color);
        }

        /* 范围滑块 */
        .range-group {
          min-width: 200px;
        }

        .range-display {
          margin-left: auto;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.75rem;
          color: #60a5fa;
        }

        .range-slider-container {
          position: relative;
          height: 24px;
          padding: 8px 0;
        }

        .range-track {
          position: absolute;
          top: 50%;
          left: 0;
          right: 0;
          height: 4px;
          transform: translateY(-50%);
          background: rgba(59, 130, 246, 0.2);
          border-radius: 2px;
        }

        .range-fill {
          position: absolute;
          top: 0;
          bottom: 0;
          background: linear-gradient(90deg, #3b82f6, #60a5fa);
          border-radius: 2px;
        }

        .range-input {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          -webkit-appearance: none;
          background: transparent;
          pointer-events: none;
        }

        .range-input::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 16px;
          height: 16px;
          background: #3b82f6;
          border: 2px solid #fff;
          border-radius: 50%;
          cursor: pointer;
          pointer-events: auto;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
          transition: transform 0.15s;
        }

        .range-input::-webkit-slider-thumb:hover {
          transform: scale(1.15);
        }
      `}</style>
    </div>
  );
}
