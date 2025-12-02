/**
 * CreateSpeciesModal - 创建新物种面板
 * 重新设计的现代化界面，支持AI生成物种
 */
import { useEffect, useState } from "react";
import { Sparkles, Dna, Leaf, Bug, Bird, Fish, Zap, RefreshCw, Check, AlertCircle } from "lucide-react";
import { AnalysisPanel, AnalysisSection, ActionButton, EmptyState } from "./common/AnalysisPanel";
import { fetchSpeciesList, generateSpecies } from "@/services/api";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

// 物种模板预设
const SPECIES_TEMPLATES = [
  { 
    id: "producer", 
    icon: <Leaf size={20} />, 
    name: "生产者", 
    color: "#22c55e",
    prompt: "一种能够进行光合作用的植物或藻类，为生态系统提供基础能量..."
  },
  { 
    id: "herbivore", 
    icon: <Bug size={20} />, 
    name: "草食者", 
    color: "#3b82f6",
    prompt: "一种以植物为主要食物来源的动物，可能具有特殊的消化系统..."
  },
  { 
    id: "carnivore", 
    icon: <Bird size={20} />, 
    name: "肉食者", 
    color: "#ef4444",
    prompt: "一种以其他动物为食的捕食者，拥有敏锐的感官和捕猎能力..."
  },
  { 
    id: "aquatic", 
    icon: <Fish size={20} />, 
    name: "水生物种", 
    color: "#06b6d4",
    prompt: "一种生活在水中的生物，适应了水下环境，可能拥有鳃或其他水生适应..."
  },
];

export function CreateSpeciesModal({ onClose, onSuccess }: Props) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedCode, setSuggestedCode] = useState<string>("");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [charCount, setCharCount] = useState(0);

  useEffect(() => {
    // 自动计算可用的 Lineage Code
    fetchSpeciesList()
      .then((list) => {
        const usedCodes = new Set(list.map((s) => s.lineage_code));
        let bestPrefix = "S";
        let index = 1;
        while (usedCodes.has(`${bestPrefix}${index}`)) {
          index++;
        }
        setSuggestedCode(`${bestPrefix}${index}`);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    setCharCount(prompt.length);
  }, [prompt]);

  const handleTemplateSelect = (template: typeof SPECIES_TEMPLATES[0]) => {
    setSelectedTemplate(template.id);
    if (!prompt) {
      setPrompt(template.prompt);
    }
  };

  async function handleCreate() {
    if (!prompt.trim()) {
      setError("请输入物种描述");
      return;
    }
    if (!suggestedCode) {
      setError("正在计算编号，请稍候...");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await generateSpecies(prompt, suggestedCode);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      console.error(err);
      setError(err instanceof Error ? err.message : "生成失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  const handleRandomize = () => {
    const randomTemplate = SPECIES_TEMPLATES[Math.floor(Math.random() * SPECIES_TEMPLATES.length)];
    setSelectedTemplate(randomTemplate.id);
    setPrompt(randomTemplate.prompt);
  };

  return (
    <AnalysisPanel
      title="创造新物种"
      icon={<Sparkles size={20} />}
      accentColor="#a855f7"
      onClose={onClose}
      size="medium"
      footer={
        <>
          <ActionButton variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </ActionButton>
          <ActionButton 
            variant="success" 
            icon={<Zap size={18} />}
            onClick={handleCreate} 
            loading={loading}
            disabled={!prompt.trim()}
          >
            {loading ? "创造中..." : "确认创造"}
          </ActionButton>
        </>
      }
    >
      <div className="create-species-content">
        {/* 物种编号预览 */}
        <div className="species-code-preview">
          <div className="code-label">
            <Dna size={16} />
            <span>物种编号</span>
          </div>
          <div className="code-value">
            {suggestedCode || (
              <span className="loading-text">计算中...</span>
            )}
          </div>
          <div className="code-hint">此编号将成为物种的唯一标识</div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="error-message">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* 模板选择 */}
        <AnalysisSection title="快速模板" icon={<Sparkles size={16} />} accentColor="#a855f7">
          <div className="templates-grid">
            {SPECIES_TEMPLATES.map((template) => (
              <button
                key={template.id}
                className={`template-card ${selectedTemplate === template.id ? 'selected' : ''}`}
                style={{ '--template-color': template.color } as React.CSSProperties}
                onClick={() => handleTemplateSelect(template)}
              >
                <span className="template-icon">{template.icon}</span>
                <span className="template-name">{template.name}</span>
              </button>
            ))}
            <button
              className="template-card randomize"
              onClick={handleRandomize}
            >
              <span className="template-icon"><RefreshCw size={20} /></span>
              <span className="template-name">随机</span>
            </button>
          </div>
        </AnalysisSection>

        {/* 物种描述输入 */}
        <AnalysisSection title="物种描述" icon={<Dna size={16} />} accentColor="#3b82f6">
          <div className="prompt-input-wrapper">
            <textarea
              className="prompt-textarea"
              rows={6}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述你想创造的物种...&#10;&#10;例如：一种体型巨大的陆行鸟类，拥有厚重的骨质装甲以防御捕食者。它的喙部特化为能够咬碎坚果的强力结构，主要以低矮灌木和坚硬种子为食。具有较强的领地意识，通常独居。"
            />
            <div className="prompt-footer">
              <span className={`char-count ${charCount > 500 ? 'warning' : ''}`}>
                {charCount} / 500 字符
              </span>
              <div className="prompt-tips">
                <span className="tip">💡 提示: 描述越详细，生成的物种越丰富</span>
              </div>
            </div>
          </div>
        </AnalysisSection>

        {/* 生成说明 */}
        <div className="create-info-banner">
          <Sparkles size={18} />
          <div className="info-text">
            <strong>AI 驱动的物种创造</strong>
            <p>AI 将根据你的描述生成物种的外观、行为、生态位等详细属性，并将其投放到当前生态系统中。</p>
          </div>
        </div>
      </div>

      <style>{`
        .create-species-content {
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          position: relative;
          z-index: 1;
        }

        /* 物种编号预览 */
        .species-code-preview {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 24px 20px;
          background: linear-gradient(135deg, 
            rgba(168, 85, 247, 0.1) 0%, 
            rgba(168, 85, 247, 0.03) 100%
          );
          border: 1px solid rgba(168, 85, 247, 0.2);
          border-radius: 16px;
          text-align: center;
          position: relative;
          z-index: 2;
          flex-shrink: 0;
        }

        .code-label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          margin-bottom: 8px;
        }

        .code-label svg {
          color: #a855f7;
        }

        .code-value {
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 2.2rem;
          font-weight: 700;
          color: #a855f7;
          text-shadow: 0 0 30px rgba(168, 85, 247, 0.5);
          letter-spacing: 0.1em;
          line-height: 1;
        }

        .loading-text {
          font-size: 1rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: var(--font-body);
        }

        .code-hint {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
          margin-top: 8px;
        }

        /* 错误消息 */
        .error-message {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 18px;
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.25);
          border-radius: 12px;
          color: #fca5a5;
          font-size: 0.9rem;
        }

        .error-message svg {
          flex-shrink: 0;
          color: #ef4444;
        }

        .error-message span {
          flex: 1;
        }

        .error-message button {
          background: none;
          border: none;
          color: inherit;
          font-size: 1.3rem;
          cursor: pointer;
          opacity: 0.7;
          padding: 0 4px;
        }

        .error-message button:hover {
          opacity: 1;
        }

        /* 模板网格 */
        .templates-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
          gap: 12px;
        }

        .template-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 10px;
          padding: 18px 14px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .template-card:hover {
          background: rgba(255, 255, 255, 0.06);
          border-color: var(--template-color, rgba(255, 255, 255, 0.15));
          transform: translateY(-3px);
        }

        .template-card.selected {
          background: color-mix(in srgb, var(--template-color) 12%, transparent);
          border-color: var(--template-color);
          box-shadow: 0 0 20px color-mix(in srgb, var(--template-color) 30%, transparent);
        }

        .template-card.randomize {
          --template-color: #f59e0b;
          border-style: dashed;
        }

        .template-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          color: var(--template-color, rgba(255, 255, 255, 0.7));
          transition: all 0.2s;
        }

        .template-card.selected .template-icon,
        .template-card:hover .template-icon {
          background: color-mix(in srgb, var(--template-color) 15%, transparent);
          color: var(--template-color);
        }

        .template-name {
          font-size: 0.85rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.7);
        }

        .template-card.selected .template-name,
        .template-card:hover .template-name {
          color: rgba(255, 255, 255, 0.95);
        }

        /* 描述输入 */
        .prompt-input-wrapper {
          display: flex;
          flex-direction: column;
        }

        .prompt-textarea {
          width: 100%;
          padding: 18px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 14px;
          color: #f1f5f9;
          font-size: 0.95rem;
          line-height: 1.65;
          resize: vertical;
          min-height: 160px;
          font-family: inherit;
          transition: all 0.2s;
        }

        .prompt-textarea:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
        }

        .prompt-textarea::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .prompt-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 12px;
          padding: 0 4px;
        }

        .char-count {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: var(--font-mono, monospace);
        }

        .char-count.warning {
          color: #f59e0b;
        }

        .prompt-tips {
          display: flex;
          gap: 16px;
        }

        .tip {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
        }

        /* 信息横幅 - 使用特定类名避免与全局样式冲突 */
        .create-info-banner {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          padding: 16px;
          background: linear-gradient(135deg, 
            rgba(59, 130, 246, 0.08) 0%, 
            rgba(168, 85, 247, 0.05) 100%
          );
          border: 1px solid rgba(59, 130, 246, 0.15);
          border-radius: 14px;
          position: relative;
          z-index: 2;
          flex-shrink: 0;
        }

        .create-info-banner svg {
          color: #60a5fa;
          flex-shrink: 0;
          margin-top: 2px;
        }

        .info-text {
          flex: 1;
          min-width: 0;
        }

        .info-text strong {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.9);
          display: block;
          margin-bottom: 4px;
        }

        .info-text p {
          margin: 0;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.55);
          line-height: 1.5;
        }
      `}</style>
    </AnalysisPanel>
  );
}
