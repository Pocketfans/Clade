import { useEffect, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import { Sparkles, RefreshCw, Search, Filter, Zap, Target, Layers, TrendingUp } from "lucide-react";
import type { SpeciesListItem, NicheCompareResult } from "@/services/api.types";
import { fetchSpeciesList, compareNiche } from "@/services/api";
import { embeddingApi, type SpeciesCompareResponse } from "../services/embedding.api";

interface NicheCompareViewProps {
  onClose?: () => void;
}

const ROLE_CONFIG: Record<string, { color: string; icon: string; bg: string }> = {
  "生产者": { color: "#22c55e", icon: "🌱", bg: "rgba(34, 197, 94, 0.15)" },
  "草食者": { color: "#3b82f6", icon: "🐰", bg: "rgba(59, 130, 246, 0.15)" },
  "肉食者": { color: "#ef4444", icon: "🦁", bg: "rgba(239, 68, 68, 0.15)" },
  "杂食者": { color: "#f59e0b", icon: "🦊", bg: "rgba(245, 158, 11, 0.15)" },
  "分解者": { color: "#8b5cf6", icon: "🍄", bg: "rgba(139, 92, 246, 0.15)" },
};

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  alive: { color: "#22c55e", label: "存活" },
  extinct: { color: "#ef4444", label: "灭绝" },
  critical: { color: "#f59e0b", label: "濒危" },
};

export function NicheCompareView({ onClose }: NicheCompareViewProps) {
  const [speciesList, setSpeciesList] = useState<SpeciesListItem[]>([]);
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<NicheCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // AI 对比状态
  const [aiCompareResult, setAiCompareResult] = useState<SpeciesCompareResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [searchA, setSearchA] = useState("");
  const [searchB, setSearchB] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterRole, setFilterRole] = useState<string>("all");

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

  const filterSpecies = (species: SpeciesListItem[], search: string) => {
    let filtered = species;

    if (filterStatus !== "all") {
      filtered = filtered.filter((s) => s.status === filterStatus);
    }

    if (filterRole !== "all") {
      filtered = filtered.filter((s) => s.ecological_role === filterRole);
    }

    if (search) {
      const searchLower = search.toLowerCase();
      filtered = filtered.filter(
        (s) =>
          s.common_name.toLowerCase().includes(searchLower) ||
          s.latin_name.toLowerCase().includes(searchLower) ||
          s.lineage_code.toLowerCase().includes(searchLower)
      );
    }

    return filtered;
  };

  const filteredSpeciesA = filterSpecies(speciesList, searchA);
  const filteredSpeciesB = filterSpecies(speciesList, searchB);

  const selectedSpeciesA = useMemo(
    () => speciesList.find((s) => s.lineage_code === selectedA),
    [speciesList, selectedA]
  );
  const selectedSpeciesB = useMemo(
    () => speciesList.find((s) => s.lineage_code === selectedB),
    [speciesList, selectedB]
  );

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

  const getRoleConfig = (role: string) => {
    return ROLE_CONFIG[role] || { color: "#6b7280", icon: "❓", bg: "rgba(107, 114, 128, 0.15)" };
  };

  const getStatusConfig = (status: string) => {
    return STATUS_CONFIG[status] || { color: "#9ca3af", label: status };
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  const getIntensityLevel = (value: number): { color: string; label: string; icon: string } => {
    if (value < 0.3) return { color: "#22c55e", label: "低", icon: "🟢" };
    if (value < 0.6) return { color: "#f59e0b", label: "中", icon: "🟡" };
    return { color: "#ef4444", label: "高", icon: "🔴" };
  };

  const renderSpeciesSelector = (
    side: "A" | "B",
    selected: string | null,
    setSelected: (v: string | null) => void,
    search: string,
    setSearch: (v: string) => void,
    filteredList: SpeciesListItem[]
  ) => {
    const accentColor = side === "A" ? "#3b82f6" : "#10b981";
    const label = side === "A" ? "物种 A (基准)" : "物种 B (对比)";
    const selectedSpecies = side === "A" ? selectedSpeciesA : selectedSpeciesB;

    return (
      <div className="niche-species-selector">
        <div className="niche-selector-header" style={{ borderColor: accentColor }}>
          <div className="niche-selector-icon" style={{ backgroundColor: `${accentColor}20`, borderColor: `${accentColor}40` }}>
            {side === "A" ? "🔬" : "🧬"}
          </div>
          <div className="niche-selector-title">
            <span style={{ color: accentColor }}>{label}</span>
            {selectedSpecies && (
              <span className="niche-selector-selected">{selectedSpecies.common_name}</span>
            )}
          </div>
        </div>

        <div className="niche-search-box">
          <Search size={16} className="niche-search-icon" />
          <input
            type="text"
            placeholder="搜索物种名、学名或代码..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="niche-search-input"
          />
          {search && (
            <button className="niche-search-clear" onClick={() => setSearch("")}>
              ×
            </button>
          )}
        </div>

        <div className="niche-species-list custom-scrollbar">
          {filteredList.length === 0 ? (
            <div className="niche-empty-list">
              <span>🔍</span>
              <span>未找到匹配的物种</span>
            </div>
          ) : (
            filteredList.map((species) => {
              const roleConfig = getRoleConfig(species.ecological_role);
              const statusConfig = getStatusConfig(species.status);
              const isSelected = selected === species.lineage_code;

              return (
                <button
                  key={species.lineage_code}
                  className={`niche-species-item ${isSelected ? "selected" : ""}`}
                  style={{
                    borderLeftColor: isSelected ? accentColor : "transparent",
                    backgroundColor: isSelected ? `${accentColor}15` : undefined,
                  }}
                  onClick={() => setSelected(species.lineage_code)}
                >
                  <div className="niche-species-main">
                    <div className="niche-species-name-row">
                      <span className="niche-species-icon">{roleConfig.icon}</span>
                      <span className="niche-species-name">{species.common_name}</span>
                      <span className="niche-species-code">[{species.lineage_code}]</span>
                    </div>
                    <div className="niche-species-latin">{species.latin_name}</div>
                  </div>
                  <div className="niche-species-meta">
                    <span
                      className="niche-species-role"
                      style={{ backgroundColor: roleConfig.bg, color: roleConfig.color }}
                    >
                      {species.ecological_role}
                    </span>
                    <span className="niche-species-pop">
                      <span
                        className="niche-status-dot"
                        style={{ backgroundColor: statusConfig.color }}
                      />
                      {formatNumber(species.population)}
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  };

  const renderCompareResult = () => {
    if (!compareResult) return null;

    const intensityLevel = getIntensityLevel(compareResult.competition_intensity);

    return (
      <div className="niche-result fade-in">
        {/* 核心指标卡片 */}
        <div className="niche-metrics-row">
          <div className="niche-metric-card similarity">
            <div className="niche-metric-icon">
              <Layers size={24} />
            </div>
            <div className="niche-metric-content">
              <div className="niche-metric-label">生态位相似度</div>
              <div className="niche-metric-value">
                {(compareResult.similarity * 100).toFixed(1)}
                <span className="niche-metric-unit">%</span>
              </div>
              <div className="niche-metric-bar">
                <div
                  className="niche-metric-bar-fill similarity"
                  style={{ width: `${compareResult.similarity * 100}%` }}
                />
              </div>
              <div className="niche-metric-hint">基于描述向量的余弦相似度</div>
            </div>
          </div>

          <div className="niche-metric-card overlap">
            <div className="niche-metric-icon">
              <Target size={24} />
            </div>
            <div className="niche-metric-content">
              <div className="niche-metric-label">生态位重叠度</div>
              <div className="niche-metric-value">
                {(compareResult.overlap * 100).toFixed(1)}
                <span className="niche-metric-unit">%</span>
              </div>
              <div className="niche-metric-bar">
                <div
                  className="niche-metric-bar-fill overlap"
                  style={{ width: `${compareResult.overlap * 100}%` }}
                />
              </div>
              <div className="niche-metric-hint">资源利用的重叠程度</div>
            </div>
          </div>

          <div className="niche-metric-card competition">
            <div className="niche-metric-icon" style={{ color: intensityLevel.color }}>
              <Zap size={24} />
            </div>
            <div className="niche-metric-content">
              <div className="niche-metric-label">
                竞争强度
                <span className="niche-intensity-badge" style={{ backgroundColor: `${intensityLevel.color}20`, color: intensityLevel.color }}>
                  {intensityLevel.icon} {intensityLevel.label}
                </span>
              </div>
              <div className="niche-metric-value" style={{ color: intensityLevel.color }}>
                {(compareResult.competition_intensity * 100).toFixed(1)}
                <span className="niche-metric-unit">%</span>
              </div>
              <div className="niche-metric-bar">
                <div
                  className="niche-metric-bar-fill competition"
                  style={{
                    width: `${compareResult.competition_intensity * 100}%`,
                    backgroundColor: intensityLevel.color,
                  }}
                />
              </div>
              <div className="niche-metric-hint">综合考虑生物量的竞争压力</div>
            </div>
          </div>
        </div>

        {/* 维度对比 */}
        <div className="niche-dimensions-section">
          <div className="niche-section-header">
            <TrendingUp size={18} />
            <span>生态位维度对比</span>
          </div>
          <div className="niche-dimensions-grid">
            {Object.entries(compareResult.niche_dimensions).map(([dimension, values]) => {
              const valueA = values.species_a;
              const valueB = values.species_b;
              const maxValue = Math.max(valueA, valueB) || 1;
              const percentA = (valueA / maxValue) * 100;
              const percentB = (valueB / maxValue) * 100;
              const diff = valueA - valueB;
              const diffPercent = maxValue > 0 ? Math.abs(diff / maxValue * 100).toFixed(0) : 0;

              return (
                <div key={dimension} className="niche-dimension-row">
                  <div className="niche-dimension-label">{dimension}</div>
                  <div className="niche-dimension-compare">
                    <div className="niche-dimension-side left">
                      <span className="niche-dimension-value">{formatNumber(valueA)}</span>
                      <div className="niche-dimension-bar-wrapper">
                        <div
                          className="niche-dimension-bar left"
                          style={{ width: `${percentA}%` }}
                        />
                      </div>
                    </div>
                    <div className="niche-dimension-vs">
                      <span className={`niche-dimension-diff ${diff > 0 ? 'positive' : diff < 0 ? 'negative' : ''}`}>
                        {diff > 0 ? '+' : ''}{diffPercent}%
                      </span>
                    </div>
                    <div className="niche-dimension-side right">
                      <div className="niche-dimension-bar-wrapper">
                        <div
                          className="niche-dimension-bar right"
                          style={{ width: `${percentB}%` }}
                        />
                      </div>
                      <span className="niche-dimension-value">{formatNumber(valueB)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 物种详情对比 */}
        <div className="niche-species-details">
          <div className="niche-species-detail-card left">
            <div className="niche-detail-header">
              <span className="niche-detail-dot" style={{ backgroundColor: "#3b82f6" }} />
              <div>
                <h4>{compareResult.species_a.common_name}</h4>
                <span className="niche-detail-latin">{compareResult.species_a.latin_name}</span>
              </div>
            </div>
            <p className="niche-detail-desc">{compareResult.species_a.description}</p>
          </div>

          <div className="niche-species-detail-card right">
            <div className="niche-detail-header">
              <span className="niche-detail-dot" style={{ backgroundColor: "#10b981" }} />
              <div>
                <h4>{compareResult.species_b.common_name}</h4>
                <span className="niche-detail-latin">{compareResult.species_b.latin_name}</span>
              </div>
            </div>
            <p className="niche-detail-desc">{compareResult.species_b.description}</p>
          </div>
        </div>

        {/* AI 深度分析 */}
        <div className="niche-ai-section">
          <div className="niche-ai-header">
            <div className="niche-ai-title">
              <Sparkles size={18} />
              <span>AI 向量相似度分析</span>
            </div>
            {!aiCompareResult && (
              <button onClick={handleAiCompare} disabled={aiLoading} className="niche-ai-btn">
                {aiLoading ? (
                  <>
                    <RefreshCw size={14} className="spinning" />
                    <span>分析中...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={14} />
                    <span>开始 AI 分析</span>
                  </>
                )}
              </button>
            )}
          </div>

          {aiCompareResult ? (
            <div className="niche-ai-result">
              <div className="niche-ai-metrics">
                <div className="niche-ai-metric">
                  <div className="niche-ai-metric-label">向量相似度</div>
                  <div className="niche-ai-metric-value">
                    {(aiCompareResult.similarity * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="niche-ai-metric">
                  <div className="niche-ai-metric-label">关系类型</div>
                  <div className="niche-ai-relationship">{aiCompareResult.relationship}</div>
                </div>
              </div>

              {aiCompareResult.details && (
                <div className="niche-ai-details">
                  {aiCompareResult.details.same_habitat !== undefined && (
                    <div className="niche-ai-detail-row">
                      <span>栖息地相同</span>
                      <span
                        className={`niche-ai-detail-value ${aiCompareResult.details.same_habitat ? "yes" : "no"}`}
                      >
                        {aiCompareResult.details.same_habitat ? "✓ 是" : "✗ 否"}
                      </span>
                    </div>
                  )}
                  {aiCompareResult.details.trophic_difference !== undefined && (
                    <div className="niche-ai-detail-row">
                      <span>营养级差异</span>
                      <span className="niche-ai-detail-value mono">
                        {aiCompareResult.details.trophic_difference.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="niche-ai-placeholder">
              <Sparkles size={24} />
              <p>点击上方按钮，使用 AI 分析两个物种的向量相似度和演化关系</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  return createPortal(
    <div className={`niche-backdrop ${mounted ? "visible" : ""}`} onClick={onClose}>
      <div
        className={`niche-panel ${mounted ? "visible" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 装饰光效 */}
        <div className="niche-glow-tl" />
        <div className="niche-glow-br" />

        {/* 头部 */}
        <header className="niche-header">
          <div className="niche-header-left">
            <div className="niche-header-icon">🔬</div>
            <div className="niche-header-titles">
              <h1>生态位对比分析</h1>
              <p>Ecological Niche Comparison</p>
            </div>
          </div>
          <button className="niche-close-btn" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </header>

        {/* 主内容 */}
        <main className="niche-main custom-scrollbar">
          {/* 错误提示 */}
          {error && (
            <div className="niche-error">
              <span>⚠️</span>
              <span>{error}</span>
              <button onClick={() => setError(null)}>×</button>
            </div>
          )}

          {/* 筛选栏 */}
          <div className="niche-filter-bar">
            <div className="niche-filter-group">
              <Filter size={14} />
              <span>筛选:</span>
            </div>
            <div className="niche-filter-item">
              <label>状态</label>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="niche-filter-select"
              >
                <option value="all">全部</option>
                <option value="alive">存活</option>
                <option value="extinct">灭绝</option>
                <option value="critical">濒危</option>
              </select>
            </div>
            <div className="niche-filter-item">
              <label>生态角色</label>
              <select
                value={filterRole}
                onChange={(e) => setFilterRole(e.target.value)}
                className="niche-filter-select"
              >
                <option value="all">全部</option>
                <option value="生产者">🌱 生产者</option>
                <option value="草食者">🐰 草食者</option>
                <option value="肉食者">🦁 肉食者</option>
                <option value="杂食者">🦊 杂食者</option>
              </select>
            </div>
            <div className="niche-filter-stats">
              共 <strong>{speciesList.length}</strong> 个物种
            </div>
          </div>

          {/* 物种选择器 */}
          <div className="niche-selectors-grid">
            {renderSpeciesSelector("A", selectedA, setSelectedA, searchA, setSearchA, filteredSpeciesA)}

            <div className="niche-vs-divider">
              <div className="niche-vs-line" />
              <div className="niche-vs-badge">VS</div>
              <div className="niche-vs-line" />
            </div>

            {renderSpeciesSelector("B", selectedB, setSelectedB, searchB, setSearchB, filteredSpeciesB)}
          </div>

          {/* 对比按钮 */}
          <div className="niche-compare-action">
            <button
              onClick={handleCompare}
              disabled={!selectedA || !selectedB || loading}
              className={`niche-compare-btn ${selectedA && selectedB ? "ready" : ""}`}
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
                </>
              )}
            </button>
            {selectedA && selectedB && (
              <div className="niche-compare-preview">
                <span className="preview-item a">{selectedSpeciesA?.common_name}</span>
                <span className="preview-vs">⚔️</span>
                <span className="preview-item b">{selectedSpeciesB?.common_name}</span>
              </div>
            )}
          </div>

          {/* 对比结果 */}
          {renderCompareResult()}
        </main>
      </div>
    </div>,
    document.body
  );
}
