import { useMemo, useState, useEffect } from "react";
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
  sulfide_event: "☠️",
  methane_release: "♨️",
  extreme_weather: "🌪️",
  sea_level_rise: "🌊",
  sea_level_fall: "🏝️",
  earthquake_period: "🏚️",
  wildfire_period: "🔥",
  algal_bloom: "🤢",
  uv_radiation_increase: "🔆",
  gamma_ray_burst: "☢️",
  salinity_change: "🧂",
  land_degradation: "🏜️",
  ocean_current_shift: "🌊",
  species_invasion: "🦗",
  predator_rise: "🦈",
  fog_period: "🌫️",
  monsoon_shift: "🌬️",
};

// 零消耗的压力类型
const FREE_PRESSURE_KINDS = new Set(["natural_evolution"]);

// Tier 主题色配置
const TIER_THEMES = {
  1: {
    color: "#2dd4bf", // Teal
    bg: "rgba(45, 212, 191, 0.1)",
    border: "rgba(45, 212, 191, 0.3)",
    gradient: "linear-gradient(135deg, rgba(45, 212, 191, 0.2), rgba(34, 197, 94, 0.15))",
    label: "一阶 · 生态波动",
    desc: "轻微的环境变化，主要影响生物互动与局部生态",
    icon: "🌿"
  },
  2: {
    color: "#f59e0b", // Amber
    bg: "rgba(245, 158, 11, 0.1)",
    border: "rgba(245, 158, 11, 0.3)",
    gradient: "linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(251, 191, 36, 0.15))",
    label: "二阶 · 环境变迁",
    desc: "显著的气候与地理改变，迫使物种进行适应性演化",
    icon: "🌪️"
  },
  3: {
    color: "#ef4444", // Red
    bg: "rgba(239, 68, 68, 0.15)",
    border: "rgba(239, 68, 68, 0.4)",
    gradient: "linear-gradient(135deg, rgba(239, 68, 68, 0.25), rgba(220, 38, 38, 0.2))",
    label: "三阶 · 天灾降临",
    desc: "毁灭性的地质灾难，可能导致大规模灭绝与生态重组",
    icon: "🌋"
  }
};

export function PressureModal({
  pressures,
  templates,
  onChange,
  onQueue,
  onExecute,
  onBatchExecute,
  onClose,
}: Props) {
  // 状态
  const [activeTier, setActiveTier] = useState<number>(2); // 默认选中 Tier 2
  const [selectedKind, setSelectedKind] = useState<string>("");
  const [intensity, setIntensity] = useState(5);
  const [rounds, setRounds] = useState(1);
  
  // 批量模式
  const [batchRounds, setBatchRounds] = useState(5);
  const [randomEnergy, setRandomEnergy] = useState(750);
  const [showBatchMode, setShowBatchMode] = useState(false);

  // 初始化选中项
  useEffect(() => {
    const tierTemplates = templates.filter(t => (t.tier || 2) === activeTier);
    if (tierTemplates.length > 0 && !tierTemplates.find(t => t.kind === selectedKind)) {
      setSelectedKind(tierTemplates[0].kind);
    }
  }, [activeTier, templates]);

  // 常量
  const PRESSURE_TIER_1_LIMIT = 3;
  const PRESSURE_TIER_2_LIMIT = 7;
  const PRESSURE_TIER_1_MULT = 1.0;
  const PRESSURE_TIER_2_MULT = 2.0;
  const PRESSURE_TIER_3_MULT = 5.0;

  // 过滤当前 Tier 的模板
  const currentTierTemplates = useMemo(() => {
    return templates.filter(t => (t.tier || 2) === activeTier);
  }, [templates, activeTier]);

  // 选中的模板对象
  const selectedTemplate = useMemo(
    () => templates.find((tpl) => tpl.kind === selectedKind),
    [templates, selectedKind]
  );

  // 消耗计算
  const getPressureCost = (kind: string, intensityVal: number) => {
    if (FREE_PRESSURE_KINDS.has(kind)) return 0;
    const tpl = templates.find(t => t.kind === kind);
    const baseCost = tpl?.base_cost ?? 20;
    
    let multiplier = PRESSURE_TIER_1_MULT;
    if (intensityVal > PRESSURE_TIER_2_LIMIT) multiplier = PRESSURE_TIER_3_MULT;
    else if (intensityVal > PRESSURE_TIER_1_LIMIT) multiplier = PRESSURE_TIER_2_MULT;
    
    return Math.round(baseCost * intensityVal * multiplier);
  };

  const currentCost = useMemo(() => getPressureCost(selectedKind, intensity), [selectedKind, intensity]);
  const totalCost = useMemo(() => pressures.reduce((sum, p) => sum + getPressureCost(p.kind, p.intensity), 0), [pressures]);

  // 限制检查
  const limitReached = pressures.length >= 3;
  const conflictInfo = useMemo(() => {
    if (!selectedKind) return null;
    const conflicts = MUTUAL_EXCLUSIONS[selectedKind];
    if (!conflicts) return null;
    const existing = pressures.find((p) => conflicts.includes(p.kind));
    return existing ? existing.label || existing.kind : null;
  }, [selectedKind, pressures]);

  // 辅助函数
  function addPressure() {
    if (!selectedKind || !selectedTemplate || limitReached || conflictInfo) return;
    onChange([...pressures, { 
      kind: selectedKind, 
      intensity, 
      label: selectedTemplate.label,
      narrative_note: selectedTemplate.description 
    }]);
  }

  function remove(index: number) {
    onChange(pressures.filter((_, i) => i !== index));
  }

  function isKindDisabled(kind: string) {
     const conflicts = MUTUAL_EXCLUSIONS[kind];
     if (!conflicts) return false;
     return pressures.some(p => conflicts.includes(p.kind));
  }

  function getIntensityLabel(val: number) {
    // 【v3】更新倍率显示，与后端一致
    if (val <= PRESSURE_TIER_1_LIMIT) return "轻微 (×0.3)";
    if (val <= PRESSURE_TIER_2_LIMIT) return "显著 (×0.6)";
    return "毁灭性 (×1.5)";  // 大浪淘沙！
  }

  function getIntensityColor(val: number) {
    if (val <= PRESSURE_TIER_1_LIMIT) return "#2dd4bf"; // Teal
    if (val <= PRESSURE_TIER_2_LIMIT) return "#f59e0b"; // Amber
    return "#ef4444"; // Red
  }

  // 获取当前 Tier 的主题色
  const theme = TIER_THEMES[activeTier as keyof typeof TIER_THEMES];

  return (
    <div className="drawer-overlay" style={{ 
      background: 'rgba(0, 0, 0, 0.85)',
      backdropFilter: 'blur(8px)',
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      zIndex: 2000
    }}>
      <div 
        className="drawer-panel pressure-modal fullscreen-panel" 
        style={{
          width: '96vw',
          maxWidth: '1400px',
          height: '92vh',
          maxHeight: '960px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          padding: 0,
          borderRadius: '24px',
          background: 'linear-gradient(160deg, #0f1714 0%, #050a08 100%)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)',
          border: '1px solid rgba(255, 255, 255, 0.08)'
        }}
      >
        
        {/* Header */}
        <header style={{
          padding: '24px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
          background: 'rgba(0, 0, 0, 0.2)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(45, 212, 191, 0.2), rgba(34, 197, 94, 0.1))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              border: '1px solid rgba(45, 212, 191, 0.3)'
            }}>⚡</div>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f0f4e8', letterSpacing: '-0.02em' }}>神力干预</h2>
              <p style={{ margin: '4px 0 0', fontSize: '0.9rem', color: 'rgba(240, 244, 232, 0.5)' }}>配置环境事件，引导文明演化方向</p>
            </div>
          </div>
          <button onClick={onClose} style={{
            width: '40px', height: '40px', borderRadius: '50%', border: 'none',
            background: 'rgba(255, 255, 255, 0.05)', color: 'rgba(255, 255, 255, 0.6)',
            fontSize: '24px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s'
          }} className="hover:bg-white/10 hover:text-white">
            ×
          </button>
        </header>
        
        {/* Main Content */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* Left Sidebar: Selection */}
          <div style={{
            width: '360px',
            display: 'flex',
            flexDirection: 'column',
            borderRight: '1px solid rgba(255, 255, 255, 0.06)',
            background: 'rgba(0, 0, 0, 0.2)'
          }}>
            {/* Tier Tabs */}
            <div style={{ padding: '20px 20px 10px', display: 'flex', gap: '8px' }}>
              {[1, 2, 3].map(tier => {
                const isActive = activeTier === tier;
                const t = TIER_THEMES[tier as keyof typeof TIER_THEMES];
                return (
                  <button
                    key={tier}
                    onClick={() => setActiveTier(tier)}
                    style={{
                      flex: 1,
                      padding: '10px 0',
                      borderRadius: '10px',
                      border: `1px solid ${isActive ? t.color : 'transparent'}`,
                      background: isActive ? t.bg : 'rgba(255, 255, 255, 0.03)',
                      color: isActive ? t.color : 'rgba(255, 255, 255, 0.4)',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.3s',
                      position: 'relative',
                      overflow: 'hidden'
                    }}
                  >
                    <div style={{ position: 'relative', zIndex: 1 }}>{tier === 1 ? '一阶' : tier === 2 ? '二阶' : '三阶'}</div>
                    {isActive && <div style={{
                      position: 'absolute', inset: 0, opacity: 0.2,
                      background: `linear-gradient(to bottom, transparent, ${t.color})`
                    }} />}
                  </button>
                );
              })}
            </div>

            {/* Tier Info Banner */}
            <div style={{
              margin: '0 20px 16px',
              padding: '12px 16px',
              borderRadius: '12px',
              background: theme.bg,
              border: `1px solid ${theme.border}`,
              display: 'flex',
              gap: '12px',
              alignItems: 'center'
            }}>
              <div style={{ fontSize: '24px' }}>{theme.icon}</div>
              <div>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: theme.color }}>{theme.label}</div>
                <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)', marginTop: '2px' }}>{theme.desc}</div>
              </div>
            </div>
            
            {/* Template List */}
            <div className="custom-scrollbar" style={{ flex: 1, overflowY: 'auto', padding: '0 20px 20px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {currentTierTemplates.map(template => {
                  const isActive = selectedKind === template.kind;
                  const isDisabled = isKindDisabled(template.kind);
                  
                  return (
                    <button
                      key={template.kind}
                      onClick={() => !isDisabled && setSelectedKind(template.kind)}
                      disabled={isDisabled}
                      style={{
                        padding: '14px',
                        borderRadius: '14px',
                        background: isActive 
                          ? `linear-gradient(90deg, ${theme.bg}, transparent)`
                          : 'rgba(255, 255, 255, 0.03)',
                        border: `1px solid ${isActive ? theme.color : 'rgba(255, 255, 255, 0.05)'}`,
                        borderLeft: isActive ? `4px solid ${theme.color}` : undefined,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '14px',
                        cursor: isDisabled ? 'not-allowed' : 'pointer',
                        opacity: isDisabled ? 0.5 : 1,
                        transition: 'all 0.2s',
                        textAlign: 'left',
                        position: 'relative'
                      }}
                    >
                      <div style={{
                        width: '36px', height: '36px', borderRadius: '8px',
                        background: isActive ? theme.color : 'rgba(255, 255, 255, 0.08)',
                        color: isActive ? '#000' : '#eee',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '20px', flexShrink: 0
                      }}>
                        {PRESSURE_ICONS[template.kind] || "⚡"}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.95rem', color: isActive ? '#fff' : 'rgba(255, 255, 255, 0.8)' }}>
                          {template.label}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.4)', marginTop: '2px' }}>
                          {template.base_cost > 0 ? `⚡ 基础消耗 ${template.base_cost}` : '✨ 免费'}
                        </div>
                      </div>
                      {isDisabled && (
                        <div style={{
                          position: 'absolute', right: '10px', top: '10px',
                          fontSize: '0.65rem', color: '#ef4444',
                          background: 'rgba(239, 68, 68, 0.1)', padding: '2px 6px', borderRadius: '4px'
                        }}>冲突</div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Middle: Configuration */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            padding: '40px',
            position: 'relative',
            background: `radial-gradient(circle at 50% 30%, ${theme.color}11 0%, transparent 70%)`
          }}>
            {selectedTemplate ? (
              <div className="fade-in" style={{ maxWidth: '640px', margin: '0 auto', width: '100%' }}>
                {/* Icon & Title */}
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                  <div style={{
                    width: '96px', height: '96px', margin: '0 auto 24px',
                    borderRadius: '24px',
                    background: `linear-gradient(135deg, ${theme.color}33, ${theme.color}11)`,
                    border: `1px solid ${theme.color}44`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '48px',
                    boxShadow: `0 0 40px ${theme.color}22`
                  }}>
                    {PRESSURE_ICONS[selectedKind] || "⚡"}
                  </div>
                  <h2 style={{ fontSize: '2.5rem', margin: '0 0 12px', fontWeight: 800, color: '#fff' }}>
                    {selectedTemplate.label}
                  </h2>
                  <p style={{ fontSize: '1.1rem', color: 'rgba(255, 255, 255, 0.7)', lineHeight: 1.6, maxWidth: '540px', margin: '0 auto' }}>
                    {selectedTemplate.description}
                  </p>
                </div>

                {/* Controls */}
                <div style={{
                  background: 'rgba(0, 0, 0, 0.3)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '20px',
                  padding: '32px',
                  backdropFilter: 'blur(10px)'
                }}>
                  {/* Intensity Slider */}
                  <div style={{ marginBottom: '32px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', alignItems: 'flex-end' }}>
                      <label style={{ fontSize: '0.9rem', fontWeight: 600, color: 'rgba(255, 255, 255, 0.6)' }}>
                        强度设置
                      </label>
                      <div style={{ textAlign: 'right' }}>
                        <span style={{ fontSize: '2rem', fontWeight: 700, color: getIntensityColor(intensity), marginRight: '8px' }}>
                          {intensity}
                        </span>
                        <span style={{ fontSize: '1rem', color: getIntensityColor(intensity) }}>
                          / {getIntensityLabel(intensity)}
                        </span>
                      </div>
                    </div>
                    
                    <input
                      type="range"
                      min={1}
                      max={10}
                      value={intensity}
                      onChange={(e) => setIntensity(parseInt(e.target.value))}
                      className="pressure-intensity-slider"
                      style={{
                        '--thumb-color': getIntensityColor(intensity),
                        width: '100%',
                        marginBottom: '12px'
                      } as any}
                    />
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.3)' }}>
                      <span>1 级 (×1.0)</span>
                      <span>5 级 (×2.0)</span>
                      <span>10 级 (×5.0)</span>
                    </div>
                  </div>

                  {/* Cost & Action */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '24px', borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
                    <div>
                      <div style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.5)', marginBottom: '4px' }}>预计能量消耗</div>
                      <div style={{ fontSize: '1.8rem', fontWeight: 700, color: currentCost === 0 ? '#2dd4bf' : '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {currentCost === 0 ? 'FREE' : currentCost}
                        <span style={{ fontSize: '1rem', opacity: 0.7 }}>⚡</span>
                      </div>
                    </div>
                    
                    <button
                      onClick={addPressure}
                      disabled={limitReached || !!conflictInfo}
                      style={{
                        padding: '16px 32px',
                        borderRadius: '14px',
                        background: limitReached || conflictInfo 
                          ? 'rgba(255, 255, 255, 0.1)' 
                          : theme.gradient,
                        border: 'none',
                        color: limitReached || conflictInfo ? 'rgba(255, 255, 255, 0.3)' : '#fff',
                        fontSize: '1.1rem',
                        fontWeight: 700,
                        cursor: limitReached || conflictInfo ? 'not-allowed' : 'pointer',
                        boxShadow: limitReached || conflictInfo ? 'none' : `0 10px 20px -5px ${theme.color}44`,
                        transition: 'all 0.2s',
                        display: 'flex', alignItems: 'center', gap: '8px'
                      }}
                    >
                      {limitReached ? '队列已满' : conflictInfo ? '存在冲突' : '添加到队列 +'}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.3, flexDirection: 'column', gap: '20px' }}>
                <div style={{ fontSize: '64px' }}>👈</div>
                <div style={{ fontSize: '1.5rem' }}>请从左侧选择一个事件</div>
              </div>
            )}
          </div>

          {/* Right Sidebar: Queue & Execute */}
          <div style={{
            width: '380px',
            background: 'rgba(0, 0, 0, 0.3)',
            borderLeft: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            flexDirection: 'column'
          }}>
            
            {/* Queue Header */}
            <div style={{ padding: '24px', borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>📦</span> 待执行列表
                </h3>
                <span style={{ 
                  fontSize: '0.8rem', 
                  padding: '2px 8px', 
                  borderRadius: '10px',
                  background: pressures.length >= 3 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(45, 212, 191, 0.1)',
                  color: pressures.length >= 3 ? '#ef4444' : '#2dd4bf'
                }}>
                  {pressures.length} / 3
                </span>
              </div>
              
              {/* Total Cost */}
              <div style={{ 
                background: 'rgba(0, 0, 0, 0.2)', 
                padding: '12px', 
                borderRadius: '10px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span style={{ fontSize: '0.9rem', color: 'rgba(255, 255, 255, 0.6)' }}>总计消耗</span>
                <span style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f59e0b' }}>
                  {totalCost} <span style={{ fontSize: '0.9rem' }}>⚡</span>
                </span>
              </div>
            </div>

            {/* Queue Items */}
            <div className="custom-scrollbar" style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {pressures.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 0', color: 'rgba(255, 255, 255, 0.2)' }}>
                  <div style={{ fontSize: '48px', marginBottom: '16px', filter: 'grayscale(1)' }}>📭</div>
                  <div>暂无待执行事件</div>
                </div>
              ) : (
                pressures.map((p, idx) => {
                  const tpl = templates.find(t => t.kind === p.kind);
                  const cost = getPressureCost(p.kind, p.intensity);
                  const pTheme = TIER_THEMES[(tpl?.tier || 2) as keyof typeof TIER_THEMES];
                  
                  return (
                    <div key={idx} className="list-item" style={{
                      background: 'rgba(255, 255, 255, 0.05)',
                      borderRadius: '12px',
                      padding: '12px',
                      border: `1px solid ${pTheme.color}33`,
                      position: 'relative',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        position: 'absolute', left: 0, top: 0, bottom: 0, width: '4px',
                        background: pTheme.color
                      }} />
                      
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'start' }}>
                        <div style={{
                          fontSize: '24px', width: '40px', height: '40px',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: 'rgba(0,0,0,0.2)', borderRadius: '8px'
                        }}>
                          {PRESSURE_ICONS[p.kind]}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <div style={{ fontWeight: 600, color: '#fff' }}>{p.label}</div>
                            <button onClick={() => remove(idx)} style={{ 
                              border: 'none', background: 'transparent', color: 'rgba(255,255,255,0.3)',
                              cursor: 'pointer', fontSize: '16px', padding: 0
                            }} className="hover:text-red-400">×</button>
                          </div>
                          <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                            <span style={{ fontSize: '0.75rem', background: `${pTheme.color}22`, color: pTheme.color, padding: '2px 6px', borderRadius: '4px' }}>
                              强度 {p.intensity}
                            </span>
                            <span style={{ fontSize: '0.75rem', color: '#f59e0b' }}>
                              {cost} ⚡
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Action Footer */}
            <div style={{ padding: '24px', background: 'rgba(0, 0, 0, 0.2)', borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
              
              {/* Toggle Mode */}
              <div style={{ display: 'flex', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '8px', padding: '4px', marginBottom: '16px' }}>
                <button
                  onClick={() => setShowBatchMode(false)}
                  style={{
                    flex: 1, padding: '8px', borderRadius: '6px',
                    border: 'none', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                    background: !showBatchMode ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
                    color: !showBatchMode ? '#fff' : 'rgba(255, 255, 255, 0.4)'
                  }}
                >
                  单回合模式
                </button>
                <button
                  onClick={() => setShowBatchMode(true)}
                  style={{
                    flex: 1, padding: '8px', borderRadius: '6px',
                    border: 'none', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                    background: showBatchMode ? 'rgba(168, 85, 247, 0.2)' : 'transparent',
                    color: showBatchMode ? '#a855f7' : 'rgba(255, 255, 255, 0.4)'
                  }}
                >
                  自动演化
                </button>
              </div>

              {!showBatchMode ? (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>持续时间:</span>
                    <input 
                      type="number" min={1} max={20} value={rounds} 
                      onChange={e => setRounds(parseInt(e.target.value))}
                      style={{ 
                        background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
                        color: '#fff', padding: '6px 10px', borderRadius: '6px', width: '60px'
                      }}
                    />
                    <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>回合</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <button
                      onClick={() => onExecute(pressures)}
                      disabled={pressures.length === 0}
                      style={{
                        gridColumn: '1 / -1',
                        padding: '14px', borderRadius: '10px',
                        background: pressures.length > 0 ? 'linear-gradient(135deg, #22c55e 0%, #15803d 100%)' : 'rgba(255,255,255,0.1)',
                        border: 'none', color: pressures.length > 0 ? '#fff' : 'rgba(255,255,255,0.3)',
                        fontWeight: 700, fontSize: '1rem', cursor: pressures.length > 0 ? 'pointer' : 'not-allowed',
                        boxShadow: pressures.length > 0 ? '0 4px 12px rgba(34, 197, 94, 0.3)' : 'none'
                      }}
                    >
                      ▶ 执行回合
                    </button>
                    <button
                      onClick={() => onQueue(pressures, rounds)}
                      disabled={pressures.length === 0}
                      style={{
                        padding: '12px', borderRadius: '10px',
                        background: 'rgba(45, 212, 191, 0.1)',
                        border: '1px solid rgba(45, 212, 191, 0.2)',
                        color: '#2dd4bf', fontWeight: 600, cursor: pressures.length > 0 ? 'pointer' : 'not-allowed',
                        opacity: pressures.length > 0 ? 1 : 0.5
                      }}
                    >
                      加入后台队列
                    </button>
                    <button
                      onClick={() => onChange([])}
                      disabled={pressures.length === 0}
                      style={{
                        padding: '12px', borderRadius: '10px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        color: '#ef4444', fontWeight: 600, cursor: pressures.length > 0 ? 'pointer' : 'not-allowed',
                        opacity: pressures.length > 0 ? 1 : 0.5
                      }}
                    >
                      清空
                    </button>
                  </div>
                </>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                    自动随机选择事件并快进。
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                     <input 
                        type="number" value={batchRounds} onChange={e => setBatchRounds(parseInt(e.target.value))}
                        style={{ width: '60px', padding: '6px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '6px' }}
                     />
                     <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem' }}>回合</span>
                     <span style={{ flex: 1 }}></span>
                     <input 
                        type="number" value={randomEnergy} onChange={e => setRandomEnergy(parseInt(e.target.value))}
                        style={{ width: '60px', padding: '6px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '6px' }}
                     />
                     <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem' }}>神力/回</span>
                  </div>
                  <button
                    onClick={() => onBatchExecute(batchRounds, [], randomEnergy)}
                    style={{
                      padding: '14px', borderRadius: '10px',
                      background: 'linear-gradient(135deg, #a855f7 0%, #7e22ce 100%)',
                      border: 'none', color: '#fff',
                      fontWeight: 700, fontSize: '1rem', cursor: 'pointer',
                      marginTop: '8px',
                      boxShadow: '0 4px 12px rgba(168, 85, 247, 0.3)'
                    }}
                  >
                    🎲 开始自动演化
                  </button>
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
      
      <style>{`
        .pressure-intensity-slider {
          -webkit-appearance: none;
          height: 6px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
          outline: none;
        }
        .pressure-intensity-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: var(--thumb-color, #fff);
          cursor: pointer;
          box-shadow: 0 0 10px var(--thumb-color, #fff);
          transition: transform 0.1s;
        }
        .pressure-intensity-slider::-webkit-slider-thumb:hover {
          transform: scale(1.2);
        }
      `}</style>
    </div>
  );
}
