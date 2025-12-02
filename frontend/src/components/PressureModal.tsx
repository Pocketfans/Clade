import { useMemo, useState } from "react";

import type { PressureDraft, PressureTemplate } from "@/services/api.types";

interface Props {
  pressures: PressureDraft[];
  templates: PressureTemplate[];
  onChange: (next: PressureDraft[]) => void;
  onQueue: (next: PressureDraft[], rounds: number) => void;
  onExecute: (next: PressureDraft[]) => void;
  onBatchExecute: (rounds: number, pressures: PressureDraft[], randomEnergy: number) => void;
  onClose: () => void;
}

const MUTUAL_EXCLUSIONS: Record<string, string[]> = {
  glacial_period: ["greenhouse_earth"],
  greenhouse_earth: ["glacial_period"],
  pluvial_period: ["drought_period"],
  drought_period: ["pluvial_period"],
  resource_abundance: ["productivity_decline"],
  productivity_decline: ["resource_abundance"],
  oxygen_increase: ["anoxic_event"],
  anoxic_event: ["oxygen_increase"],
  subsidence: ["orogeny"],
  orogeny: ["subsidence"],
};

// 压力类型图标映射
const PRESSURE_ICONS: Record<string, string> = {
  natural_evolution: "🌱",  // 零消耗的自然演化
  glacial_period: "🧊",
  greenhouse_earth: "🔥",
  pluvial_period: "🌧️",
  drought_period: "☀️",
  resource_abundance: "🌿",
  productivity_decline: "🍂",
  oxygen_increase: "💨",
  anoxic_event: "💀",
  subsidence: "⬇️",
  orogeny: "⛰️",
  volcanic_eruption: "🌋",
  meteor_impact: "☄️",
  disease_outbreak: "🦠",
  predator_surge: "🐺",
  habitat_fragmentation: "🔀",
};

// 零消耗的压力类型
const FREE_PRESSURE_KINDS = new Set(["natural_evolution"]);

export function PressureModal({
  pressures,
  templates,
  onChange,
  onQueue,
  onExecute,
  onBatchExecute,
  onClose,
}: Props) {
  const [selectedKind, setSelectedKind] = useState(templates[0]?.kind ?? "");
  const [intensity, setIntensity] = useState(5);
  const [rounds, setRounds] = useState(1);
  
  // 批量执行模式
  const [batchRounds, setBatchRounds] = useState(5);
  const [randomEnergy, setRandomEnergy] = useState(15);
  const [showBatchMode, setShowBatchMode] = useState(false);

  // 能量消耗计算：基础消耗(3) × 强度，自然演化为0
  const PRESSURE_BASE_COST = 3;
  const getPressureCost = (kind: string, intensity: number) => {
    return FREE_PRESSURE_KINDS.has(kind) ? 0 : PRESSURE_BASE_COST * intensity;
  };
  const currentCost = getPressureCost(selectedKind, intensity);
  const totalCost = useMemo(() => {
    return pressures.reduce((sum, p) => sum + getPressureCost(p.kind, p.intensity), 0);
  }, [pressures]);

  const selectedTemplate = useMemo(
    () => templates.find((tpl) => tpl.kind === selectedKind),
    [templates, selectedKind],
  );

  const limitReached = pressures.length >= 3;

  const conflictInfo = useMemo(() => {
    if (!selectedKind) return null;
    const conflicts = MUTUAL_EXCLUSIONS[selectedKind];
    if (!conflicts) return null;
    const existing = pressures.find((p) => conflicts.includes(p.kind));
    return existing ? existing.label || existing.kind : null;
  }, [selectedKind, pressures]);

  function addPressure() {
    if (!selectedKind || !selectedTemplate) return;
    if (limitReached) return;
    if (conflictInfo) return;
    
    onChange([
      ...pressures, 
      { 
        kind: selectedKind, 
        intensity, 
        label: selectedTemplate.label,
        narrative_note: selectedTemplate.description 
      }
    ]);
  }

  function remove(index: number) {
    onChange(pressures.filter((_, i) => i !== index));
  }

  function isKindDisabled(kind: string) {
     const conflicts = MUTUAL_EXCLUSIONS[kind];
     if (!conflicts) return false;
     return pressures.some(p => conflicts.includes(p.kind));
  }

  // 获取强度等级描述
  function getIntensityLabel(val: number): string {
    if (val <= 2) return "微弱";
    if (val <= 4) return "温和";
    if (val <= 6) return "显著";
    if (val <= 8) return "剧烈";
    return "灾难性";
  }

  // 获取强度颜色
  function getIntensityColor(val: number): string {
    if (val <= 2) return "rgba(45, 212, 191, 0.8)";
    if (val <= 4) return "rgba(34, 197, 94, 0.8)";
    if (val <= 6) return "rgba(245, 158, 11, 0.8)";
    if (val <= 8) return "rgba(249, 115, 22, 0.8)";
    return "rgba(239, 68, 68, 0.8)";
  }

  return (
    <div className="drawer-overlay" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div 
        className="drawer-panel pressure-modal" 
        style={{
          width: '95vw',
          maxWidth: '1200px',
          height: '88vh',
          maxHeight: '900px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          padding: 0,
          borderRadius: '20px',
        }}
      >
        
        {/* Header */}
        <header className="pressure-modal-header flex-shrink-0">
          <div>
            <h2 className="pressure-modal-title">环境压力策划</h2>
            <p className="pressure-modal-subtitle">配置自然灾害与环境变迁事件</p>
          </div>
          <button onClick={onClose} className="pressure-close-btn" aria-label="关闭">
            ×
          </button>
        </header>
        
        {/* 三栏主内容区 */}
        <div style={{
          display: 'flex',
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          position: 'relative',
          zIndex: 1,
        }}>
          
          {/* 左栏：模板选择 */}
          <div 
            className="custom-scrollbar"
            style={{
              width: '280px',
              flexShrink: 0,
              borderRight: '1px solid rgba(45, 212, 191, 0.1)',
              overflowY: 'auto',
              padding: '20px',
              background: 'rgba(5, 10, 8, 0.5)',
            }}
          >
            <div className="pressure-section-title" style={{ marginBottom: '12px' }}>
              <span className="title-icon">📋</span>
              事件模板
            </div>
            
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column',
              gap: '8px' 
            }}>
              {templates.map((item) => {
                const disabled = isKindDisabled(item.kind);
                const isSelected = selectedKind === item.kind;
                const icon = PRESSURE_ICONS[item.kind] || "⚡";
                return (
                  <button
                    key={item.kind}
                    disabled={disabled}
                    onClick={() => !disabled && setSelectedKind(item.kind)}
                    title={disabled ? "与已选事件互斥" : item.description}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '12px 14px',
                      background: isSelected 
                        ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.08))'
                        : 'linear-gradient(135deg, rgba(20, 30, 25, 0.6), rgba(15, 22, 18, 0.8))',
                      border: `1px solid ${isSelected 
                        ? 'rgba(245, 158, 11, 0.5)' 
                        : 'rgba(45, 212, 191, 0.1)'}`,
                      borderRadius: '10px',
                      cursor: disabled ? 'not-allowed' : 'pointer',
                      opacity: disabled ? 0.4 : 1,
                      transition: 'all 0.2s',
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ 
                      fontSize: '1.3rem',
                      width: '32px',
                      height: '32px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: isSelected 
                        ? 'rgba(245, 158, 11, 0.15)' 
                        : 'rgba(45, 212, 191, 0.08)',
                      borderRadius: '8px',
                      flexShrink: 0,
                    }}>
                      {icon}
                    </span>
                    <span style={{ 
                      fontSize: '0.85rem', 
                      fontWeight: 600, 
                      color: isSelected ? '#f59e0b' : '#f0f4e8',
                      flex: 1,
                    }}>
                      {item.label}
                    </span>
                    {disabled && (
                      <span style={{ 
                        fontSize: '0.65rem', 
                        color: 'rgba(239, 68, 68, 0.8)',
                        background: 'rgba(239, 68, 68, 0.1)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                      }}>
                        冲突
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 中栏：配置区 */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            padding: '24px 28px',
            minWidth: 0,
            overflow: 'hidden',
          }}>
            {selectedTemplate ? (
              <>
                {/* 模板信息 */}
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'flex-start', 
                  gap: '16px',
                  marginBottom: '24px',
                  padding: '20px',
                  background: 'linear-gradient(135deg, rgba(20, 28, 24, 0.6), rgba(15, 22, 18, 0.8))',
                  border: '1px solid rgba(45, 212, 191, 0.1)',
                  borderRadius: '14px',
                }}>
                  <div style={{
                    width: '56px',
                    height: '56px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '2rem',
                    background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.08))',
                    border: '1px solid rgba(245, 158, 11, 0.25)',
                    borderRadius: '12px',
                    flexShrink: 0,
                  }}>
                    {PRESSURE_ICONS[selectedKind] || "⚡"}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h3 style={{ 
                      margin: 0, 
                      fontSize: '1.25rem', 
                      fontWeight: 700, 
                      color: '#f0f4e8',
                      marginBottom: '8px'
                    }}>
                      {selectedTemplate.label}
                    </h3>
                    <p style={{ 
                      margin: 0,
                      fontSize: '0.9rem', 
                      color: 'rgba(240, 244, 232, 0.6)', 
                      lineHeight: 1.6,
                    }}>
                      {selectedTemplate.description}
                    </p>
                  </div>
                </div>
                
                {/* 强度配置 */}
                <div style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  padding: '24px',
                  background: 'linear-gradient(135deg, rgba(15, 22, 18, 0.5), rgba(10, 16, 12, 0.6))',
                  border: '1px solid rgba(45, 212, 191, 0.08)',
                  borderRadius: '14px',
                }}>
                  {/* 强度标题和数值 */}
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center',
                    marginBottom: '20px'
                  }}>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'rgba(240, 244, 232, 0.5)', marginBottom: '4px' }}>
                        强度等级
                      </div>
                      <div style={{ 
                        fontSize: '1rem', 
                        fontWeight: 600,
                        color: getIntensityColor(intensity)
                      }}>
                        {getIntensityLabel(intensity)}
                      </div>
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                      <div className="pressure-intensity-value">{intensity}</div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.7rem', color: 'rgba(240, 244, 232, 0.4)' }}>能量消耗</div>
                        <div style={{ 
                          fontSize: '1.2rem', 
                          fontWeight: 700, 
                          color: currentCost === 0 ? '#22c55e' : '#f59e0b',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          {currentCost === 0 ? (
                            <><span>✨</span> 免费</>
                          ) : (
                            <><span>⚡</span> {currentCost}</>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* 滑块 */}
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={intensity}
                    onChange={(e) => setIntensity(parseInt(e.target.value, 10))}
                    className="pressure-intensity-slider"
                  />
                  
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    fontSize: '0.75rem',
                    color: 'rgba(240, 244, 232, 0.35)',
                    marginTop: '10px'
                  }}>
                    <span>微弱变化</span>
                    <span>灾难性影响</span>
                  </div>
                </div>

                {/* 添加按钮 */}
                <button 
                  type="button" 
                  onClick={addPressure}
                  disabled={limitReached || !!conflictInfo}
                  style={{
                    marginTop: '20px',
                    padding: '16px 24px',
                    fontWeight: 700,
                    fontSize: '1rem',
                    borderRadius: '12px',
                    background: limitReached || conflictInfo 
                      ? 'rgba(60, 60, 60, 0.5)' 
                      : 'linear-gradient(135deg, rgba(45, 212, 191, 0.2), rgba(34, 197, 94, 0.15))',
                    border: limitReached || conflictInfo 
                      ? '1px solid rgba(100, 100, 100, 0.3)'
                      : '1px solid rgba(45, 212, 191, 0.4)',
                    color: limitReached || conflictInfo 
                      ? 'rgba(255, 255, 255, 0.3)'
                      : '#2dd4bf',
                    cursor: limitReached || conflictInfo ? 'not-allowed' : 'pointer',
                    transition: 'all 0.3s',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  {limitReached 
                    ? "⚠️ 队列已满 (3/3)" 
                    : conflictInfo 
                      ? `⛔ 与「${conflictInfo}」冲突` 
                      : "➕ 添加至执行列表"}
                </button>
              </>
            ) : (
              <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'rgba(240, 244, 232, 0.35)',
                textAlign: 'center',
              }}>
                <div style={{ fontSize: '4rem', marginBottom: '16px', opacity: 0.3 }}>⚡</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 500 }}>请选择一个压力模板</div>
                <div style={{ fontSize: '0.9rem', marginTop: '8px', opacity: 0.7 }}>
                  从左侧列表中选择以开始配置
                </div>
              </div>
            )}
          </div>

          {/* 右栏：执行队列 */}
          <div 
            className="pressure-right-panel"
            style={{
              width: '300px',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* 队列列表 */}
            <div 
              className="flex-1 overflow-y-auto custom-scrollbar" 
              style={{ padding: '20px' }}
            >
              <div className="pressure-section-title" style={{ marginBottom: '12px' }}>
                <span className="title-icon">📦</span>
                执行队列
                <span style={{
                  marginLeft: 'auto',
                  padding: '3px 8px',
                  background: pressures.length >= 3 
                    ? 'rgba(239, 68, 68, 0.15)' 
                    : 'rgba(45, 212, 191, 0.1)',
                  border: `1px solid ${pressures.length >= 3 
                    ? 'rgba(239, 68, 68, 0.3)' 
                    : 'rgba(45, 212, 191, 0.2)'}`,
                  borderRadius: '12px',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  color: pressures.length >= 3 ? '#ef4444' : '#2dd4bf',
                  letterSpacing: 0
                }}>
                  {pressures.length}/3
                </span>
              </div>

              {pressures.length === 0 ? (
                <div className="pressure-empty-state" style={{ padding: '30px 16px' }}>
                  <div className="pressure-empty-state-icon" style={{ fontSize: '2.5rem' }}>📭</div>
                  <div style={{ fontWeight: 500, marginBottom: '4px', fontSize: '0.9rem' }}>暂无事件</div>
                  <div style={{ fontSize: '0.8rem' }}>从中间配置区添加</div>
                </div>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {pressures.map((pressure, index) => (
                    <li 
                      key={`${pressure.kind}-${index}`}
                      className="pressure-queue-item"
                      style={{ padding: '12px 14px' }}
                    >
                      <div style={{ 
                        width: '32px', 
                        height: '32px', 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        fontSize: '1.1rem',
                        background: 'rgba(245, 158, 11, 0.1)',
                        borderRadius: '8px',
                        flexShrink: 0
                      }}>
                        {PRESSURE_ICONS[pressure.kind] || "⚡"}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#f0f4e8' }}>
                          {pressure.label}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                          <span className="pressure-queue-badge" style={{ padding: '2px 8px', fontSize: '0.7rem' }}>
                            <span style={{ 
                              width: '6px', 
                              height: '6px', 
                              borderRadius: '50%', 
                              background: getIntensityColor(pressure.intensity) 
                            }} />
                            Lv.{pressure.intensity}
                          </span>
                          <span style={{ fontSize: '0.7rem', color: FREE_PRESSURE_KINDS.has(pressure.kind) ? '#22c55e' : '#f59e0b' }}>
                            {FREE_PRESSURE_KINDS.has(pressure.kind) ? '✨免费' : `⚡${PRESSURE_BASE_COST * pressure.intensity}`}
                          </span>
                        </div>
                      </div>
                      <button 
                        onClick={() => remove(index)}
                        className="pressure-remove-btn"
                        style={{ width: '28px', height: '28px', fontSize: '1rem' }}
                        title="移除"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* 操作区 */}
            <div className="pressure-action-footer" style={{ padding: '16px' }}>
              {/* 模式切换 */}
              <div style={{ 
                display: 'flex', 
                marginBottom: '12px',
                background: 'rgba(0, 0, 0, 0.2)',
                borderRadius: '8px',
                padding: '4px',
              }}>
                <button
                  onClick={() => setShowBatchMode(false)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    background: !showBatchMode ? 'rgba(45, 212, 191, 0.15)' : 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    color: !showBatchMode ? '#2dd4bf' : 'rgba(255, 255, 255, 0.5)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  📋 手动模式
                </button>
                <button
                  onClick={() => setShowBatchMode(true)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    background: showBatchMode ? 'rgba(168, 85, 247, 0.15)' : 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    color: showBatchMode ? '#a855f7' : 'rgba(255, 255, 255, 0.5)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  🎲 自动模式
                </button>
              </div>

              {!showBatchMode ? (
                <>
                  {/* 手动模式：持续时间 */}
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '10px',
                    marginBottom: '12px'
                  }}>
                    <span style={{ fontSize: '0.75rem', color: 'rgba(240, 244, 232, 0.5)' }}>
                      持续
                    </span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={rounds}
                      onChange={(e) => setRounds(parseInt(e.target.value, 10))}
                      className="pressure-duration-input"
                      style={{ width: '60px', padding: '8px 10px', fontSize: '0.9rem' }}
                    />
                    <span style={{ fontSize: '0.75rem', color: 'rgba(240, 244, 232, 0.5)', flex: 1 }}>
                      回合
                    </span>
                  </div>

                  {/* 总能量消耗 */}
                  {pressures.length > 0 && (
                    <div className="pressure-cost-display" style={{ marginBottom: '12px', padding: '10px 12px' }}>
                      <span className="pressure-cost-icon" style={{ fontSize: '1rem' }}>⚡</span>
                      <span style={{ fontSize: '0.85rem', color: '#f59e0b', fontWeight: 600, position: 'relative', zIndex: 1 }}>
                        总消耗: <strong>{totalCost}</strong>
                      </span>
                    </div>
                  )}

                  {/* 手动模式按钮 */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <button 
                      onClick={() => onExecute(pressures)}
                      className="pressure-execute-btn"
                      disabled={pressures.length === 0}
                      style={{ padding: '12px 16px', fontSize: '0.9rem' }}
                    >
                      {pressures.length === 0 ? "请先添加事件" : `🚀 立即推演`}
                    </button>
                    
                    <button
                      onClick={() => onBatchExecute(rounds, pressures, 0)}
                      disabled={pressures.length === 0 || rounds <= 1}
                      style={{
                        padding: '10px 12px',
                        background: (pressures.length === 0 || rounds <= 1)
                          ? 'rgba(60, 60, 60, 0.4)' 
                          : 'linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(168, 85, 247, 0.1))',
                        border: `1px solid ${(pressures.length === 0 || rounds <= 1)
                          ? 'rgba(100, 100, 100, 0.2)' 
                          : 'rgba(168, 85, 247, 0.3)'}`,
                        borderRadius: '8px',
                        color: (pressures.length === 0 || rounds <= 1)
                          ? 'rgba(255, 255, 255, 0.25)' 
                          : '#a855f7',
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        cursor: (pressures.length === 0 || rounds <= 1) ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s'
                      }}
                      title="连续执行多回合，不中断"
                    >
                      ⚡ 连续执行 {rounds} 回合
                    </button>
                    
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => onQueue(pressures, rounds)}
                        disabled={pressures.length === 0}
                        style={{
                          flex: 1,
                          padding: '10px 12px',
                          background: pressures.length === 0 
                            ? 'rgba(60, 60, 60, 0.4)' 
                            : 'rgba(45, 212, 191, 0.1)',
                          border: `1px solid ${pressures.length === 0 
                            ? 'rgba(100, 100, 100, 0.2)' 
                            : 'rgba(45, 212, 191, 0.2)'}`,
                          borderRadius: '8px',
                          color: pressures.length === 0 
                            ? 'rgba(255, 255, 255, 0.25)' 
                            : 'rgba(45, 212, 191, 0.9)',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          cursor: pressures.length === 0 ? 'not-allowed' : 'pointer',
                          transition: 'all 0.2s'
                        }}
                        title="加入后台队列"
                      >
                        📋 加入队列
                      </button>
                      <button 
                        style={{
                          padding: '10px 14px',
                          background: pressures.length === 0 
                            ? 'rgba(60, 60, 60, 0.3)' 
                            : 'rgba(239, 68, 68, 0.08)',
                          border: `1px solid ${pressures.length === 0 
                            ? 'rgba(100, 100, 100, 0.15)' 
                            : 'rgba(239, 68, 68, 0.15)'}`,
                          borderRadius: '8px',
                          color: pressures.length === 0 
                            ? 'rgba(255, 255, 255, 0.2)' 
                            : 'rgba(239, 68, 68, 0.7)',
                          fontSize: '0.8rem',
                          cursor: pressures.length === 0 ? 'not-allowed' : 'pointer',
                          transition: 'all 0.2s'
                        }}
                        onClick={() => onChange([])}
                        disabled={pressures.length === 0}
                        title="清空列表"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  {/* 自动模式 */}
                  <div style={{ 
                    padding: '12px',
                    background: 'rgba(168, 85, 247, 0.05)',
                    border: '1px solid rgba(168, 85, 247, 0.15)',
                    borderRadius: '10px',
                    marginBottom: '12px',
                  }}>
                    <div style={{ fontSize: '0.75rem', color: '#a855f7', fontWeight: 600, marginBottom: '10px' }}>
                      🎲 自动随机压力模式
                    </div>
                    <p style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.5)', margin: '0 0 12px 0', lineHeight: 1.5 }}>
                      系统会在每回合自动随机选择压力事件，连续执行指定回合数后再显示结果。
                    </p>
                    
                    {/* 回合数设置 */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '10px',
                      marginBottom: '10px'
                    }}>
                      <span style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' }}>
                        执行
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={batchRounds}
                        onChange={(e) => setBatchRounds(Math.max(1, parseInt(e.target.value, 10) || 1))}
                        className="pressure-duration-input"
                        style={{ width: '60px', padding: '8px 10px', fontSize: '0.9rem' }}
                      />
                      <span style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' }}>
                        回合
                      </span>
                    </div>
                    
                    {/* 每回合能量设置 */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '10px',
                    }}>
                      <span style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' }}>
                        每回合
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={randomEnergy}
                        onChange={(e) => setRandomEnergy(Math.max(0, parseInt(e.target.value, 10) || 0))}
                        className="pressure-duration-input"
                        style={{ width: '60px', padding: '8px 10px', fontSize: '0.9rem' }}
                      />
                      <span style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' }}>
                        ⚡ 神力
                      </span>
                    </div>
                  </div>
                  
                  {/* 预计消耗 */}
                  <div className="pressure-cost-display" style={{ marginBottom: '12px', padding: '10px 12px' }}>
                    <span className="pressure-cost-icon" style={{ fontSize: '1rem' }}>⚡</span>
                    <span style={{ fontSize: '0.85rem', color: '#a855f7', fontWeight: 600 }}>
                      预计总消耗: <strong>{batchRounds * randomEnergy}</strong>
                    </span>
                  </div>
                  
                  {/* 自动模式执行按钮 */}
                  <button 
                    onClick={() => onBatchExecute(batchRounds, [], randomEnergy)}
                    style={{
                      width: '100%',
                      padding: '14px 16px',
                      background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.3), rgba(139, 92, 246, 0.2))',
                      border: '1px solid rgba(168, 85, 247, 0.4)',
                      borderRadius: '10px',
                      color: '#fff',
                      fontSize: '0.95rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                    }}
                  >
                    🎲 开始自动演化 ({batchRounds} 回合)
                  </button>
                  
                  <p style={{ 
                    fontSize: '0.65rem', 
                    color: 'rgba(255, 255, 255, 0.35)', 
                    textAlign: 'center',
                    marginTop: '8px',
                    lineHeight: 1.4
                  }}>
                    执行过程中会显示进度，完成后统一显示最终报告
                  </p>
                </>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
