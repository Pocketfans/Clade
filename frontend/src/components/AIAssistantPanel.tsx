/**
 * AI 助手面板 - 统一的智能搜索、问答与提示界面
 * 
 * 功能：
 * 1. 语义搜索 - 搜索物种、事件、概念
 * 2. 智能问答 - 基于上下文的AI问答
 * 3. 演化预测 - 预测物种在特定压力下的演化方向
 */

import { useState, useCallback, useEffect } from "react";
import { Search, MessageCircle, Sparkles, X, ChevronRight, Zap, HelpCircle, Lightbulb, TrendingUp, ArrowRight } from "lucide-react";
import { GamePanel } from "./common/GamePanel";
import { embeddingApi, type SearchResult, type QAResponse, type EvolutionPredictionResponse, type EvolutionPressure } from "../services/embedding.api";

interface Props {
  onClose: () => void;
  initialTab?: "search" | "qa" | "predict";
  initialSpeciesCode?: string;
}

type Tab = "search" | "qa" | "predict";

export function AIAssistantPanel({ onClose, initialTab = "search", initialSpeciesCode }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  
  // 搜索状态
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchTypes, setSearchTypes] = useState<string[]>([]);
  
  // 问答状态
  const [question, setQuestion] = useState("");
  const [qaResponse, setQaResponse] = useState<QAResponse | null>(null);
  const [qaLoading, setQaLoading] = useState(false);
  const [qaHistory, setQaHistory] = useState<Array<{ question: string; answer: QAResponse }>>([]);
  
  // 演化预测状态
  const [predictSpeciesCode, setPredictSpeciesCode] = useState(initialSpeciesCode || "");
  const [selectedPressures, setSelectedPressures] = useState<string[]>([]);
  const [availablePressures, setAvailablePressures] = useState<EvolutionPressure[]>([]);
  const [predictionResult, setPredictionResult] = useState<EvolutionPredictionResponse | null>(null);
  const [predictLoading, setPredictLoading] = useState(false);
  const [generateDescription, setGenerateDescription] = useState(false);
  
  const [error, setError] = useState<string | null>(null);
  
  // 加载可用的压力类型
  useEffect(() => {
    embeddingApi.listPressures()
      .then(res => setAvailablePressures(res.pressures))
      .catch(err => console.error("加载压力类型失败:", err));
  }, []);
  
  // 搜索功能
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    
    setSearchLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.search(
        searchQuery, 
        searchTypes.length > 0 ? searchTypes : undefined,
        10
      );
      setSearchResults(result.results);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "搜索失败");
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery, searchTypes]);
  
  // 问答功能
  const handleAskQuestion = useCallback(async () => {
    if (!question.trim()) return;
    
    setQaLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.askQuestion(question);
      setQaResponse(result);
      setQaHistory(prev => [...prev, { question, answer: result }]);
      setQuestion("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "问答失败");
    } finally {
      setQaLoading(false);
    }
  }, [question]);
  
  // 演化预测功能
  const handlePredict = useCallback(async () => {
    if (!predictSpeciesCode || selectedPressures.length === 0) return;
    
    setPredictLoading(true);
    setError(null);
    try {
      const result = await embeddingApi.predictEvolution({
        species_code: predictSpeciesCode,
        pressure_types: selectedPressures,
        generate_description: generateDescription,
      });
      setPredictionResult(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "预测失败");
    } finally {
      setPredictLoading(false);
    }
  }, [predictSpeciesCode, selectedPressures, generateDescription]);
  
  // 快速提问
  const handleFollowUp = (followUpQuestion: string) => {
    setQuestion(followUpQuestion);
  };

  const togglePressure = (pressureName: string) => {
    setSelectedPressures(prev => 
      prev.includes(pressureName) 
        ? prev.filter(p => p !== pressureName)
        : [...prev, pressureName]
    );
  };

  const toggleSearchType = (type: string) => {
    setSearchTypes(prev =>
      prev.includes(type)
        ? prev.filter(t => t !== type)
        : [...prev, type]
    );
  };

  const getResultIcon = (type: string) => {
    switch (type) {
      case 'species': return '🧬';
      case 'event': return '📅';
      case 'concept': return '💡';
      default: return '📄';
    }
  };

  const getResultColor = (type: string) => {
    switch (type) {
      case 'species': return '#3b82f6';
      case 'event': return '#f59e0b';
      case 'concept': return '#a855f7';
      default: return '#64748b';
    }
  };

  return (
    <GamePanel
      title="AI 演化助手"
      onClose={onClose}
      variant="modal"
      width="800px"
      height="85vh"
    >
      <div className="ai-assistant-panel">
        {/* 标签栏 */}
        <div className="tab-bar">
          <button 
            className={`tab-button ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => setActiveTab('search')}
          >
            <Search size={16} />
            <span>语义搜索</span>
          </button>
          <button 
            className={`tab-button ${activeTab === 'qa' ? 'active' : ''}`}
            onClick={() => setActiveTab('qa')}
          >
            <MessageCircle size={16} />
            <span>智能问答</span>
          </button>
          <button 
            className={`tab-button ${activeTab === 'predict' ? 'active' : ''}`}
            onClick={() => setActiveTab('predict')}
          >
            <Sparkles size={16} />
            <span>演化预测</span>
          </button>
        </div>
        
        {/* 错误提示 */}
        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}
        
        {/* 搜索面板 */}
        {activeTab === 'search' && (
          <div className="panel-content">
            <div className="search-section">
              <div className="search-input-wrapper">
                <Search size={18} className="search-icon" />
                <input
                  type="text"
                  placeholder="搜索物种、事件或概念..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="search-input"
                />
                <button 
                  className="search-btn" 
                  onClick={handleSearch}
                  disabled={searchLoading || !searchQuery.trim()}
                >
                  {searchLoading ? <span className="spinner" /> : '搜索'}
                </button>
              </div>
              
              {/* 搜索类型筛选 */}
              <div className="search-filters">
                <span className="filter-label">筛选：</span>
                {['species', 'event', 'concept'].map(type => (
                  <button
                    key={type}
                    className={`filter-chip ${searchTypes.includes(type) ? 'active' : ''}`}
                    onClick={() => toggleSearchType(type)}
                    style={{ 
                      '--chip-color': getResultColor(type),
                      borderColor: searchTypes.includes(type) ? getResultColor(type) : 'transparent'
                    } as React.CSSProperties}
                  >
                    <span>{getResultIcon(type)}</span>
                    <span>{type === 'species' ? '物种' : type === 'event' ? '事件' : '概念'}</span>
                  </button>
                ))}
              </div>
            </div>
            
            {/* 搜索结果 */}
            <div className="results-section">
              {searchResults.length === 0 ? (
                <div className="empty-state">
                  <Search size={48} strokeWidth={1} />
                  <p>输入关键词开始语义搜索</p>
                  <p className="hint">支持自然语言查询，如"能飞的食肉动物"</p>
                </div>
              ) : (
                <div className="results-list">
                  {searchResults.map((result, idx) => (
                    <div key={`${result.type}-${result.id}-${idx}`} className="result-card">
                      <div className="result-header">
                        <span 
                          className="result-type-badge"
                          style={{ background: `${getResultColor(result.type)}20`, color: getResultColor(result.type) }}
                        >
                          {getResultIcon(result.type)} {result.type === 'species' ? '物种' : result.type === 'event' ? '事件' : '概念'}
                        </span>
                        <span className="result-similarity">
                          {(result.similarity * 100).toFixed(0)}% 相似
                        </span>
                      </div>
                      <h4 className="result-title">{result.title}</h4>
                      <p className="result-desc">{result.description}</p>
                      {result.metadata && Object.keys(result.metadata).length > 0 && (
                        <div className="result-meta">
                          {Object.entries(result.metadata).slice(0, 3).map(([key, value]) => (
                            <span key={key} className="meta-tag">
                              {key}: {String(value)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* 问答面板 */}
        {activeTab === 'qa' && (
          <div className="panel-content qa-panel">
            {/* 历史对话 */}
            <div className="qa-history">
              {qaHistory.length === 0 && !qaResponse ? (
                <div className="empty-state">
                  <MessageCircle size={48} strokeWidth={1} />
                  <p>向 AI 提问关于演化的问题</p>
                  <p className="hint">例如："哪些物种适应了寒冷环境？"</p>
                </div>
              ) : (
                <>
                  {qaHistory.map((item, idx) => (
                    <div key={idx} className="qa-exchange">
                      <div className="user-question">
                        <HelpCircle size={16} />
                        <span>{item.question}</span>
                      </div>
                      <div className="ai-answer">
                        <div className="answer-header">
                          <Sparkles size={16} />
                          <span>AI 回答</span>
                          <span className="confidence">
                            置信度: {(item.answer.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p>{item.answer.answer}</p>
                        {item.answer.sources.length > 0 && (
                          <div className="answer-sources">
                            <span className="sources-label">参考来源：</span>
                            {item.answer.sources.map((s, i) => (
                              <span key={i} className="source-tag">
                                {s.title} ({(s.similarity * 100).toFixed(0)}%)
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
            
            {/* 追问建议 */}
            {qaResponse && qaResponse.follow_up_questions.length > 0 && (
              <div className="follow-up-section">
                <span className="follow-up-label"><Lightbulb size={14} /> 你可能还想问：</span>
                <div className="follow-up-list">
                  {qaResponse.follow_up_questions.map((q, idx) => (
                    <button 
                      key={idx} 
                      className="follow-up-btn"
                      onClick={() => handleFollowUp(q)}
                    >
                      {q}
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              </div>
            )}
            
            {/* 输入区 */}
            <div className="qa-input-section">
              <div className="qa-input-wrapper">
                <input
                  type="text"
                  placeholder="输入你的问题..."
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAskQuestion()}
                  className="qa-input"
                />
                <button 
                  className="qa-send-btn"
                  onClick={handleAskQuestion}
                  disabled={qaLoading || !question.trim()}
                >
                  {qaLoading ? <span className="spinner" /> : <ArrowRight size={18} />}
                </button>
              </div>
            </div>
          </div>
        )}
        
        {/* 演化预测面板 */}
        {activeTab === 'predict' && (
          <div className="panel-content predict-panel">
            <div className="predict-form">
              {/* 物种选择 */}
              <div className="form-section">
                <label className="form-label">
                  <span className="label-icon">🧬</span>
                  物种代码
                </label>
                <input
                  type="text"
                  placeholder="输入物种代码 (如: A-1)"
                  value={predictSpeciesCode}
                  onChange={(e) => setPredictSpeciesCode(e.target.value)}
                  className="form-input"
                />
              </div>
              
              {/* 压力选择 */}
              <div className="form-section">
                <label className="form-label">
                  <span className="label-icon">⚡</span>
                  选择演化压力
                </label>
                <div className="pressure-grid">
                  {availablePressures.map(p => (
                    <button
                      key={p.name}
                      className={`pressure-chip ${selectedPressures.includes(p.name) ? 'selected' : ''}`}
                      onClick={() => togglePressure(p.name)}
                      title={p.description}
                    >
                      <Zap size={12} />
                      <span>{p.name_cn || p.name}</span>
                    </button>
                  ))}
                </div>
              </div>
              
              {/* 选项 */}
              <div className="form-section">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={generateDescription}
                    onChange={(e) => setGenerateDescription(e.target.checked)}
                  />
                  <span>生成 AI 描述（需要更长时间）</span>
                </label>
              </div>
              
              {/* 预测按钮 */}
              <button 
                className="predict-btn"
                onClick={handlePredict}
                disabled={predictLoading || !predictSpeciesCode || selectedPressures.length === 0}
              >
                {predictLoading ? (
                  <><span className="spinner" /> 预测中...</>
                ) : (
                  <><TrendingUp size={18} /> 开始预测</>
                )}
              </button>
            </div>
            
            {/* 预测结果 */}
            {predictionResult && (
              <div className="predict-result">
                <div className="result-header-card">
                  <div className="species-info">
                    <h3>{predictionResult.species_name}</h3>
                    <span className="species-code">{predictionResult.species_code}</span>
                  </div>
                  <div className="confidence-badge">
                    置信度: {(predictionResult.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                
                {/* 应用的压力 */}
                <div className="applied-pressures">
                  <span className="section-label">应用压力：</span>
                  <div className="pressure-tags">
                    {predictionResult.applied_pressures.map(p => (
                      <span key={p} className="pressure-tag">{p}</span>
                    ))}
                  </div>
                </div>
                
                {/* 预测的特征变化 */}
                <div className="trait-changes">
                  <span className="section-label">预测特征变化：</span>
                  <div className="traits-grid">
                    {Object.entries(predictionResult.predicted_trait_changes).map(([trait, change]) => (
                      <div key={trait} className="trait-change-item">
                        <span className="trait-name">{trait}</span>
                        <div className="change-bar">
                          <div 
                            className={`change-fill ${change >= 0 ? 'positive' : 'negative'}`}
                            style={{ width: `${Math.min(Math.abs(change) * 10, 100)}%` }}
                          />
                        </div>
                        <span className={`change-value ${change >= 0 ? 'positive' : 'negative'}`}>
                          {change >= 0 ? '+' : ''}{change.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* 参考物种 */}
                {predictionResult.reference_species.length > 0 && (
                  <div className="reference-species">
                    <span className="section-label">参考物种：</span>
                    <div className="reference-list">
                      {predictionResult.reference_species.map(ref => (
                        <div key={ref.code} className="reference-item">
                          <span className="ref-name">{ref.name}</span>
                          <span className="ref-code">{ref.code}</span>
                          <span className="ref-similarity">{(ref.similarity * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* AI 描述 */}
                {predictionResult.predicted_description && (
                  <div className="ai-description">
                    <span className="section-label"><Sparkles size={14} /> AI 分析：</span>
                    <p>{predictionResult.predicted_description}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      
      <style>{`
        .ai-assistant-panel {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(10, 15, 30, 0.99) 100%);
        }
        
        /* Tab Bar */
        .tab-bar {
          display: flex;
          gap: 4px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        
        .tab-button {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 20px;
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .tab-button:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.9);
        }
        
        .tab-button.active {
          background: rgba(59, 130, 246, 0.15);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }
        
        /* Error Banner */
        .error-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 16px;
          background: rgba(239, 68, 68, 0.15);
          border-bottom: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5;
          font-size: 0.9rem;
        }
        
        .error-banner button {
          background: none;
          border: none;
          color: inherit;
          cursor: pointer;
          padding: 4px;
        }
        
        /* Panel Content */
        .panel-content {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
        }
        
        /* Search Section */
        .search-section {
          margin-bottom: 20px;
        }
        
        .search-input-wrapper {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          margin-bottom: 12px;
        }
        
        .search-icon {
          color: rgba(255, 255, 255, 0.4);
        }
        
        .search-input {
          flex: 1;
          background: none;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 1rem;
        }
        
        .search-input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }
        
        .search-btn {
          padding: 8px 20px;
          background: linear-gradient(135deg, #3b82f6, #2563eb);
          border: none;
          border-radius: 8px;
          color: white;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .search-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
        
        .search-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        /* Search Filters */
        .search-filters {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .filter-label {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }
        
        .filter-chip {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid transparent;
          border-radius: 20px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .filter-chip:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        
        .filter-chip.active {
          background: rgba(var(--chip-color), 0.15);
          color: var(--chip-color);
        }
        
        /* Results */
        .results-section {
          flex: 1;
        }
        
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 60px 20px;
          color: rgba(255, 255, 255, 0.4);
          text-align: center;
        }
        
        .empty-state p {
          margin: 8px 0 0 0;
        }
        
        .empty-state .hint {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.3);
        }
        
        .results-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .result-card {
          padding: 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          transition: all 0.2s;
        }
        
        .result-card:hover {
          background: rgba(255, 255, 255, 0.05);
          border-color: rgba(59, 130, 246, 0.3);
        }
        
        .result-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }
        
        .result-type-badge {
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 0.75rem;
          font-weight: 600;
        }
        
        .result-similarity {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: 'JetBrains Mono', monospace;
        }
        
        .result-title {
          margin: 0 0 8px 0;
          font-size: 1.05rem;
          font-weight: 600;
          color: #f1f5f9;
        }
        
        .result-desc {
          margin: 0;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.7);
          line-height: 1.5;
        }
        
        .result-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        
        .meta-tag {
          padding: 3px 8px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
        }
        
        /* QA Panel */
        .qa-panel {
          display: flex;
          flex-direction: column;
        }
        
        .qa-history {
          flex: 1;
          overflow-y: auto;
          padding-bottom: 20px;
        }
        
        .qa-exchange {
          margin-bottom: 20px;
        }
        
        .user-question {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 12px 16px;
          background: rgba(59, 130, 246, 0.1);
          border-radius: 12px 12px 12px 4px;
          color: #93c5fd;
          margin-bottom: 12px;
        }
        
        .ai-answer {
          padding: 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 4px 12px 12px 12px;
        }
        
        .answer-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
          font-size: 0.85rem;
          color: #a78bfa;
        }
        
        .confidence {
          margin-left: auto;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
        }
        
        .ai-answer p {
          margin: 0;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.85);
        }
        
        .answer-sources {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .sources-label {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
        }
        
        .source-tag {
          padding: 3px 8px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.6);
        }
        
        /* Follow-up */
        .follow-up-section {
          padding: 12px 0;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .follow-up-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
          margin-bottom: 10px;
        }
        
        .follow-up-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        
        .follow-up-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: rgba(167, 139, 250, 0.1);
          border: 1px solid rgba(167, 139, 250, 0.2);
          border-radius: 20px;
          color: #c4b5fd;
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .follow-up-btn:hover {
          background: rgba(167, 139, 250, 0.2);
        }
        
        /* QA Input */
        .qa-input-section {
          padding-top: 16px;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
        }
        
        .qa-input-wrapper {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
        }
        
        .qa-input {
          flex: 1;
          background: none;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 1rem;
        }
        
        .qa-input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }
        
        .qa-send-btn {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #a855f7, #7c3aed);
          border: none;
          border-radius: 10px;
          color: white;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .qa-send-btn:hover:not(:disabled) {
          transform: scale(1.05);
        }
        
        .qa-send-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        /* Predict Panel */
        .predict-panel {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }
        
        .predict-form {
          padding: 20px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 16px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .form-section {
          margin-bottom: 20px;
        }
        
        .form-label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.9rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.8);
          margin-bottom: 10px;
        }
        
        .label-icon {
          font-size: 1rem;
        }
        
        .form-input {
          width: 100%;
          padding: 12px 16px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.95rem;
          transition: all 0.2s;
        }
        
        .form-input:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
        }
        
        .pressure-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        
        .pressure-chip {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 20px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .pressure-chip:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        
        .pressure-chip.selected {
          background: rgba(251, 191, 36, 0.15);
          border-color: rgba(251, 191, 36, 0.4);
          color: #fbbf24;
        }
        
        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.7);
          cursor: pointer;
        }
        
        .checkbox-label input {
          width: 18px;
          height: 18px;
          accent-color: #3b82f6;
        }
        
        .predict-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          width: 100%;
          padding: 14px;
          background: linear-gradient(135deg, #10b981, #059669);
          border: none;
          border-radius: 12px;
          color: white;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .predict-btn:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(16, 185, 129, 0.3);
        }
        
        .predict-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        /* Predict Result */
        .predict-result {
          padding: 20px;
          background: rgba(16, 185, 129, 0.05);
          border: 1px solid rgba(16, 185, 129, 0.2);
          border-radius: 16px;
        }
        
        .result-header-card {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding-bottom: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          margin-bottom: 16px;
        }
        
        .species-info h3 {
          margin: 0 0 4px 0;
          font-size: 1.2rem;
          color: #f1f5f9;
        }
        
        .species-code {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: 'JetBrains Mono', monospace;
        }
        
        .confidence-badge {
          padding: 8px 16px;
          background: rgba(16, 185, 129, 0.2);
          border-radius: 20px;
          font-size: 0.85rem;
          font-weight: 600;
          color: #34d399;
        }
        
        .section-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.6);
          margin-bottom: 10px;
        }
        
        .applied-pressures, .reference-species, .ai-description {
          margin-bottom: 16px;
        }
        
        .pressure-tags, .reference-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        
        .pressure-tag {
          padding: 6px 12px;
          background: rgba(251, 191, 36, 0.15);
          border-radius: 6px;
          font-size: 0.85rem;
          color: #fbbf24;
        }
        
        .trait-changes {
          margin-bottom: 16px;
        }
        
        .traits-grid {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        
        .trait-change-item {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        .trait-name {
          width: 100px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
        }
        
        .change-bar {
          flex: 1;
          height: 8px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          overflow: hidden;
        }
        
        .change-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s;
        }
        
        .change-fill.positive {
          background: linear-gradient(90deg, #10b981, #34d399);
        }
        
        .change-fill.negative {
          background: linear-gradient(90deg, #f43f5e, #fb7185);
        }
        
        .change-value {
          width: 50px;
          text-align: right;
          font-size: 0.85rem;
          font-family: 'JetBrains Mono', monospace;
          font-weight: 600;
        }
        
        .change-value.positive {
          color: #34d399;
        }
        
        .change-value.negative {
          color: #fb7185;
        }
        
        .reference-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 14px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 8px;
        }
        
        .ref-name {
          font-size: 0.9rem;
          color: #f1f5f9;
        }
        
        .ref-code {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: 'JetBrains Mono', monospace;
        }
        
        .ref-similarity {
          margin-left: auto;
          font-size: 0.8rem;
          color: #60a5fa;
        }
        
        .ai-description p {
          margin: 0;
          padding: 14px;
          background: rgba(167, 139, 250, 0.1);
          border-radius: 10px;
          font-size: 0.95rem;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.85);
        }
        
        /* Spinner */
        .spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        /* Scrollbar */
        .panel-content::-webkit-scrollbar,
        .qa-history::-webkit-scrollbar {
          width: 6px;
        }
        
        .panel-content::-webkit-scrollbar-track,
        .qa-history::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }
        
        .panel-content::-webkit-scrollbar-thumb,
        .qa-history::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 3px;
        }
      `}</style>
    </GamePanel>
  );
}

