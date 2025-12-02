/**
 * AI 增强的演化年鉴 - 整合 AI 叙事和时代划分功能
 * 
 * 功能：
 * 1. 时代划分 - 自动识别演化历史中的关键时代
 * 2. AI 叙事 - 为每个回合生成叙事性描述
 * 3. 物种传记入口 - 快速查看物种的历史传记
 */

import { useState, useEffect, useCallback } from "react";
import { Clock, Sparkles, Globe, ChevronDown, ChevronUp, RefreshCw, BookOpen, Zap } from "lucide-react";
import { GamePanel } from "./common/GamePanel";
import { embeddingApi, type NarrativeResponse, type Era } from "@/services/embedding.api";
import type { TurnReport } from "@/services/api.types";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface Props {
  reports: TurnReport[];
  onClose?: () => void;
}

export function AIEnhancedTimeline({ reports, onClose }: Props) {
  const [activeView, setActiveView] = useState<"timeline" | "eras">("timeline");
  
  // AI 叙事状态
  const [narratives, setNarratives] = useState<Map<number, NarrativeResponse>>(new Map());
  const [loadingTurns, setLoadingTurns] = useState<Set<number>>(new Set());
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set());
  
  // 时代划分状态
  const [eras, setEras] = useState<Era[]>([]);
  const [erasLoading, setErasLoading] = useState(false);
  const [expandedEras, setExpandedEras] = useState<Set<string>>(new Set());
  
  const [error, setError] = useState<string | null>(null);
  
  // 加载时代划分
  const loadEras = useCallback(async () => {
    if (reports.length === 0) return;
    
    setErasLoading(true);
    setError(null);
    try {
      const maxTurn = Math.max(...reports.map(r => r.turn_index));
      const result = await embeddingApi.getEras(0, maxTurn);
      setEras(result.eras);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载时代划分失败");
    } finally {
      setErasLoading(false);
    }
  }, [reports]);
  
  // 加载单个回合的 AI 叙事
  const loadNarrative = useCallback(async (turnIndex: number) => {
    if (narratives.has(turnIndex) || loadingTurns.has(turnIndex)) return;
    
    setLoadingTurns(prev => new Set(prev).add(turnIndex));
    try {
      const result = await embeddingApi.getTurnNarrative(turnIndex);
      setNarratives(prev => new Map(prev).set(turnIndex, result));
    } catch (err: unknown) {
      console.error(`加载回合 ${turnIndex} 叙事失败:`, err);
    } finally {
      setLoadingTurns(prev => {
        const next = new Set(prev);
        next.delete(turnIndex);
        return next;
      });
    }
  }, [narratives, loadingTurns]);
  
  // 切换回合展开状态
  const toggleTurn = (turnIndex: number) => {
    setExpandedTurns(prev => {
      const next = new Set(prev);
      if (next.has(turnIndex)) {
        next.delete(turnIndex);
      } else {
        next.add(turnIndex);
        // 展开时自动加载叙事
        loadNarrative(turnIndex);
      }
      return next;
    });
  };
  
  // 切换时代展开状态
  const toggleEra = (eraName: string) => {
    setExpandedEras(prev => {
      const next = new Set(prev);
      if (next.has(eraName)) {
        next.delete(eraName);
      } else {
        next.add(eraName);
      }
      return next;
    });
  };
  
  // 切换到时代视图时自动加载
  useEffect(() => {
    if (activeView === "eras" && eras.length === 0 && !erasLoading) {
      loadEras();
    }
  }, [activeView, eras, erasLoading, loadEras]);
  
  const getEraColor = (index: number) => {
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4'];
    return colors[index % colors.length];
  };

  return (
    <GamePanel
      title="演化年鉴 (AI 增强版)"
      onClose={onClose}
      variant="modal"
      width="900px"
      height="85vh"
    >
      <div className="ai-timeline">
        {/* 视图切换 */}
        <div className="view-switcher">
          <button 
            className={`view-btn ${activeView === 'timeline' ? 'active' : ''}`}
            onClick={() => setActiveView('timeline')}
          >
            <Clock size={16} />
            <span>回合时间线</span>
          </button>
          <button 
            className={`view-btn ${activeView === 'eras' ? 'active' : ''}`}
            onClick={() => setActiveView('eras')}
          >
            <Globe size={16} />
            <span>时代划分</span>
          </button>
        </div>
        
        {/* 错误提示 */}
        {error && (
          <div className="error-banner">
            <span>{error}</span>
          </div>
        )}
        
        {/* 回合时间线视图 */}
        {activeView === 'timeline' && (
          <div className="timeline-view">
            {reports.length === 0 ? (
              <div className="empty-state">
                <Clock size={48} strokeWidth={1} />
                <p>暂无历史记录</p>
              </div>
            ) : (
              <div className="timeline-list">
                {reports.slice().reverse().map(report => {
                  const isExpanded = expandedTurns.has(report.turn_index);
                  const isLoading = loadingTurns.has(report.turn_index);
                  const narrative = narratives.get(report.turn_index);
                  
                  return (
                    <div key={report.turn_index} className="timeline-card">
                      <div 
                        className={`timeline-header ${isExpanded ? 'expanded' : ''}`}
                        onClick={() => toggleTurn(report.turn_index)}
                      >
                        <div className="turn-info">
                          <span className="turn-number">回合 #{report.turn_index + 1}</span>
                          <span className="turn-summary">{report.pressures_summary || "平稳期"}</span>
                        </div>
                        <div className="turn-stats">
                          <span className="stat">🧬 {report.species.length} 物种</span>
                          {(report.extinction_count ?? 0) > 0 && (
                            <span className="stat extinct">💀 {report.extinction_count} 灭绝</span>
                          )}
                        </div>
                        <button className="expand-btn">
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      </div>
                      
                      {isExpanded && (
                        <div className="timeline-content">
                          {/* 原始叙事 */}
                          <div className="original-narrative">
                            <h5>📜 回合叙事</h5>
                            <div className="narrative-text">
                              <MarkdownRenderer content={report.narrative} />
                            </div>
                          </div>
                          
                          {/* AI 增强叙事 */}
                          <div className="ai-narrative">
                            <div className="ai-header">
                              <h5><Sparkles size={14} /> AI 深度分析</h5>
                              {!narrative && !isLoading && (
                                <button 
                                  className="load-ai-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    loadNarrative(report.turn_index);
                                  }}
                                >
                                  加载 AI 分析
                                </button>
                              )}
                            </div>
                            
                            {isLoading ? (
                              <div className="loading-state">
                                <span className="spinner" />
                                <span>AI 正在分析...</span>
                              </div>
                            ) : narrative ? (
                              <div className="ai-content">
                                <div className="ai-text">
                                  <p>{narrative.narrative}</p>
                                </div>
                                
                                {narrative.key_events.length > 0 && (
                                  <div className="key-events">
                                    <h6>关键事件</h6>
                                    <div className="events-list">
                                      {narrative.key_events.map((event, idx) => (
                                        <div key={idx} className="event-item">
                                          <span className="event-title">{event.title}</span>
                                          <span className="event-desc">{event.description}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                
                                {narrative.related_species.length > 0 && (
                                  <div className="related-species">
                                    <span className="label">相关物种：</span>
                                    {narrative.related_species.map(code => (
                                      <span key={code} className="species-tag">{code}</span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ) : (
                              <p className="ai-placeholder">点击上方按钮加载 AI 深度分析</p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
        
        {/* 时代划分视图 */}
        {activeView === 'eras' && (
          <div className="eras-view">
            <div className="eras-header">
              <p className="eras-intro">
                AI 自动识别演化历史中的关键时代，根据重大事件和物种变化进行划分
              </p>
              <button 
                className="refresh-btn"
                onClick={loadEras}
                disabled={erasLoading}
              >
                <RefreshCw size={14} className={erasLoading ? 'spinning' : ''} />
                {erasLoading ? '分析中...' : '重新分析'}
              </button>
            </div>
            
            {erasLoading && eras.length === 0 ? (
              <div className="loading-state">
                <span className="spinner" />
                <span>AI 正在分析演化历史...</span>
              </div>
            ) : eras.length === 0 ? (
              <div className="empty-state">
                <Globe size={48} strokeWidth={1} />
                <p>暂无足够的历史数据进行时代划分</p>
                <p className="hint">需要至少经历几个回合的演化</p>
              </div>
            ) : (
              <div className="eras-list">
                {eras.map((era, idx) => {
                  const isExpanded = expandedEras.has(era.name);
                  const color = getEraColor(idx);
                  
                  return (
                    <div 
                      key={era.name} 
                      className="era-card"
                      style={{ borderLeftColor: color }}
                    >
                      <div 
                        className="era-header"
                        onClick={() => toggleEra(era.name)}
                      >
                        <div className="era-title" style={{ color }}>
                          <span className="era-icon">🌍</span>
                          <span>{era.name}</span>
                        </div>
                        <div className="era-meta">
                          <span className="era-turns">
                            回合 {era.start_turn + 1} - {era.end_turn + 1}
                          </span>
                          <span className="era-events">
                            <Zap size={12} />
                            {era.event_count} 事件
                          </span>
                        </div>
                        <button className="expand-btn">
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      </div>
                      
                      {isExpanded && (
                        <div className="era-content">
                          <p>{era.summary}</p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
      
      <style>{`
        .ai-timeline {
          display: flex;
          flex-direction: column;
          height: 100%;
          padding: 16px;
          background: linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(10, 15, 30, 0.99) 100%);
        }
        
        .view-switcher {
          display: flex;
          gap: 8px;
          margin-bottom: 20px;
        }
        
        .view-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px 24px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .view-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.9);
        }
        
        .view-btn.active {
          background: rgba(59, 130, 246, 0.15);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }
        
        .error-banner {
          padding: 12px 16px;
          background: rgba(239, 68, 68, 0.15);
          border-radius: 8px;
          color: #fca5a5;
          margin-bottom: 16px;
        }
        
        .timeline-view, .eras-view {
          flex: 1;
          overflow-y: auto;
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
          margin: 12px 0 0 0;
        }
        
        .empty-state .hint {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.3);
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
          border: 2px solid rgba(59, 130, 246, 0.2);
          border-top-color: #3b82f6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        /* Timeline List */
        .timeline-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .timeline-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          overflow: hidden;
          transition: all 0.2s;
        }
        
        .timeline-card:hover {
          border-color: rgba(59, 130, 246, 0.3);
        }
        
        .timeline-header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .timeline-header:hover {
          background: rgba(255, 255, 255, 0.02);
        }
        
        .timeline-header.expanded {
          background: rgba(59, 130, 246, 0.05);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .turn-info {
          flex: 1;
        }
        
        .turn-number {
          font-weight: 600;
          font-size: 1rem;
          color: #f1f5f9;
          margin-right: 12px;
        }
        
        .turn-summary {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }
        
        .turn-stats {
          display: flex;
          gap: 12px;
        }
        
        .stat {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
        }
        
        .stat.extinct {
          color: #ef4444;
        }
        
        .expand-btn {
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: none;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
        }
        
        .timeline-content {
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .original-narrative, .ai-narrative {
          padding: 14px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 10px;
        }
        
        .original-narrative h5, .ai-header h5 {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 0 0 12px 0;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.7);
        }
        
        .ai-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        
        .ai-header h5 {
          color: #c4b5fd;
        }
        
        .load-ai-btn {
          padding: 6px 14px;
          background: rgba(167, 139, 250, 0.15);
          border: 1px solid rgba(167, 139, 250, 0.3);
          border-radius: 6px;
          color: #c4b5fd;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .load-ai-btn:hover {
          background: rgba(167, 139, 250, 0.25);
        }
        
        .narrative-text {
          font-size: 0.9rem;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.8);
        }
        
        .ai-text p {
          margin: 0;
          font-size: 0.9rem;
          line-height: 1.7;
          color: rgba(255, 255, 255, 0.85);
        }
        
        .ai-placeholder {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.4);
          font-style: italic;
        }
        
        .key-events {
          margin-top: 14px;
          padding-top: 14px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .key-events h6 {
          margin: 0 0 10px 0;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
        }
        
        .events-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .event-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 8px 12px;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 6px;
        }
        
        .event-title {
          font-size: 0.85rem;
          font-weight: 600;
          color: #f1f5f9;
        }
        
        .event-desc {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
        }
        
        .related-species {
          margin-top: 12px;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
        }
        
        .related-species .label {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
        }
        
        .species-tag {
          padding: 4px 10px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          font-size: 0.75rem;
          font-family: 'JetBrains Mono', monospace;
          color: rgba(255, 255, 255, 0.7);
        }
        
        /* Eras View */
        .eras-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 20px;
          padding: 14px;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 10px;
        }
        
        .eras-intro {
          margin: 0;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
        }
        
        .refresh-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          background: rgba(59, 130, 246, 0.15);
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 8px;
          color: #60a5fa;
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .refresh-btn:hover:not(:disabled) {
          background: rgba(59, 130, 246, 0.25);
        }
        
        .refresh-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        .refresh-btn .spinning {
          animation: spin 1s linear infinite;
        }
        
        .eras-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .era-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-left: 4px solid;
          border-radius: 0 12px 12px 0;
          overflow: hidden;
        }
        
        .era-header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .era-header:hover {
          background: rgba(255, 255, 255, 0.02);
        }
        
        .era-title {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1.1rem;
          font-weight: 600;
        }
        
        .era-icon {
          font-size: 1.2rem;
        }
        
        .era-meta {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-left: auto;
        }
        
        .era-turns {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: 'JetBrains Mono', monospace;
        }
        
        .era-events {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 0.8rem;
          color: #fbbf24;
        }
        
        .era-content {
          padding: 16px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .era-content p {
          margin: 0;
          font-size: 0.9rem;
          line-height: 1.7;
          color: rgba(255, 255, 255, 0.8);
        }
        
        /* Scrollbar */
        .timeline-view::-webkit-scrollbar,
        .eras-view::-webkit-scrollbar {
          width: 6px;
        }
        
        .timeline-view::-webkit-scrollbar-track,
        .eras-view::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }
        
        .timeline-view::-webkit-scrollbar-thumb,
        .eras-view::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 3px;
        }
      `}</style>
    </GamePanel>
  );
}

