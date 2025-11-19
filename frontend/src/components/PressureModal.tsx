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

  function addPressure() {
    if (!selectedKind) return;
    onChange([...pressures, { kind: selectedKind, intensity }]);
  }

  function remove(index: number) {
    onChange(pressures.filter((_, i) => i !== index));
  }

  return (
    <div className="drawer-overlay">
      <div className="drawer-panel pressure-modal">
        <header className="flex justify-between items-center mb-lg">
          <div>
            <h2 className="text-2xl font-bold font-display mb-sm">压力策划</h2>
            <p className="text-sm text-secondary">为下一回合或队列指定环境变化，再开始推演。</p>
          </div>
          <button onClick={onClose} className="btn-icon" aria-label="关闭">
            ×
          </button>
        </header>
        
        <div className="drawer-section">
          <h3 className="text-lg font-semibold mb-md font-display">预设事件</h3>
          <div className="flex flex-col gap-md">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--spacing-sm)' }}>
              {templates.map((item) => (
                <button
                  key={item.kind}
                  className={selectedKind === item.kind ? "btn btn-sm btn-primary" : "btn btn-sm btn-secondary"}
                  onClick={() => setSelectedKind(item.kind)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <p className="text-sm text-tertiary">{selectedTemplate?.description || "选择一个压力主题。"}</p>
            
            <label className="flex flex-col gap-sm">
              <span className="text-sm font-medium">强度：{intensity}</span>
              <input
                type="range"
                min={1}
                max={10}
                value={intensity}
                onChange={(e) => setIntensity(parseInt(e.target.value, 10))}
                style={{ width: '100%' }}
              />
            </label>
            
            <button type="button" className="btn btn-secondary" onClick={addPressure}>
              添加到本回合
            </button>
          </div>
        </div>
        
        <div className="drawer-section">
          <h3 className="text-lg font-semibold mb-md font-display">本回合压力列表</h3>
          {pressures.length === 0 ? (
            <p className="text-sm text-muted">尚未设置压力，默认保持当前环境。</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
              {pressures.map((pressure, index) => (
                <li 
                  key={`${pressure.kind}-${index}`}
                  className="flex justify-between items-center p-md rounded-md"
                  style={{ background: 'var(--bg-glass)' }}
                >
                  <span className="text-sm">
                    <span className="font-semibold">{pressure.kind}</span>
                    <span className="text-tertiary ml-sm">· 强度 {pressure.intensity}</span>
                  </span>
                  <button 
                    onClick={() => remove(index)}
                    className="btn btn-sm btn-danger"
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
          )}
          
          <div className="flex gap-md items-center mt-lg" style={{ flexWrap: 'wrap' }}>
            <label className="flex flex-col gap-xs" style={{ flex: '1 1 150px' }}>
              <span className="text-sm font-medium">队列回合</span>
              <input
                type="number"
                min={1}
                max={20}
                value={rounds}
                onChange={(e) => setRounds(parseInt(e.target.value, 10))}
                className="field-input"
              />
            </label>
            <button
              onClick={() => onQueue(pressures, rounds)}
              disabled={pressures.length === 0}
              className="btn btn-primary"
              style={{ alignSelf: 'flex-end' }}
            >
              加入自动队列
            </button>
          </div>
        </div>
        
        <footer className="flex justify-between items-center gap-md mt-lg pt-lg" style={{ borderTop: '1px solid var(--border-primary)' }}>
          <button 
            onClick={() => onExecute(pressures)}
            className="btn btn-primary btn-lg"
          >
            立即推演
          </button>
          <button 
            className="btn btn-danger btn-sm" 
            onClick={() => onChange([])}
            disabled={pressures.length === 0}
          >
            清空本回合
          </button>
        </footer>
      </div>
    </div>
  );
}
