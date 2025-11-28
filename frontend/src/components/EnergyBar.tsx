import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";

interface EnergyStatus {
  enabled: boolean;
  current: number;
  maximum: number;
  regen_per_turn: number;
  total_spent: number;
  total_regenerated: number;
  percentage: number;
}

interface Props {
  className?: string;
  onOpenHistory?: () => void;
}

export function EnergyBar({ className = "", onOpenHistory }: Props) {
  const [energy, setEnergy] = useState<EnergyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPos, setTooltipPos] = useState({ top: 0, left: 0 });
  const barRef = useRef<HTMLDivElement>(null);

  async function fetchEnergy() {
    try {
      const response = await fetch("/api/energy");
      const data = await response.json();
      setEnergy(data);
    } catch (e) {
      console.error("获取能量状态失败:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchEnergy();
    
    // 定期刷新
    const interval = setInterval(fetchEnergy, 3000);
    
    // 监听能量变化事件
    const handleEnergyEvent = (e: CustomEvent) => {
      fetchEnergy();
    };
    window.addEventListener("energy-changed", handleEnergyEvent as EventListener);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener("energy-changed", handleEnergyEvent as EventListener);
    };
  }, []);

  if (loading || !energy) {
    return (
      <div className={`energy-bar ${className}`}>
        <span className="energy-icon">⚡</span>
        <span className="energy-loading">--</span>
      </div>
    );
  }

  if (!energy.enabled) {
    return (
      <div className={`energy-bar disabled ${className}`}>
        <span className="energy-icon">⚡</span>
        <span className="energy-text">∞</span>
      </div>
    );
  }

  const isLow = energy.percentage < 25;
  const isCritical = energy.percentage < 10;

  const handleMouseEnter = () => {
    if (barRef.current) {
      const rect = barRef.current.getBoundingClientRect();
      setTooltipPos({
        top: rect.bottom + 8,
        left: rect.left + rect.width / 2,
      });
    }
    setShowTooltip(true);
  };

  // Tooltip 使用 Portal 渲染到 body，避免被父容器遮挡
  const tooltipElement = showTooltip && createPortal(
    <div 
      className="energy-tooltip-portal"
      style={{
        position: 'fixed',
        top: tooltipPos.top,
        left: tooltipPos.left,
        transform: 'translateX(-50%)',
        zIndex: 99999,
      }}
    >
      <div className="tooltip-header">
        <span className="tooltip-icon">⚡</span>
        <span className="tooltip-title">神力能量</span>
      </div>
      <div className="tooltip-body">
        <div className="tooltip-row">
          <span>当前能量</span>
          <span className="value">{energy.current} / {energy.maximum}</span>
        </div>
        <div className="tooltip-row">
          <span>每回合恢复</span>
          <span className="value">+{energy.regen_per_turn}</span>
        </div>
        <div className="tooltip-row">
          <span>总消耗</span>
          <span className="value">{energy.total_spent}</span>
        </div>
        <div className="tooltip-row">
          <span>总恢复</span>
          <span className="value">{energy.total_regenerated}</span>
        </div>
      </div>
      <div className="tooltip-footer">
        点击查看消耗历史
      </div>
    </div>,
    document.body
  );

  return (
    <div 
      ref={barRef}
      className={`energy-bar ${className} ${isLow ? 'low' : ''} ${isCritical ? 'critical' : ''}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setShowTooltip(false)}
      onClick={onOpenHistory}
      style={{ cursor: onOpenHistory ? 'pointer' : 'default' }}
    >
      <span className="energy-icon">⚡</span>
      
      <div className="energy-gauge">
        <div 
          className="energy-fill"
          style={{ width: `${energy.percentage}%` }}
        />
        <span className="energy-text">
          {energy.current}/{energy.maximum}
        </span>
      </div>

      <span className="regen-hint">+{energy.regen_per_turn}/回合</span>

      {tooltipElement}

      {/* 保留原有 tooltip 结构用于样式定义，但不再使用 */}
      {false && (
        <div className="energy-tooltip">
          <div className="tooltip-header">
            <span className="tooltip-icon">⚡</span>
            <span className="tooltip-title">神力能量</span>
          </div>
          <div className="tooltip-body">
            <div className="tooltip-row">
              <span>当前能量</span>
              <span className="value">{energy.current} / {energy.maximum}</span>
            </div>
            <div className="tooltip-row">
              <span>每回合恢复</span>
              <span className="value">+{energy.regen_per_turn}</span>
            </div>
            <div className="tooltip-row">
              <span>总消耗</span>
              <span className="value">{energy.total_spent}</span>
            </div>
            <div className="tooltip-row">
              <span>总恢复</span>
              <span className="value">{energy.total_regenerated}</span>
            </div>
          </div>
          <div className="tooltip-footer">
            点击查看消耗历史
          </div>
        </div>
      )}

      <style>{`
        .energy-bar {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          background: rgba(245, 158, 11, 0.1);
          border: 1px solid rgba(245, 158, 11, 0.3);
          border-radius: 20px;
          position: relative;
          transition: all 0.3s;
        }

        .energy-bar:hover {
          background: rgba(245, 158, 11, 0.15);
          border-color: rgba(245, 158, 11, 0.5);
        }

        .energy-bar.low {
          background: rgba(239, 68, 68, 0.1);
          border-color: rgba(239, 68, 68, 0.3);
        }

        .energy-bar.critical {
          animation: pulse-critical 1s infinite;
        }

        @keyframes pulse-critical {
          0%, 100% { 
            background: rgba(239, 68, 68, 0.1); 
            box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
          }
          50% { 
            background: rgba(239, 68, 68, 0.2); 
            box-shadow: 0 0 8px 2px rgba(239, 68, 68, 0.3);
          }
        }

        .energy-bar.disabled {
          background: rgba(100, 100, 100, 0.1);
          border-color: rgba(100, 100, 100, 0.3);
        }

        .energy-icon {
          font-size: 1rem;
        }

        .energy-gauge {
          position: relative;
          width: 80px;
          height: 16px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 8px;
          overflow: hidden;
        }

        .energy-fill {
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          background: linear-gradient(90deg, #f59e0b, #fbbf24);
          border-radius: 8px;
          transition: width 0.3s ease;
        }

        .energy-bar.low .energy-fill {
          background: linear-gradient(90deg, #ef4444, #f87171);
        }

        .energy-text {
          position: absolute;
          left: 50%;
          top: 50%;
          transform: translate(-50%, -50%);
          font-size: 0.7rem;
          font-weight: 600;
          color: white;
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
          white-space: nowrap;
        }

        .energy-loading {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .regen-hint {
          font-size: 0.7rem;
          color: rgba(245, 158, 11, 0.8);
          margin-left: 2px;
        }

        .energy-tooltip {
          position: absolute;
          top: calc(100% + 8px);
          left: 50%;
          transform: translateX(-50%);
          width: 200px;
          background: var(--bg-primary);
          border: 1px solid var(--border-primary);
          border-radius: var(--radius-md);
          box-shadow: var(--shadow-lg);
          z-index: 1000;
          padding: var(--spacing-sm);
        }

        .energy-tooltip::before {
          content: '';
          position: absolute;
          top: -6px;
          left: 50%;
          transform: translateX(-50%);
          border-left: 6px solid transparent;
          border-right: 6px solid transparent;
          border-bottom: 6px solid var(--border-primary);
        }

        .tooltip-header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding-bottom: var(--spacing-xs);
          border-bottom: 1px solid var(--border-primary);
          margin-bottom: var(--spacing-xs);
        }

        .tooltip-icon {
          font-size: 1.1rem;
        }

        .tooltip-title {
          font-weight: 600;
          color: var(--text-primary);
        }

        .tooltip-body {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .tooltip-row {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          color: var(--text-secondary);
        }

        .tooltip-row .value {
          font-weight: 600;
          color: var(--text-primary);
        }

        .tooltip-footer {
          margin-top: var(--spacing-xs);
          padding-top: var(--spacing-xs);
          border-top: 1px solid var(--border-primary);
          font-size: 0.75rem;
          color: var(--text-muted);
          text-align: center;
        }
      `}</style>
    </div>
  );
}

// 导出事件触发函数，供其他组件使用
export function dispatchEnergyChanged() {
  window.dispatchEvent(new CustomEvent("energy-changed"));
}

