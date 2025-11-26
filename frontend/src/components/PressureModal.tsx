import { useMemo, useState } from "react";

import type { PressureDraft, PressureTemplate } from "../services/api.types";

interface Props {
  pressures: PressureDraft[];
  templates: PressureTemplate[];
  onChange: (next: PressureDraft[]) => void;
  onQueue: (next: PressureDraft[], rounds: number) => void;
  onExecute: (next: PressureDraft[]) => void;
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

export function PressureModal({
  pressures,
  templates,
  onChange,
  onQueue,
  onExecute,
  onClose,
}: Props) {
  const [selectedKind, setSelectedKind] = useState(templates[0]?.kind ?? "");
  const [intensity, setIntensity] = useState(5);
  const [rounds, setRounds] = useState(1);

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

  // Layout Styles
  const modalStyle: React.CSSProperties = {
    width: '90vw',
    maxWidth: '1000px',
    height: '80vh',
    maxHeight: '800px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    padding: 0, // Override default padding to manage internal layout
  };

  const contentStyle: React.CSSProperties = {
    display: 'flex',
    flex: 1,
    minHeight: 0, // Critical for nested scrolling
    overflow: 'hidden',
  };

  const leftPanelStyle: React.CSSProperties = {
    flex: '2',
    display: 'flex',
    flexDirection: 'column',
    borderRight: '1px solid var(--border-primary)',
    padding: 'var(--spacing-lg)',
    overflowY: 'auto',
    minWidth: '300px',
  };

  const rightPanelStyle: React.CSSProperties = {
    flex: '1',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--bg-tertiary)', 
    minWidth: '280px',
  };

  return (
    <div className="drawer-overlay" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="drawer-panel pressure-modal" style={modalStyle}>
        
        {/* Header */}
        <header className="flex justify-between items-center px-lg py-md border-b border-primary-subtle flex-shrink-0">
          <div>
            <h2 className="text-xl font-bold font-display">环境压力策划</h2>
            <p className="text-xs text-secondary">配置自然灾害与环境变迁事件</p>
          </div>
          <button onClick={onClose} className="btn-icon" aria-label="关闭">
            ×
          </button>
        </header>
        
        {/* Main Content Area: Split View */}
        <div style={contentStyle}>
          
          {/* Left: Template Selection & Configuration */}
          <div className="custom-scrollbar" style={leftPanelStyle}>
            
            <section className="mb-lg">
              <h3 className="text-sm font-bold text-tertiary uppercase tracking-wider mb-sm">1. 选择事件模板</h3>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', 
                gap: 'var(--spacing-sm)' 
              }}>
                {templates.map((item) => {
                  const disabled = isKindDisabled(item.kind);
                  const isSelected = selectedKind === item.kind;
                  return (
                    <button
                      key={item.kind}
                      disabled={disabled}
                      className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-secondary"}`}
                      style={{ 
                        opacity: disabled ? 0.5 : 1,
                        textDecoration: disabled ? 'line-through' : 'none',
                        height: 'auto',
                        padding: 'var(--spacing-sm)',
                        textAlign: 'center',
                        justifyContent: 'center',
                        whiteSpace: 'normal'
                      }}
                      onClick={() => setSelectedKind(item.kind)}
                      title={disabled ? "与已选事件互斥" : item.label}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="flex-1 flex flex-col">
              <h3 className="text-sm font-bold text-tertiary uppercase tracking-wider mb-sm">2. 配置强度</h3>
              <div className="p-md rounded-md flex-1 flex flex-col" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border-primary)' }}>
                <div className="mb-md">
                   <h4 className="text-lg font-bold text-primary mb-xs">{selectedTemplate?.label || "未选择"}</h4>
                   <p className="text-sm text-secondary leading-relaxed">
                     {selectedTemplate?.description || "请在上方选择一个压力模板以开始配置。"}
                   </p>
                </div>
                
                {selectedTemplate && (
                  <>
                    <div className="mt-auto mb-lg">
                      <div className="flex justify-between items-end mb-sm">
                        <label className="font-medium">强度等级</label>
                        <span className="text-xl font-display text-primary">{intensity}</span>
                      </div>
                      <input
                        type="range"
                        min={1}
                        max={10}
                        value={intensity}
                        onChange={(e) => setIntensity(parseInt(e.target.value, 10))}
                        className="w-full accent-primary cursor-pointer"
                        style={{ height: '6px' }}
                      />
                      <div className="flex justify-between text-xs text-tertiary mt-xs">
                        <span>温和变化</span>
                        <span>极度剧烈</span>
                      </div>
                    </div>

                    <button 
                      type="button" 
                      className="btn btn-secondary w-full py-md font-bold" 
                      onClick={addPressure}
                      disabled={limitReached || !!conflictInfo}
                    >
                      {limitReached 
                        ? "队列已满 (3/3)" 
                        : conflictInfo 
                          ? `无法添加 (与 ${conflictInfo} 冲突)` 
                          : "添加至执行列表 →"}
                    </button>
                  </>
                )}
              </div>
            </section>
          </div>

          {/* Right: Staging Area & Execution */}
          <div style={rightPanelStyle}>
            <div className="flex-1 overflow-y-auto custom-scrollbar p-md">
              <div className="flex justify-between items-center mb-md">
                 <h3 className="text-sm font-bold text-tertiary uppercase tracking-wider">待执行列表</h3>
                 <span className="text-xs px-xs py-xxs rounded" style={{ background: 'var(--bg-glass-hover)' }}>{pressures.length}/3</span>
              </div>

              {pressures.length === 0 ? (
                <div className="h-32 flex items-center justify-center text-muted text-sm text-center border border-dashed border-primary-subtle rounded">
                  暂无待执行事件<br/>请从左侧添加
                </div>
              ) : (
                <ul className="flex flex-col gap-sm">
                  {pressures.map((pressure, index) => (
                    <li 
                      key={`${pressure.kind}-${index}`}
                      className="p-sm rounded border border-primary-subtle flex justify-between items-center fade-in"
                      style={{ background: 'var(--bg-glass)' }}
                    >
                      <div>
                        <div className="font-bold text-sm">{pressure.label}</div>
                        <div className="text-xs text-tertiary">强度: {pressure.intensity}</div>
                      </div>
                      <button 
                        onClick={() => remove(index)}
                        className="btn btn-icon btn-ghost text-muted hover:text-danger"
                        title="移除"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Action Footer */}
            <div className="p-md border-t border-primary-subtle shadow-lg z-10" style={{ background: 'var(--bg-secondary)' }}>
              <div className="mb-md">
                <label className="flex flex-col gap-xs">
                  <span className="text-xs font-medium text-secondary">持续时间 (回合)</span>
                  <div className="flex items-center gap-sm">
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={rounds}
                      onChange={(e) => setRounds(parseInt(e.target.value, 10))}
                      className="field-input flex-1"
                    />
                    <span className="text-xs text-tertiary whitespace-nowrap">
                      {rounds > 1 ? "加入自动队列" : "单回合立即生效"}
                    </span>
                  </div>
                </label>
              </div>

              <div className="flex flex-col gap-sm">
                <button 
                  onClick={() => onExecute(pressures)}
                  className="btn btn-primary w-full py-sm"
                  disabled={pressures.length === 0}
                >
                  {pressures.length === 0 ? "请先配置事件" : "立即推演"}
                </button>
                
                <div className="flex gap-sm">
                  <button
                    onClick={() => onQueue(pressures, rounds)}
                    disabled={pressures.length === 0}
                    className="btn btn-secondary flex-1 text-sm"
                    title="加入后台队列，按回合自动执行"
                  >
                    加入队列
                  </button>
                  <button 
                    className="btn btn-ghost text-muted px-sm" 
                    onClick={() => onChange([])}
                    disabled={pressures.length === 0}
                    title="清空列表"
                  >
                    清空
                  </button>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
