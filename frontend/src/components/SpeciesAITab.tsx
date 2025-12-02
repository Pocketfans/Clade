/**
 * 物种 AI 分析标签页 - 集成到 SpeciesPanel 中
 * 
 * 功能：
 * 1. 演化解释 - 解释物种为何演化成当前状态
 * 2. 游戏提示 - 获取针对该物种的游戏建议
 * 3. 物种传记 - 生成物种的历史传记
 */

import { useState, useCallback, useEffect } from "react";
import { Sparkles, Lightbulb, BookOpen, RefreshCw, AlertTriangle, TrendingUp, Target, AlertCircle } from "lucide-react";
import { 
  embeddingApi, 
  type SpeciesExplanationResponse, 
  type GameHint,
  type BiographyResponse 
} from "../services/embedding.api";

interface Props {
  speciesCode: string;
  speciesName: string;
}

type SubTab = "explain" | "hints" | "biography";

export function SpeciesAITab({ speciesCode, speciesName }: Props) {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>("explain");
  
  // 解释状态
  const [explanation, setExplanation] = useState<SpeciesExplanationResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  
  // 提示状态
  const [hints, setHints] = useState<GameHint[]>([]);
  const [hintsLoading, setHintsLoading] = useState(false);
  
  // 传记状态
  const [biography, setBiography] = useState<BiographyResponse | null>(null);
  const [biographyLoading, setBiographyLoading] = useState(false);
  
  const [error, setError] = useState<string | null>(null);
  
  // 加载演化解释
  const loadExplanation = useCallback(async () => {
    setExplainLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.explainSpecies(speciesCode);
      setExplanation(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载解释失败");
    } finally {
      setExplainLoading(false);
    }
  }, [speciesCode]);
  
  // 加载游戏提示
  const loadHints = useCallback(async () => {
    setHintsLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.getHints(speciesCode);
      setHints(result.hints);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载提示失败");
    } finally {
      setHintsLoading(false);
    }
  }, [speciesCode]);
  
  // 加载物种传记
  const loadBiography = useCallback(async () => {
    setBiographyLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.getSpeciesBiography(speciesCode);
      setBiography(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载传记失败");
    } finally {
      setBiographyLoading(false);
    }
  }, [speciesCode]);
  
  // 切换子标签时自动加载数据
  useEffect(() => {
    if (activeSubTab === "explain" && !explanation && !explainLoading) {
      loadExplanation();
    } else if (activeSubTab === "hints" && hints.length === 0 && !hintsLoading) {
      loadHints();
    } else if (activeSubTab === "biography" && !biography && !biographyLoading) {
      loadBiography();
    }
  }, [activeSubTab, explanation, hints, biography, explainLoading, hintsLoading, biographyLoading, loadExplanation, loadHints, loadBiography]);
  
  // 物种代码变化时重置
  useEffect(() => {
    setExplanation(null);
    setHints([]);
    setBiography(null);
    setError(null);
  }, [speciesCode]);
  
  const getHintIcon = (type: string) => {
    switch (type) {
      case 'evolution': return <TrendingUp size={16} />;
      case 'competition': return <Target size={16} />;
      case 'warning': return <AlertTriangle size={16} />;
      case 'opportunity': return <Lightbulb size={16} />;
      default: return <Lightbulb size={16} />;
    }
  };
  
  const getHintColor = (type: string) => {
    switch (type) {
      case 'evolution': return '#3b82f6';
      case 'competition': return '#f59e0b';
      case 'warning': return '#ef4444';
      case 'opportunity': return '#10b981';
      default: return '#64748b';
    }
  };
  
  const getPriorityBadge = (priority: string) => {
    const colors = {
      critical: { bg: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' },
      high: { bg: 'rgba(249, 115, 22, 0.15)', color: '#f97316' },
      medium: { bg: 'rgba(251, 191, 36, 0.15)', color: '#fbbf24' },
      low: { bg: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8' },
    };
    return colors[priority as keyof typeof colors] || colors.low;
  };

  return (
    <div className="species-ai-tab">
      {/* 子标签栏 */}
      <div className="sub-tab-bar">
        <button 
          className={`sub-tab ${activeSubTab === 'explain' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('explain')}
        >
          <Sparkles size={14} />
          <span>演化解释</span>
        </button>
        <button 
          className={`sub-tab ${activeSubTab === 'hints' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('hints')}
        >
          <Lightbulb size={14} />
          <span>游戏提示</span>
        </button>
        <button 
          className={`sub-tab ${activeSubTab === 'biography' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('biography')}
        >
          <BookOpen size={14} />
          <span>物种传记</span>
        </button>
      </div>
      
      {/* 错误提示 */}
      {error && (
        <div className="ai-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      
      {/* 演化解释 */}
      {activeSubTab === 'explain' && (
        <div className="sub-content">
          {explainLoading ? (
            <div className="loading-state">
              <span className="spinner" />
              <span>AI 正在分析演化历程...</span>
            </div>
          ) : explanation ? (
            <div className="explain-content">
              <div className="explain-header">
                <h4>
                  <Sparkles size={16} />
                  {explanation.species_name} 的演化解释
                </h4>
                <button className="refresh-btn" onClick={loadExplanation} title="重新分析">
                  <RefreshCw size={14} />
                </button>
              </div>
              
              <div className="explain-text">
                <p>{explanation.explanation}</p>
              </div>
              
              {explanation.key_factors.length > 0 && (
                <div className="key-factors">
                  <h5>关键因素</h5>
                  <div className="factors-list">
                    {explanation.key_factors.map((factor, idx) => (
                      <div key={idx} className="factor-item">
                        <span className="factor-number">{idx + 1}</span>
                        <span className="factor-text">{factor}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {Object.keys(explanation.trait_explanations).length > 0 && (
                <div className="trait-explanations">
                  <h5>特征解释</h5>
                  <div className="trait-list">
                    {Object.entries(explanation.trait_explanations).map(([trait, desc]) => (
                      <div key={trait} className="trait-explain-item">
                        <span className="trait-name">{trait}</span>
                        <span className="trait-desc">{desc}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <Sparkles size={32} strokeWidth={1} />
              <p>点击加载 AI 演化分析</p>
              <button className="load-btn" onClick={loadExplanation}>
                开始分析
              </button>
            </div>
          )}
        </div>
      )}
      
      {/* 游戏提示 */}
      {activeSubTab === 'hints' && (
        <div className="sub-content">
          {hintsLoading ? (
            <div className="loading-state">
              <span className="spinner" />
              <span>正在生成游戏提示...</span>
            </div>
          ) : hints.length > 0 ? (
            <div className="hints-content">
              <div className="hints-header">
                <h4>
                  <Lightbulb size={16} />
                  {speciesName} 的游戏提示
                </h4>
                <button className="refresh-btn" onClick={loadHints} title="刷新提示">
                  <RefreshCw size={14} />
                </button>
              </div>
              
              <div className="hints-list">
                {hints.map((hint, idx) => (
                  <div 
                    key={idx} 
                    className="hint-card"
                    style={{ borderLeftColor: getHintColor(hint.type) }}
                  >
                    <div className="hint-header">
                      <span className="hint-type" style={{ color: getHintColor(hint.type) }}>
                        {getHintIcon(hint.type)}
                        <span>{hint.type === 'evolution' ? '演化' : hint.type === 'competition' ? '竞争' : hint.type === 'warning' ? '警告' : '机遇'}</span>
                      </span>
                      <span 
                        className="hint-priority"
                        style={getPriorityBadge(hint.priority)}
                      >
                        {hint.priority === 'critical' ? '紧急' : hint.priority === 'high' ? '高' : hint.priority === 'medium' ? '中' : '低'}
                      </span>
                    </div>
                    
                    <p className="hint-message">{hint.message}</p>
                    
                    {hint.suggested_actions.length > 0 && (
                      <div className="hint-actions">
                        <span className="actions-label">建议操作：</span>
                        <ul>
                          {hint.suggested_actions.map((action, i) => (
                            <li key={i}>{action}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {hint.related_species.length > 0 && (
                      <div className="hint-related">
                        <span className="related-label">相关物种：</span>
                        <div className="related-tags">
                          {hint.related_species.map(code => (
                            <span key={code} className="related-tag">{code}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <Lightbulb size={32} strokeWidth={1} />
              <p>点击获取针对此物种的游戏建议</p>
              <button className="load-btn" onClick={loadHints}>
                获取提示
              </button>
            </div>
          )}
        </div>
      )}
      
      {/* 物种传记 */}
      {activeSubTab === 'biography' && (
        <div className="sub-content">
          {biographyLoading ? (
            <div className="loading-state">
              <span className="spinner" />
              <span>AI 正在撰写物种传记...</span>
            </div>
          ) : biography ? (
            <div className="biography-content">
              <div className="biography-header">
                <h4>
                  <BookOpen size={16} />
                  {biography.species_name} 的传记
                </h4>
                <button className="refresh-btn" onClick={loadBiography} title="重新生成">
                  <RefreshCw size={14} />
                </button>
              </div>
              
              <div className="biography-text">
                {biography.biography.split('\n').map((paragraph, idx) => (
                  <p key={idx}>{paragraph}</p>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <BookOpen size={32} strokeWidth={1} />
              <p>点击生成物种的演化历史传记</p>
              <button className="load-btn" onClick={loadBiography}>
                生成传记
              </button>
            </div>
          )}
        </div>
      )}
      
      <style>{`
        .species-ai-tab {
          display: flex;
          flex-direction: column;
          height: 100%;
        }
        
        .sub-tab-bar {
          display: flex;
          gap: 4px;
          padding: 8px 0;
          margin-bottom: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        
        .sub-tab {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .sub-tab:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }
        
        .sub-tab.active {
          background: rgba(167, 139, 250, 0.15);
          border-color: rgba(167, 139, 250, 0.3);
          color: #c4b5fd;
        }
        
        .ai-error {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          background: rgba(239, 68, 68, 0.1);
          border-radius: 8px;
          color: #fca5a5;
          font-size: 0.85rem;
          margin-bottom: 12px;
        }
        
        .sub-content {
          flex: 1;
          overflow-y: auto;
        }
        
        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px;
          gap: 12px;
          color: rgba(255, 255, 255, 0.5);
        }
        
        .spinner {
          width: 24px;
          height: 24px;
          border: 2px solid rgba(167, 139, 250, 0.2);
          border-top-color: #a78bfa;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px 20px;
          color: rgba(255, 255, 255, 0.4);
          text-align: center;
        }
        
        .empty-state p {
          margin: 12px 0;
        }
        
        .load-btn {
          padding: 10px 24px;
          background: linear-gradient(135deg, #a855f7, #7c3aed);
          border: none;
          border-radius: 10px;
          color: white;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .load-btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3);
        }
        
        /* Explain Content */
        .explain-content, .hints-content, .biography-content {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .explain-header, .hints-header, .biography-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        
        .explain-header h4, .hints-header h4, .biography-header h4 {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 0;
          font-size: 1rem;
          color: #c4b5fd;
        }
        
        .refresh-btn {
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .refresh-btn:hover {
          background: rgba(167, 139, 250, 0.2);
          color: #c4b5fd;
        }
        
        .explain-text, .biography-text {
          padding: 14px;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 10px;
          font-size: 0.9rem;
          line-height: 1.7;
          color: rgba(255, 255, 255, 0.85);
        }
        
        .explain-text p, .biography-text p {
          margin: 0 0 12px 0;
        }
        
        .explain-text p:last-child, .biography-text p:last-child {
          margin-bottom: 0;
        }
        
        .key-factors, .trait-explanations {
          margin-top: 8px;
        }
        
        .key-factors h5, .trait-explanations h5 {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.6);
          margin: 0 0 10px 0;
        }
        
        .factors-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .factor-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 10px 12px;
          background: rgba(59, 130, 246, 0.08);
          border-radius: 8px;
        }
        
        .factor-number {
          width: 22px;
          height: 22px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(59, 130, 246, 0.2);
          border-radius: 50%;
          font-size: 0.75rem;
          font-weight: 600;
          color: #60a5fa;
          flex-shrink: 0;
        }
        
        .factor-text {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.8);
          line-height: 1.5;
        }
        
        .trait-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .trait-explain-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 10px 12px;
          background: rgba(255, 255, 255, 0.03);
          border-left: 3px solid #a855f7;
          border-radius: 0 8px 8px 0;
        }
        
        .trait-explain-item .trait-name {
          font-size: 0.8rem;
          font-weight: 600;
          color: #c4b5fd;
        }
        
        .trait-explain-item .trait-desc {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
        }
        
        /* Hints */
        .hints-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .hint-card {
          padding: 14px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-left: 3px solid;
          border-radius: 0 10px 10px 0;
        }
        
        .hint-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 10px;
        }
        
        .hint-type {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.8rem;
          font-weight: 600;
        }
        
        .hint-priority {
          padding: 3px 10px;
          border-radius: 12px;
          font-size: 0.7rem;
          font-weight: 600;
        }
        
        .hint-message {
          margin: 0 0 12px 0;
          font-size: 0.9rem;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.85);
        }
        
        .hint-actions {
          margin-bottom: 10px;
        }
        
        .actions-label, .related-label {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          margin-bottom: 6px;
          display: block;
        }
        
        .hint-actions ul {
          margin: 0;
          padding-left: 18px;
        }
        
        .hint-actions li {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 4px;
        }
        
        .related-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        
        .related-tag {
          padding: 4px 10px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          font-size: 0.75rem;
          font-family: 'JetBrains Mono', monospace;
          color: rgba(255, 255, 255, 0.6);
        }
      `}</style>
    </div>
  );
}

