import React, { useMemo, useState, useEffect } from "react";
import { SpeciesSnapshot } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  speciesList: SpeciesSnapshot[];
  onClose: () => void;
  onSelectSpecies: (id: string) => void;
  selectedSpeciesId?: string | null; // 新增：当前选中的物种ID
}

type SortField = "population" | "population_share" | "death_rate" | "latin_name" | "status" | "trophic_level";
type SortOrder = "asc" | "desc";

// 生态角色配置
const roleConfig: Record<string, { color: string; icon: string; label: string }> = {
  producer: { color: "#10b981", icon: "🌿", label: "生产者" },
  herbivore: { color: "#fbbf24", icon: "🦌", label: "食草" },
  carnivore: { color: "#f43f5e", icon: "🦁", label: "食肉" },
  omnivore: { color: "#f97316", icon: "🐻", label: "杂食" },
  mixotroph: { color: "#22d3ee", icon: "🔬", label: "混养" },
  decomposer: { color: "#a78bfa", icon: "🍄", label: "分解者" },
  scavenger: { color: "#64748b", icon: "🦅", label: "食腐" },
  unknown: { color: "#3b82f6", icon: "🧬", label: "未知" }
};

export function SpeciesLedger({ speciesList, onClose, onSelectSpecies, selectedSpeciesId }: Props) {
  const [sortField, setSortField] = useState<SortField>("trophic_level");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [filterText, setFilterText] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);
  
  // 内部追踪当前选中的物种（用于高亮显示）
  const [internalSelected, setInternalSelected] = useState<string | null>(selectedSpeciesId || null);
  
  // 同步外部选中状态
  useEffect(() => {
    if (selectedSpeciesId !== undefined) {
      setInternalSelected(selectedSpeciesId);
    }
  }, [selectedSpeciesId]);
  
  // 处理物种选择 - 不关闭图鉴
  const handleSpeciesClick = (code: string) => {
    setInternalSelected(code);
    onSelectSpecies(code);
  };

  const sortedAndFilteredList = useMemo(() => {
    let list = [...speciesList];

    if (filterText) {
      const lower = filterText.toLowerCase();
      list = list.filter(
        (s) =>
          s.latin_name.toLowerCase().includes(lower) ||
          s.common_name.toLowerCase().includes(lower) ||
          s.lineage_code.toLowerCase().includes(lower)
      );
    }

    if (statusFilter !== "all") {
      list = list.filter((s) => s.status === statusFilter);
    }

    list.sort((a, b) => {
      let valA: any = a[sortField];
      let valB: any = b[sortField];

      if (valA < valB) return sortOrder === "asc" ? -1 : 1;
      if (valA > valB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });

    return list;
  }, [speciesList, sortField, sortOrder, filterText, statusFilter]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  // 统计数据
  const stats = useMemo(() => {
    const alive = speciesList.filter(s => s.status === "alive").length;
    const extinct = speciesList.filter(s => s.status === "extinct").length;
    const totalPop = speciesList.reduce((sum, s) => sum + s.population, 0);
    return { alive, extinct, totalPop };
  }, [speciesList]);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span className="sort-icon inactive">⇅</span>;
    return <span className="sort-icon active">{sortOrder === "asc" ? "↑" : "↓"}</span>;
  };

  return (
    <GamePanel
      title={
        <div className="ledger-title">
          <div className="title-main">
            <span className="title-icon">📊</span>
            <span>物种统计表</span>
            <span className="title-hint">💡 点击物种在地图上查看分布</span>
          </div>
          <div className="title-stats">
            <span className="stat alive">
              <span className="dot" />
              {stats.alive} 存活
            </span>
            <span className="stat extinct">
              <span className="dot" />
              {stats.extinct} 灭绝
            </span>
            <span className="stat total">
              共 {formatNumber(stats.totalPop)} kg
            </span>
          </div>
        </div>
      }
      onClose={onClose}
      variant="modal"
      width="1100px"
      height="85vh"
    >
      <div className="ledger-container">
        {/* 工具栏 */}
        <div className="ledger-toolbar">
          <div className="search-box">
            <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <input
              type="text"
              placeholder="搜索物种名称、学名或代号..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
            />
            {filterText && (
              <button className="clear-btn" onClick={() => setFilterText("")}>×</button>
            )}
          </div>
          
          <div className="filter-group">
            <button 
              className={`filter-btn ${statusFilter === "all" ? "active" : ""}`}
              onClick={() => setStatusFilter("all")}
            >
              全部
            </button>
            <button 
              className={`filter-btn ${statusFilter === "alive" ? "active" : ""}`}
              onClick={() => setStatusFilter("alive")}
            >
              <span className="dot alive" />
              存活
            </button>
            <button 
              className={`filter-btn ${statusFilter === "extinct" ? "active" : ""}`}
              onClick={() => setStatusFilter("extinct")}
            >
              <span className="dot extinct" />
              灭绝
            </button>
          </div>

          <div className="result-count">
            显示 <strong>{sortedAndFilteredList.length}</strong> / {speciesList.length} 条
          </div>
        </div>

        {/* 表头 */}
        <div className="ledger-header">
          <div className="col col-code" onClick={() => handleSort("latin_name")}>
            代号 <SortIcon field="latin_name" />
          </div>
          <div className="col col-name" onClick={() => handleSort("latin_name")}>
            物种名称 <SortIcon field="latin_name" />
          </div>
          <div className="col col-role">生态角色</div>
          <div className="col col-pop" onClick={() => handleSort("population")}>
            生物量 <SortIcon field="population" />
          </div>
          <div className="col col-share" onClick={() => handleSort("population_share")}>
            生态占比 <SortIcon field="population_share" />
          </div>
          <div className="col col-death" onClick={() => handleSort("death_rate")}>
            死亡率 <SortIcon field="death_rate" />
          </div>
          <div className="col col-tier" onClick={() => handleSort("trophic_level")}>
            营养级 <SortIcon field="trophic_level" />
          </div>
          <div className="col col-status" onClick={() => handleSort("status")}>
            状态 <SortIcon field="status" />
          </div>
        </div>

        {/* 表体 */}
        <div className="ledger-body">
          {sortedAndFilteredList.map((species, index) => {
            const role = roleConfig[species.ecological_role?.toLowerCase()] || roleConfig.unknown;
            const isExtinct = species.status === "extinct";
            const isHovered = hoveredRow === species.lineage_code;
            const isSelected = internalSelected === species.lineage_code;
            
            return (
              <div
                key={species.lineage_code}
                className={`ledger-row ${isExtinct ? "extinct" : ""} ${isHovered ? "hovered" : ""} ${isSelected ? "selected" : ""}`}
                onClick={() => handleSpeciesClick(species.lineage_code)}
                onMouseEnter={() => setHoveredRow(species.lineage_code)}
                onMouseLeave={() => setHoveredRow(null)}
                style={{ 
                  animationDelay: `${index * 20}ms`,
                  borderLeftColor: isSelected ? role.color : (isHovered ? `${role.color}80` : "transparent"),
                  background: isSelected ? `${role.color}15` : undefined
                }}
              >
                <div className="col col-code">
                  <span className="code-text">{species.lineage_code}</span>
                </div>
                
                <div className="col col-name">
                  <div className="name-common">{species.common_name}</div>
                  <div className="name-latin">{species.latin_name}</div>
                </div>
                
                <div className="col col-role">
                  <div className="role-badge" style={{ 
                    background: `${role.color}15`,
                    borderColor: `${role.color}40`
                  }}>
                    <span className="role-icon">{role.icon}</span>
                    <span className="role-label" style={{ color: role.color }}>{role.label}</span>
                  </div>
                </div>
                
                <div className="col col-pop">
                  <div className="pop-value">{formatNumber(species.population)}</div>
                  <div className="pop-bar">
                    <div 
                      className="pop-fill" 
                      style={{ 
                        width: `${Math.min(species.population_share * 100 * 3, 100)}%`,
                        background: role.color
                      }} 
                    />
                  </div>
                </div>
                
                <div className="col col-share">
                  <span className="share-value">{(species.population_share * 100).toFixed(1)}%</span>
                </div>
                
                <div className="col col-death">
                  <span className={`death-value ${getDeathRateClass(species.death_rate)}`}>
                    {(species.death_rate * 100).toFixed(1)}%
                  </span>
                </div>
                
                <div className="col col-tier">
                  <span className="tier-badge" style={{ color: getTrophicColor(species.tier) }}>
                    {species.tier || "—"}
                  </span>
                </div>
                
                <div className="col col-status">
                  <StatusBadge status={species.status} />
                </div>
              </div>
            );
          })}
          
          {sortedAndFilteredList.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <div className="empty-text">没有找到匹配的物种</div>
              <div className="empty-hint">尝试调整搜索条件或筛选器</div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .ledger-title {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
        }
        
        .title-main {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1.1rem;
          font-weight: 700;
        }
        
        .title-icon {
          font-size: 1.3rem;
        }
        
        .title-hint {
          font-size: 0.75rem;
          font-weight: 400;
          color: rgba(45, 212, 191, 0.7);
          margin-left: 12px;
          padding: 3px 10px;
          background: rgba(45, 212, 191, 0.1);
          border-radius: 12px;
          border: 1px solid rgba(45, 212, 191, 0.2);
        }
        
        .title-stats {
          display: flex;
          gap: 16px;
          font-size: 0.8rem;
          font-weight: 400;
        }
        
        .title-stats .stat {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 20px;
        }
        
        .title-stats .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }
        
        .title-stats .stat.alive .dot { background: #22c55e; }
        .title-stats .stat.extinct .dot { background: #ef4444; }
        .title-stats .stat.alive { color: #22c55e; }
        .title-stats .stat.extinct { color: #94a3b8; }
        .title-stats .stat.total { color: rgba(255, 255, 255, 0.6); }

        .ledger-container {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: linear-gradient(180deg, rgba(15, 23, 42, 0.5) 0%, rgba(15, 23, 42, 0.8) 100%);
        }

        .ledger-toolbar {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px 20px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .search-box {
          position: relative;
          flex: 1;
          max-width: 400px;
        }

        .search-box input {
          width: 100%;
          padding: 10px 36px 10px 40px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.9rem;
          transition: all 0.2s;
        }

        .search-box input:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
          background: rgba(15, 23, 42, 1);
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .search-box input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .search-icon {
          position: absolute;
          left: 12px;
          top: 50%;
          transform: translateY(-50%);
          color: rgba(255, 255, 255, 0.3);
        }

        .clear-btn {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          width: 20px;
          height: 20px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 50%;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          font-size: 14px;
          line-height: 1;
        }

        .clear-btn:hover {
          background: rgba(255, 255, 255, 0.2);
          color: white;
        }

        .filter-group {
          display: flex;
          gap: 4px;
          padding: 4px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 10px;
        }

        .filter-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          border: none;
          background: transparent;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }

        .filter-btn.active {
          background: rgba(59, 130, 246, 0.2);
          color: #60a5fa;
        }

        .filter-btn .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }

        .filter-btn .dot.alive { background: #22c55e; }
        .filter-btn .dot.extinct { background: #ef4444; }

        .result-count {
          margin-left: auto;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .result-count strong {
          color: #60a5fa;
        }

        .ledger-header {
          display: grid;
          grid-template-columns: 90px 2fr 120px 140px 100px 90px 80px 100px;
          padding: 14px 20px;
          background: rgba(0, 0, 0, 0.3);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: rgba(255, 255, 255, 0.5);
          user-select: none;
          position: sticky;
          top: 0;
          z-index: 10;
        }

        .ledger-header .col {
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: color 0.2s;
        }

        .ledger-header .col:hover {
          color: rgba(255, 255, 255, 0.8);
        }

        .sort-icon {
          font-size: 10px;
        }

        .sort-icon.inactive {
          opacity: 0.3;
        }

        .sort-icon.active {
          color: #60a5fa;
        }

        .ledger-body {
          flex: 1;
          overflow-y: auto;
        }

        .ledger-row {
          position: relative;
          display: grid;
          grid-template-columns: 90px 2fr 120px 140px 100px 90px 80px 100px;
          padding: 14px 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.03);
          border-left: 3px solid transparent;
          cursor: pointer;
          transition: all 0.15s ease;
          animation: fadeSlideIn 0.3s ease forwards;
          opacity: 0;
        }

        @keyframes fadeSlideIn {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        .ledger-row:hover,
        .ledger-row.hovered {
          background: rgba(59, 130, 246, 0.05);
        }
        
        .ledger-row.selected {
          background: rgba(45, 212, 191, 0.1);
          border-left-width: 4px;
          box-shadow: inset 0 0 20px rgba(45, 212, 191, 0.05);
        }
        
        .ledger-row.selected::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 4px;
          background: currentColor;
          opacity: 0.8;
        }
        
        .ledger-row.selected .name-common {
          color: #2dd4bf;
        }

        .ledger-row.extinct {
          opacity: 0.5;
        }

        .ledger-row.extinct:hover {
          opacity: 0.7;
        }

        .col {
          display: flex;
          align-items: center;
        }

        .col-code {
          justify-content: flex-start;
        }

        .code-text {
          font-family: 'JetBrains Mono', Monaco, Consolas, monospace;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
          padding: 4px 8px;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 4px;
        }

        .col-name {
          flex-direction: column;
          align-items: flex-start;
          gap: 2px;
        }

        .name-common {
          color: #f1f5f9;
          font-weight: 600;
          font-size: 0.95rem;
        }

        .name-latin {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
          font-style: italic;
        }

        .role-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 5px 10px;
          border: 1px solid;
          border-radius: 20px;
          font-size: 0.75rem;
        }

        .role-icon {
          font-size: 0.9rem;
        }

        .role-label {
          font-weight: 500;
        }

        .col-pop {
          flex-direction: column;
          align-items: flex-end;
          gap: 4px;
        }

        .pop-value {
          font-family: 'JetBrains Mono', Monaco, Consolas, monospace;
          font-weight: 600;
          font-size: 0.95rem;
          color: #f1f5f9;
        }

        .pop-bar {
          width: 80px;
          height: 3px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 2px;
          overflow: hidden;
        }

        .pop-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        .col-share {
          justify-content: flex-end;
        }

        .share-value {
          font-family: 'JetBrains Mono', Monaco, Consolas, monospace;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .col-death {
          justify-content: flex-end;
        }

        .death-value {
          font-family: 'JetBrains Mono', Monaco, Consolas, monospace;
          font-size: 0.9rem;
          padding: 3px 8px;
          border-radius: 4px;
        }

        .death-value.low {
          color: #22c55e;
          background: rgba(34, 197, 94, 0.1);
        }

        .death-value.medium {
          color: #fbbf24;
          background: rgba(251, 191, 36, 0.1);
        }

        .death-value.high {
          color: #f97316;
          background: rgba(249, 115, 22, 0.1);
        }

        .death-value.critical {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.15);
        }

        .col-tier {
          justify-content: center;
        }

        .tier-badge {
          font-family: 'JetBrains Mono', Monaco, Consolas, monospace;
          font-weight: 600;
          font-size: 0.85rem;
        }

        .col-status {
          justify-content: center;
        }

        .status-badge {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .status-badge.alive {
          background: rgba(34, 197, 94, 0.15);
          color: #22c55e;
        }

        .status-badge.extinct {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
        }

        .status-badge.endangered {
          background: rgba(251, 191, 36, 0.15);
          color: #fbbf24;
        }

        .status-badge .status-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: currentColor;
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 60px 20px;
          text-align: center;
        }

        .empty-icon {
          font-size: 3rem;
          margin-bottom: 16px;
          opacity: 0.5;
        }

        .empty-text {
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.6);
          margin-bottom: 8px;
        }

        .empty-hint {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.3);
        }

        /* 滚动条 */
        .ledger-body::-webkit-scrollbar {
          width: 8px;
        }

        .ledger-body::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }

        .ledger-body::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 4px;
        }

        .ledger-body::-webkit-scrollbar-thumb:hover {
          background: rgba(59, 130, 246, 0.5);
        }
      `}</style>
    </GamePanel>
  );
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString();
}

function getTrophicColor(tier?: string | null): string {
  if (!tier) return "#64748b";
  if (tier.startsWith("T1")) return "#22c55e";
  if (tier.startsWith("T2")) return "#fbbf24";
  if (tier.startsWith("T3")) return "#f97316";
  return "#ef4444";
}

function getDeathRateClass(rate: number): string {
  if (rate < 0.03) return "low";
  if (rate < 0.08) return "medium";
  if (rate < 0.15) return "high";
  return "critical";
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    alive: { label: "存活", className: "alive" },
    extinct: { label: "灭绝", className: "extinct" },
    endangered: { label: "濒危", className: "endangered" }
  };
  
  const { label, className } = config[status.toLowerCase()] || { label: status, className: "" };

  return (
    <span className={`status-badge ${className}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}
