/**
 * HybridizationPanel - 物种杂交面板
 * 重新设计的现代化界面，提供直观的物种配对与杂交预览
 * 
 * 【强行杂交】支持跨属/幻想杂交，创造嵌合体生物
 */
import { useEffect, useState, useCallback } from "react";
import { 
  Dna, GitMerge, Search, Zap, Check, X, AlertTriangle, 
  ArrowRight, Sparkles, Heart, Shield, ChevronDown, Skull, FlaskConical
} from "lucide-react";
import { AnalysisPanel, AnalysisSection, ActionButton, StatCard, EmptyState } from "./common/AnalysisPanel";

interface SpeciesInfo {
  lineage_code: string;
  common_name: string;
  latin_name: string;
  genus_code: string;
}

interface HybridCandidate {
  species_a: SpeciesInfo;
  species_b: SpeciesInfo;
  fertility: number;
  genus: string;
}

interface HybridPreview {
  can_hybridize: boolean;
  fertility?: number;
  energy_cost?: number;
  can_afford?: boolean;
  reason?: string;
  preview?: {
    lineage_code: string;
    common_name: string;
    predicted_trophic_level: number;
    combined_capabilities: string[];
  };
}

interface ForceHybridPreview {
  can_force_hybridize: boolean;
  reason: string;
  can_normal_hybridize: boolean;
  normal_fertility: number;
  energy_cost: number;
  can_afford: boolean;
  current_energy: number;
  preview: {
    type: string;
    estimated_fertility: number;
    stability: string;
    parent_a: { code: string; name: string; trophic: number };
    parent_b: { code: string; name: string; trophic: number };
    warnings: string[];
  };
}

interface AllSpecies {
  lineage_code: string;
  common_name: string;
  latin_name: string;
  status: string;
  population: number;
  ecological_role: string;
}

interface Props {
  onClose: () => void;
  onSuccess?: () => void;
}

export function HybridizationPanel({ onClose, onSuccess }: Props) {
  // 模式切换：normal（普通杂交）| forced（强行杂交）
  const [mode, setMode] = useState<"normal" | "forced">("normal");
  
  // 普通杂交状态
  const [candidates, setCandidates] = useState<HybridCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const [selectedPair, setSelectedPair] = useState<HybridCandidate | null>(null);
  const [preview, setPreview] = useState<HybridPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  
  const [genusFilter, setGenusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // 强行杂交状态
  const [allSpecies, setAllSpecies] = useState<AllSpecies[]>([]);
  const [forceSpeciesA, setForceSpeciesA] = useState<AllSpecies | null>(null);
  const [forceSpeciesB, setForceSpeciesB] = useState<AllSpecies | null>(null);
  const [forcePreview, setForcePreview] = useState<ForceHybridPreview | null>(null);
  const [forceSearchA, setForceSearchA] = useState("");
  const [forceSearchB, setForceSearchB] = useState("");

  useEffect(() => {
    fetchCandidates();
    fetchAllSpecies();
  }, []);

  async function fetchAllSpecies() {
    try {
      // 正确的API端点是 /api/species/list
      const response = await fetch("/api/species/list");
      const data = await response.json();
      // 支持多种可能的数据结构
      const speciesList = data.species || data || [];
      const alive = speciesList.filter((s: AllSpecies) => s.status === "alive");
      console.log("获取到存活物种:", alive.length, "个");
      setAllSpecies(alive);
    } catch (e) {
      console.error("获取物种列表失败:", e);
    }
  }

  async function fetchCandidates() {
    try {
      setLoading(true);
      const response = await fetch("/api/hybridization/candidates");
      const data = await response.json();
      setCandidates(data.candidates || []);
    } catch (e) {
      console.error("获取杂交候选失败:", e);
      setError("获取杂交候选失败");
    } finally {
      setLoading(false);
    }
  }

  const fetchPreview = useCallback(async (pair: HybridCandidate) => {
    try {
      setPreviewLoading(true);
      const response = await fetch(
        `/api/hybridization/preview?species_a=${pair.species_a.lineage_code}&species_b=${pair.species_b.lineage_code}`
      );
      const data = await response.json();
      setPreview(data);
    } catch (e) {
      console.error("获取预览失败:", e);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedPair) {
      fetchPreview(selectedPair);
    } else {
      setPreview(null);
    }
  }, [selectedPair, fetchPreview]);

  // 强行杂交预览
  useEffect(() => {
    if (mode === "forced" && forceSpeciesA && forceSpeciesB) {
      fetchForcePreview();
    } else {
      setForcePreview(null);
    }
  }, [mode, forceSpeciesA, forceSpeciesB]);

  async function fetchForcePreview() {
    if (!forceSpeciesA || !forceSpeciesB) return;
    try {
      setPreviewLoading(true);
      const response = await fetch(
        `/api/hybridization/force/preview?species_a=${forceSpeciesA.lineage_code}&species_b=${forceSpeciesB.lineage_code}`
      );
      const data = await response.json();
      setForcePreview(data);
    } catch (e) {
      console.error("获取强行杂交预览失败:", e);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function executeForceHybridization() {
    if (!forceSpeciesA || !forceSpeciesB) return;
    
    try {
      setExecuting(true);
      setError(null);
      setSuccess(null);
      
      const response = await fetch("/api/hybridization/force/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          species_a: forceSpeciesA.lineage_code,
          species_b: forceSpeciesB.lineage_code,
        }),
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || "强行杂交失败");
      }
      
      setSuccess(`🧬 成功创造嵌合体：${data.chimera.common_name}！消耗 ${data.energy_spent} 能量`);
      setForceSpeciesA(null);
      setForceSpeciesB(null);
      fetchAllSpecies();
      onSuccess?.();
      
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "强行杂交失败");
    } finally {
      setExecuting(false);
    }
  }

  async function executeHybridization() {
    if (!selectedPair) return;
    
    try {
      setExecuting(true);
      setError(null);
      setSuccess(null);
      
      const response = await fetch("/api/hybridization/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          species_a: selectedPair.species_a.lineage_code,
          species_b: selectedPair.species_b.lineage_code,
        }),
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || "杂交失败");
      }
      
      setSuccess(`成功创建杂交种：${data.hybrid.common_name}！消耗 ${data.energy_spent} 能量`);
      setSelectedPair(null);
      fetchCandidates();
      onSuccess?.();
      
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "杂交失败");
    } finally {
      setExecuting(false);
    }
  }

  const allGenera = [...new Set(candidates.map(c => c.genus))];
  
  const filteredCandidates = candidates.filter(c => {
    if (genusFilter !== "all" && c.genus !== genusFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        c.species_a.common_name.toLowerCase().includes(query) ||
        c.species_a.lineage_code.toLowerCase().includes(query) ||
        c.species_b.common_name.toLowerCase().includes(query) ||
        c.species_b.lineage_code.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const getFertilityColor = (fertility: number) => {
    if (fertility >= 0.8) return '#22c55e';
    if (fertility >= 0.5) return '#f59e0b';
    return '#ef4444';
  };

  // 强行杂交的物种过滤
  const filteredForceSpeciesA = allSpecies.filter(s => {
    if (forceSearchA) {
      const q = forceSearchA.toLowerCase();
      return s.common_name.toLowerCase().includes(q) || s.lineage_code.toLowerCase().includes(q);
    }
    return true;
  }).filter(s => s.lineage_code !== forceSpeciesB?.lineage_code);

  const filteredForceSpeciesB = allSpecies.filter(s => {
    if (forceSearchB) {
      const q = forceSearchB.toLowerCase();
      return s.common_name.toLowerCase().includes(q) || s.lineage_code.toLowerCase().includes(q);
    }
    return true;
  }).filter(s => s.lineage_code !== forceSpeciesA?.lineage_code);

  return (
    <AnalysisPanel
      title={mode === "normal" ? "物种杂交" : "🧬 强行杂交实验"}
      icon={mode === "normal" ? <GitMerge size={20} /> : <FlaskConical size={20} />}
      accentColor={mode === "normal" ? "#10b981" : "#f43f5e"}
      onClose={onClose}
      size="large"
      showMaximize
    >
      <div className="hybridization-content">
        {/* 模式切换 */}
        <div className="mode-switcher">
          <button 
            className={`mode-btn ${mode === "normal" ? "active" : ""}`}
            onClick={() => setMode("normal")}
          >
            <Heart size={16} />
            普通杂交
          </button>
          <button 
            className={`mode-btn forced ${mode === "forced" ? "active" : ""}`}
            onClick={() => setMode("forced")}
          >
            <Skull size={16} />
            强行杂交
            <span className="mode-badge">疯狂实验</span>
          </button>
        </div>

        {/* 消息提示 */}
        {error && (
          <div className="message-banner error">
            <AlertTriangle size={18} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}
        {success && (
          <div className="message-banner success">
            <Check size={18} />
            <span>{success}</span>
            <button onClick={() => setSuccess(null)}>×</button>
          </div>
        )}

        {mode === "normal" ? (
          /* ========== 普通杂交模式 ========== */
          <div className="hybridization-layout">
            {/* 左侧：候选列表 */}
            <div className="candidates-panel">
              <div className="panel-header">
                <h3>
                  <Dna size={18} />
                  可杂交物种对
                  <span className="count-badge">{filteredCandidates.length}</span>
                </h3>
              </div>

            {/* 筛选器 */}
            <div className="filter-bar">
              <div className="search-box">
                <Search size={16} />
                <input
                  type="text"
                  placeholder="搜索物种..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div className="genus-select-wrapper">
                <select 
                  value={genusFilter}
                  onChange={(e) => setGenusFilter(e.target.value)}
                  className="genus-select"
                >
                  <option value="all">所有属</option>
                  {allGenera.map(g => (
                    <option key={g} value={g}>{g} 属</option>
                  ))}
                </select>
                <ChevronDown size={14} className="select-arrow" />
              </div>
            </div>
            
            {/* 候选列表 */}
            <div className="candidates-list">
              {loading ? (
                <div className="loading-state">
                  <div className="loading-spinner" />
                  <span>加载杂交候选中...</span>
                </div>
              ) : filteredCandidates.length === 0 ? (
                <EmptyState
                  icon="🔬"
                  title="暂无可杂交物种对"
                  description="杂交需要同属且遗传距离较近的物种。尝试演化更多同属物种后再试。"
                />
              ) : (
                filteredCandidates.map((pair) => (
                  <CandidateCard
                    key={`${pair.species_a.lineage_code}-${pair.species_b.lineage_code}`}
                    pair={pair}
                    selected={selectedPair === pair}
                    onSelect={() => setSelectedPair(pair)}
                    fertilityColor={getFertilityColor(pair.fertility)}
                  />
                ))
              )}
            </div>
          </div>

          {/* 右侧：预览面板 */}
          <div className="preview-panel">
            {!selectedPair ? (
              <div className="preview-placeholder">
                <div className="placeholder-icon">
                  <GitMerge size={48} strokeWidth={1} />
                </div>
                <h4>选择物种对</h4>
                <p>从左侧列表选择一对物种，查看杂交预览并执行杂交</p>
              </div>
            ) : previewLoading ? (
              <div className="loading-state">
                <div className="loading-spinner" />
                <span>计算杂交预览...</span>
              </div>
            ) : preview ? (
              <div className="preview-content">
                {/* 亲本展示 */}
                <div className="parents-display">
                  <div className="parent-card">
                    <div className="parent-code">{selectedPair.species_a.lineage_code}</div>
                    <div className="parent-name">{selectedPair.species_a.common_name}</div>
                    <div className="parent-latin">{selectedPair.species_a.latin_name}</div>
                  </div>
                  <div className="merge-indicator">
                    <Heart size={24} />
                    <span>杂交</span>
                  </div>
                  <div className="parent-card">
                    <div className="parent-code">{selectedPair.species_b.lineage_code}</div>
                    <div className="parent-name">{selectedPair.species_b.common_name}</div>
                    <div className="parent-latin">{selectedPair.species_b.latin_name}</div>
                  </div>
                </div>

                {preview.can_hybridize && preview.preview ? (
                  <>
                    {/* 后代预览 */}
                    <AnalysisSection 
                      title="后代预览" 
                      icon={<Sparkles size={16} />}
                      accentColor="#a855f7"
                    >
                      <div className="offspring-preview">
                        <div className="offspring-header">
                          <div className="offspring-code">{preview.preview.lineage_code}</div>
                          <div className="offspring-name">{preview.preview.common_name}</div>
                        </div>
                        
                        <div className="offspring-stats">
                          <div className="stat-item">
                            <span className="stat-label">可育性</span>
                            <div className="fertility-bar">
                              <div 
                                className="fertility-fill"
                                style={{ 
                                  width: `${preview.fertility! * 100}%`,
                                  background: getFertilityColor(preview.fertility!)
                                }}
                              />
                            </div>
                            <span 
                              className="stat-value"
                              style={{ color: getFertilityColor(preview.fertility!) }}
                            >
                              {(preview.fertility! * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div className="stat-item">
                            <span className="stat-label">营养级</span>
                            <span className="stat-value">
                              T{preview.preview.predicted_trophic_level.toFixed(1)}
                            </span>
                          </div>
                        </div>

                        {preview.preview.combined_capabilities.length > 0 && (
                          <div className="capabilities-section">
                            <div className="cap-label">继承能力</div>
                            <div className="cap-list">
                              {preview.preview.combined_capabilities.map(cap => (
                                <span key={cap} className="cap-tag">
                                  <Shield size={12} />
                                  {cap}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </AnalysisSection>

                    {/* 能量消耗 */}
                    <div className="energy-cost-section">
                      <div className="cost-info">
                        <Zap size={24} />
                        <div className="cost-details">
                          <span className="cost-value">{preview.energy_cost}</span>
                          <span className="cost-label">能量消耗</span>
                        </div>
                      </div>
                      {!preview.can_afford && (
                        <div className="cost-warning">
                          <AlertTriangle size={16} />
                          <span>能量不足</span>
                        </div>
                      )}
                    </div>

                    {/* 执行按钮 */}
                    <ActionButton
                      variant="success"
                      size="large"
                      fullWidth
                      icon={<GitMerge size={20} />}
                      onClick={executeHybridization}
                      disabled={!preview.can_afford}
                      loading={executing}
                    >
                      {executing ? "杂交中..." : "执行杂交"}
                    </ActionButton>
                  </>
                ) : (
                  <div className="cannot-hybridize">
                    <AlertTriangle size={48} strokeWidth={1} />
                    <h4>无法杂交</h4>
                    <p>{preview.reason || "未知原因"}</p>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
        ) : (
          /* ========== 强行杂交模式 ========== */
          <div className="force-hybridization-layout">
            {/* 顶部警告横幅 */}
            <div className="force-warning-banner">
              <div className="warning-icon-pulse">
                <FlaskConical size={28} />
              </div>
              <div className="warning-text">
                <strong>🔬 疯狂科学家实验室</strong>
                <p>打破自然界限，将任意两个物种强行融合成嵌合体！这种违背自然规律的操作需要消耗 <span className="energy-highlight">50 能量</span>。</p>
              </div>
              <div className="species-count-badge">
                {allSpecies.length} 个可用物种
              </div>
            </div>

            {/* 物种选择区 - 改进布局 */}
            <div className="force-selection-area">
              {/* 选择物种A */}
              <div className={`force-species-selector ${forceSpeciesA ? 'has-selection' : ''}`}>
                <div className="selector-header">
                  <div className="selector-title">
                    <span className="selector-emoji">🧫</span>
                    <span className="selector-label">第一个物种</span>
                  </div>
                  {forceSpeciesA && (
                    <button className="clear-btn" onClick={() => setForceSpeciesA(null)}>
                      <X size={14} /> 移除
                    </button>
                  )}
                </div>
                {forceSpeciesA ? (
                  <div className="selected-species-card glowing">
                    <div className="species-avatar">🦠</div>
                    <div className="species-info">
                      <div className="species-code">{forceSpeciesA.lineage_code}</div>
                      <div className="species-name">{forceSpeciesA.common_name}</div>
                      <div className="species-meta">
                        <span className="species-role">{forceSpeciesA.ecological_role}</span>
                        <span className="species-population">🔢 {forceSpeciesA.population.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="species-picker">
                    <div className="search-box enhanced">
                      <Search size={18} />
                      <input
                        type="text"
                        placeholder="输入物种名称或代码搜索..."
                        value={forceSearchA}
                        onChange={(e) => setForceSearchA(e.target.value)}
                      />
                      {forceSearchA && (
                        <button className="search-clear" onClick={() => setForceSearchA("")}>
                          <X size={14} />
                        </button>
                      )}
                    </div>
                    <div className="species-list">
                      {allSpecies.length === 0 ? (
                        <div className="empty-species-hint">
                          <span className="empty-icon">🔍</span>
                          <span>没有找到存活的物种</span>
                          <span className="empty-sub">请先在模拟中创建一些物种</span>
                        </div>
                      ) : filteredForceSpeciesA.length === 0 ? (
                        <div className="empty-species-hint">
                          <span className="empty-icon">😕</span>
                          <span>没有匹配 "{forceSearchA}" 的物种</span>
                        </div>
                      ) : (
                        filteredForceSpeciesA.slice(0, 10).map((sp, idx) => (
                          <div 
                            key={sp.lineage_code} 
                            className="species-option"
                            style={{ animationDelay: `${idx * 30}ms` }}
                            onClick={() => { setForceSpeciesA(sp); setForceSearchA(""); }}
                          >
                            <div className="option-avatar">🧬</div>
                            <div className="option-info">
                              <span className="option-code">{sp.lineage_code}</span>
                              <span className="option-name">{sp.common_name}</span>
                            </div>
                            <span className="option-role">{sp.ecological_role}</span>
                          </div>
                        ))
                      )}
                      {filteredForceSpeciesA.length > 10 && (
                        <div className="more-hint">还有 {filteredForceSpeciesA.length - 10} 个物种...</div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* 融合指示器 - 动态效果 */}
              <div className={`force-merge-indicator ${forceSpeciesA && forceSpeciesB ? 'ready' : ''}`}>
                <div className="merge-icon-container">
                  <div className="merge-ring ring-1"></div>
                  <div className="merge-ring ring-2"></div>
                  <Skull size={36} />
                </div>
                <span className="merge-label">
                  {forceSpeciesA && forceSpeciesB ? '准备融合!' : '融合'}
                </span>
                <div className="merge-arrows">
                  <ArrowRight className="arrow-left" size={20} />
                  <ArrowRight className="arrow-right" size={20} />
                </div>
              </div>

              {/* 选择物种B */}
              <div className={`force-species-selector ${forceSpeciesB ? 'has-selection' : ''}`}>
                <div className="selector-header">
                  <div className="selector-title">
                    <span className="selector-emoji">🧪</span>
                    <span className="selector-label">第二个物种</span>
                  </div>
                  {forceSpeciesB && (
                    <button className="clear-btn" onClick={() => setForceSpeciesB(null)}>
                      <X size={14} /> 移除
                    </button>
                  )}
                </div>
                {forceSpeciesB ? (
                  <div className="selected-species-card glowing">
                    <div className="species-avatar">🦠</div>
                    <div className="species-info">
                      <div className="species-code">{forceSpeciesB.lineage_code}</div>
                      <div className="species-name">{forceSpeciesB.common_name}</div>
                      <div className="species-meta">
                        <span className="species-role">{forceSpeciesB.ecological_role}</span>
                        <span className="species-population">🔢 {forceSpeciesB.population.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="species-picker">
                    <div className="search-box enhanced">
                      <Search size={18} />
                      <input
                        type="text"
                        placeholder="输入物种名称或代码搜索..."
                        value={forceSearchB}
                        onChange={(e) => setForceSearchB(e.target.value)}
                      />
                      {forceSearchB && (
                        <button className="search-clear" onClick={() => setForceSearchB("")}>
                          <X size={14} />
                        </button>
                      )}
                    </div>
                    <div className="species-list">
                      {allSpecies.length === 0 ? (
                        <div className="empty-species-hint">
                          <span className="empty-icon">🔍</span>
                          <span>没有找到存活的物种</span>
                          <span className="empty-sub">请先在模拟中创建一些物种</span>
                        </div>
                      ) : filteredForceSpeciesB.length === 0 ? (
                        <div className="empty-species-hint">
                          <span className="empty-icon">😕</span>
                          <span>没有匹配 "{forceSearchB}" 的物种</span>
                        </div>
                      ) : (
                        filteredForceSpeciesB.slice(0, 10).map((sp, idx) => (
                          <div 
                            key={sp.lineage_code} 
                            className="species-option"
                            style={{ animationDelay: `${idx * 30}ms` }}
                            onClick={() => { setForceSpeciesB(sp); setForceSearchB(""); }}
                          >
                            <div className="option-avatar">🧬</div>
                            <div className="option-info">
                              <span className="option-code">{sp.lineage_code}</span>
                              <span className="option-name">{sp.common_name}</span>
                            </div>
                            <span className="option-role">{sp.ecological_role}</span>
                          </div>
                        ))
                      )}
                      {filteredForceSpeciesB.length > 10 && (
                        <div className="more-hint">还有 {filteredForceSpeciesB.length - 10} 个物种...</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 预览区 */}
            {forceSpeciesA && forceSpeciesB && (
              <div className="force-preview-area">
                {previewLoading ? (
                  <div className="loading-state">
                    <div className="loading-spinner" />
                    <span>分析嵌合体可行性...</span>
                  </div>
                ) : forcePreview ? (
                  <div className="force-preview-content">
                    <div className="chimera-preview-header">
                      <Sparkles size={24} />
                      <h3>嵌合体预览</h3>
                    </div>
                    
                    <div className="chimera-stats">
                      <div className="stat-row">
                        <span className="stat-label">预估可育性</span>
                        <span className="stat-value" style={{ color: forcePreview.preview.estimated_fertility > 0.05 ? '#f59e0b' : '#ef4444' }}>
                          {(forcePreview.preview.estimated_fertility * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="stat-row">
                        <span className="stat-label">基因稳定性</span>
                        <span className={`stability-badge ${forcePreview.preview.stability}`}>
                          {forcePreview.preview.stability === 'stable' ? '稳定' : 
                           forcePreview.preview.stability === 'unstable' ? '不稳定' : '易变'}
                        </span>
                      </div>
                    </div>

                    {forcePreview.can_normal_hybridize && (
                      <div className="normal-hybrid-hint">
                        <Check size={16} />
                        <span>这两个物种可以普通杂交（消耗更少能量）</span>
                      </div>
                    )}

                    <div className="warnings-section">
                      {forcePreview.preview.warnings.map((w, i) => (
                        <div key={i} className="warning-item">
                          <AlertTriangle size={14} />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>

                    <div className="force-energy-section">
                      <div className="energy-info">
                        <Zap size={24} />
                        <div className="energy-details">
                          <span className="energy-value">{forcePreview.energy_cost}</span>
                          <span className="energy-label">能量消耗</span>
                        </div>
                      </div>
                      <div className="energy-current">
                        当前: {forcePreview.current_energy}
                      </div>
                    </div>

                    <ActionButton
                      variant="danger"
                      size="large"
                      fullWidth
                      icon={<FlaskConical size={20} />}
                      onClick={executeForceHybridization}
                      disabled={!forcePreview.can_afford || !forcePreview.can_force_hybridize}
                      loading={executing}
                    >
                      {executing ? "创造嵌合体中..." : "🧬 执行强行杂交"}
                    </ActionButton>

                    {!forcePreview.can_afford && (
                      <div className="insufficient-energy">
                        能量不足！需要 {forcePreview.energy_cost} 能量
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`
        .hybridization-content {
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 20px;
          gap: 16px;
        }

        /* 模式切换器 */
        .mode-switcher {
          display: flex;
          gap: 8px;
          background: rgba(0, 0, 0, 0.3);
          padding: 6px;
          border-radius: 12px;
          flex-shrink: 0;
        }

        .mode-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 12px 16px;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .mode-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.7);
        }

        .mode-btn.active {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
        }

        .mode-btn.forced.active {
          background: rgba(244, 63, 94, 0.15);
          color: #f43f5e;
        }

        .mode-badge {
          font-size: 0.7rem;
          padding: 2px 8px;
          background: rgba(244, 63, 94, 0.3);
          border-radius: 10px;
          color: #fb7185;
        }

        /* 消息横幅 */
        .message-banner {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 18px;
          border-radius: 12px;
          font-size: 0.9rem;
          flex-shrink: 0;
        }

        .message-banner.error {
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.25);
          color: #fca5a5;
        }

        .message-banner.error svg { color: #ef4444; }

        .message-banner.success {
          background: rgba(34, 197, 94, 0.12);
          border: 1px solid rgba(34, 197, 94, 0.25);
          color: #86efac;
        }

        .message-banner.success svg { color: #22c55e; }

        .message-banner span { flex: 1; }

        .message-banner button {
          background: none;
          border: none;
          color: inherit;
          font-size: 1.3rem;
          cursor: pointer;
          opacity: 0.7;
        }

        .message-banner button:hover { opacity: 1; }

        /* 主布局 */
        .hybridization-layout {
          flex: 1;
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          min-height: 0;
        }

        /* 候选面板 */
        .candidates-panel {
          display: flex;
          flex-direction: column;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          overflow: hidden;
        }

        .panel-header {
          padding: 16px 20px;
          background: rgba(255, 255, 255, 0.02);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .panel-header h3 {
          margin: 0;
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
        }

        .panel-header h3 svg {
          color: #10b981;
        }

        .count-badge {
          background: rgba(16, 185, 129, 0.15);
          color: #34d399;
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 0.8rem;
          margin-left: auto;
        }

        /* 筛选器 */
        .filter-bar {
          display: flex;
          gap: 12px;
          padding: 14px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .search-box {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
        }

        .search-box svg {
          color: rgba(255, 255, 255, 0.4);
        }

        .search-box input {
          flex: 1;
          background: none;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 0.9rem;
        }

        .search-box input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .genus-select-wrapper {
          position: relative;
          display: flex;
          align-items: center;
        }

        .genus-select {
          padding: 10px 36px 10px 14px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.9rem;
          cursor: pointer;
          appearance: none;
        }

        .select-arrow {
          position: absolute;
          right: 12px;
          color: rgba(255, 255, 255, 0.4);
          pointer-events: none;
        }

        /* 候选列表 */
        .candidates-list {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
          padding: 60px 20px;
          color: rgba(255, 255, 255, 0.5);
        }

        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid rgba(255, 255, 255, 0.1);
          border-top-color: #10b981;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* 预览面板 */
        .preview-panel {
          display: flex;
          flex-direction: column;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          overflow: hidden;
        }

        .preview-placeholder {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 40px;
          color: rgba(255, 255, 255, 0.4);
        }

        .placeholder-icon {
          width: 100px;
          height: 100px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(16, 185, 129, 0.08);
          border: 1px dashed rgba(16, 185, 129, 0.3);
          border-radius: 50%;
          margin-bottom: 24px;
          color: #10b981;
        }

        .preview-placeholder h4 {
          margin: 0 0 10px;
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .preview-placeholder p {
          margin: 0;
          font-size: 0.9rem;
          max-width: 280px;
          line-height: 1.5;
        }

        .preview-content {
          flex: 1;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          overflow-y: auto;
        }

        /* 亲本展示 */
        .parents-display {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 20px;
          padding: 24px;
          background: linear-gradient(135deg, 
            rgba(16, 185, 129, 0.08) 0%, 
            rgba(16, 185, 129, 0.02) 100%
          );
          border: 1px solid rgba(16, 185, 129, 0.15);
          border-radius: 16px;
        }

        .parent-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          padding: 16px 24px;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          min-width: 140px;
        }

        .parent-code {
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 1.3rem;
          font-weight: 700;
          color: #10b981;
          margin-bottom: 6px;
        }

        .parent-name {
          font-size: 0.95rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.9);
          margin-bottom: 4px;
        }

        .parent-latin {
          font-size: 0.8rem;
          font-style: italic;
          color: rgba(255, 255, 255, 0.4);
        }

        .merge-indicator {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          color: #f43f5e;
        }

        .merge-indicator span {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        /* 后代预览 */
        .offspring-preview {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .offspring-header {
          text-align: center;
          padding-bottom: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .offspring-code {
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 1.6rem;
          font-weight: 700;
          color: #a855f7;
          text-shadow: 0 0 30px rgba(168, 85, 247, 0.4);
        }

        .offspring-name {
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.85);
          margin-top: 8px;
        }

        .offspring-stats {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 16px;
          align-items: center;
        }

        .stat-item {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .stat-label {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
          min-width: 60px;
        }

        .fertility-bar {
          flex: 1;
          height: 8px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          overflow: hidden;
        }

        .fertility-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s;
        }

        .stat-value {
          font-size: 1rem;
          font-weight: 700;
          font-family: var(--font-mono, monospace);
          min-width: 50px;
          text-align: right;
        }

        /* 能力标签 */
        .capabilities-section {
          padding-top: 16px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .cap-label {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
          margin-bottom: 10px;
        }

        .cap-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .cap-tag {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          background: rgba(168, 85, 247, 0.12);
          border: 1px solid rgba(168, 85, 247, 0.25);
          border-radius: 8px;
          font-size: 0.8rem;
          color: #c4b5fd;
        }

        /* 能量消耗 */
        .energy-cost-section {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 18px;
          background: linear-gradient(135deg, 
            rgba(245, 158, 11, 0.1) 0%, 
            rgba(245, 158, 11, 0.03) 100%
          );
          border: 1px solid rgba(245, 158, 11, 0.2);
          border-radius: 14px;
        }

        .cost-info {
          display: flex;
          align-items: center;
          gap: 14px;
          color: #f59e0b;
        }

        .cost-details {
          display: flex;
          flex-direction: column;
        }

        .cost-value {
          font-size: 1.8rem;
          font-weight: 700;
          font-family: var(--font-mono, monospace);
          line-height: 1;
        }

        .cost-label {
          font-size: 0.8rem;
          color: rgba(245, 158, 11, 0.7);
        }

        .cost-warning {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 14px;
          background: rgba(239, 68, 68, 0.15);
          border-radius: 8px;
          color: #f87171;
          font-size: 0.85rem;
          font-weight: 600;
        }

        /* 无法杂交 */
        .cannot-hybridize {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 40px;
          color: rgba(255, 255, 255, 0.4);
        }

        .cannot-hybridize svg {
          color: #f59e0b;
          margin-bottom: 16px;
        }

        .cannot-hybridize h4 {
          margin: 0 0 10px;
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .cannot-hybridize p {
          margin: 0;
          font-size: 0.9rem;
          max-width: 280px;
        }

        /* ========== 强行杂交样式 ========== */
        .force-hybridization-layout {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 20px;
          overflow-y: auto;
        }

        .force-warning-banner {
          display: flex;
          align-items: center;
          gap: 20px;
          padding: 20px 24px;
          background: linear-gradient(135deg, 
            rgba(244, 63, 94, 0.2) 0%,
            rgba(168, 85, 247, 0.1) 50%,
            rgba(244, 63, 94, 0.05) 100%
          );
          border: 1px solid rgba(244, 63, 94, 0.35);
          border-radius: 16px;
          flex-shrink: 0;
          position: relative;
          overflow: hidden;
        }

        .force-warning-banner::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: repeating-linear-gradient(
            -45deg,
            transparent,
            transparent 10px,
            rgba(244, 63, 94, 0.03) 10px,
            rgba(244, 63, 94, 0.03) 20px
          );
          pointer-events: none;
        }

        .warning-icon-pulse {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 56px;
          height: 56px;
          background: rgba(244, 63, 94, 0.15);
          border: 2px solid rgba(244, 63, 94, 0.4);
          border-radius: 14px;
          color: #f43f5e;
          flex-shrink: 0;
          animation: pulse-glow 2s ease-in-out infinite;
        }

        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 20px rgba(244, 63, 94, 0.3); }
          50% { box-shadow: 0 0 35px rgba(244, 63, 94, 0.5); }
        }

        .warning-text {
          flex: 1;
        }

        .warning-text strong {
          display: block;
          color: #fb7185;
          font-size: 1.1rem;
          margin-bottom: 6px;
        }

        .warning-text p {
          margin: 0;
          color: rgba(255, 255, 255, 0.65);
          font-size: 0.9rem;
          line-height: 1.6;
        }

        .energy-highlight {
          color: #fbbf24;
          font-weight: 700;
        }

        .species-count-badge {
          padding: 10px 18px;
          background: rgba(168, 85, 247, 0.2);
          border: 1px solid rgba(168, 85, 247, 0.4);
          border-radius: 30px;
          color: #c4b5fd;
          font-size: 0.85rem;
          font-weight: 600;
          white-space: nowrap;
        }

        .force-selection-area {
          display: flex;
          gap: 16px;
          align-items: stretch;
          min-height: 380px;
        }

        .force-species-selector {
          flex: 1;
          display: flex;
          flex-direction: column;
          background: linear-gradient(180deg, 
            rgba(255, 255, 255, 0.03) 0%,
            rgba(255, 255, 255, 0.01) 100%
          );
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 20px;
          padding: 20px;
          transition: all 0.3s ease;
        }

        .force-species-selector:hover {
          border-color: rgba(244, 63, 94, 0.25);
        }

        .force-species-selector.has-selection {
          background: linear-gradient(180deg, 
            rgba(244, 63, 94, 0.08) 0%,
            rgba(244, 63, 94, 0.02) 100%
          );
          border-color: rgba(244, 63, 94, 0.35);
        }

        .selector-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .selector-title {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .selector-emoji {
          font-size: 1.3rem;
        }

        .selector-label {
          font-size: 1rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
        }

        .clear-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: 8px;
          color: #fca5a5;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .clear-btn:hover {
          background: rgba(239, 68, 68, 0.25);
          border-color: rgba(239, 68, 68, 0.5);
        }

        .species-picker {
          flex: 1;
          display: flex;
          flex-direction: column;
        }

        .search-box.enhanced {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 18px;
          background: rgba(0, 0, 0, 0.35);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 14px;
          transition: all 0.2s;
        }

        .search-box.enhanced:focus-within {
          border-color: rgba(244, 63, 94, 0.5);
          box-shadow: 0 0 20px rgba(244, 63, 94, 0.15);
        }

        .search-box.enhanced svg {
          color: rgba(255, 255, 255, 0.4);
        }

        .search-box.enhanced input {
          flex: 1;
          background: none;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 0.95rem;
        }

        .search-box.enhanced input::placeholder {
          color: rgba(255, 255, 255, 0.35);
        }

        .search-clear {
          display: flex;
          padding: 4px;
          background: rgba(255, 255, 255, 0.1);
          border: none;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
        }

        .search-clear:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .species-list {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 8px;
          overflow-y: auto;
          margin-top: 14px;
          padding-right: 4px;
        }

        .species-list::-webkit-scrollbar {
          width: 6px;
        }

        .species-list::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.02);
          border-radius: 3px;
        }

        .species-list::-webkit-scrollbar-thumb {
          background: rgba(244, 63, 94, 0.3);
          border-radius: 3px;
        }

        .empty-species-hint {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 40px 20px;
          color: rgba(255, 255, 255, 0.4);
          text-align: center;
        }

        .empty-icon {
          font-size: 2.5rem;
          margin-bottom: 8px;
        }

        .empty-species-hint span:nth-child(2) {
          font-size: 0.95rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .empty-sub {
          font-size: 0.8rem !important;
          color: rgba(255, 255, 255, 0.35) !important;
        }

        .species-option {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 12px 16px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          animation: fadeSlideIn 0.3s ease backwards;
        }

        @keyframes fadeSlideIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .species-option:hover {
          background: rgba(244, 63, 94, 0.12);
          border-color: rgba(244, 63, 94, 0.35);
          transform: translateX(4px);
        }

        .option-avatar {
          font-size: 1.2rem;
        }

        .option-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }

        .option-code {
          font-family: var(--font-display, 'Cinzel', serif);
          font-weight: 700;
          font-size: 0.95rem;
          color: #f43f5e;
        }

        .option-name {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.65);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .option-role {
          font-size: 0.75rem;
          padding: 4px 10px;
          background: rgba(168, 85, 247, 0.15);
          border-radius: 12px;
          color: #c4b5fd;
          flex-shrink: 0;
        }

        .species-role {
          font-size: 0.85rem;
          color: #a78bfa;
          background: rgba(168, 85, 247, 0.2);
          padding: 6px 14px;
          border-radius: 20px;
        }

        .species-population {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          background: rgba(255, 255, 255, 0.08);
          padding: 6px 12px;
          border-radius: 20px;
        }

        .more-hint {
          text-align: center;
          padding: 12px;
          color: rgba(255, 255, 255, 0.4);
          font-size: 0.8rem;
        }

        .selected-species-card {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 20px;
          padding: 24px;
          background: linear-gradient(135deg,
            rgba(244, 63, 94, 0.12) 0%,
            rgba(168, 85, 247, 0.08) 100%
          );
          border: 2px solid rgba(244, 63, 94, 0.35);
          border-radius: 16px;
        }

        .selected-species-card.glowing {
          animation: card-glow 3s ease-in-out infinite;
        }

        @keyframes card-glow {
          0%, 100% { box-shadow: 0 0 25px rgba(244, 63, 94, 0.2); }
          50% { box-shadow: 0 0 40px rgba(244, 63, 94, 0.35); }
        }

        .species-avatar {
          font-size: 2.5rem;
        }

        .species-info {
          flex: 1;
        }

        .selected-species-card .species-code {
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 1.6rem;
          font-weight: 700;
          color: #f43f5e;
          margin-bottom: 4px;
          text-shadow: 0 0 30px rgba(244, 63, 94, 0.5);
        }

        .selected-species-card .species-name {
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.9);
          margin-bottom: 10px;
        }

        .species-meta {
          display: flex;
          gap: 10px;
        }


        /* 融合指示器增强 */
        .force-merge-indicator {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 10px;
          padding: 20px 16px;
          color: #f43f5e;
          position: relative;
        }

        .merge-icon-container {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 80px;
          height: 80px;
        }

        .merge-ring {
          position: absolute;
          border: 2px dashed rgba(244, 63, 94, 0.3);
          border-radius: 50%;
          animation: ring-rotate 10s linear infinite;
        }

        .ring-1 {
          width: 70px;
          height: 70px;
        }

        .ring-2 {
          width: 90px;
          height: 90px;
          animation-direction: reverse;
          animation-duration: 15s;
        }

        @keyframes ring-rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .force-merge-indicator.ready .merge-icon-container svg {
          animation: skull-pulse 0.8s ease-in-out infinite;
        }

        @keyframes skull-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.15); }
        }

        .merge-label {
          font-size: 0.85rem;
          text-transform: uppercase;
          letter-spacing: 0.15em;
          color: rgba(244, 63, 94, 0.8);
          font-weight: 600;
        }

        .force-merge-indicator.ready .merge-label {
          color: #f43f5e;
          animation: label-flash 1s ease-in-out infinite;
        }

        @keyframes label-flash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        .merge-arrows {
          display: flex;
          gap: 30px;
          margin-top: 8px;
        }

        .arrow-left {
          transform: rotate(180deg);
          color: rgba(244, 63, 94, 0.5);
        }

        .arrow-right {
          color: rgba(244, 63, 94, 0.5);
        }

        .force-merge-indicator.ready .arrow-left,
        .force-merge-indicator.ready .arrow-right {
          animation: arrow-blink 0.6s ease-in-out infinite alternate;
        }

        @keyframes arrow-blink {
          from { opacity: 0.3; }
          to { opacity: 1; color: #f43f5e; }
        }

        .force-preview-area {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 20px;
        }

        .force-preview-content {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .chimera-preview-header {
          display: flex;
          align-items: center;
          gap: 12px;
          color: #a855f7;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(168, 85, 247, 0.2);
        }

        .chimera-preview-header h3 {
          margin: 0;
          font-size: 1.1rem;
        }

        .chimera-stats {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .stat-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .stability-badge {
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 0.8rem;
          font-weight: 600;
        }

        .stability-badge.stable {
          background: rgba(34, 197, 94, 0.15);
          color: #22c55e;
        }

        .stability-badge.unstable {
          background: rgba(245, 158, 11, 0.15);
          color: #f59e0b;
        }

        .stability-badge.volatile {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
        }

        .normal-hybrid-hint {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 16px;
          background: rgba(34, 197, 94, 0.1);
          border: 1px solid rgba(34, 197, 94, 0.25);
          border-radius: 10px;
          color: #86efac;
          font-size: 0.85rem;
        }

        .warnings-section {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .warning-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 10px 14px;
          background: rgba(245, 158, 11, 0.08);
          border-radius: 8px;
          font-size: 0.85rem;
          color: #fcd34d;
        }

        .warning-item svg {
          flex-shrink: 0;
          margin-top: 2px;
        }

        .force-energy-section {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 18px;
          background: linear-gradient(135deg, 
            rgba(244, 63, 94, 0.12) 0%,
            rgba(244, 63, 94, 0.04) 100%
          );
          border: 1px solid rgba(244, 63, 94, 0.25);
          border-radius: 14px;
        }

        .energy-info {
          display: flex;
          align-items: center;
          gap: 14px;
          color: #f43f5e;
        }

        .energy-details {
          display: flex;
          flex-direction: column;
        }

        .energy-value {
          font-size: 1.8rem;
          font-weight: 700;
          font-family: var(--font-mono, monospace);
          line-height: 1;
        }

        .energy-label {
          font-size: 0.8rem;
          color: rgba(244, 63, 94, 0.7);
        }

        .energy-current {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .insufficient-energy {
          text-align: center;
          padding: 12px;
          background: rgba(239, 68, 68, 0.1);
          border-radius: 8px;
          color: #f87171;
          font-size: 0.9rem;
        }
      `}</style>
    </AnalysisPanel>
  );
}

/**
 * CandidateCard - 候选物种对卡片
 */
function CandidateCard({ 
  pair, 
  selected, 
  onSelect,
  fertilityColor 
}: { 
  pair: HybridCandidate; 
  selected: boolean;
  onSelect: () => void;
  fertilityColor: string;
}) {
  return (
    <div 
      className={`candidate-card ${selected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="candidate-species">
        <span className="species-code">{pair.species_a.lineage_code}</span>
        <span className="species-name">{pair.species_a.common_name}</span>
      </div>
      <div className="candidate-cross">
        <GitMerge size={16} />
      </div>
      <div className="candidate-species">
        <span className="species-code">{pair.species_b.lineage_code}</span>
        <span className="species-name">{pair.species_b.common_name}</span>
      </div>
      <div 
        className="fertility-badge"
        style={{ 
          background: `${fertilityColor}20`,
          borderColor: `${fertilityColor}40`,
          color: fertilityColor
        }}
      >
        {(pair.fertility * 100).toFixed(0)}%
      </div>

      <style>{`
        .candidate-card {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 16px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .candidate-card:hover {
          background: rgba(255, 255, 255, 0.04);
          border-color: rgba(16, 185, 129, 0.3);
        }

        .candidate-card.selected {
          background: rgba(16, 185, 129, 0.08);
          border-color: rgba(16, 185, 129, 0.4);
          box-shadow: 0 0 20px rgba(16, 185, 129, 0.15);
        }

        .candidate-species {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 3px;
          min-width: 0;
        }

        .species-code {
          font-family: var(--font-display, 'Cinzel', serif);
          font-weight: 700;
          font-size: 0.95rem;
          color: #10b981;
        }

        .species-name {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .candidate-cross {
          color: rgba(255, 255, 255, 0.3);
          flex-shrink: 0;
        }

        .fertility-badge {
          padding: 5px 10px;
          border: 1px solid;
          border-radius: 8px;
          font-size: 0.8rem;
          font-weight: 700;
          font-family: var(--font-mono, monospace);
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
}
