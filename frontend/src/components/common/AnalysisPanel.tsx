/**
 * AnalysisPanel - 统一的分析工具面板容器
 * 为所有分析类工具提供一致的视觉风格和交互体验
 */
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Maximize2, Minimize2 } from 'lucide-react';

interface Props {
  title: string;
  icon?: React.ReactNode;
  accentColor?: string;
  children: React.ReactNode;
  onClose?: () => void;
  size?: 'small' | 'medium' | 'large' | 'fullscreen';
  showMaximize?: boolean;
  footer?: React.ReactNode;
  headerExtra?: React.ReactNode;
  className?: string;
}

const SIZE_CONFIGS = {
  small: { width: '500px', height: 'auto', maxHeight: '600px' },
  medium: { width: '800px', height: 'auto', maxHeight: '85vh' },
  large: { width: '1200px', height: '90vh', maxHeight: '90vh' },
  fullscreen: { width: '98vw', height: '95vh', maxHeight: '95vh' },
};

export function AnalysisPanel({
  title,
  icon,
  accentColor = '#3b82f6',
  children,
  onClose,
  size = 'medium',
  showMaximize = false,
  footer,
  headerExtra,
  className = '',
}: Props) {
  const [mounted, setMounted] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    setMounted(true);
    // 禁止背景滚动
    document.body.style.overflow = 'hidden';
    return () => {
      setMounted(false);
      document.body.style.overflow = '';
    };
  }, []);

  const currentSize = isMaximized ? 'fullscreen' : size;
  const sizeConfig = SIZE_CONFIGS[currentSize];

  const panelStyle: React.CSSProperties = {
    '--accent-color': accentColor,
    '--accent-glow': `${accentColor}40`,
    '--accent-subtle': `${accentColor}15`,
  } as React.CSSProperties;

  return createPortal(
    <div 
      className={`analysis-panel-backdrop ${mounted ? 'visible' : ''}`}
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div 
        className={`analysis-panel ${className} ${mounted ? 'visible' : ''}`}
        style={{
          ...panelStyle,
          width: sizeConfig.width,
          height: sizeConfig.height,
          maxHeight: sizeConfig.maxHeight,
        }}
      >
        {/* 装饰边框 */}
        <div className="panel-glow-border" />
        
        {/* 头部 */}
        <header className="analysis-panel-header">
          <div className="header-left">
            {icon && <span className="header-icon">{icon}</span>}
            <h2 className="header-title">{title}</h2>
          </div>
          
          <div className="header-right">
            {headerExtra}
            {showMaximize && (
              <button 
                className="header-btn"
                onClick={() => setIsMaximized(!isMaximized)}
                title={isMaximized ? '还原' : '最大化'}
              >
                {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
            )}
            {onClose && (
              <button className="header-btn close-btn" onClick={onClose} title="关闭">
                <X size={18} />
              </button>
            )}
          </div>
        </header>

        {/* 内容区 */}
        <div className="analysis-panel-body">
          {children}
        </div>

        {/* 底部（可选） */}
        {footer && (
          <footer className="analysis-panel-footer">
            {footer}
          </footer>
        )}
      </div>

      <style>{`
        .analysis-panel-backdrop {
          position: fixed;
          inset: 0;
          z-index: 2000;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0, 0, 0, 0);
          backdrop-filter: blur(0px);
          transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .analysis-panel-backdrop.visible {
          background: rgba(0, 5, 10, 0.6);
          backdrop-filter: blur(8px);
        }

        .analysis-panel {
          position: relative;
          display: flex;
          flex-direction: column;
          background: linear-gradient(165deg, 
            rgba(15, 23, 42, 0.98) 0%, 
            rgba(10, 15, 25, 0.99) 50%,
            rgba(8, 12, 20, 0.99) 100%
          );
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 20px;
          overflow: hidden;
          box-shadow: 
            0 25px 80px rgba(0, 0, 0, 0.5),
            0 0 1px rgba(255, 255, 255, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
          transform: scale(0.92) translateY(20px);
          opacity: 0;
          transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .analysis-panel.visible {
          transform: scale(1) translateY(0);
          opacity: 1;
        }

        /* 发光边框 */
        .panel-glow-border {
          position: absolute;
          inset: -1px;
          border-radius: 20px;
          background: linear-gradient(135deg, 
            var(--accent-color) 0%, 
            transparent 25%, 
            transparent 75%, 
            var(--accent-color) 100%
          );
          opacity: 0.3;
          pointer-events: none;
          z-index: -1;
        }

        .panel-glow-border::before {
          content: '';
          position: absolute;
          inset: 1px;
          border-radius: 19px;
          background: linear-gradient(165deg, 
            rgba(15, 23, 42, 0.98) 0%, 
            rgba(10, 15, 25, 0.99) 100%
          );
        }

        /* 头部样式 */
        .analysis-panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 18px 24px;
          background: linear-gradient(180deg, 
            rgba(255, 255, 255, 0.03) 0%, 
            transparent 100%
          );
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          flex-shrink: 0;
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .header-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 40px;
          height: 40px;
          background: var(--accent-subtle);
          border: 1px solid var(--accent-glow);
          border-radius: 12px;
          font-size: 1.25rem;
          color: var(--accent-color);
          box-shadow: 0 0 20px var(--accent-glow);
        }

        .header-title {
          margin: 0;
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 1.35rem;
          font-weight: 700;
          color: #fff;
          letter-spacing: 0.02em;
          text-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
        }

        .header-right {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .header-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .header-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.9);
          border-color: rgba(255, 255, 255, 0.15);
        }

        .close-btn:hover {
          background: rgba(239, 68, 68, 0.15);
          border-color: rgba(239, 68, 68, 0.3);
          color: #f87171;
        }

        /* 内容区样式 */
        .analysis-panel-body {
          flex: 1;
          overflow-y: auto;
          overflow-x: hidden;
          position: relative;
          display: flex;
          flex-direction: column;
        }

        /* 自定义滚动条 */
        .analysis-panel-body::-webkit-scrollbar {
          width: 8px;
        }

        .analysis-panel-body::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
        }

        .analysis-panel-body::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          border: 2px solid transparent;
          background-clip: content-box;
        }

        .analysis-panel-body::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
          background-clip: content-box;
        }

        /* 底部样式 */
        .analysis-panel-footer {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          gap: 12px;
          padding: 16px 24px;
          background: linear-gradient(0deg, 
            rgba(0, 0, 0, 0.3) 0%, 
            transparent 100%
          );
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          flex-shrink: 0;
        }
      `}</style>
    </div>,
    document.body
  );
}

/**
 * AnalysisSection - 面板内的分区组件
 */
interface SectionProps {
  title?: string;
  icon?: React.ReactNode;
  accentColor?: string;
  children: React.ReactNode;
  className?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export function AnalysisSection({
  title,
  icon,
  accentColor,
  children,
  className = '',
  collapsible = false,
  defaultCollapsed = false,
}: SectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div 
      className={`analysis-section ${className}`}
      style={{ '--section-accent': accentColor } as React.CSSProperties}
    >
      {title && (
        <div 
          className={`section-header ${collapsible ? 'collapsible' : ''}`}
          onClick={() => collapsible && setCollapsed(!collapsed)}
        >
          {icon && <span className="section-icon">{icon}</span>}
          <span className="section-title">{title}</span>
          {collapsible && (
            <span className={`collapse-icon ${collapsed ? 'collapsed' : ''}`}>▼</span>
          )}
        </div>
      )}
      {!collapsed && (
        <div className="section-content">
          {children}
        </div>
      )}

      <style>{`
        .analysis-section {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          overflow: hidden;
        }

        .section-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 18px;
          background: rgba(255, 255, 255, 0.02);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .section-header.collapsible {
          cursor: pointer;
          transition: background 0.2s;
        }

        .section-header.collapsible:hover {
          background: rgba(255, 255, 255, 0.04);
        }

        .section-icon {
          display: flex;
          color: var(--section-accent, #3b82f6);
          font-size: 1rem;
        }

        .section-title {
          font-size: 0.9rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.85);
          letter-spacing: 0.02em;
        }

        .collapse-icon {
          margin-left: auto;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.4);
          transition: transform 0.2s;
        }

        .collapse-icon.collapsed {
          transform: rotate(-90deg);
        }

        .section-content {
          padding: 18px;
        }
      `}</style>
    </div>
  );
}

/**
 * StatCard - 统计卡片组件
 */
interface StatCardProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  accentColor?: string;
}

export function StatCard({ label, value, icon, trend, trendValue, accentColor = '#3b82f6' }: StatCardProps) {
  const trendColors = {
    up: '#22c55e',
    down: '#ef4444',
    neutral: '#94a3b8',
  };

  return (
    <div 
      className="stat-card"
      style={{ '--stat-accent': accentColor } as React.CSSProperties}
    >
      {icon && <div className="stat-icon">{icon}</div>}
      <div className="stat-content">
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {trend && trendValue && (
          <div 
            className="stat-trend"
            style={{ color: trendColors[trend] }}
          >
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} {trendValue}
          </div>
        )}
      </div>

      <style>{`
        .stat-card {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          padding: 18px;
          background: linear-gradient(135deg, 
            rgba(255, 255, 255, 0.03) 0%, 
            rgba(255, 255, 255, 0.01) 100%
          );
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          transition: all 0.2s ease;
        }

        .stat-card:hover {
          background: rgba(255, 255, 255, 0.05);
          border-color: rgba(255, 255, 255, 0.1);
          transform: translateY(-2px);
        }

        .stat-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          background: linear-gradient(135deg, 
            color-mix(in srgb, var(--stat-accent) 15%, transparent) 0%,
            color-mix(in srgb, var(--stat-accent) 5%, transparent) 100%
          );
          border: 1px solid color-mix(in srgb, var(--stat-accent) 25%, transparent);
          border-radius: 12px;
          color: var(--stat-accent);
          font-size: 1.1rem;
          flex-shrink: 0;
        }

        .stat-content {
          flex: 1;
          min-width: 0;
        }

        .stat-label {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 4px;
        }

        .stat-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #fff;
          font-family: var(--font-mono, 'JetBrains Mono', monospace);
          line-height: 1.2;
        }

        .stat-trend {
          font-size: 0.8rem;
          font-weight: 600;
          margin-top: 4px;
        }
      `}</style>
    </div>
  );
}

/**
 * ActionButton - 操作按钮组件
 */
interface ActionButtonProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'ghost';
  size?: 'small' | 'medium' | 'large';
  icon?: React.ReactNode;
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  fullWidth?: boolean;
}

export function ActionButton({
  children,
  variant = 'primary',
  size = 'medium',
  icon,
  loading = false,
  disabled = false,
  onClick,
  fullWidth = false,
}: ActionButtonProps) {
  return (
    <button
      className={`action-button ${variant} ${size} ${fullWidth ? 'full-width' : ''}`}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? (
        <span className="loading-spinner" />
      ) : icon ? (
        <span className="button-icon">{icon}</span>
      ) : null}
      <span className="button-text">{children}</span>

      <style>{`
        .action-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          font-weight: 600;
          border-radius: 12px;
          border: none;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
        }

        .action-button.full-width {
          width: 100%;
        }

        /* 尺寸 */
        .action-button.small {
          padding: 8px 16px;
          font-size: 0.85rem;
        }

        .action-button.medium {
          padding: 12px 24px;
          font-size: 0.95rem;
        }

        .action-button.large {
          padding: 16px 32px;
          font-size: 1.05rem;
        }

        /* 变体 */
        .action-button.primary {
          background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
          color: white;
          box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
        }

        .action-button.primary:hover:not(:disabled) {
          background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
          box-shadow: 0 6px 25px rgba(59, 130, 246, 0.4);
          transform: translateY(-2px);
        }

        .action-button.secondary {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: rgba(255, 255, 255, 0.85);
        }

        .action-button.secondary:hover:not(:disabled) {
          background: rgba(255, 255, 255, 0.1);
          border-color: rgba(255, 255, 255, 0.2);
        }

        .action-button.success {
          background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
          color: white;
          box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
        }

        .action-button.success:hover:not(:disabled) {
          background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
          box-shadow: 0 6px 25px rgba(34, 197, 94, 0.4);
          transform: translateY(-2px);
        }

        .action-button.danger {
          background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
          color: white;
          box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
        }

        .action-button.danger:hover:not(:disabled) {
          box-shadow: 0 6px 25px rgba(239, 68, 68, 0.4);
          transform: translateY(-2px);
        }

        .action-button.ghost {
          background: transparent;
          color: rgba(255, 255, 255, 0.7);
        }

        .action-button.ghost:hover:not(:disabled) {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.9);
        }

        .action-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none !important;
        }

        .button-icon {
          display: flex;
          align-items: center;
        }

        .loading-spinner {
          width: 18px;
          height: 18px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </button>
  );
}

/**
 * EmptyState - 空状态组件
 */
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3 className="empty-title">{title}</h3>
      {description && <p className="empty-desc">{description}</p>}
      {action && <div className="empty-action">{action}</div>}

      <style>{`
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 60px 40px;
          color: rgba(255, 255, 255, 0.5);
        }

        .empty-icon {
          font-size: 4rem;
          margin-bottom: 20px;
          opacity: 0.5;
        }

        .empty-title {
          margin: 0 0 10px;
          font-size: 1.2rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.7);
        }

        .empty-desc {
          margin: 0 0 24px;
          font-size: 0.95rem;
          max-width: 400px;
          line-height: 1.6;
        }

        .empty-action {
          margin-top: 8px;
        }
      `}</style>
    </div>
  );
}

