import { useEffect, useState, useRef, useCallback } from "react";
import { connectToEventStream, abortCurrentTasks, getTaskDiagnostics } from "../services/api";

interface Props {
  message?: string;
  showDetails?: boolean;
}

// 连接状态类型
type ConnectionStatus = "connecting" | "connected" | "receiving" | "error" | "disconnected";

// 演化阶段定义 - 与后端新流程匹配
const EVOLUTION_STAGES = [
  { id: "pressure", icon: "🌡️", label: "环境压力", color: "#fb923c" },
  { id: "geology", icon: "🗺️", label: "地质演化", color: "#8b5cf6" },
  { id: "ecology", icon: "📊", label: "生态分析", color: "#fbbf24" },
  { id: "mortality", icon: "💀", label: "死亡/迁徙", color: "#f43f5e" },
  { id: "ai_eval", icon: "🤖", label: "AI评估", color: "#a855f7" },
  { id: "reproduction", icon: "🐣", label: "繁殖增长", color: "#4ade80" },
  { id: "evolution", icon: "🧬", label: "演化事件", color: "#2dd4bf" },
  { id: "ai_tasks", icon: "🔀", label: "AI处理", color: "#c084fc" },
  { id: "report", icon: "📝", label: "生成报告", color: "#38bdf8" },
];

// AI并发处理进度状态
interface AIProgress {
  total: number;
  completed: number;
  current_task: string;
  last_activity: number;
}

export function TurnProgressOverlay({ message = "推演进行中...", showDetails = true }: Props) {
  // 状态管理
  const [displayedLogs, setDisplayedLogs] = useState<Array<{ icon: string; text: string; category: string; timestamp: number }>>([]);
  const [currentStage, setCurrentStage] = useState<string>("等待推演开始...");
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(-1);
  const [streamingText, setStreamingText] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [tokenCount, setTokenCount] = useState<number>(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [isStreamingActive, setIsStreamingActive] = useState<boolean>(false);
  
  // AI并发处理进度
  const [aiProgress, setAIProgress] = useState<AIProgress | null>(null);
  const [lastAIActivity, setLastAIActivity] = useState<number>(0);
  const [aiElapsedSeconds, setAIElapsedSeconds] = useState<number>(0);
  
  // 任务中断状态
  const [isAborting, setIsAborting] = useState<boolean>(false);
  const [abortMessage, setAbortMessage] = useState<string>("");
  
  // 日志队列管理（逐条动画显示）
  const logQueueRef = useRef<Array<{ icon: string; text: string; category: string; timestamp: number }>>([]);
  const isProcessingRef = useRef<boolean>(false);
  
  // Refs
  const logContainerRef = useRef<HTMLDivElement>(null);
  const streamingContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 自动滚动流式文本到底部
  const scrollStreamingToBottom = useCallback(() => {
    if (streamingContainerRef.current) {
      streamingContainerRef.current.scrollTop = streamingContainerRef.current.scrollHeight;
    }
  }, []);
  
  // 自动滚动日志到底部
  const scrollLogsToBottom = useCallback(() => {
    if (logContainerRef.current) {
      const logList = logContainerRef.current.querySelector('.log-list');
      if (logList) {
        logList.scrollTop = logList.scrollHeight;
      }
    }
  }, []);

  // 逐条处理日志队列的函数
  const processLogQueue = useCallback(() => {
    if (isProcessingRef.current || logQueueRef.current.length === 0) return;
    
    isProcessingRef.current = true;
    
    const processNext = () => {
      if (logQueueRef.current.length === 0) {
        isProcessingRef.current = false;
        return;
      }
      
      const nextLog = logQueueRef.current.shift()!;
      setDisplayedLogs(prev => [...prev, nextLog].slice(-50));
      
      // 滚动到底部
      requestAnimationFrame(scrollLogsToBottom);
      
      // 根据消息类型决定延迟时间
      // 阶段切换消息显示稍长一些，普通消息较快
      const delay = nextLog.category === "系统" || nextLog.text.includes("阶段") ? 200 : 80;
      
      if (logQueueRef.current.length > 0) {
        setTimeout(processNext, delay);
      } else {
        isProcessingRef.current = false;
      }
    };
    
    processNext();
  }, [scrollLogsToBottom]);

  // 添加日志到队列
  const addLogToQueue = useCallback((log: { icon: string; text: string; category: string; timestamp: number }) => {
    logQueueRef.current.push(log);
    processLogQueue();
  }, [processLogQueue]);
  
  // AI活动计时器
  useEffect(() => {
    if (!aiProgress || aiProgress.completed >= aiProgress.total) {
      setAIElapsedSeconds(0);
      return;
    }
    
    // 如果 lastAIActivity 为 0 或无效，不计算
    if (!lastAIActivity || lastAIActivity <= 0) {
      setAIElapsedSeconds(0);
      return;
    }
    
    const timer = setInterval(() => {
      const now = Date.now();
      const elapsed = Math.floor((now - lastAIActivity) / 1000);
      // 只显示合理的时间（最多显示300秒）
      setAIElapsedSeconds(Math.min(elapsed, 300));
    }, 1000);
    
    return () => clearInterval(timer);
  }, [aiProgress, lastAIActivity]);

  // 根据阶段文本判断当前阶段索引 - 与新流程匹配
  const detectStageIndex = useCallback((stageText: string): number => {
    const lowerText = stageText.toLowerCase();
    // 0. 环境压力
    if (lowerText.includes("压力") || lowerText.includes("pressure")) return 0;
    // 1. 地质演化
    if (lowerText.includes("地图") || lowerText.includes("地质") || lowerText.includes("geology") || lowerText.includes("海平面")) return 1;
    // 2. 生态分析（物种列表、分层、生态位）
    if (lowerText.includes("物种列表") || lowerText.includes("分层") || lowerText.includes("生态位") || lowerText.includes("ecology")) return 2;
    // 3. 死亡/迁徙（营养级、死亡率、迁徙）
    if (lowerText.includes("死亡") || lowerText.includes("mortality") || lowerText.includes("营养级") || lowerText.includes("迁徙") || lowerText.includes("migration") || lowerText.includes("阶段1") || lowerText.includes("阶段2") || lowerText.includes("阶段3")) return 3;
    // 4. AI综合评估
    if ((lowerText.includes("ai") && lowerText.includes("评估")) || lowerText.includes("ai综合") || lowerText.includes("阶段3.5")) return 4;
    // 5. 繁殖增长
    if (lowerText.includes("繁殖") || lowerText.includes("reproduction") || lowerText.includes("种群")) return 5;
    // 6. 演化事件（基因激活、基因流动、亚种晋升）
    if (lowerText.includes("基因") || lowerText.includes("激活") || lowerText.includes("流动") || lowerText.includes("亚种") || lowerText.includes("晋升")) return 6;
    // 7. AI处理（叙事、适应、分化）
    if (lowerText.includes("ai顺序") || lowerText.includes("分化") || lowerText.includes("speciation") || lowerText.includes("适应") || lowerText.includes("叙事生成")) return 7;
    // 8. 生成报告
    if (lowerText.includes("报告") || lowerText.includes("report")) return 8;
    return -1;
  }, []);

  useEffect(() => {
    if (!showDetails) return;

    console.log("[事件流] 正在连接到服务器...");
    setConnectionStatus("connecting");
    setStartTime(Date.now());
    
    const eventSource = connectToEventStream((event) => {
      if (event.type === 'connected') {
        console.log("[事件流] 连接成功");
        setConnectionStatus("connected");
        setCurrentStage("已连接，等待推演开始...");
        return;
      }

      if (event.type === 'narrative_token') {
        // 处理流式文本片段
        const token = event.message || "";
        setStreamingText(prev => prev + token);
        setTokenCount(prev => prev + 1);
        setIsStreamingActive(true);
        setConnectionStatus("receiving");
        
        // 自动滚动
        requestAnimationFrame(scrollStreamingToBottom);
        return;
      }
      
      // 处理AI并发进度事件
      if (event.type === 'ai_progress') {
        setAIProgress({
          total: event.total || 0,
          completed: event.completed || 0,
          current_task: event.current_task || "",
          last_activity: Date.now()
        });
        setLastAIActivity(Date.now());
        setConnectionStatus("receiving");
        return;
      }
      
      // 处理AI心跳事件
      if (event.type === 'ai_heartbeat') {
        setLastAIActivity(Date.now());
        setConnectionStatus("receiving");
        return;
      }
      
      // 处理普通事件
      const eventMessage = event.message || "";
      const category = event.category || "其他";
      
      // 根据消息内容推断图标
      let icon = "📝";
      if (eventMessage.includes("🌍") || eventMessage.includes("🗺️")) icon = "🗺️";
      else if (eventMessage.includes("🧬") || eventMessage.includes("🔀")) icon = "🧬";
      else if (eventMessage.includes("🤖") || eventMessage.includes("AI")) icon = "🤖";
      else if (eventMessage.includes("💀") || eventMessage.includes("死亡")) icon = "💀";
      else if (eventMessage.includes("🐣") || eventMessage.includes("繁殖")) icon = "🐣";
      else if (eventMessage.includes("🌳") || eventMessage.includes("分化")) icon = "🌳";
      else if (eventMessage.includes("🦅") || eventMessage.includes("迁徙")) icon = "🦅";
      else if (eventMessage.includes("📊") || eventMessage.includes("分析")) icon = "📊";
      else if (eventMessage.includes("✅") || eventMessage.includes("完成")) icon = "✅";
      else if (eventMessage.includes("❌") || eventMessage.includes("失败")) icon = "❌";
      
      const cleanMessage = eventMessage.replace(/[\u{1F300}-\u{1F9FF}]/gu, "").trim();
      
      // 使用队列方式添加日志，实现逐条动画
      addLogToQueue({ 
        icon, 
        text: cleanMessage, 
        category, 
        timestamp: Date.now() 
      });
      
      // 更新当前阶段
      if (event.type === 'stage') {
        const stageText = cleanMessage.length > 60 ? cleanMessage.substring(0, 60) + '...' : cleanMessage;
        setCurrentStage(stageText);
        setCurrentStageIndex(detectStageIndex(cleanMessage));
        
        // 如果进入AI并发处理阶段，初始化AI进度
        if (cleanMessage.includes("AI并发")) {
          setAIProgress({ total: 4, completed: 0, current_task: "初始化...", last_activity: Date.now() });
          setLastAIActivity(Date.now());
        }
        
        // 如果进入报告阶段，清空之前的流式文本和AI进度
        if (cleanMessage.includes("报告") || cleanMessage.includes("叙事")) {
          setStreamingText("");
          setTokenCount(0);
          setIsStreamingActive(false);
          setAIProgress(null);
        }
      }

      // 支持两种完成事件类型：turn_complete 和 complete
      if (event.type === 'turn_complete' || event.type === 'complete') {
        console.log("[事件流] 推演完成");
        setIsStreamingActive(false);
        setConnectionStatus("connected");
        setAIProgress(null);
        setCurrentStage("推演完成！");
        setCurrentStageIndex(EVOLUTION_STAGES.length - 1);
      }

      if (event.type === 'error') {
        setConnectionStatus("error");
      }
    });
    
    eventSourceRef.current = eventSource;

    return () => {
      console.log("[事件流] 断开连接");
      setConnectionStatus("disconnected");
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [showDetails, detectStageIndex, scrollStreamingToBottom, addLogToQueue]);

  // 重置状态
  useEffect(() => {
    if (message.includes("开始")) {
      setDisplayedLogs([]);
      logQueueRef.current = [];
      isProcessingRef.current = false;
      setStreamingText("");
      setTokenCount(0);
      setCurrentStageIndex(-1);
      setIsStreamingActive(false);
      setStartTime(Date.now());
      setAIProgress(null);
      setLastAIActivity(0);
      setAIElapsedSeconds(0);
    }
  }, [message]);

  // 计算经过时间
  const elapsedTime = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0;
  const elapsedMinutes = Math.floor(elapsedTime / 60);
  const elapsedSeconds = elapsedTime % 60;

  // 重置连接处理函数
  const handleAbortTasks = useCallback(async () => {
    if (isAborting) return;
    
    setIsAborting(true);
    setAbortMessage("正在重置连接...");
    
    try {
      const result = await abortCurrentTasks();
      if (result.success) {
        setAbortMessage(`✅ ${result.message}`);
        // 添加日志
        logQueueRef.current.push({
          icon: "🔄",
          text: `连接已重置 - 活跃: ${result.active_requests || 0}, 排队: ${result.queued_requests || 0}`,
          category: "系统",
          timestamp: Date.now()
        });
      } else {
        setAbortMessage(`❌ ${result.message}`);
      }
    } catch (error: any) {
      setAbortMessage(`❌ 重置失败: ${error.message}`);
    }
    
    // 3秒后清除消息
    setTimeout(() => {
      setAbortMessage("");
      setIsAborting(false);
    }, 3000);
  }, [isAborting]);

  // 连接状态配置
  const statusConfig: Record<ConnectionStatus, { color: string; text: string; icon: string }> = {
    connecting: { color: "#fbbf24", text: "连接中", icon: "⏳" },
    connected: { color: "#4ade80", text: "已连接", icon: "🔗" },
    receiving: { color: "#2dd4bf", text: "接收数据", icon: "📡" },
    error: { color: "#f43f5e", text: "连接错误", icon: "❌" },
    disconnected: { color: "#94a3b8", text: "已断开", icon: "🔌" },
  };

  const currentStatusConfig = statusConfig[connectionStatus];

  return (
    <div className="evolution-overlay">
      <div className="evolution-panel">
        {/* 顶部状态栏 */}
        <div className="status-bar">
          <div className="status-item">
            <span className="status-icon" style={{ color: currentStatusConfig.color }}>
              {currentStatusConfig.icon}
            </span>
            <span className="status-text" style={{ color: currentStatusConfig.color }}>
              {currentStatusConfig.text}
            </span>
          </div>
          <div className="status-item">
            <span className="status-icon">⏱️</span>
            <span className="status-text">
              {elapsedMinutes > 0 ? `${elapsedMinutes}分` : ""}{elapsedSeconds}秒
            </span>
          </div>
          {tokenCount > 0 && (
            <div className="status-item">
              <span className="status-icon">📝</span>
              <span className="status-text">{tokenCount} tokens</span>
            </div>
          )}
          {/* 卡住时显示重置按钮（超过30秒） */}
          {elapsedTime > 30 && (
            <button 
              className="abort-btn"
              onClick={handleAbortTasks}
              disabled={isAborting}
              title="如果卡住了，点击重置连接"
            >
              {isAborting ? "⏳" : "🔄"} {isAborting ? "重置中..." : "重置连接"}
            </button>
          )}
        </div>
        {/* 重置状态消息 */}
        {abortMessage && (
          <div className="abort-message" style={{ 
            padding: '8px 16px', 
            background: abortMessage.includes('✅') ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
            borderRadius: '8px',
            marginBottom: '12px',
            fontSize: '13px',
            textAlign: 'center'
          }}>
            {abortMessage}
          </div>
        )}

        {/* DNA 双螺旋加载动画 */}
        <div className="dna-loader">
          <div className="dna-strand-container">
            {Array.from({ length: 10 }).map((_, i) => (
              <div 
                key={i} 
                className="dna-pair"
                style={{ animationDelay: `${i * 0.12}s` }}
              >
                <div className="dna-node-left" />
                <div className="dna-bridge" />
                <div className="dna-node-right" />
              </div>
            ))}
          </div>
          <div className="dna-glow" />
        </div>
        
        <h2 className="evolution-title">
          <span className="title-icon">🧬</span>
          <span className="title-text">演化推演中</span>
        </h2>
        
        <p className="evolution-message">{message}</p>
        
        {showDetails && (
          <>
            {/* 进度阶段指示器 */}
            <div className="progress-stages">
              {EVOLUTION_STAGES.map((stage, idx) => (
                <div 
                  key={stage.id}
                  className={`progress-stage ${idx <= currentStageIndex ? 'active' : ''} ${idx === currentStageIndex ? 'current' : ''}`}
                  style={{ 
                    '--stage-color': stage.color,
                    '--stage-delay': `${idx * 0.1}s`
                  } as React.CSSProperties}
                >
                  <div className="stage-circle">
                    <span className="stage-emoji">{stage.icon}</span>
                  </div>
                  <span className="stage-label">{stage.label}</span>
                </div>
              ))}
              <div 
                className="progress-line"
                style={{ 
                  width: `${Math.max(0, (currentStageIndex / (EVOLUTION_STAGES.length - 1)) * 100)}%`
                }}
              />
            </div>

            {/* 当前阶段卡片 */}
            <div className="current-stage-card">
              <span className="stage-icon-large">
                {currentStageIndex >= 0 ? EVOLUTION_STAGES[currentStageIndex]?.icon : "📖"}
              </span>
              <span className="stage-text-main">{currentStage}</span>
              {isStreamingActive && <div className="stage-pulse-indicator" />}
            </div>

            {/* AI并发处理进度指示器 */}
            {aiProgress && aiProgress.total > 0 && (
              <div className="ai-progress-container">
                <div className="ai-progress-header">
                  <div className="ai-progress-title">
                    <span className={`ai-activity-indicator ${aiElapsedSeconds < 5 ? 'active' : 'stale'}`} />
                    <span>🤖 AI 并发处理中</span>
                  </div>
                  <div className="ai-progress-stats">
                    <span className="ai-progress-count">
                      {aiProgress.completed}/{aiProgress.total} 任务
                    </span>
                    <span className="ai-elapsed-time">
                      {aiElapsedSeconds > 0 && (
                        aiElapsedSeconds >= 30 
                          ? `⚠️ ${aiElapsedSeconds}秒未响应` 
                          : `${aiElapsedSeconds}秒`
                      )}
                    </span>
                  </div>
                </div>
                <div className="ai-progress-bar-container">
                  <div 
                    className="ai-progress-bar" 
                    style={{ width: `${(aiProgress.completed / aiProgress.total) * 100}%` }}
                  />
                </div>
                {aiProgress.current_task && (
                  <div className="ai-current-task">
                    正在处理: {aiProgress.current_task}
                  </div>
                )}
                {aiElapsedSeconds >= 15 && (
                  <div className="ai-waiting-hint">
                    ⏳ AI正在处理复杂任务，请耐心等待...
                  </div>
                )}
              </div>
            )}

            {/* 流式文本显示区域 - 改进版 */}
            {(streamingText || isStreamingActive) && (
              <div className="streaming-container">
                <div className="streaming-header">
                  <div className="streaming-title">
                    <span className={`streaming-indicator ${isStreamingActive ? 'active' : ''}`} />
                    <span>AI 正在生成推演报告</span>
                  </div>
                  <div className="streaming-stats">
                    {tokenCount > 0 && <span className="token-count">{tokenCount} tokens</span>}
                  </div>
                </div>
                <div className="streaming-content" ref={streamingContainerRef}>
                  <div className="streaming-text">
                    {streamingText}
                    {isStreamingActive && <span className="typing-cursor">▊</span>}
                  </div>
                </div>
              </div>
            )}

            {/* 演化日志 */}
            <div className="evolution-log-container" ref={logContainerRef}>
              <div className="log-header">
                <span>📋 推演日志</span>
                {displayedLogs.length > 0 && (
                  <span className="log-count">{displayedLogs.length} 条</span>
                )}
                {logQueueRef.current.length > 0 && (
                  <span className="log-pending">+{logQueueRef.current.length}</span>
                )}
              </div>
              {displayedLogs.length === 0 ? (
                <div className="log-empty">
                  <span className="empty-icon">🌱</span>
                  <span>等待演化数据...</span>
                </div>
              ) : (
                <div className="log-list">
                  {displayedLogs.map((log, idx) => (
                    <div
                      key={`${log.timestamp}-${idx}`}
                      className="log-item log-item-animated"
                      style={{ 
                        '--log-color': getCategoryColor(log.category),
                      } as React.CSSProperties}
                    >
                      <span className="log-icon">{log.icon}</span>
                      <span className="log-text">{log.text}</span>
                      <span className="log-category" style={{ background: getCategoryColor(log.category) + '30' }}>
                        {log.category}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
      
      <style>{`
        .evolution-overlay {
          position: fixed;
          inset: 0;
          background: radial-gradient(ellipse at center, rgba(8, 15, 12, 0.97), rgba(3, 7, 5, 0.99));
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10000;
          backdrop-filter: blur(12px);
          padding: 12px;
        }

        .evolution-panel {
          background: linear-gradient(145deg, rgba(15, 25, 20, 0.95), rgba(8, 16, 12, 0.98));
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 20px;
          padding: 20px 24px;
          text-align: center;
          max-width: 720px;
          width: 95%;
          box-shadow: 
            0 30px 100px rgba(0, 0, 0, 0.7),
            0 0 80px rgba(45, 212, 191, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 0.03);
          max-height: calc(100vh - 24px);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        /* 大屏幕（>=1200px）稍微增加宽度 */
        @media (min-width: 1200px) {
          .evolution-panel {
            max-width: 780px;
            padding: 24px 28px;
          }
        }
        
        /* 低分辨率屏幕（<1024px）紧凑模式 */
        @media (max-width: 1024px) {
          .evolution-overlay {
            padding: 8px;
          }
          .evolution-panel {
            padding: 16px 18px;
            border-radius: 16px;
            max-width: 680px;
          }
        }
        
        /* 非常小的屏幕（<768px） */
        @media (max-width: 768px) {
          .evolution-panel {
            padding: 12px 14px;
            border-radius: 12px;
            max-width: 100%;
          }
        }

        /* 状态栏 - 紧凑响应式 */
        .status-bar {
          display: flex;
          justify-content: center;
          flex-wrap: wrap;
          gap: 8px 14px;
          margin-bottom: 10px;
          padding: 6px 12px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .status-item {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 0.7rem;
        }

        .status-icon {
          font-size: 0.8rem;
        }

        .status-text {
          color: rgba(255, 255, 255, 0.7);
          font-family: var(--font-mono, monospace);
        }

        .abort-btn {
          padding: 4px 8px;
          background: rgba(239, 68, 68, 0.2);
          border: 1px solid rgba(239, 68, 68, 0.4);
          border-radius: 5px;
          color: #fca5a5;
          font-size: 0.65rem;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 3px;
        }

        .abort-btn:hover:not(:disabled) {
          background: rgba(239, 68, 68, 0.3);
          border-color: rgba(239, 68, 68, 0.6);
          color: #fecaca;
        }

        .abort-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        /* 低分辨率优化状态栏 */
        @media (max-width: 1024px) {
          .status-bar {
            gap: 6px 10px;
            padding: 5px 10px;
            margin-bottom: 8px;
          }
          .status-item {
            font-size: 0.65rem;
          }
          .status-icon {
            font-size: 0.75rem;
          }
        }
        
        @media (max-width: 768px) {
          .status-bar {
            gap: 5px 8px;
            padding: 4px 8px;
          }
          .status-item {
            font-size: 0.6rem;
          }
          .abort-btn {
            padding: 3px 6px;
            font-size: 0.6rem;
          }
        }

        /* DNA 加载动画 - 紧凑版 */
        .dna-loader {
          position: relative;
          margin: 0 auto 10px;
          width: 50px;
          height: 55px;
        }

        .dna-strand-container {
          position: relative;
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .dna-pair {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 5px;
          animation: dna-wave 1.8s ease-in-out infinite;
        }

        .dna-node-left, .dna-node-right {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #2dd4bf;
          box-shadow: 0 0 8px rgba(45, 212, 191, 0.7);
        }

        .dna-node-right {
          background: #22c55e;
          box-shadow: 0 0 8px rgba(34, 197, 94, 0.7);
        }

        .dna-bridge {
          width: 20px;
          height: 2px;
          background: linear-gradient(90deg, rgba(45, 212, 191, 0.9), rgba(34, 197, 94, 0.9));
          border-radius: 2px;
        }

        @keyframes dna-wave {
          0%, 100% { transform: translateX(-8px) rotateY(0deg); }
          50% { transform: translateX(8px) rotateY(180deg); }
        }

        .dna-glow {
          position: absolute;
          inset: -15px;
          background: radial-gradient(ellipse at center, rgba(45, 212, 191, 0.12), transparent 65%);
          animation: glow-pulse 2.5s ease-in-out infinite;
        }

        @keyframes glow-pulse {
          0%, 100% { opacity: 0.4; transform: scale(0.95); }
          50% { opacity: 1; transform: scale(1.1); }
        }

        /* 标题 */
        .evolution-title {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          margin-bottom: 5px;
        }

        .title-icon {
          font-size: 1.3rem;
          animation: title-bounce 2.5s ease-in-out infinite;
        }

        @keyframes title-bounce {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          25% { transform: translateY(-2px) rotate(-3deg); }
          75% { transform: translateY(-2px) rotate(3deg); }
        }

        .title-text {
          font-size: 1.2rem;
          font-weight: 700;
          font-family: var(--font-display);
          background: linear-gradient(135deg, #2dd4bf, #22c55e, #4ade80);
          background-size: 200% 200%;
          animation: gradient-shift 3s ease infinite;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        @keyframes gradient-shift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }

        .evolution-message {
          font-size: 0.82rem;
          color: rgba(240, 244, 232, 0.7);
          margin-bottom: 12px;
          line-height: 1.35;
        }
        
        /* 低分辨率优化动画和标题 */
        @media (max-width: 1024px) {
          .dna-loader {
            width: 42px;
            height: 46px;
            margin-bottom: 8px;
          }
          .dna-node-left, .dna-node-right {
            width: 5px;
            height: 5px;
          }
          .dna-bridge {
            width: 16px;
          }
          .evolution-title {
            margin-bottom: 4px;
          }
          .title-icon {
            font-size: 1.1rem;
          }
          .title-text {
            font-size: 1.05rem;
          }
          .evolution-message {
            font-size: 0.78rem;
            margin-bottom: 10px;
          }
        }
        
        @media (max-width: 768px) {
          .dna-loader {
            width: 36px;
            height: 40px;
            margin-bottom: 6px;
          }
          .title-text {
            font-size: 0.95rem;
          }
          .evolution-message {
            font-size: 0.72rem;
            margin-bottom: 8px;
          }
        }

        /* 进度阶段指示器 - 紧凑布局 */
        .progress-stages {
          display: flex;
          justify-content: center;
          align-items: flex-start;
          margin-bottom: 16px;
          padding: 0;
          position: relative;
          flex-wrap: wrap;
          gap: 6px 2px;
        }

        .progress-stage {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 3px;
          z-index: 1;
          opacity: 0.35;
          transition: all 0.4s ease;
          flex-shrink: 0;
          width: 58px;
        }

        .progress-stage.active {
          opacity: 1;
        }

        .progress-stage.current .stage-circle {
          transform: scale(1.08);
          box-shadow: 0 0 14px var(--stage-color);
        }

        .stage-circle {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: rgba(0, 0, 0, 0.4);
          border: 2px solid rgba(255, 255, 255, 0.1);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.4s ease;
        }

        .progress-stage.active .stage-circle {
          border-color: var(--stage-color);
          background: color-mix(in srgb, var(--stage-color) 20%, transparent);
        }

        .stage-emoji {
          font-size: 0.85rem;
        }

        .stage-label {
          font-size: 0.6rem;
          color: rgba(255, 255, 255, 0.5);
          max-width: 58px;
          text-align: center;
          line-height: 1.15;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .progress-stage.active .stage-label {
          color: rgba(255, 255, 255, 0.9);
        }

        .progress-line {
          display: none;
        }
        
        /* 低分辨率屏幕阶段指示器紧凑模式 */
        @media (max-width: 1024px) {
          .progress-stages {
            margin-bottom: 14px;
            gap: 4px 0;
          }
          .progress-stage {
            width: 52px;
          }
          .stage-circle {
            width: 26px;
            height: 26px;
          }
          .stage-emoji {
            font-size: 0.8rem;
          }
          .stage-label {
            font-size: 0.55rem;
            max-width: 52px;
          }
        }
        
        @media (max-width: 768px) {
          .progress-stages {
            margin-bottom: 10px;
            gap: 3px 0;
          }
          .progress-stage {
            width: 44px;
          }
          .stage-circle {
            width: 22px;
            height: 22px;
          }
          .stage-emoji {
            font-size: 0.7rem;
          }
          .stage-label {
            font-size: 0.5rem;
            max-width: 44px;
          }
        }

        /* 当前阶段卡片 - 紧凑版 */
        .current-stage-card {
          position: relative;
          background: linear-gradient(135deg, rgba(45, 212, 191, 0.08), rgba(34, 197, 94, 0.04));
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 10px;
          padding: 10px 14px;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 10px;
          overflow: hidden;
        }

        .stage-icon-large {
          font-size: 1.2rem;
          flex-shrink: 0;
        }

        .stage-text-main {
          font-size: 0.82rem;
          color: #f0f4e8;
          font-weight: 500;
          flex: 1;
          text-align: left;
          line-height: 1.35;
        }

        .stage-pulse-indicator {
          width: 8px;
          height: 8px;
          background: #4ade80;
          border-radius: 50%;
          animation: pulse-indicator 1.2s ease-in-out infinite;
          flex-shrink: 0;
        }

        @keyframes pulse-indicator {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
        
        /* 低分辨率优化当前阶段卡片 */
        @media (max-width: 1024px) {
          .current-stage-card {
            padding: 8px 12px;
            margin-bottom: 10px;
            border-radius: 8px;
            gap: 8px;
          }
          .stage-icon-large {
            font-size: 1.1rem;
          }
          .stage-text-main {
            font-size: 0.78rem;
          }
        }
        
        @media (max-width: 768px) {
          .current-stage-card {
            padding: 6px 10px;
            margin-bottom: 8px;
          }
          .stage-icon-large {
            font-size: 1rem;
          }
          .stage-text-main {
            font-size: 0.72rem;
          }
        }

        /* 流式文本容器 - 优化低分辨率显示 */
        .streaming-container {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.06), rgba(45, 212, 191, 0.03));
          border: 1px solid rgba(34, 197, 94, 0.2);
          border-radius: 10px;
          margin-bottom: 10px;
          overflow: hidden;
          flex: 1;
          min-height: 100px;
          display: flex;
          flex-direction: column;
        }

        .streaming-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(34, 197, 94, 0.1);
          flex-shrink: 0;
        }

        .streaming-title {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          color: #4ade80;
          font-weight: 600;
        }

        .streaming-indicator {
          width: 8px;
          height: 8px;
          background: #4ade80;
          border-radius: 50%;
          opacity: 0.5;
        }

        .streaming-indicator.active {
          animation: streaming-blink 0.8s ease-in-out infinite;
        }

        @keyframes streaming-blink {
          0%, 100% { opacity: 1; box-shadow: 0 0 10px #4ade80; }
          50% { opacity: 0.3; box-shadow: none; }
        }

        .streaming-stats {
          display: flex;
          gap: 12px;
        }

        .token-count {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: var(--font-mono, monospace);
          background: rgba(0, 0, 0, 0.3);
          padding: 2px 6px;
          border-radius: 4px;
        }

        .streaming-content {
          padding: 10px 12px;
          flex: 1;
          min-height: 80px;
          max-height: 30vh;
          overflow-y: auto;
          scroll-behavior: smooth;
        }

        .streaming-text {
          color: rgba(240, 244, 232, 0.9);
          font-size: 0.8rem;
          line-height: 1.6;
          white-space: pre-wrap;
          text-align: left;
          font-family: var(--font-body);
        }

        .typing-cursor {
          display: inline-block;
          color: #4ade80;
          animation: cursor-blink 0.6s step-end infinite;
          margin-left: 2px;
          font-weight: bold;
        }

        @keyframes cursor-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        
        /* 低分辨率优化流式文本 */
        @media (max-width: 1024px) {
          .streaming-container {
            border-radius: 8px;
            min-height: 80px;
          }
          .streaming-header {
            padding: 6px 10px;
          }
          .streaming-title {
            font-size: 0.7rem;
          }
          .streaming-content {
            padding: 8px 10px;
            max-height: 35vh;
          }
          .streaming-text {
            font-size: 0.75rem;
            line-height: 1.5;
          }
        }
        
        @media (max-width: 768px) {
          .streaming-content {
            max-height: 40vh;
          }
          .streaming-text {
            font-size: 0.7rem;
          }
        }

        /* 日志容器 - 优化低分辨率显示 */
        .evolution-log-container {
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(45, 212, 191, 0.1);
          border-radius: 10px;
          min-height: 80px;
          max-height: 150px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
        }

        .log-header {
          font-size: 0.75rem;
          color: rgba(240, 244, 232, 0.7);
          padding: 8px 12px;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(0, 0, 0, 0.2);
          flex-shrink: 0;
        }

        .log-count {
          font-size: 0.6rem;
          color: rgba(240, 244, 232, 0.4);
          background: rgba(255, 255, 255, 0.05);
          padding: 2px 5px;
          border-radius: 8px;
        }

        .log-list {
          padding: 5px;
          overflow-y: auto;
          flex: 1;
        }

        .log-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 5px;
          height: 100%;
          color: rgba(240, 244, 232, 0.3);
          font-size: 0.75rem;
        }

        .empty-icon {
          font-size: 1.2rem;
          opacity: 0.5;
        }

        .log-pending {
          font-size: 0.55rem;
          color: #fbbf24;
          background: rgba(251, 191, 36, 0.15);
          padding: 1px 4px;
          border-radius: 6px;
          margin-left: 3px;
          animation: pending-pulse 1s ease-in-out infinite;
        }

        @keyframes pending-pulse {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 1; }
        }

        .log-item {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 5px 8px;
          margin-bottom: 2px;
          background: rgba(45, 212, 191, 0.02);
          border-left: 2px solid var(--log-color);
          border-radius: 4px;
        }

        .log-item-animated {
          animation: log-slide-in 0.25s ease-out both;
        }

        @keyframes log-slide-in {
          from { 
            opacity: 0; 
            transform: translateX(-15px) scale(0.95);
            background: rgba(45, 212, 191, 0.1);
          }
          to { 
            opacity: 1; 
            transform: translateX(0) scale(1);
            background: rgba(45, 212, 191, 0.02);
          }
        }
        
        /* 低分辨率优化日志 */
        @media (max-width: 1024px) {
          .evolution-log-container {
            min-height: 70px;
            max-height: 130px;
            border-radius: 8px;
          }
          .log-header {
            padding: 6px 10px;
            font-size: 0.7rem;
          }
          .log-item {
            padding: 4px 6px;
            gap: 5px;
          }
        }
        
        @media (max-width: 768px) {
          .evolution-log-container {
            min-height: 50px;
            max-height: 100px;
          }
          .log-header {
            padding: 5px 8px;
            font-size: 0.65rem;
          }
        }

        /* AI并发处理进度样式 - 紧凑响应式 */
        .ai-progress-container {
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(168, 85, 247, 0.04));
          border: 1px solid rgba(139, 92, 246, 0.25);
          border-radius: 10px;
          margin-bottom: 10px;
          padding: 10px 12px;
          overflow: hidden;
        }

        .ai-progress-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          flex-wrap: wrap;
          gap: 6px;
        }

        .ai-progress-title {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.78rem;
          color: #c084fc;
          font-weight: 600;
        }

        .ai-activity-indicator {
          width: 9px;
          height: 9px;
          border-radius: 50%;
          background: #a855f7;
          flex-shrink: 0;
        }

        .ai-activity-indicator.active {
          animation: ai-pulse 0.8s ease-in-out infinite;
          box-shadow: 0 0 10px rgba(168, 85, 247, 0.6);
        }

        .ai-activity-indicator.stale {
          background: #fbbf24;
          animation: ai-stale-blink 1.5s ease-in-out infinite;
        }

        @keyframes ai-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }

        @keyframes ai-stale-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .ai-progress-stats {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .ai-progress-count {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.7);
          font-family: var(--font-mono, monospace);
          background: rgba(139, 92, 246, 0.2);
          padding: 2px 6px;
          border-radius: 4px;
        }

        .ai-elapsed-time {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: var(--font-mono, monospace);
        }

        .ai-progress-bar-container {
          height: 4px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 2px;
          overflow: hidden;
          margin-bottom: 6px;
        }

        .ai-progress-bar {
          height: 100%;
          background: linear-gradient(90deg, #8b5cf6, #a855f7, #c084fc);
          border-radius: 2px;
          transition: width 0.5s ease-out;
          box-shadow: 0 0 6px rgba(139, 92, 246, 0.4);
        }

        .ai-current-task {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.6);
          text-align: left;
        }

        .ai-waiting-hint {
          font-size: 0.65rem;
          color: #fbbf24;
          text-align: center;
          margin-top: 5px;
          padding: 4px 6px;
          background: rgba(251, 191, 36, 0.1);
          border-radius: 4px;
          animation: hint-fade 2s ease-in-out infinite;
        }

        @keyframes hint-fade {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 1; }
        }
        
        /* 低分辨率优化AI进度 */
        @media (max-width: 1024px) {
          .ai-progress-container {
            padding: 8px 10px;
            margin-bottom: 8px;
            border-radius: 8px;
          }
          .ai-progress-title {
            font-size: 0.72rem;
          }
          .ai-progress-count {
            font-size: 0.65rem;
          }
          .ai-current-task {
            font-size: 0.65rem;
          }
        }
        
        @media (max-width: 768px) {
          .ai-progress-container {
            padding: 6px 8px;
          }
          .ai-progress-title {
            font-size: 0.68rem;
          }
        }

        .log-icon {
          font-size: 0.82rem;
          flex-shrink: 0;
        }

        .log-text {
          flex: 1;
          font-size: 0.72rem;
          color: rgba(240, 244, 232, 0.85);
          text-align: left;
          line-height: 1.35;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .log-category {
          font-size: 0.55rem;
          padding: 2px 5px;
          border-radius: 4px;
          color: rgba(255, 255, 255, 0.7);
          flex-shrink: 0;
        }

        /* 滚动条样式 */
        .streaming-content::-webkit-scrollbar,
        .log-list::-webkit-scrollbar {
          width: 4px;
        }

        .streaming-content::-webkit-scrollbar-track,
        .log-list::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 2px;
        }

        .streaming-content::-webkit-scrollbar-thumb,
        .log-list::-webkit-scrollbar-thumb {
          background: rgba(45, 212, 191, 0.3);
          border-radius: 2px;
        }

        .streaming-content::-webkit-scrollbar-thumb:hover,
        .log-list::-webkit-scrollbar-thumb:hover {
          background: rgba(45, 212, 191, 0.5);
        }
        
        /* 低分辨率优化日志文本 */
        @media (max-width: 1024px) {
          .log-icon {
            font-size: 0.75rem;
          }
          .log-text {
            font-size: 0.68rem;
          }
          .log-category {
            font-size: 0.5rem;
            padding: 1px 4px;
          }
        }
        
        @media (max-width: 768px) {
          .log-icon {
            font-size: 0.7rem;
          }
          .log-text {
            font-size: 0.62rem;
          }
          .log-category {
            display: none;
          }
        }
      `}</style>
    </div>
  );
}

// 根据类别返回颜色
function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    "地质": "#fb923c",
    "分化": "#c084fc",
    "繁殖": "#4ade80",
    "死亡": "#f43f5e",
    "适应": "#2dd4bf",
    "进化": "#2dd4bf",
    "迁徙": "#38bdf8",
    "生态位": "#fbbf24",
    "报告": "#94a3b8",
    "系统": "#6366f1",
    "物种": "#ec4899",
    "环境": "#f97316",
    "AI": "#8b5cf6",
    "其他": "rgba(45, 212, 191, 0.5)"
  };
  return colors[category] || colors["其他"];
}
