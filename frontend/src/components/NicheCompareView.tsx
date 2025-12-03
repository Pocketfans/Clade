import { useEffect, useState, useMemo, useCallback } from "react";
import { createPortal } from "react-dom";
import { 
  Sparkles, 
  RefreshCw, 
  Search, 
  X,
  Zap, 
  Target, 
  Layers, 
  ArrowRight,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Dna,
  Scale,
  Flame
} from "lucide-react";
import type { SpeciesListItem, NicheCompareResult } from "@/services/api.types";
import { fetchSpeciesList, compareNiche } from "@/services/api";
import { embeddingApi, type SpeciesCompareResponse } from "../services/embedding.api";

interface NicheCompareViewProps {
  onClose?: () => void;
}

const ROLE_CONFIG: Record<string, { color: string; icon: string; bg: string; glow: string }> = {
  "生产者": { color: "#22c55e", icon: "🌱", bg: "rgba(34, 197, 94, 0.15)", glow: "rgba(34, 197, 94, 0.3)" },
  "草食者": { color: "#3b82f6", icon: "🐰", bg: "rgba(59, 130, 246, 0.15)", glow: "rgba(59, 130, 246, 0.3)" },
  "肉食者": { color: "#ef4444", icon: "🦁", bg: "rgba(239, 68, 68, 0.15)", glow: "rgba(239, 68, 68, 0.3)" },
  "杂食者": { color: "#f59e0b", icon: "🦊", bg: "rgba(245, 158, 11, 0.15)", glow: "rgba(245, 158, 11, 0.3)" },
  "分解者": { color: "#8b5cf6", icon: "🍄", bg: "rgba(139, 92, 246, 0.15)", glow: "rgba(139, 92, 246, 0.3)" },
};

const STATUS_CONFIG: Record<string, { color: string; label: string; icon: typeof Circle }> = {
  alive: { color: "#22c55e", label: "存活", icon: CheckCircle2 },
  extinct: { color: "#ef4444", label: "灭绝", icon: X },
  critical: { color: "#f59e0b", label: "濒危", icon: AlertTriangle },
};

export function NicheCompareView({ onClose }: NicheCompareViewProps) {
  const [speciesList, setSpeciesList] = useState<SpeciesListItem[]>([]);
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<NicheCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [step, setStep] = useState<'select' | 'result'>('select');

  // AI 对比状态
  const [aiCompareResult, setAiCompareResult] = useState<SpeciesCompareResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSelector, setActiveSelector] = useState<'A' | 'B' | null>(null);

  // Mount animation
  useEffect(() => {
    setMounted(true);
    document.body.style.overflow = "hidden";
    return () => {
      setMounted(false);
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    fetchSpeciesList()
      .then(setSpeciesList)
      .catch((err) => {
        console.error("加载物种列表失败:", err);
        setError("加载物种列表失败");
      });
  }, []);

  // 过滤物种
  const filteredSpecies = useMemo(() => {
    if (!searchQuery) return speciesList.filter(s => s.status === 'alive');
    const query = searchQuery.toLowerCase();
    return speciesList.filter(
      (s) =>
        s.status === 'alive' && (
          s.common_name.toLowerCase().includes(query) ||
          s.latin_name.toLowerCase().includes(query) ||
          s.lineage_code.toLowerCase().includes(query)
        )
    );
  }, [speciesList, searchQuery]);

  const selectedSpeciesA = useMemo(
    () => speciesList.find((s) => s.lineage_code === selectedA),
    [speciesList, selectedA]
  );
  
  const selectedSpeciesB = useMemo(
    () => speciesList.find((s) => s.lineage_code === selectedB),
    [speciesList, selectedB]
  );

  const handleSelectSpecies = useCallback((lineageCode: string) => {
    if (activeSelector === 'A') {
      setSelectedA(lineageCode);
      if (!selectedB) {
        setActiveSelector('B');
      } else {
        setActiveSelector(null);
      }
    } else if (activeSelector === 'B') {
      setSelectedB(lineageCode);
      setActiveSelector(null);
    }
    setSearchQuery("");
  }, [activeSelector, selectedB]);

  const handleCompare = async () => {
    if (!selectedA || !selectedB) {
      setError("请选择两个物种");
      return;
    }

    if (selectedA === selectedB) {
      setError("请选择不同的物种");
      return;
    }

    setLoading(true);
    setError(null);
    setAiCompareResult(null);
    try {
      const result = await compareNiche(selectedA, selectedB);
      setCompareResult(result);
      setStep('result');
    } catch (err: unknown) {
      console.error("对比失败:", err);
      setError(err instanceof Error ? err.message : "对比失败");
    } finally {
      setLoading(false);
    }
  };

  const handleAiCompare = async () => {
    if (!selectedA || !selectedB) return;

    setAiLoading(true);
    try {
      const result = await embeddingApi.compareSpecies(selectedA, selectedB);
      setAiCompareResult(result);
    } catch (err: unknown) {
      console.error("AI对比失败:", err);
    } finally {
      setAiLoading(false);
    }
  };

  const handleReset = () => {
    setSelectedA(null);
    setSelectedB(null);
    setCompareResult(null);
    setAiCompareResult(null);
    setStep('select');
    setActiveSelector('A');
  };

  const getRoleConfig = (role: string) => {
    return ROLE_CONFIG[role] || { color: "#6b7280", icon: "❓", bg: "rgba(107, 114, 128, 0.15)", glow: "rgba(107, 114, 128, 0.3)" };
  };

  const getStatusConfig = (status: string) => {
    return STATUS_CONFIG[status] || { color: "#9ca3af", label: status, icon: Circle };
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  // 渲染物种选择卡片
  const renderSpeciesCard = (
    side: 'A' | 'B',
    species: SpeciesListItem | undefined,
    isActive: boolean
  ) => {
    const accentColor = side === 'A' ? '#3b82f6' : '#10b981';
    const isEmpty = !species;
    const roleConfig = species ? getRoleConfig(species.ecological_role) : null;

    return (
      <div 
        className={`ncv-species-card ${isEmpty ? 'empty' : ''} ${isActive ? 'active' : ''}`}
        style={{ 
          '--accent-color': accentColor,
          borderColor: isActive ? accentColor : undefined
        } as React.CSSProperties}
        onClick={() => setActiveSelector(side)}
      >
        {isEmpty ? (
          <div className="ncv-card-empty">
            <div className="ncv-card-empty-icon" style={{ borderColor: `${accentColor}50` }}>
              <span style={{ color: accentColor }}>{side === 'A' ? '🔬' : '🧬'}</span>
            </div>
            <div className="ncv-card-empty-text">
              <span style={{ color: accentColor }}>选择物种 {side}</span>
              <span>点击从列表中选择</span>
            </div>
          </div>
        ) : (
          <>
            <div className="ncv-card-header">
              <div className="ncv-card-avatar" style={{ background: roleConfig?.bg, borderColor: `${roleConfig?.color}50` }}>
                <span>{roleConfig?.icon}</span>
              </div>
              <div className="ncv-card-info">
                <h4>{species.common_name}</h4>
                <span className="ncv-card-latin">{species.latin_name}</span>
              </div>
              <button 
                className="ncv-card-clear" 
                onClick={(e) => {
                  e.stopPropagation();
                  if (side === 'A') setSelectedA(null);
                  else setSelectedB(null);
                }}
              >
                <X size={14} />
              </button>
            </div>
            <div className="ncv-card-meta">
              <span className="ncv-card-code">{species.lineage_code}</span>
              <span className="ncv-card-role" style={{ background: roleConfig?.bg, color: roleConfig?.color }}>
                {species.ecological_role}
              </span>
              <span className="ncv-card-pop">
                {formatNumber(species.population)} kg
              </span>
            </div>
          </>
        )}
        <div className="ncv-card-indicator" style={{ background: accentColor }}></div>
      </div>
    );
  };

  // 渲染物种列表
  const renderSpeciesList = () => {
    if (!activeSelector) return null;

    return (
      <div className="ncv-species-picker">
        <div className="ncv-picker-header">
          <span>选择物种 {activeSelector}</span>
          <button className="ncv-picker-close" onClick={() => setActiveSelector(null)}>
            <X size={16} />
          </button>
        </div>
        
        <div className="ncv-picker-search">
          <Search size={16} />
          <input
            type="text"
            placeholder="搜索物种名、学名或代码..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoFocus
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")}><X size={14} /></button>
          )}
        </div>

        <div className="ncv-picker-list custom-scrollbar">
          {filteredSpecies.length === 0 ? (
            <div className="ncv-picker-empty">
              <Search size={24} />
              <span>未找到匹配的物种</span>
            </div>
          ) : (
            filteredSpecies.map((species, index) => {
              const roleConfig = getRoleConfig(species.ecological_role);
              const isSelectedOther = 
                (activeSelector === 'A' && species.lineage_code === selectedB) ||
                (activeSelector === 'B' && species.lineage_code === selectedA);

              return (
                <button
                  key={species.lineage_code}
                  className={`ncv-picker-item ${isSelectedOther ? 'disabled' : ''}`}
                  onClick={() => !isSelectedOther && handleSelectSpecies(species.lineage_code)}
                  disabled={isSelectedOther}
                  style={{ animationDelay: `${index * 0.02}s` }}
                >
                  <div className="ncv-picker-item-avatar" style={{ background: roleConfig.bg }}>
                    {roleConfig.icon}
                  </div>
                  <div className="ncv-picker-item-info">
                    <span className="ncv-picker-item-name">{species.common_name}</span>
                    <span className="ncv-picker-item-latin">{species.latin_name}</span>
                  </div>
                  <div className="ncv-picker-item-meta">
                    <span className="ncv-picker-item-role" style={{ color: roleConfig.color }}>
                      {species.ecological_role}
                    </span>
                    <span className="ncv-picker-item-pop">{formatNumber(species.population)}</span>
                  </div>
                  {isSelectedOther && <span className="ncv-picker-item-badge">已选为对比物种</span>}
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  };

  // 渲染对比结果
  const renderResult = () => {
    if (!compareResult) return null;

    const similarity = compareResult.similarity;
    const overlap = compareResult.overlap;
    const competition = compareResult.competition_intensity;

    // 判断竞争关系
    const getRelationship = () => {
      if (competition > 0.7) return { text: "强竞争", color: "#ef4444", icon: Flame };
      if (competition > 0.4) return { text: "中等竞争", color: "#f59e0b", icon: Zap };
      if (overlap > 0.5) return { text: "生态位重叠", color: "#3b82f6", icon: Layers };
      return { text: "共存良好", color: "#22c55e", icon: CheckCircle2 };
    };

    const relationship = getRelationship();
    const RelIcon = relationship.icon;

    return (
      <div className="ncv-result">
        {/* 核心判断 */}
        <div className="ncv-verdict" style={{ borderColor: `${relationship.color}40` }}>
          <div className="ncv-verdict-icon" style={{ background: `${relationship.color}20`, color: relationship.color }}>
            <RelIcon size={28} />
          </div>
          <div className="ncv-verdict-content">
            <h3 style={{ color: relationship.color }}>{relationship.text}</h3>
            <p>
              {competition > 0.7 
                ? "两个物种在资源利用上高度重叠，竞争激烈，可能导致一方被排斥"
                : competition > 0.4 
                ? "存在一定程度的资源竞争，但尚可共存"
                : overlap > 0.5
                ? "生态位有所重叠，但竞争压力较小"
                : "两个物种占据不同生态位，可以和平共存"
              }
            </p>
          </div>
        </div>

        {/* 核心指标 */}
        <div className="ncv-metrics">
          <div className="ncv-metric" title="基于物种描述向量的余弦相似度，反映两个物种在生态特征上的相似程度">
            <div className="ncv-metric-ring">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                <circle 
                  cx="50" cy="50" r="42" 
                  fill="none" 
                  stroke="#8b5cf6" 
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${similarity * 264} 264`}
                  transform="rotate(-90 50 50)"
                  className="ncv-metric-progress"
                />
              </svg>
              <div className="ncv-metric-center">
                <span className="ncv-metric-value">{(similarity * 100).toFixed(0)}</span>
                <span className="ncv-metric-unit">%</span>
              </div>
            </div>
            <div className="ncv-metric-label">
              <Layers size={14} />
              <span>生态位相似度</span>
            </div>
            <div className="ncv-metric-desc">
              特征向量的余弦相似度
            </div>
          </div>

          <div className="ncv-metric" title="两个物种在各生态维度上的重叠程度，重叠度越高意味着资源利用越相似">
            <div className="ncv-metric-ring">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                <circle 
                  cx="50" cy="50" r="42" 
                  fill="none" 
                  stroke="#3b82f6" 
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${overlap * 264} 264`}
                  transform="rotate(-90 50 50)"
                  className="ncv-metric-progress"
                />
              </svg>
              <div className="ncv-metric-center">
                <span className="ncv-metric-value">{(overlap * 100).toFixed(0)}</span>
                <span className="ncv-metric-unit">%</span>
              </div>
            </div>
            <div className="ncv-metric-label">
              <Target size={14} />
              <span>资源重叠度</span>
            </div>
            <div className="ncv-metric-desc">
              资源利用的重叠程度
            </div>
          </div>

          <div className="ncv-metric" title="综合考虑生态位重叠和种群生物量计算的竞争压力指数">
            <div className="ncv-metric-ring">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
                <circle 
                  cx="50" cy="50" r="42" 
                  fill="none" 
                  stroke={competition > 0.6 ? "#ef4444" : competition > 0.3 ? "#f59e0b" : "#22c55e"} 
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${competition * 264} 264`}
                  transform="rotate(-90 50 50)"
                  className="ncv-metric-progress"
                />
              </svg>
              <div className="ncv-metric-center">
                <span className="ncv-metric-value">{(competition * 100).toFixed(0)}</span>
                <span className="ncv-metric-unit">%</span>
              </div>
            </div>
            <div className="ncv-metric-label">
              <Zap size={14} />
              <span>竞争强度</span>
            </div>
            <div className="ncv-metric-desc">
              {competition > 0.6 ? "高竞争压力" : competition > 0.3 ? "中等竞争" : "低竞争压力"}
            </div>
          </div>
        </div>

        {/* 维度对比 */}
        <div className="ncv-dimensions">
          <div className="ncv-dimensions-header">
            <h4>
              <Scale size={16} />
              <span>生态位维度对比</span>
            </h4>
            <span className="ncv-dimensions-hint">各维度数值越接近，竞争越激烈</span>
          </div>
          <div className="ncv-dimensions-grid">
            {Object.entries(compareResult.niche_dimensions).map(([dim, values]) => {
              const valueA = values.species_a;
              const valueB = values.species_b;
              const maxVal = Math.max(valueA, valueB, 1);
              const pctA = (valueA / maxVal) * 100;
              const pctB = (valueB / maxVal) * 100;

              return (
                <div key={dim} className="ncv-dim-row">
                  <div className="ncv-dim-label">{dim}</div>
                  <div className="ncv-dim-bars">
                    <div className="ncv-dim-bar-wrap left">
                      <div className="ncv-dim-bar left" style={{ width: `${pctA}%` }}></div>
                      <span className="ncv-dim-value">{formatNumber(valueA)}</span>
                    </div>
                    <div className="ncv-dim-bar-wrap right">
                      <span className="ncv-dim-value">{formatNumber(valueB)}</span>
                      <div className="ncv-dim-bar right" style={{ width: `${pctB}%` }}></div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="ncv-dim-legend">
            <span><span className="ncv-legend-dot a"></span>{selectedSpeciesA?.common_name}</span>
            <span><span className="ncv-legend-dot b"></span>{selectedSpeciesB?.common_name}</span>
          </div>
        </div>

        {/* AI 分析 */}
        <div className="ncv-ai-section">
          <div className="ncv-ai-header">
            <div className="ncv-ai-title">
              <Sparkles size={16} />
              <span>AI 深度分析</span>
            </div>
            {!aiCompareResult && (
              <button className="ncv-ai-btn" onClick={handleAiCompare} disabled={aiLoading}>
                {aiLoading ? (
                  <>
                    <RefreshCw size={14} className="spinning" />
                    <span>分析中...</span>
                  </>
                ) : (
                  <>
                    <Dna size={14} />
                    <span>开始分析</span>
                  </>
                )}
              </button>
            )}
          </div>

          {aiCompareResult ? (
            <div className="ncv-ai-result">
              <div className="ncv-ai-metrics">
                <div className="ncv-ai-metric">
                  <span className="ncv-ai-metric-label">向量相似度</span>
                  <span className="ncv-ai-metric-value">{(aiCompareResult.similarity * 100).toFixed(1)}%</span>
                  <span className="ncv-ai-metric-hint">基于物种描述的语义嵌入向量</span>
                </div>
                <div className="ncv-ai-metric">
                  <span className="ncv-ai-metric-label">演化关系判定</span>
                  <span className="ncv-ai-metric-value highlight">{aiCompareResult.relationship}</span>
                  <span className="ncv-ai-metric-hint">AI推断的亲缘/竞争关系</span>
                </div>
              </div>
              {aiCompareResult.details && (
                <div className="ncv-ai-details">
                  {aiCompareResult.details.same_habitat !== undefined && (
                    <div className="ncv-ai-detail">
                      <span>栖息地重叠</span>
                      <span className={aiCompareResult.details.same_habitat ? 'yes' : 'no'}>
                        {aiCompareResult.details.same_habitat ? '✓ 是' : '✗ 否'}
                      </span>
                    </div>
                  )}
                  {aiCompareResult.details.trophic_difference !== undefined && (
                    <div className="ncv-ai-detail">
                      <span>营养级差异</span>
                      <span>{aiCompareResult.details.trophic_difference.toFixed(2)} 级</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="ncv-ai-placeholder">
              <Sparkles size={24} />
              <div className="ncv-ai-placeholder-text">
                <span>AI 深度分析</span>
                <p>使用语义嵌入向量分析两个物种的相似度，并推断它们的演化关系和竞争模式</p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  return createPortal(
    <div className={`ncv-backdrop ${mounted ? 'visible' : ''}`} onClick={onClose}>
      <div className={`ncv-modal ${mounted ? 'visible' : ''}`} onClick={(e) => e.stopPropagation()}>
        {/* 装饰背景 */}
        <div className="ncv-bg-glow ncv-bg-glow-1"></div>
        <div className="ncv-bg-glow ncv-bg-glow-2"></div>
        <div className="ncv-bg-pattern"></div>

        {/* 头部 */}
        <header className="ncv-header">
          <div className="ncv-header-left">
            <div className="ncv-header-icon">🔬</div>
            <div className="ncv-header-text">
              <h1>生态位对比分析</h1>
              <p>分析两个物种的生态位重叠程度和竞争关系</p>
            </div>
          </div>
          <div className="ncv-header-actions">
            {step === 'result' && (
              <button className="ncv-reset-btn" onClick={handleReset}>
                <RefreshCw size={16} />
                <span>重新选择</span>
              </button>
            )}
            <button className="ncv-close-btn" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </header>

        {/* 错误提示 */}
        {error && (
          <div className="ncv-error">
            <AlertTriangle size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}

        {/* 主内容区 */}
        <main className="ncv-main custom-scrollbar">
          {/* 说明区 */}
          {step === 'select' && (
            <div className="ncv-intro">
              <div className="ncv-intro-icon">💡</div>
              <div className="ncv-intro-content">
                <h3>什么是生态位对比？</h3>
                <p>
                  生态位是指一个物种在生态系统中所占据的位置，包括它利用的资源、活动的时间和空间等。
                  通过对比两个物种的生态位，可以判断它们之间的<strong>竞争关系</strong>和<strong>共存可能性</strong>。
                </p>
                <div className="ncv-intro-tips">
                  <span><strong>高重叠</strong> = 强竞争，可能导致竞争排斥</span>
                  <span><strong>低重叠</strong> = 可以共存，各取所需</span>
                </div>
              </div>
            </div>
          )}

          {/* 物种选择区 */}
          <div className={`ncv-selection ${step === 'result' ? 'compact' : ''}`}>
            <div className="ncv-cards-row">
              {renderSpeciesCard('A', selectedSpeciesA, activeSelector === 'A')}
              
              <div className="ncv-vs">
                <div className="ncv-vs-line"></div>
                <div className="ncv-vs-badge">
                  {step === 'result' ? <ArrowRight size={16} /> : 'VS'}
                </div>
                <div className="ncv-vs-line"></div>
              </div>

              {renderSpeciesCard('B', selectedSpeciesB, activeSelector === 'B')}
            </div>

            {/* 物种选择器弹出层 */}
            {activeSelector && renderSpeciesList()}

            {/* 对比按钮 */}
            {step === 'select' && (
              <div className="ncv-action">
                <button
                  className={`ncv-compare-btn ${selectedA && selectedB ? 'ready' : ''}`}
                  onClick={handleCompare}
                  disabled={!selectedA || !selectedB || loading}
                >
                  {loading ? (
                    <>
                      <RefreshCw size={18} className="spinning" />
                      <span>正在分析...</span>
                    </>
                  ) : (
                    <>
                      <Zap size={18} />
                      <span>开始对比分析</span>
                      <ChevronRight size={18} />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* 对比结果 */}
          {step === 'result' && renderResult()}
        </main>
      </div>
    </div>,
    document.body
  );
}
