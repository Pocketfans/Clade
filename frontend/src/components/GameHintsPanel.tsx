/**
 * GameHintsPanel - 智能游戏提示面板
 * 重新设计的现代化浮动面板，提供实时的游戏建议
 */
import { useEffect, useState, useCallback } from "react";
import { 
  Lightbulb, RefreshCw, ChevronDown, ChevronUp, X, AlertTriangle, 
  TrendingUp, Zap, Target, Leaf, Skull, GitBranch, Minimize2, Maximize2 
} from "lucide-react";

interface GameHint {
  type: "warning" | "opportunity" | "evolution" | "competition" | "ecosystem";
  priority: "low" | "medium" | "high" | "critical";
  title: string;
  message: string;
  icon: string;
  related_species: string[];
  suggested_actions: string[];
}

interface Props {
  onSelectSpecies?: (code: string) => void;
  refreshTrigger?: number;
}

const PRIORITY_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: "#ef4444", bg: "rgba(239, 68, 68, 0.12)", label: "紧急" },
  high: { color: "#f59e0b", bg: "rgba(245, 158, 11, 0.12)", label: "高" },
  medium: { color: "#3b82f6", bg: "rgba(59, 130, 246, 0.12)", label: "中" },
  low: { color: "#6b7280", bg: "rgba(107, 114, 128, 0.12)", label: "低" },
};

const TYPE_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  warning: { icon: <AlertTriangle size={14} />, label: "警告", color: "#ef4444" },
  opportunity: { icon: <TrendingUp size={14} />, label: "机会", color: "#22c55e" },
  evolution: { icon: <GitBranch size={14} />, label: "演化", color: "#a855f7" },
  competition: { icon: <Target size={14} />, label: "竞争", color: "#f59e0b" },
  ecosystem: { icon: <Leaf size={14} />, label: "生态", color: "#10b981" },
};

export function GameHintsPanel({ onSelectSpecies, refreshTrigger }: Props) {
  const [hints, setHints] = useState<GameHint[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [expandedHint, setExpandedHint] = useState<number | null>(null);

  const fetchHints = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/hints");
      const data = await response.json();
      setHints(data.hints || []);
    } catch (error) {
      console.error("获取提示失败:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHints();
  }, [fetchHints, refreshTrigger]);

  // 自动刷新
  useEffect(() => {
    const interval = setInterval(fetchHints, 30000);
    return () => clearInterval(interval);
  }, [fetchHints]);

  // 获取优先级最高的提示
  const criticalCount = hints.filter(h => h.priority === 'critical').length;
  const highCount = hints.filter(h => h.priority === 'high').length;

  if (minimized) {
    return (
      <div 
        className="hints-minimized"
        onClick={() => setMinimized(false)}
      >
        <div className="minimized-icon">
          <Lightbulb size={18} />
        </div>
        {hints.length > 0 && (
          <div className="minimized-badge">
            {criticalCount > 0 ? (
              <span className="critical-badge">{criticalCount}</span>
            ) : highCount > 0 ? (
              <span className="high-badge">{highCount}</span>
            ) : (
              <span className="normal-badge">{hints.length}</span>
            )}
          </div>
        )}

        <style>{`
          .hints-minimized {
            position: fixed;
            bottom: 90px;
            right: 20px;
            width: 52px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, 
              rgba(15, 23, 42, 0.95) 0%, 
              rgba(10, 15, 25, 0.98) 100%
            );
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            cursor: pointer;
            z-index: 100;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
          }

          .hints-minimized:hover {
            transform: scale(1.08);
            border-color: rgba(59, 130, 246, 0.4);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4), 0 0 20px rgba(59, 130, 246, 0.2);
          }

          .minimized-icon {
            color: #60a5fa;
          }

          .minimized-badge {
            position: absolute;
            top: -6px;
            right: -6px;
          }

          .critical-badge, .high-badge, .normal-badge {
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 20px;
            height: 20px;
            padding: 0 6px;
            border-radius: 10px;
            font-size: 0.7rem;
            font-weight: 700;
          }

          .critical-badge {
            background: #ef4444;
            color: white;
            animation: pulse-critical 2s ease-in-out infinite;
          }

          .high-badge {
            background: #f59e0b;
            color: white;
          }

          .normal-badge {
            background: rgba(59, 130, 246, 0.8);
            color: white;
          }

          @keyframes pulse-critical {
            0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
            50% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className={`hints-panel ${collapsed ? 'collapsed' : ''}`}>
      {/* 头部 */}
      <div className="hints-header">
        <div className="header-left">
          <Lightbulb size={18} />
          <span className="header-title">智能提示</span>
          {hints.length > 0 && (
            <span className="hints-count">{hints.length}</span>
          )}
        </div>
        <div className="header-actions">
          <button 
            className="header-btn refresh-btn" 
            onClick={fetchHints}
            title="刷新提示"
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          </button>
          <button 
            className="header-btn" 
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? "展开" : "收起"}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button 
            className="header-btn" 
            onClick={() => setMinimized(true)}
            title="最小化"
          >
            <Minimize2 size={14} />
          </button>
        </div>
      </div>

      {/* 内容 */}
      {!collapsed && (
        <div className="hints-body">
          {loading && hints.length === 0 ? (
            <div className="hints-loading">
              <div className="loading-spinner" />
              <span>分析生态系统...</span>
            </div>
          ) : hints.length === 0 ? (
            <div className="hints-empty">
              <div className="empty-icon">✨</div>
              <span className="empty-title">生态系统运行良好</span>
              <span className="empty-desc">暂无需要注意的事项</span>
            </div>
          ) : (
            <div className="hints-list">
              {hints.map((hint, index) => (
                <HintCard
                  key={`${hint.title}-${index}`}
                  hint={hint}
                  index={index}
                  expanded={expandedHint === index}
                  onToggle={() => setExpandedHint(expandedHint === index ? null : index)}
                  onSelectSpecies={onSelectSpecies}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <style>{`
        .hints-panel {
          position: fixed;
          bottom: 90px;
          right: 20px;
          width: 360px;
          max-height: 480px;
          display: flex;
          flex-direction: column;
          background: linear-gradient(165deg, 
            rgba(15, 23, 42, 0.96) 0%, 
            rgba(10, 15, 25, 0.98) 100%
          );
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 20px;
          overflow: hidden;
          z-index: 100;
          box-shadow: 
            0 20px 60px rgba(0, 0, 0, 0.4),
            0 0 1px rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(16px);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .hints-panel.collapsed {
          max-height: 60px;
        }

        /* 头部 */
        .hints-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 14px 16px;
          background: linear-gradient(180deg, 
            rgba(255, 255, 255, 0.03) 0%, 
            transparent 100%
          );
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          flex-shrink: 0;
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 10px;
          color: #60a5fa;
        }

        .header-title {
          font-size: 0.95rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
        }

        .hints-count {
          padding: 2px 8px;
          background: rgba(59, 130, 246, 0.15);
          border-radius: 10px;
          font-size: 0.75rem;
          font-weight: 600;
          color: #60a5fa;
        }

        .header-actions {
          display: flex;
          gap: 6px;
        }

        .header-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 28px;
          height: 28px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          transition: all 0.2s;
        }

        .header-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.9);
        }

        .refresh-btn svg.spinning {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* 内容区 */
        .hints-body {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
        }

        .hints-body::-webkit-scrollbar {
          width: 6px;
        }

        .hints-body::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }

        .hints-body::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
        }

        .hints-loading, .hints-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px 20px;
          text-align: center;
          color: rgba(255, 255, 255, 0.4);
        }

        .loading-spinner {
          width: 28px;
          height: 28px;
          border: 2px solid rgba(255, 255, 255, 0.1);
          border-top-color: #60a5fa;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: 12px;
        }

        .empty-icon {
          font-size: 2.5rem;
          margin-bottom: 12px;
        }

        .empty-title {
          font-size: 0.95rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 4px;
        }

        .empty-desc {
          font-size: 0.8rem;
        }

        .hints-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
      `}</style>
    </div>
  );
}

/**
 * HintCard - 提示卡片组件
 */
function HintCard({ 
  hint, 
  index,
  expanded, 
  onToggle,
  onSelectSpecies 
}: { 
  hint: GameHint; 
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onSelectSpecies?: (code: string) => void;
}) {
  const priorityConfig = PRIORITY_CONFIG[hint.priority];
  const typeConfig = TYPE_CONFIG[hint.type];

  return (
    <div 
      className={`hint-card priority-${hint.priority} ${expanded ? 'expanded' : ''}`}
      style={{
        '--priority-color': priorityConfig.color,
        '--priority-bg': priorityConfig.bg,
        '--type-color': typeConfig.color,
        animationDelay: `${index * 50}ms`
      } as React.CSSProperties}
    >
      <div className="hint-main" onClick={onToggle}>
        <div className="hint-icon-wrapper">
          <span className="hint-emoji">{hint.icon}</span>
        </div>
        
        <div className="hint-content">
          <div className="hint-header">
            <span className="hint-title">{hint.title}</span>
            <div className="hint-badges">
              <span className="type-badge">
                {typeConfig.icon}
                {typeConfig.label}
              </span>
            </div>
          </div>
          <p className="hint-message">{hint.message}</p>
        </div>
        
        <button className="expand-btn">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {expanded && (
        <div className="hint-details">
          {hint.related_species.length > 0 && (
            <div className="detail-section">
              <span className="detail-label">相关物种</span>
              <div className="species-tags">
                {hint.related_species.map((code) => (
                  <button
                    key={code}
                    className="species-tag"
                    onClick={() => onSelectSpecies?.(code)}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>
          )}
          
          {hint.suggested_actions.length > 0 && (
            <div className="detail-section">
              <span className="detail-label">建议操作</span>
              <ul className="actions-list">
                {hint.suggested_actions.map((action, i) => (
                  <li key={i}>
                    <Zap size={12} />
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <style>{`
        .hint-card {
          background: var(--priority-bg);
          border: 1px solid color-mix(in srgb, var(--priority-color) 25%, transparent);
          border-left: 3px solid var(--priority-color);
          border-radius: 14px;
          overflow: hidden;
          transition: all 0.25s ease;
          animation: slideIn 0.3s ease forwards;
          opacity: 0;
        }

        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        .hint-card:hover {
          border-color: color-mix(in srgb, var(--priority-color) 40%, transparent);
        }

        .hint-card.priority-critical {
          animation: slideIn 0.3s ease forwards, pulse-border 2s ease-in-out infinite 0.3s;
        }

        @keyframes pulse-border {
          0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--priority-color) 40%, transparent); }
          50% { box-shadow: 0 0 10px 2px color-mix(in srgb, var(--priority-color) 20%, transparent); }
        }

        .hint-main {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 14px;
          cursor: pointer;
        }

        .hint-icon-wrapper {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          flex-shrink: 0;
        }

        .hint-emoji {
          font-size: 1.25rem;
        }

        .hint-content {
          flex: 1;
          min-width: 0;
        }

        .hint-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 10px;
          margin-bottom: 6px;
        }

        .hint-title {
          font-weight: 600;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.9);
          line-height: 1.3;
        }

        .hint-badges {
          display: flex;
          gap: 6px;
          flex-shrink: 0;
        }

        .type-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          background: color-mix(in srgb, var(--type-color) 15%, transparent);
          border-radius: 6px;
          font-size: 0.7rem;
          font-weight: 500;
          color: var(--type-color);
        }

        .hint-message {
          margin: 0;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          line-height: 1.5;
        }

        .expand-btn {
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: none;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.4);
          cursor: pointer;
          flex-shrink: 0;
          transition: all 0.2s;
        }

        .expand-btn:hover {
          background: rgba(255, 255, 255, 0.1);
          color: rgba(255, 255, 255, 0.8);
        }

        /* 展开详情 */
        .hint-details {
          padding: 0 14px 14px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          border-top: 1px dashed rgba(255, 255, 255, 0.06);
          margin-top: 0;
          padding-top: 12px;
        }

        .detail-section {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .detail-label {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: rgba(255, 255, 255, 0.4);
        }

        .species-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .species-tag {
          padding: 5px 10px;
          background: rgba(59, 130, 246, 0.12);
          border: 1px solid rgba(59, 130, 246, 0.25);
          border-radius: 8px;
          font-size: 0.75rem;
          font-weight: 600;
          color: #60a5fa;
          cursor: pointer;
          transition: all 0.2s;
        }

        .species-tag:hover {
          background: rgba(59, 130, 246, 0.25);
          transform: translateY(-1px);
        }

        .actions-list {
          margin: 0;
          padding: 0;
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .actions-list li {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.7);
          line-height: 1.4;
        }

        .actions-list li svg {
          margin-top: 3px;
          color: var(--priority-color);
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
}

/**
 * AchievementNotification - 成就解锁通知组件
 */
export function AchievementNotification({ 
  achievement, 
  onClose 
}: { 
  achievement: { name: string; icon: string; description: string; rarity: string };
  onClose: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const rarityColors: Record<string, { color: string; glow: string }> = {
    common: { color: "#94a3b8", glow: "rgba(148, 163, 184, 0.3)" },
    uncommon: { color: "#22c55e", glow: "rgba(34, 197, 94, 0.4)" },
    rare: { color: "#3b82f6", glow: "rgba(59, 130, 246, 0.4)" },
    epic: { color: "#a855f7", glow: "rgba(168, 85, 247, 0.5)" },
    legendary: { color: "#f59e0b", glow: "rgba(245, 158, 11, 0.5)" },
  };

  const rarityConfig = rarityColors[achievement.rarity] || rarityColors.common;

  return (
    <div 
      className="achievement-notification"
      style={{ 
        '--rarity-color': rarityConfig.color,
        '--rarity-glow': rarityConfig.glow
      } as React.CSSProperties}
    >
      <div className="notif-glow" />
      <div className="notif-content">
        <div className="notif-icon">{achievement.icon}</div>
        <div className="notif-info">
          <div className="notif-header">🏆 成就解锁</div>
          <div className="notif-name">{achievement.name}</div>
          <div className="notif-desc">{achievement.description}</div>
        </div>
        <button className="notif-close" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <style>{`
        .achievement-notification {
          position: fixed;
          top: 80px;
          right: 20px;
          width: 380px;
          background: linear-gradient(135deg, 
            rgba(15, 23, 42, 0.98) 0%, 
            rgba(10, 15, 25, 0.99) 100%
          );
          border: 2px solid var(--rarity-color);
          border-radius: 20px;
          overflow: hidden;
          z-index: 9999;
          animation: notifSlideIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
          box-shadow: 
            0 20px 60px rgba(0, 0, 0, 0.5),
            0 0 40px var(--rarity-glow);
        }

        @keyframes notifSlideIn {
          from {
            transform: translateX(100%) scale(0.8);
            opacity: 0;
          }
          to {
            transform: translateX(0) scale(1);
            opacity: 1;
          }
        }

        .notif-glow {
          position: absolute;
          inset: -50%;
          background: conic-gradient(
            from 0deg,
            transparent,
            var(--rarity-glow),
            transparent,
            var(--rarity-glow),
            transparent
          );
          animation: rotateGlow 4s linear infinite;
        }

        @keyframes rotateGlow {
          to { transform: rotate(360deg); }
        }

        .notif-content {
          position: relative;
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 20px;
          background: linear-gradient(135deg, 
            rgba(15, 23, 42, 0.98) 0%, 
            rgba(10, 15, 25, 0.99) 100%
          );
          border-radius: 18px;
        }

        .notif-icon {
          font-size: 3rem;
          animation: iconBounce 0.6s ease-out;
        }

        @keyframes iconBounce {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.2); }
        }

        .notif-info {
          flex: 1;
        }

        .notif-header {
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--rarity-color);
          margin-bottom: 4px;
        }

        .notif-name {
          font-size: 1.15rem;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.95);
          margin-bottom: 4px;
        }

        .notif-desc {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          line-height: 1.4;
        }

        .notif-close {
          position: absolute;
          top: 12px;
          right: 12px;
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: none;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.4);
          cursor: pointer;
          transition: all 0.2s;
        }

        .notif-close:hover {
          background: rgba(255, 255, 255, 0.1);
          color: rgba(255, 255, 255, 0.9);
        }
      `}</style>
    </div>
  );
}
