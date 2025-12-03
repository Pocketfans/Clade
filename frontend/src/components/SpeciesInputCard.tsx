/**
 * SpeciesInputCard - 主菜单物种输入卡片
 * 
 * 用于空白剧本创建时的物种描述输入，提供：
 * - 模板选择
 * - 栖息地类型选择
 * - 食性类型选择
 * - 植物/动物切换
 */
import { useState } from "react";
import { 
  Sparkles, Leaf, Bug, Bird, Fish, Sun, 
  Mountain, Waves, Droplets, ChevronDown, ChevronUp,
  TreeDeciduous, Crown, Shrub, X, RefreshCw
} from "lucide-react";

export interface SpeciesInputData {
  prompt: string;
  habitat_type?: string;
  diet_type?: string;
  is_plant?: boolean;
  plant_stage?: number;
}

interface Props {
  index: number;
  required?: boolean;
  value: SpeciesInputData;
  onChange: (data: SpeciesInputData) => void;
  onRemove?: () => void;
}

// 快速模板
const QUICK_TEMPLATES = [
  { 
    id: "algae", 
    name: "浮游藻类",
    icon: <Leaf size={14} />, 
    color: "#22c55e",
    prompt: "一种微小的浮游藻类，漂浮在海洋表层进行光合作用，是生态系统的基础生产者",
    habitat: "marine", 
    diet: "autotroph",
    isPlant: true,
    plantStage: 1
  },
  { 
    id: "bacteria", 
    name: "化能细菌",
    icon: <Sun size={14} />, 
    color: "#f59e0b",
    prompt: "一种生活在深海热泉的化能合成细菌，不依赖阳光，通过氧化硫化物获取能量",
    habitat: "deep_sea", 
    diet: "autotroph",
    isPlant: true,
    plantStage: 0
  },
  { 
    id: "moss", 
    name: "苔藓植物",
    icon: <TreeDeciduous size={14} />, 
    color: "#16a34a",
    prompt: "一种低矮的苔藓植物，贴附在潮湿的岩石或土壤表面生长，是陆地植物的先驱",
    habitat: "terrestrial", 
    diet: "autotroph",
    isPlant: true,
    plantStage: 3
  },
  { 
    id: "filter", 
    name: "滤食动物",
    icon: <Bug size={14} />, 
    color: "#3b82f6",
    prompt: "一种小型滤食性动物，通过过滤海水中的浮游生物为生，身体透明适应漂浮生活",
    habitat: "marine", 
    diet: "herbivore"
  },
  { 
    id: "grazer", 
    name: "陆地食草者",
    icon: <Bug size={14} />, 
    color: "#84cc16",
    prompt: "一种以植物为食的陆生动物，拥有适合咀嚼纤维的口器",
    habitat: "terrestrial", 
    diet: "herbivore"
  },
  { 
    id: "predator", 
    name: "小型捕食者",
    icon: <Bird size={14} />, 
    color: "#ef4444",
    prompt: "一种敏捷的小型捕食者，以小型动物为食，具有敏锐的感觉器官",
    habitat: "marine", 
    diet: "carnivore"
  },
  { 
    id: "apex", 
    name: "顶级掠食者",
    icon: <Crown size={14} />, 
    color: "#dc2626",
    prompt: "一种处于食物链顶端的强大捕食者，拥有锋利的捕猎器官和高效的追踪能力",
    habitat: "terrestrial", 
    diet: "carnivore"
  },
  { 
    id: "opportunist", 
    name: "机会主义者",
    icon: <Fish size={14} />, 
    color: "#f97316",
    prompt: "一种适应性强的杂食动物，既能捕食小型动物，也能摄取植物和有机碎屑",
    habitat: "coastal", 
    diet: "omnivore"
  },
  { 
    id: "decomposer", 
    name: "分解者",
    icon: <Shrub size={14} />, 
    color: "#78716c",
    prompt: "一种以死亡有机物为食的分解者，在生态系统中扮演物质循环的重要角色",
    habitat: "terrestrial", 
    diet: "detritivore"
  },
];

// 栖息地选项
const HABITATS = [
  { id: "marine", name: "海洋", icon: <Waves size={14} /> },
  { id: "deep_sea", name: "深海", icon: <Waves size={14} /> },
  { id: "coastal", name: "海岸", icon: <Waves size={14} /> },
  { id: "freshwater", name: "淡水", icon: <Droplets size={14} /> },
  { id: "amphibious", name: "两栖", icon: <Droplets size={14} /> },
  { id: "terrestrial", name: "陆生", icon: <Mountain size={14} /> },
  { id: "aerial", name: "空中", icon: <Bird size={14} /> },
];

// 食性选项
const DIETS = [
  { id: "autotroph", name: "自养", desc: "T1" },
  { id: "herbivore", name: "草食", desc: "T2" },
  { id: "carnivore", name: "肉食", desc: "T3+" },
  { id: "omnivore", name: "杂食", desc: "T2.5" },
  { id: "detritivore", name: "腐食", desc: "T1.5" },
];

export function SpeciesInputCard({ index, required, value, onChange, onRemove }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showTemplates, setShowTemplates] = useState(!value.prompt);

  const handleTemplateClick = (template: typeof QUICK_TEMPLATES[0]) => {
    onChange({
      prompt: template.prompt,
      habitat_type: template.habitat,
      diet_type: template.diet,
      is_plant: template.isPlant || false,
      plant_stage: template.plantStage,
    });
    setShowTemplates(false);
  };

  const isEmpty = !value.prompt.trim();

  return (
    <div className={`species-input-card ${isEmpty ? 'empty' : 'filled'}`}>
      {/* 头部 */}
      <div className="card-header">
        <div className="card-title">
          <span className="card-number">{index + 1}</span>
          <span>初始物种</span>
          {required && <span className="required-badge">必填</span>}
        </div>
        <div className="card-actions">
          {!isEmpty && (
            <button 
              className="clear-btn"
              onClick={() => onChange({ prompt: "" })}
              title="清空"
            >
              <X size={14} />
            </button>
          )}
          {onRemove && !required && (
            <button className="remove-btn" onClick={onRemove}>移除</button>
          )}
        </div>
      </div>

      {/* 快速模板选择 */}
      {showTemplates && isEmpty && (
        <div className="quick-templates">
          <div className="templates-label">
            <Sparkles size={12} />
            <span>快速选择模板</span>
          </div>
          <div className="templates-grid">
            {QUICK_TEMPLATES.map(t => (
              <button
                key={t.id}
                className="template-btn"
                style={{ '--t-color': t.color } as React.CSSProperties}
                onClick={() => handleTemplateClick(t)}
              >
                {t.icon}
                <span>{t.name}</span>
              </button>
            ))}
            <button
              className="template-btn randomize"
              style={{ '--t-color': '#a855f7' } as React.CSSProperties}
              onClick={() => {
                const randomTemplate = QUICK_TEMPLATES[Math.floor(Math.random() * QUICK_TEMPLATES.length)];
                handleTemplateClick(randomTemplate);
              }}
            >
              <RefreshCw size={14} />
              <span>随机</span>
            </button>
          </div>
        </div>
      )}

      {/* 描述输入 */}
      <div className="prompt-wrapper">
        <textarea
          value={value.prompt}
          onChange={(e) => onChange({ ...value, prompt: e.target.value })}
          placeholder={
            index === 0 
              ? "例如：一种生活在深海的发光水母，靠捕食小型浮游生物为生..." 
              : "描述另一个物种..."
          }
          rows={3}
          onFocus={() => setShowTemplates(true)}
        />
        {!isEmpty && (
          <button 
            className="expand-toggle"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            <span>高级选项</span>
          </button>
        )}
      </div>

      {/* 高级选项 */}
      {expanded && !isEmpty && (
        <div className="advanced-options">
          {/* 栖息地 */}
          <div className="option-row">
            <label>栖息地</label>
            <div className="option-chips">
              {HABITATS.map(h => (
                <button
                  key={h.id}
                  className={`chip ${value.habitat_type === h.id ? 'active' : ''}`}
                  onClick={() => onChange({ 
                    ...value, 
                    habitat_type: value.habitat_type === h.id ? undefined : h.id 
                  })}
                >
                  {h.icon}
                  <span>{h.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 食性 */}
          <div className="option-row">
            <label>食性</label>
            <div className="option-chips">
              {DIETS.map(d => (
                <button
                  key={d.id}
                  className={`chip ${value.diet_type === d.id ? 'active' : ''}`}
                  onClick={() => {
                    const newDiet = value.diet_type === d.id ? undefined : d.id;
                    onChange({ 
                      ...value, 
                      diet_type: newDiet,
                      is_plant: newDiet === 'autotroph'
                    });
                  }}
                >
                  <span>{d.name}</span>
                  <small>{d.desc}</small>
                </button>
              ))}
            </div>
          </div>

          {/* 植物阶段（仅自养生物） */}
          {value.is_plant && (
            <div className="option-row">
              <label>植物阶段</label>
              <div className="plant-stages">
                {[
                  { stage: 0, name: "原核" },
                  { stage: 1, name: "单细胞真核" },
                  { stage: 2, name: "群体藻类" },
                  { stage: 3, name: "苔藓" },
                ].map(s => (
                  <button
                    key={s.stage}
                    className={`stage-btn ${value.plant_stage === s.stage ? 'active' : ''}`}
                    onClick={() => onChange({
                      ...value,
                      plant_stage: value.plant_stage === s.stage ? undefined : s.stage
                    })}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .species-input-card {
          background: rgba(8, 16, 12, 0.5);
          border: 1px solid rgba(139, 92, 246, 0.12);
          border-radius: 14px;
          padding: 1.125rem;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .species-input-card:hover {
          border-color: rgba(139, 92, 246, 0.25);
          box-shadow: 0 4px 20px rgba(139, 92, 246, 0.08);
        }

        .species-input-card.filled {
          background: rgba(8, 16, 12, 0.7);
          border-color: rgba(139, 92, 246, 0.2);
        }

        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 14px;
        }

        .card-title {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.9rem;
          font-weight: 500;
          color: rgba(240, 244, 232, 0.85);
        }

        .card-number {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 26px;
          height: 26px;
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(168, 85, 247, 0.15));
          border: 1px solid rgba(139, 92, 246, 0.3);
          border-radius: 8px;
          font-size: 0.85rem;
          font-weight: 700;
          color: #c4b5fd;
          font-family: var(--font-mono, monospace);
        }

        .required-badge {
          font-size: 0.65rem;
          font-weight: 600;
          padding: 3px 8px;
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.25);
          border-radius: 6px;
          color: #fca5a5;
          letter-spacing: 0.03em;
        }

        .card-actions {
          display: flex;
          gap: 8px;
        }

        .clear-btn, .remove-btn {
          padding: 5px 10px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          color: rgba(240, 244, 232, 0.5);
          cursor: pointer;
          font-size: 0.75rem;
          display: flex;
          align-items: center;
          transition: all 0.2s;
        }

        .clear-btn:hover, .remove-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          border-color: rgba(255, 255, 255, 0.15);
          color: rgba(240, 244, 232, 0.85);
        }

        /* 快速模板 */
        .quick-templates {
          margin-bottom: 14px;
          padding: 12px;
          background: rgba(139, 92, 246, 0.04);
          border: 1px solid rgba(139, 92, 246, 0.1);
          border-radius: 10px;
        }

        .templates-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          font-weight: 500;
          color: rgba(168, 85, 247, 0.8);
          margin-bottom: 10px;
        }

        .templates-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(95px, 1fr));
          gap: 8px;
        }

        .template-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 9px 12px;
          background: rgba(8, 16, 12, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: rgba(240, 244, 232, 0.7);
          font-size: 0.78rem;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
        }

        .template-btn:hover {
          background: color-mix(in srgb, var(--t-color) 12%, rgba(8, 16, 12, 0.8));
          border-color: var(--t-color);
          color: #fff;
          transform: translateY(-1px);
          box-shadow: 0 3px 10px color-mix(in srgb, var(--t-color) 25%, transparent);
        }

        .template-btn svg {
          color: var(--t-color);
          flex-shrink: 0;
        }

        .template-btn.randomize {
          border-style: dashed;
          border-color: rgba(168, 85, 247, 0.25);
        }

        .template-btn.randomize:hover {
          border-style: solid;
        }

        /* 描述输入 */
        .prompt-wrapper {
          position: relative;
        }

        .prompt-wrapper textarea {
          width: 100%;
          padding: 14px;
          background: rgba(8, 16, 12, 0.6);
          border: 1px solid rgba(139, 92, 246, 0.15);
          border-radius: 10px;
          color: rgba(240, 244, 232, 0.95);
          font-size: 0.9rem;
          line-height: 1.6;
          resize: vertical;
          min-height: 80px;
          font-family: inherit;
          transition: all 0.2s;
        }

        .prompt-wrapper textarea:hover {
          border-color: rgba(139, 92, 246, 0.25);
        }

        .prompt-wrapper textarea:focus {
          outline: none;
          border-color: #8b5cf6;
          background: rgba(8, 16, 12, 0.8);
          box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
        }

        .prompt-wrapper textarea::placeholder {
          color: rgba(240, 244, 232, 0.3);
        }

        .expand-toggle {
          position: absolute;
          bottom: 10px;
          right: 10px;
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 5px 10px;
          background: rgba(139, 92, 246, 0.15);
          border: 1px solid rgba(139, 92, 246, 0.2);
          border-radius: 6px;
          color: rgba(168, 85, 247, 0.8);
          font-size: 0.7rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }

        .expand-toggle:hover {
          background: rgba(139, 92, 246, 0.25);
          color: #a78bfa;
        }

        /* 高级选项 */
        .advanced-options {
          margin-top: 14px;
          padding-top: 14px;
          border-top: 1px solid rgba(139, 92, 246, 0.12);
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .option-row {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .option-row label {
          font-size: 0.72rem;
          font-weight: 600;
          color: rgba(240, 244, 232, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .option-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .chip {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
          padding: 8px 12px;
          background: rgba(8, 16, 12, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: rgba(240, 244, 232, 0.6);
          font-size: 0.78rem;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
        }

        .chip:hover {
          background: rgba(139, 92, 246, 0.1);
          border-color: rgba(139, 92, 246, 0.3);
          color: rgba(240, 244, 232, 0.9);
        }

        .chip.active {
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(168, 85, 247, 0.15));
          border-color: rgba(139, 92, 246, 0.45);
          color: #e9d5ff;
          box-shadow: 0 2px 8px rgba(139, 92, 246, 0.2);
        }

        .chip small {
          font-size: 0.6rem;
          opacity: 0.6;
          font-family: var(--font-mono, monospace);
        }

        .plant-stages {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .stage-btn {
          padding: 8px 12px;
          background: rgba(8, 16, 12, 0.5);
          border: 1px solid rgba(34, 197, 94, 0.15);
          border-radius: 8px;
          color: rgba(240, 244, 232, 0.6);
          font-size: 0.78rem;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
          text-align: center;
        }

        .stage-btn:hover {
          background: rgba(34, 197, 94, 0.1);
          border-color: rgba(34, 197, 94, 0.35);
          color: rgba(240, 244, 232, 0.9);
        }

        .stage-btn.active {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(22, 163, 74, 0.15));
          border-color: rgba(34, 197, 94, 0.5);
          color: #86efac;
          box-shadow: 0 2px 8px rgba(34, 197, 94, 0.2);
        }
      `}</style>
    </div>
  );
}

