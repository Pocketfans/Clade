/**
 * OrganismBlueprint - 物种生理结构蓝图组件
 * 
 * Windows Aero 玻璃风格设计
 * 展示物种的器官系统、形态参数和生理特征
 */

import React from "react";
import { SpeciesDetail } from "@/services/api.types";

interface Props {
  species: SpeciesDetail;
}

// 器官系统配置
const organSystems = {
  // 动物器官系统
  animal: [
    { key: "metabolic", icon: "⚡", label: "代谢系统", color: "#f59e0b" },
    { key: "locomotion", icon: "🦶", label: "运动系统", color: "#3b82f6" },
    { key: "sensory", icon: "👁️", label: "感官系统", color: "#8b5cf6" },
    { key: "digestive", icon: "🍽️", label: "消化系统", color: "#22c55e" },
    { key: "defense", icon: "🛡️", label: "防御系统", color: "#ef4444" },
    { key: "respiratory", icon: "🫁", label: "呼吸系统", color: "#06b6d4" },
    { key: "nervous", icon: "🧠", label: "神经系统", color: "#ec4899" },
    { key: "circulatory", icon: "❤️", label: "循环系统", color: "#f43f5e" },
    { key: "reproductive", icon: "🥚", label: "繁殖系统", color: "#a855f7" },
  ],
  // 植物器官系统
  plant: [
    { key: "photosynthetic", icon: "🌿", label: "光合器官", color: "#22c55e" },
    { key: "root_system", icon: "🌱", label: "根系", color: "#84cc16" },
    { key: "stem", icon: "🌾", label: "茎干", color: "#65a30d" },
    { key: "protection", icon: "🛡️", label: "保护结构", color: "#f59e0b" },
    { key: "vascular", icon: "🔗", label: "维管系统", color: "#3b82f6" },
    { key: "storage", icon: "📦", label: "储存器官", color: "#8b5cf6" },
    { key: "reproductive", icon: "🌸", label: "繁殖器官", color: "#ec4899" },
  ],
};

// 形态参数配置
const morphologyConfig: Record<string, { label: string; icon: string; unit: string; color: string }> = {
  body_length_cm: { label: "体长", icon: "📏", unit: "cm", color: "#3b82f6" },
  body_weight_g: { label: "体重", icon: "⚖️", unit: "g", color: "#22c55e" },
  body_surface_area_cm2: { label: "体表面积", icon: "🔲", unit: "cm²", color: "#8b5cf6" },
  lifespan_days: { label: "寿命", icon: "⏳", unit: "天", color: "#f59e0b" },
  generation_time_days: { label: "世代时间", icon: "🔄", unit: "天", color: "#ec4899" },
  metabolic_rate: { label: "代谢率", icon: "🔥", unit: "", color: "#ef4444" },
  growth_rate: { label: "生长速率", icon: "📈", unit: "", color: "#22c55e" },
  reproduction_rate: { label: "繁殖率", icon: "🥚", unit: "", color: "#a855f7" },
  size: { label: "体型", icon: "📐", unit: "", color: "#06b6d4" },
  metabolism: { label: "代谢", icon: "⚡", unit: "", color: "#f59e0b" },
};

// 格式化数值
function formatValue(key: string, value: number): string {
  if (key === 'body_length_cm') {
    if (value < 0.1 && value > 0) return `${(value * 10000).toFixed(1)} µm`;
    if (value < 1 && value > 0) return `${(value * 10).toFixed(1)} mm`;
    return `${value.toFixed(2)} cm`;
  }
  if (key === 'body_weight_g') {
    if (value < 0.001 && value > 0) return `${(value * 1000000).toFixed(1)} µg`;
    if (value < 1 && value > 0) return `${(value * 1000).toFixed(1)} mg`;
    if (value >= 1000) return `${(value / 1000).toFixed(2)} kg`;
    return `${value.toFixed(2)} g`;
  }
  if (key.includes('days')) {
    if (value >= 365) return `${(value / 365).toFixed(1)} 年`;
    return `${value.toFixed(0)} 天`;
  }
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  if (value < 0.01 && value > 0) return value.toExponential(1);
  return value.toFixed(2);
}

export function OrganismBlueprint({ species }: Props) {
  // 判断是否为植物（基于营养级）
  const isPlant = species.trophic_level !== undefined && species.trophic_level <= 1.0;
  
  // 获取器官数据
  const organs = species.organs || {};
  const organKeys = isPlant ? organSystems.plant : organSystems.animal;
  
  // 整理形态参数
  const morphStats = species.morphology_stats || {};
  const validMorphKeys = Object.keys(morphStats).filter(k => 
    morphologyConfig[k] && morphStats[k] !== undefined && morphStats[k] !== null
  );

  // 获取抽象特质（用于计算"生物学分数"）
  const traits = species.abstract_traits || {};
  const traitEntries = Object.entries(traits).slice(0, 8);
  
  // 计算平均特质分数（作为"适应度"指标）
  const avgTraitScore = traitEntries.length > 0 
    ? traitEntries.reduce((sum, [, v]) => sum + (v as number), 0) / traitEntries.length 
    : 0;

  return (
    <div className="obp-container">
      {/* 顶部：物种卡片 */}
      <div className="obp-hero">
        <div className="obp-hero-avatar">
          <span className="obp-hero-icon">{isPlant ? '🌿' : '🦎'}</span>
          <div className="obp-hero-badge">T{species.trophic_level?.toFixed(1) || '?'}</div>
        </div>
        <div className="obp-hero-info">
          <div className="obp-hero-name">{species.common_name}</div>
          <div className="obp-hero-latin">{species.latin_name}</div>
          <div className="obp-hero-stats">
            <div className="obp-mini-stat">
              <span className="obp-mini-stat-label">分类</span>
              <span className="obp-mini-stat-value">{species.taxonomic_rank || '物种'}</span>
            </div>
            <div className="obp-mini-stat">
              <span className="obp-mini-stat-label">适应度</span>
              <span className="obp-mini-stat-value">{avgTraitScore.toFixed(1)}/15</span>
            </div>
          </div>
        </div>
      </div>

      {/* 形态参数网格 */}
      {validMorphKeys.length > 0 && (
        <div className="obp-section">
          <div className="obp-section-header">
            <span className="obp-section-icon">📊</span>
            <span className="obp-section-title">形态参数</span>
          </div>
          <div className="obp-morph-grid">
            {validMorphKeys.slice(0, 6).map(key => {
              const config = morphologyConfig[key];
              const value = morphStats[key] as number;
              return (
                <div key={key} className="obp-morph-card" style={{ '--accent': config.color } as React.CSSProperties}>
                  <div className="obp-morph-icon">{config.icon}</div>
                  <div className="obp-morph-value">{formatValue(key, value)}</div>
                  <div className="obp-morph-label">{config.label}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 器官系统 */}
      <div className="obp-section">
        <div className="obp-section-header">
          <span className="obp-section-icon">{isPlant ? '🌱' : '🦴'}</span>
          <span className="obp-section-title">{isPlant ? '植物结构' : '器官系统'}</span>
        </div>
        <div className="obp-organs-grid">
          {organKeys.map(({ key, icon, label, color }) => {
            const organ = organs[key];
            const hasOrgan = organ && organ.type;
            const isActive = organ?.is_active !== false;
            
            return (
              <div 
                key={key} 
                className={`obp-organ-card ${hasOrgan ? 'active' : 'inactive'} ${!isActive ? 'disabled' : ''}`}
                style={{ '--organ-color': color } as React.CSSProperties}
              >
                <div className="obp-organ-icon-wrap">
                  <span className="obp-organ-icon">{icon}</span>
                  {hasOrgan && <div className="obp-organ-glow" />}
                </div>
                <div className="obp-organ-info">
                  <div className="obp-organ-name">
                    {hasOrgan ? organ.type : '未演化'}
                  </div>
                  <div className="obp-organ-label">{label}</div>
                  {hasOrgan && organ.efficiency && (
                    <div className="obp-organ-efficiency">
                      <div className="obp-efficiency-bar">
                        <div 
                          className="obp-efficiency-fill" 
                          style={{ width: `${Math.min(organ.efficiency * 100, 100)}%` }} 
                        />
                      </div>
                      <span className="obp-efficiency-text">{(organ.efficiency * 100).toFixed(0)}%</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 特质雷达 */}
      {traitEntries.length > 0 && (
        <div className="obp-section">
          <div className="obp-section-header">
            <span className="obp-section-icon">🧬</span>
            <span className="obp-section-title">基因特质</span>
          </div>
          <div className="obp-traits-list">
            {traitEntries.map(([key, value]) => {
              const numVal = value as number;
              const percent = (numVal / 15) * 100;
              const getColor = () => {
                if (numVal >= 10) return '#f59e0b';
                if (numVal >= 5) return '#22c55e';
                return '#3b82f6';
              };
              return (
                <div key={key} className="obp-trait-row">
                  <span className="obp-trait-name">{key}</span>
                  <div className="obp-trait-bar">
                    <div 
                      className="obp-trait-fill" 
                      style={{ width: `${percent}%`, background: getColor() }} 
                    />
                  </div>
                  <span className="obp-trait-value" style={{ color: getColor() }}>{numVal.toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 能力标签 */}
      {species.capabilities && species.capabilities.length > 0 && (
        <div className="obp-section">
          <div className="obp-section-header">
            <span className="obp-section-icon">⭐</span>
            <span className="obp-section-title">特殊能力</span>
          </div>
          <div className="obp-capabilities">
            {species.capabilities.map(cap => (
              <span key={cap} className="obp-capability-tag">
                ✦ {cap}
              </span>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .obp-container {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        /* 顶部英雄卡片 */
        .obp-hero {
          display: flex;
          gap: 16px;
          padding: 20px;
          background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 12px;
          position: relative;
          overflow: hidden;
        }

        .obp-hero::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        }

        .obp-hero-avatar {
          width: 72px;
          height: 72px;
          border-radius: 14px;
          background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.03) 100%);
          border: 1px solid rgba(255,255,255,0.1);
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          flex-shrink: 0;
        }

        .obp-hero-icon {
          font-size: 2rem;
        }

        .obp-hero-badge {
          position: absolute;
          bottom: -6px;
          right: -6px;
          background: rgba(59, 130, 246, 0.9);
          color: white;
          font-size: 0.65rem;
          font-weight: 700;
          padding: 2px 6px;
          border-radius: 4px;
          font-family: 'JetBrains Mono', monospace;
        }

        .obp-hero-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .obp-hero-name {
          font-size: 1.1rem;
          font-weight: 700;
          color: rgba(255,255,255,0.95);
        }

        .obp-hero-latin {
          font-size: 0.8rem;
          font-style: italic;
          color: rgba(255,255,255,0.5);
          font-family: 'JetBrains Mono', monospace;
        }

        .obp-hero-stats {
          display: flex;
          gap: 16px;
          margin-top: 8px;
        }

        .obp-mini-stat {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .obp-mini-stat-label {
          font-size: 0.65rem;
          color: rgba(255,255,255,0.4);
          text-transform: uppercase;
        }

        .obp-mini-stat-value {
          font-size: 0.85rem;
          font-weight: 600;
          color: rgba(255,255,255,0.9);
          font-family: 'JetBrains Mono', monospace;
        }

        /* 区块 */
        .obp-section {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .obp-section-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .obp-section-icon {
          font-size: 1rem;
        }

        .obp-section-title {
          font-size: 0.85rem;
          font-weight: 600;
          color: rgba(255,255,255,0.7);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        /* 形态参数网格 */
        .obp-morph-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 10px;
        }

        .obp-morph-card {
          padding: 12px;
          background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 10px;
          text-align: center;
          position: relative;
          overflow: hidden;
          transition: all 0.2s;
        }

        .obp-morph-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 2px;
          background: var(--accent);
          opacity: 0;
          transition: opacity 0.2s;
        }

        .obp-morph-card:hover {
          background: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%);
          transform: translateY(-2px);
        }

        .obp-morph-card:hover::before {
          opacity: 1;
        }

        .obp-morph-icon {
          font-size: 1.2rem;
          margin-bottom: 6px;
        }

        .obp-morph-value {
          font-size: 1rem;
          font-weight: 700;
          color: rgba(255,255,255,0.95);
          font-family: 'JetBrains Mono', monospace;
        }

        .obp-morph-label {
          font-size: 0.7rem;
          color: rgba(255,255,255,0.5);
          margin-top: 2px;
        }

        /* 器官网格 */
        .obp-organs-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
          gap: 10px;
        }

        .obp-organ-card {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
          border: 1px solid rgba(255,255,255,0.05);
          border-radius: 10px;
          transition: all 0.2s;
        }

        .obp-organ-card.active {
          background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%);
          border-color: rgba(255,255,255,0.1);
        }

        .obp-organ-card.active:hover {
          background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.04) 100%);
          transform: translateY(-2px);
        }

        .obp-organ-card.inactive {
          opacity: 0.5;
        }

        .obp-organ-card.disabled {
          opacity: 0.3;
          filter: grayscale(0.8);
        }

        .obp-organ-icon-wrap {
          position: relative;
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .obp-organ-icon {
          font-size: 1.4rem;
          position: relative;
          z-index: 1;
        }

        .obp-organ-glow {
          position: absolute;
          inset: -4px;
          background: var(--organ-color);
          filter: blur(10px);
          opacity: 0.3;
          border-radius: 50%;
        }

        .obp-organ-info {
          flex: 1;
          min-width: 0;
        }

        .obp-organ-name {
          font-size: 0.8rem;
          font-weight: 600;
          color: rgba(255,255,255,0.9);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .obp-organ-label {
          font-size: 0.65rem;
          color: rgba(255,255,255,0.4);
        }

        .obp-organ-efficiency {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 4px;
        }

        .obp-efficiency-bar {
          flex: 1;
          height: 3px;
          background: rgba(255,255,255,0.1);
          border-radius: 2px;
          overflow: hidden;
        }

        .obp-efficiency-fill {
          height: 100%;
          background: var(--organ-color);
          border-radius: 2px;
        }

        .obp-efficiency-text {
          font-size: 0.6rem;
          color: rgba(255,255,255,0.6);
          font-family: 'JetBrains Mono', monospace;
        }

        /* 特质列表 */
        .obp-traits-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .obp-trait-row {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .obp-trait-name {
          width: 80px;
          font-size: 0.75rem;
          color: rgba(255,255,255,0.6);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .obp-trait-bar {
          flex: 1;
          height: 6px;
          background: rgba(255,255,255,0.08);
          border-radius: 3px;
          overflow: hidden;
        }

        .obp-trait-fill {
          height: 100%;
          border-radius: 3px;
          transition: width 0.5s ease;
        }

        .obp-trait-value {
          width: 36px;
          text-align: right;
          font-size: 0.75rem;
          font-weight: 600;
          font-family: 'JetBrains Mono', monospace;
        }

        /* 能力标签 */
        .obp-capabilities {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .obp-capability-tag {
          padding: 6px 12px;
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(59, 130, 246, 0.1) 100%);
          border: 1px solid rgba(139, 92, 246, 0.25);
          border-radius: 16px;
          font-size: 0.8rem;
          color: #a78bfa;
          font-weight: 500;
        }

        /* 响应式 */
        @media (max-width: 500px) {
          .obp-morph-grid {
            grid-template-columns: repeat(2, 1fr);
          }
          
          .obp-organs-grid {
            grid-template-columns: 1fr;
          }
          
          .obp-hero {
            flex-direction: column;
            align-items: center;
            text-align: center;
          }
          
          .obp-hero-stats {
            justify-content: center;
          }
        }
      `}</style>
    </div>
  );
}

export default OrganismBlueprint;
