/**
 * AchievementsPanel - 成就系统面板
 * 重新设计的现代化界面，展示成就进度和奖励
 */
import { useEffect, useState } from "react";
import { Trophy, Star, Lock, Unlock, Filter, Search, Sparkles, Crown, Target, Flame } from "lucide-react";
import { AnalysisPanel, AnalysisSection, EmptyState } from "./common/AnalysisPanel";

interface Achievement {
  id: string;
  name: string;
  description: string;
  category: string;
  rarity: string;
  icon: string;
  target_value: number;
  current_value: number;
  unlocked: boolean;
  unlock_time: string | null;
  unlock_turn: number | null;
  hidden: boolean;
}

interface AchievementStats {
  total: number;
  unlocked: number;
  percentage: number;
  by_category: Record<string, { total: number; unlocked: number }>;
  by_rarity: Record<string, { total: number; unlocked: number }>;
}

interface Props {
  onClose: () => void;
}

const CATEGORY_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  species: { label: "物种", icon: "🧬", color: "#3b82f6" },
  ecosystem: { label: "生态系统", icon: "🌿", color: "#22c55e" },
  survival: { label: "生存", icon: "⏳", color: "#f59e0b" },
  disaster: { label: "灾难", icon: "☄️", color: "#ef4444" },
  special: { label: "特殊", icon: "✨", color: "#a855f7" },
};

const RARITY_CONFIG: Record<string, { label: string; color: string; glow: string }> = {
  common: { label: "普通", color: "#94a3b8", glow: "rgba(148, 163, 184, 0.3)" },
  uncommon: { label: "罕见", color: "#22c55e", glow: "rgba(34, 197, 94, 0.3)" },
  rare: { label: "稀有", color: "#3b82f6", glow: "rgba(59, 130, 246, 0.3)" },
  epic: { label: "史诗", color: "#a855f7", glow: "rgba(168, 85, 247, 0.4)" },
  legendary: { label: "传说", color: "#f59e0b", glow: "rgba(245, 158, 11, 0.5)" },
};

export function AchievementsPanel({ onClose }: Props) {
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [stats, setStats] = useState<AchievementStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unlocked" | "locked">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchAchievements();
  }, []);

  async function fetchAchievements() {
    try {
      const response = await fetch("/api/achievements");
      const data = await response.json();
      setAchievements(data.achievements || []);
      setStats(data.stats || null);
    } catch (error) {
      console.error("获取成就失败:", error);
    } finally {
      setLoading(false);
    }
  }

  const filteredAchievements = achievements.filter((a) => {
    if (a.hidden && !a.unlocked) return false;
    if (filter === "unlocked" && !a.unlocked) return false;
    if (filter === "locked" && a.unlocked) return false;
    if (categoryFilter !== "all" && a.category !== categoryFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return a.name.toLowerCase().includes(query) || a.description.toLowerCase().includes(query);
    }
    return true;
  });

  // 按分类分组
  const groupedAchievements: Record<string, Achievement[]> = {};
  for (const a of filteredAchievements) {
    if (!groupedAchievements[a.category]) {
      groupedAchievements[a.category] = [];
    }
    groupedAchievements[a.category].push(a);
  }

  return (
    <AnalysisPanel
      title="成就殿堂"
      icon={<Trophy size={20} />}
      accentColor="#f59e0b"
      onClose={onClose}
      size="large"
      showMaximize
    >
      <div className="achievements-content">
        {/* 统计概览 */}
        {stats && (
          <div className="stats-overview">
            {/* 主进度 */}
            <div className="main-progress">
              <div className="progress-ring-wrapper">
                <svg className="progress-ring" viewBox="0 0 120 120">
                  <defs>
                    <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#f59e0b" />
                      <stop offset="100%" stopColor="#fbbf24" />
                    </linearGradient>
                  </defs>
                  <circle
                    className="ring-bg"
                    cx="60"
                    cy="60"
                    r="52"
                    fill="none"
                    stroke="rgba(255,255,255,0.08)"
                    strokeWidth="8"
                  />
                  <circle
                    className="ring-progress"
                    cx="60"
                    cy="60"
                    r="52"
                    fill="none"
                    stroke="url(#progressGradient)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${stats.percentage * 3.27} 327`}
                    transform="rotate(-90 60 60)"
                  />
                </svg>
                <div className="progress-text">
                  <span className="progress-value">{stats.unlocked}</span>
                  <span className="progress-total">/ {stats.total}</span>
                </div>
              </div>
              <div className="progress-info">
                <div className="progress-label">成就完成度</div>
                <div className="progress-percent">{stats.percentage}%</div>
              </div>
            </div>

            {/* 稀有度分布 */}
            <div className="rarity-breakdown">
              {Object.entries(stats.by_rarity).map(([rarity, data]) => {
                const config = RARITY_CONFIG[rarity];
                const percent = data.total > 0 ? (data.unlocked / data.total) * 100 : 0;
                return (
                  <div key={rarity} className="rarity-item">
                    <div className="rarity-header">
                      <span 
                        className="rarity-dot" 
                        style={{ backgroundColor: config.color, boxShadow: `0 0 8px ${config.glow}` }}
                      />
                      <span className="rarity-label">{config.label}</span>
                      <span className="rarity-count">{data.unlocked}/{data.total}</span>
                    </div>
                    <div className="rarity-bar">
                      <div 
                        className="rarity-fill" 
                        style={{ 
                          width: `${percent}%`,
                          background: `linear-gradient(90deg, ${config.color}, ${config.color}80)`
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 筛选器 */}
        <div className="filters-bar">
          <div className="search-box">
            <Search size={16} />
            <input
              type="text"
              placeholder="搜索成就..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="filter-chips">
            <button 
              className={`filter-chip ${filter === "all" ? "active" : ""}`}
              onClick={() => setFilter("all")}
            >
              全部
            </button>
            <button 
              className={`filter-chip ${filter === "unlocked" ? "active" : ""}`}
              onClick={() => setFilter("unlocked")}
            >
              <Unlock size={14} />
              已解锁
            </button>
            <button 
              className={`filter-chip ${filter === "locked" ? "active" : ""}`}
              onClick={() => setFilter("locked")}
            >
              <Lock size={14} />
              未解锁
            </button>
          </div>

          <div className="category-filter">
            <Filter size={14} />
            <select 
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="all">所有分类</option>
              {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
                <option key={key} value={key}>{config.icon} {config.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 成就列表 */}
        <div className="achievements-list">
          {loading ? (
            <div className="loading-state">
              <div className="loading-spinner" />
              <span>加载成就中...</span>
            </div>
          ) : Object.keys(groupedAchievements).length === 0 ? (
            <EmptyState
              icon="🏆"
              title="暂无符合条件的成就"
              description="尝试调整筛选条件查看更多成就"
            />
          ) : (
            Object.entries(groupedAchievements).map(([category, achs]) => {
              const categoryConfig = CATEGORY_CONFIG[category] || { label: category, icon: "📋", color: "#64748b" };
              return (
                <div key={category} className="achievement-category">
                  <div 
                    className="category-header"
                    style={{ '--category-color': categoryConfig.color } as React.CSSProperties}
                  >
                    <span className="category-icon">{categoryConfig.icon}</span>
                    <span className="category-name">{categoryConfig.label}</span>
                    <span className="category-count">{achs.length}</span>
                  </div>
                  <div className="achievements-grid">
                    {achs.map((achievement) => (
                      <AchievementCard key={achievement.id} achievement={achievement} />
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      <style>{`
        .achievements-content {
          display: flex;
          flex-direction: column;
          height: 100%;
          padding: 24px;
          gap: 24px;
        }

        /* 统计概览 */
        .stats-overview {
          display: flex;
          gap: 32px;
          padding: 28px;
          background: linear-gradient(135deg, 
            rgba(245, 158, 11, 0.08) 0%, 
            rgba(245, 158, 11, 0.02) 100%
          );
          border: 1px solid rgba(245, 158, 11, 0.15);
          border-radius: 20px;
          flex-shrink: 0;
        }

        .main-progress {
          display: flex;
          align-items: center;
          gap: 24px;
        }

        .progress-ring-wrapper {
          position: relative;
          width: 120px;
          height: 120px;
        }

        .progress-ring {
          width: 100%;
          height: 100%;
          transform: rotate(-90deg);
        }

        .ring-progress {
          transition: stroke-dasharray 0.8s ease;
        }

        .progress-text {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .progress-value {
          font-size: 1.8rem;
          font-weight: 700;
          color: #f59e0b;
          font-family: var(--font-mono, monospace);
          line-height: 1;
        }

        .progress-total {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .progress-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .progress-label {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .progress-percent {
          font-size: 2rem;
          font-weight: 700;
          color: #fbbf24;
          font-family: var(--font-mono, monospace);
        }

        .rarity-breakdown {
          flex: 1;
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 16px;
          align-content: center;
        }

        .rarity-item {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .rarity-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .rarity-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }

        .rarity-label {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .rarity-count {
          margin-left: auto;
          font-size: 0.85rem;
          font-family: var(--font-mono, monospace);
          color: rgba(255, 255, 255, 0.5);
        }

        .rarity-bar {
          height: 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 3px;
          overflow: hidden;
        }

        .rarity-fill {
          height: 100%;
          border-radius: 3px;
          transition: width 0.5s ease;
        }

        /* 筛选器 */
        .filters-bar {
          display: flex;
          align-items: center;
          gap: 16px;
          flex-wrap: wrap;
          flex-shrink: 0;
        }

        .search-box {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 16px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          min-width: 200px;
        }

        .search-box svg {
          color: rgba(255, 255, 255, 0.4);
        }

        .search-box input {
          flex: 1;
          background: none;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 0.9rem;
        }

        .search-box input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .filter-chips {
          display: flex;
          gap: 8px;
        }

        .filter-chip {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-chip:hover {
          background: rgba(255, 255, 255, 0.06);
          color: rgba(255, 255, 255, 0.9);
        }

        .filter-chip.active {
          background: rgba(245, 158, 11, 0.15);
          border-color: rgba(245, 158, 11, 0.3);
          color: #fbbf24;
        }

        .category-filter {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-left: auto;
        }

        .category-filter svg {
          color: rgba(255, 255, 255, 0.4);
        }

        .category-filter select {
          padding: 8px 14px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.85rem;
          cursor: pointer;
        }

        /* 成就列表 */
        .achievements-list {
          flex: 1;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 28px;
        }

        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
          padding: 60px 20px;
          color: rgba(255, 255, 255, 0.5);
        }

        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid rgba(255, 255, 255, 0.1);
          border-top-color: #f59e0b;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* 成就分类 */
        .achievement-category {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .category-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .category-icon {
          font-size: 1.25rem;
        }

        .category-name {
          font-size: 1.05rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.85);
        }

        .category-count {
          padding: 2px 10px;
          background: color-mix(in srgb, var(--category-color) 15%, transparent);
          border-radius: 10px;
          font-size: 0.8rem;
          color: var(--category-color);
        }

        .achievements-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 14px;
        }
      `}</style>
    </AnalysisPanel>
  );
}

/**
 * AchievementCard - 成就卡片组件
 */
function AchievementCard({ achievement }: { achievement: Achievement }) {
  const rarityConfig = RARITY_CONFIG[achievement.rarity] || RARITY_CONFIG.common;
  const progress = achievement.target_value > 1 
    ? Math.min(100, (achievement.current_value / achievement.target_value) * 100)
    : (achievement.unlocked ? 100 : 0);

  return (
    <div 
      className={`achievement-card ${achievement.unlocked ? 'unlocked' : 'locked'}`}
      style={{ 
        '--rarity-color': rarityConfig.color,
        '--rarity-glow': rarityConfig.glow
      } as React.CSSProperties}
    >
      {/* 稀有度指示器 */}
      <div className="rarity-indicator" />
      
      <div className="achievement-icon-wrapper">
        <span className="achievement-icon">{achievement.icon}</span>
        {achievement.unlocked && (
          <div className="unlock-badge">
            <Unlock size={10} />
          </div>
        )}
      </div>
      
      <div className="achievement-info">
        <div className="achievement-header">
          <span className="achievement-name">{achievement.name}</span>
          <span className="achievement-rarity">{rarityConfig.label}</span>
        </div>
        <p className="achievement-desc">{achievement.description}</p>
        
        {/* 进度条 */}
        {!achievement.unlocked && achievement.target_value > 1 && (
          <div className="achievement-progress">
            <div className="progress-bar">
              <div 
                className="progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="progress-text">
              {achievement.current_value} / {achievement.target_value}
            </span>
          </div>
        )}
        
        {/* 解锁信息 */}
        {achievement.unlocked && achievement.unlock_turn !== null && (
          <div className="unlock-info">
            <Sparkles size={12} />
            <span>回合 {achievement.unlock_turn} 解锁</span>
          </div>
        )}
      </div>

      <style>{`
        .achievement-card {
          display: flex;
          gap: 16px;
          padding: 18px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          position: relative;
          overflow: hidden;
          transition: all 0.25s ease;
        }

        .achievement-card:hover {
          background: rgba(255, 255, 255, 0.04);
          transform: translateY(-2px);
        }

        .achievement-card.unlocked {
          border-color: color-mix(in srgb, var(--rarity-color) 40%, transparent);
          box-shadow: 0 0 25px var(--rarity-glow);
        }

        .achievement-card.locked {
          opacity: 0.7;
        }

        .achievement-card.locked .achievement-icon-wrapper {
          filter: grayscale(0.8);
        }

        /* 稀有度指示器 */
        .rarity-indicator {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 3px;
          background: linear-gradient(90deg, 
            var(--rarity-color) 0%, 
            transparent 100%
          );
          opacity: 0.6;
        }

        .achievement-card.unlocked .rarity-indicator {
          opacity: 1;
        }

        .achievement-icon-wrapper {
          position: relative;
          width: 56px;
          height: 56px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, 
            rgba(255, 255, 255, 0.05) 0%, 
            rgba(255, 255, 255, 0.02) 100%
          );
          border-radius: 14px;
          flex-shrink: 0;
        }

        .achievement-card.unlocked .achievement-icon-wrapper {
          background: linear-gradient(135deg, 
            color-mix(in srgb, var(--rarity-color) 15%, transparent) 0%,
            color-mix(in srgb, var(--rarity-color) 5%, transparent) 100%
          );
          border: 1px solid color-mix(in srgb, var(--rarity-color) 25%, transparent);
        }

        .achievement-icon {
          font-size: 1.75rem;
        }

        .unlock-badge {
          position: absolute;
          bottom: -4px;
          right: -4px;
          width: 20px;
          height: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--rarity-color);
          border-radius: 50%;
          color: white;
        }

        .achievement-info {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .achievement-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 12px;
        }

        .achievement-name {
          font-weight: 600;
          font-size: 0.95rem;
          color: rgba(255, 255, 255, 0.9);
        }

        .achievement-rarity {
          font-size: 0.7rem;
          font-weight: 600;
          padding: 3px 8px;
          background: color-mix(in srgb, var(--rarity-color) 15%, transparent);
          border-radius: 6px;
          color: var(--rarity-color);
          white-space: nowrap;
        }

        .achievement-desc {
          margin: 0;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.55);
          line-height: 1.45;
        }

        .achievement-progress {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 8px;
        }

        .progress-bar {
          flex: 1;
          height: 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 3px;
          overflow: hidden;
        }

        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--rarity-color), color-mix(in srgb, var(--rarity-color) 70%, white));
          border-radius: 3px;
          transition: width 0.3s ease;
        }

        .progress-text {
          font-size: 0.75rem;
          font-family: var(--font-mono, monospace);
          color: rgba(255, 255, 255, 0.4);
          white-space: nowrap;
        }

        .unlock-info {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
          font-size: 0.75rem;
          color: var(--rarity-color);
        }
      `}</style>
    </div>
  );
}
