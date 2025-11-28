/**
 * HybridizationPanel - 物种杂交面板
 * 重新设计的现代化界面，提供直观的物种配对与杂交预览
 */
import { useEffect, useState, useCallback } from "react";
import { 
  Dna, GitMerge, Search, Zap, Check, X, AlertTriangle, 
  ArrowRight, Sparkles, Heart, Shield, ChevronDown
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

interface Props {
  onClose: () => void;
  onSuccess?: () => void;
}

export function HybridizationPanel({ onClose, onSuccess }: Props) {
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

  useEffect(() => {
    fetchCandidates();
  }, []);

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
      
    } catch (e: any) {
      setError(e.message || "杂交失败");
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

  return (
    <AnalysisPanel
      title="物种杂交"
      icon={<GitMerge size={20} />}
      accentColor="#10b981"
      onClose={onClose}
      size="large"
      showMaximize
    >
      <div className="hybridization-content">
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
      </div>

      <style>{`
        .hybridization-content {
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 20px;
          gap: 16px;
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
