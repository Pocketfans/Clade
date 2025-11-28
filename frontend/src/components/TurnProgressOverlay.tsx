import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { connectToEventStream, abortCurrentTasks, skipCurrentAIStep } from "../services/api";

interface Props {
  message?: string;
  showDetails?: boolean;
}

// 连接状态类型
type ConnectionStatus = "connecting" | "connected" | "receiving" | "warning" | "error" | "disconnected";

// 演化阶段定义 - 与后端新流程完全匹配
const EVOLUTION_STAGES = [
  { id: "pressure", icon: "🌡️", label: "环境压力", color: "#fb923c", estimatedSeconds: 2 },
  { id: "geology", icon: "🗺️", label: "地图演化", color: "#8b5cf6", estimatedSeconds: 3 },
  { id: "ecology", icon: "📊", label: "生态分析", color: "#fbbf24", estimatedSeconds: 5 },
  { id: "phase1", icon: "⚔️", label: "阶段1:死亡率", color: "#f43f5e", estimatedSeconds: 8 },
  { id: "phase2", icon: "🦅", label: "阶段2:迁徙", color: "#06b6d4", estimatedSeconds: 5 },
  { id: "phase3", icon: "💀", label: "阶段3:再评估", color: "#ef4444", estimatedSeconds: 8 },
  { id: "ai_eval", icon: "🤖", label: "AI评估", color: "#a855f7", estimatedSeconds: 30, isAI: true },
  { id: "population", icon: "🐣", label: "种群变化", color: "#4ade80", estimatedSeconds: 3 },
  { id: "evolution", icon: "🧬", label: "演化事件", color: "#2dd4bf", estimatedSeconds: 5 },
  { id: "ai_parallel", icon: "🔀", label: "AI处理", color: "#c084fc", estimatedSeconds: 120, isAI: true },
  { id: "report", icon: "📝", label: "生成报告", color: "#38bdf8", estimatedSeconds: 45, isAI: true },
  { id: "save", icon: "💾", label: "保存数据", color: "#64748b", estimatedSeconds: 3 },
];

// AI并发处理进度状态
interface AIProgress {
  total: number;
  completed: number;
  current_task: string;
  last_activity: number;
}

// 阶段时间追踪
interface StageTimer {
  startTime: number;
  stageIndex: number;
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
  const [heartbeatCount, setHeartbeatCount] = useState<number>(0);
  
  // 阶段时间追踪
  const [stageTimer, setStageTimer] = useState<StageTimer | null>(null);
  const [stageElapsedSeconds, setStageElapsedSeconds] = useState<number>(0);
  
  // 任务中断状态
  const [isAborting, setIsAborting] = useState<boolean>(false);
  const [abortMessage, setAbortMessage] = useState<string>("");
  
  // 日志显示控制
  const [showLogs, setShowLogs] = useState<boolean>(true);
  
  // 日志队列管理（逐条动画显示）
  const logQueueRef = useRef<Array<{ icon: string; text: string; category: string; timestamp: number }>>([]);
  const isProcessingRef = useRef<boolean>(false);
  
  // Refs
  const logContainerRef = useRef<HTMLDivElement>(null);
  const streamingContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 当前阶段是否为AI步骤
  const isCurrentStageAI = useMemo(() => {
    if (currentStageIndex < 0 || currentStageIndex >= EVOLUTION_STAGES.length) return false;
    return EVOLUTION_STAGES[currentStageIndex].isAI === true;
  }, [currentStageIndex]);

  // 计算预估剩余时间
  const estimatedRemainingSeconds = useMemo(() => {
    if (currentStageIndex < 0) return 0;
    let remaining = 0;
    for (let i = currentStageIndex; i < EVOLUTION_STAGES.length; i++) {
      remaining += EVOLUTION_STAGES[i].estimatedSeconds;
    }
    // 减去当前阶段已经花费的时间
    remaining -= stageElapsedSeconds;
    return Math.max(0, remaining);
  }, [currentStageIndex, stageElapsedSeconds]);

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
      const delay = nextLog.category === "系统" || nextLog.text.includes("阶段") ? 150 : 60;
      
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
  
  // 阶段计时器
  useEffect(() => {
    if (!stageTimer) {
      setStageElapsedSeconds(0);
      return;
    }
    
    const timer = setInterval(() => {
      const now = Date.now();
      const elapsed = Math.floor((now - stageTimer.startTime) / 1000);
      setStageElapsedSeconds(elapsed);
    }, 1000);
    
    return () => clearInterval(timer);
  }, [stageTimer]);
  
  // AI活动计时器
  useEffect(() => {
    if (!aiProgress || aiProgress.completed >= aiProgress.total) {
      setAIElapsedSeconds(0);
      return;
    }
    
    if (!lastAIActivity || lastAIActivity <= 0) {
      setAIElapsedSeconds(0);
      return;
    }
    
    const timer = setInterval(() => {
      const now = Date.now();
      const elapsed = Math.floor((now - lastAIActivity) / 1000);
      setAIElapsedSeconds(Math.min(elapsed, 300));
    }, 1000);
    
    return () => clearInterval(timer);
  }, [aiProgress, lastAIActivity]);

  // 根据阶段文本判断当前阶段索引 - 与后端流程完全匹配
  const detectStageIndex = useCallback((stageText: string): number => {
    const lowerText = stageText.toLowerCase();
    
    // 0. 环境压力
    if (lowerText.includes("压力") || lowerText.includes("pressure")) return 0;
    // 1. 地质演化
    if (lowerText.includes("地图演化") || lowerText.includes("地质") || lowerText.includes("geology") || lowerText.includes("海平面")) return 1;
    // 2. 生态分析（物种列表、分层、生态位）
    if (lowerText.includes("物种列表") || lowerText.includes("分层") || lowerText.includes("生态位") || lowerText.includes("ecology") || lowerText.includes("物种分层")) return 2;
    // 3. 阶段1：死亡率计算
    if (lowerText.includes("阶段1") || lowerText.includes("营养级") || (lowerText.includes("死亡率") && !lowerText.includes("阶段3"))) return 3;
    // 4. 阶段2：迁徙
    if (lowerText.includes("阶段2") || lowerText.includes("迁徙")) return 4;
    // 5. 阶段3：重新评估
    if (lowerText.includes("阶段3") && !lowerText.includes("阶段3.5")) return 5;
    // 6. AI综合评估
    if ((lowerText.includes("ai") && lowerText.includes("评估")) || lowerText.includes("阶段3.5")) return 6;
    // 7. 种群变化
    if (lowerText.includes("种群") || lowerText.includes("繁殖") || lowerText.includes("reproduction")) return 7;
    // 8. 演化事件（基因激活、基因流动、亚种晋升）
    if (lowerText.includes("基因") || lowerText.includes("激活") || lowerText.includes("流动") || lowerText.includes("亚种") || lowerText.includes("晋升")) return 8;
    // 9. AI并行处理（叙事、适应、分化）
    if (lowerText.includes("ai并行") || lowerText.includes("ai任务") || lowerText.includes("分化") || lowerText.includes("适应") || lowerText.includes("叙事")) return 9;
    // 10. 生成报告
    if (lowerText.includes("报告") || lowerText.includes("report")) return 10;
    // 11. 保存数据
    if (lowerText.includes("保存") || lowerText.includes("save") || lowerText.includes("导出") || lowerText.includes("快照")) return 11;
    
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
        const token = event.message || "";
        setStreamingText(prev => prev + token);
        setTokenCount(prev => prev + 1);
        setIsStreamingActive(true);
        setConnectionStatus("receiving");
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
        setHeartbeatCount(prev => prev + 1);
        setConnectionStatus("receiving");
        return;
      }
      
      // 【新增】处理流式心跳事件（更精确的AI活动监测）
      if (event.type === 'ai_chunk_heartbeat') {
        setLastAIActivity(Date.now());
        setHeartbeatCount(prev => prev + 1);
        setConnectionStatus("receiving");
        // 更新当前任务信息
        if (event.task) {
          setAIProgress(prev => prev ? {
            ...prev,
            current_task: `${event.task} (${event.chunks || 0} chunks)`,
            last_activity: Date.now()
          } : {
            total: 1,
            completed: 0,
            current_task: `${event.task} (${event.chunks || 0} chunks)`,
            last_activity: Date.now()
          });
        }
        return;
      }
      
      // 【新增】处理流式状态事件
      if (event.type === 'ai_stream_start') {
        setLastAIActivity(Date.now());
        setConnectionStatus("receiving");
        if (event.task) {
          setAIProgress(prev => prev ? {
            ...prev,
            current_task: `🔗 连接: ${event.task}`,
            last_activity: Date.now()
          } : {
            total: 1,
            completed: 0,
            current_task: `🔗 连接: ${event.task}`,
            last_activity: Date.now()
          });
        }
        return;
      }
      
      if (event.type === 'ai_stream_receiving') {
        setLastAIActivity(Date.now());
        setConnectionStatus("receiving");
        if (event.task) {
          setAIProgress(prev => prev ? {
            ...prev,
            current_task: `📥 接收: ${event.task}`,
            last_activity: Date.now()
          } : {
            total: 1,
            completed: 0,
            current_task: `📥 接收: ${event.task}`,
            last_activity: Date.now()
          });
        }
        return;
      }
      
      if (event.type === 'ai_stream_complete') {
        setLastAIActivity(Date.now());
        setAIProgress(prev => prev ? {
          ...prev,
          completed: prev.completed + 1,
          current_task: `✅ 完成: ${event.task || ''}`,
          last_activity: Date.now()
        } : {
          total: 1,
          completed: 1,
          current_task: `✅ 完成: ${event.task || ''}`,
          last_activity: Date.now()
        });
        return;
      }
      
      if (event.type === 'ai_stream_error') {
        // 流式错误不中断，只记录
        setConnectionStatus("error");
        setTimeout(() => setConnectionStatus("receiving"), 2000);
        return;
      }
      
      // 【新增】处理智能空闲超时事件
      if (event.type === 'ai_idle_timeout') {
        setConnectionStatus("warning");
        // 如果已经收到一些chunks，说明AI在输出只是变慢了
        const chunksReceived = event.chunks_received || 0;
        if (chunksReceived > 0) {
          setAIProgress(prev => prev ? {
            ...prev,
            current_task: `⏰ 等待响应... (已收${chunksReceived}块)`,
            last_activity: Date.now()
          } : {
            total: 1,
            completed: 0,
            current_task: `⏰ 等待响应... (已收${chunksReceived}块)`,
            last_activity: Date.now()
          });
        }
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
      else if (eventMessage.includes("⚔️")) icon = "⚔️";
      else if (eventMessage.includes("🌡️")) icon = "🌡️";
      
      const cleanMessage = eventMessage.replace(/[\u{1F300}-\u{1F9FF}]/gu, "").trim();
      
      // 使用队列方式添加日志
      addLogToQueue({ 
        icon, 
        text: cleanMessage, 
        category, 
        timestamp: Date.now() 
      });
      
      // 更新当前阶段
      if (event.type === 'stage') {
        const newStageIndex = detectStageIndex(cleanMessage);
        const stageText = cleanMessage.length > 50 ? cleanMessage.substring(0, 50) + '...' : cleanMessage;
        setCurrentStage(stageText);
        
        if (newStageIndex !== currentStageIndex && newStageIndex >= 0) {
          setCurrentStageIndex(newStageIndex);
          setStageTimer({ startTime: Date.now(), stageIndex: newStageIndex });
        }
        
        // 如果进入AI并发处理阶段，初始化AI进度
        if (cleanMessage.includes("AI并行") || cleanMessage.includes("AI任务")) {
          setAIProgress({ total: 2, completed: 0, current_task: "初始化...", last_activity: Date.now() });
          setLastAIActivity(Date.now());
        }
        
        // 如果进入报告阶段，清空之前的流式文本和AI进度
        if (cleanMessage.includes("报告") && !cleanMessage.includes("完成")) {
          setStreamingText("");
          setTokenCount(0);
          setIsStreamingActive(false);
          setAIProgress(null);
        }
      }

      // 完成事件
      if (event.type === 'turn_complete' || event.type === 'complete') {
        console.log("[事件流] 推演完成");
        setIsStreamingActive(false);
        setConnectionStatus("connected");
        setAIProgress(null);
        setCurrentStage("推演完成！");
        setCurrentStageIndex(EVOLUTION_STAGES.length - 1);
        setStageTimer(null);
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
    // 【修复】移除 currentStageIndex 依赖，避免阶段变化时重新创建 EventSource 导致事件丢失
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDetails]);

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
      setHeartbeatCount(0);
      setStageTimer(null);
      setStageElapsedSeconds(0);
    }
  }, [message]);

  // 计算经过时间
  const elapsedTime = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0;
  const elapsedMinutes = Math.floor(elapsedTime / 60);
  const elapsedSeconds = elapsedTime % 60;

  // 格式化时间
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}分${secs}秒`;
    }
    return `${secs}秒`;
  };

  // 重置连接处理函数
  const handleAbortTasks = useCallback(async () => {
    if (isAborting) return;
    
    setIsAborting(true);
    setAbortMessage("正在重置连接...");
    
    try {
      const result = await abortCurrentTasks();
      if (result.success) {
        setAbortMessage(`✅ ${result.message}`);
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
    warning: { color: "#f59e0b", text: "等待响应", icon: "⏰" },
    error: { color: "#f43f5e", text: "连接错误", icon: "❌" },
    disconnected: { color: "#94a3b8", text: "已断开", icon: "🔌" },
  };

  const currentStatusConfig = statusConfig[connectionStatus];

  // 判断是否可能卡住
  const isLikelyStuck = isCurrentStageAI && stageElapsedSeconds > 60 && aiElapsedSeconds > 30;
  const isVeryLongWait = stageElapsedSeconds > 120;

  return (
    <div className="evolution-overlay">
      <div className="evolution-panel">
        {/* 顶部状态栏 */}
        <div className="top-status-bar">
          <div className="status-left">
            <div className="connection-status" style={{ color: currentStatusConfig.color }}>
              <span className="status-dot" style={{ background: currentStatusConfig.color }} />
              <span>{currentStatusConfig.text}</span>
            </div>
            {heartbeatCount > 0 && (
              <div className="heartbeat-indicator" title={`AI 活动监测 - 共收到 ${heartbeatCount} 次心跳信号`}>
                <span className="heartbeat-dot streaming" />
                <span>💓 #{heartbeatCount}</span>
                {aiProgress?.current_task && aiProgress.current_task.includes('chunk') && (
                  <span className="streaming-badge">流式</span>
                )}
              </div>
            )}
          </div>
          <div className="status-right">
            <div className="elapsed-time">
              <span className="time-icon">⏱️</span>
              <span className="time-value">{elapsedMinutes > 0 ? `${elapsedMinutes}分` : ""}{elapsedSeconds}秒</span>
            </div>
            {estimatedRemainingSeconds > 0 && currentStageIndex >= 0 && (
              <div className="remaining-time">
                <span>约剩 {formatTime(estimatedRemainingSeconds)}</span>
              </div>
            )}
          </div>
        </div>

        {/* 主要内容区 */}
        <div className="main-content">
          {/* DNA 动画与标题 */}
          <div className="header-section">
            <div className="dna-animation">
              <div className="dna-helix">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="dna-pair" style={{ animationDelay: `${i * 0.15}s` }}>
                    <div className="dna-node left" />
                    <div className="dna-bridge" />
                    <div className="dna-node right" />
                  </div>
                ))}
              </div>
              <div className="dna-glow" />
            </div>
            
            <div className="title-section">
              <h2 className="main-title">
                <span className="title-icon">🧬</span>
                演化推演中
              </h2>
              <p className="sub-message">{message}</p>
            </div>
          </div>

          {showDetails && (
            <>
              {/* 进度阶段可视化 */}
              <div className="stages-container">
                <div className="stages-track">
                  {EVOLUTION_STAGES.map((stage, idx) => {
                    const isCompleted = idx < currentStageIndex;
                    const isCurrent = idx === currentStageIndex;
                    const isPending = idx > currentStageIndex;
                    
                    return (
                      <div 
                        key={stage.id}
                        className={`stage-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''} ${isPending ? 'pending' : ''} ${stage.isAI ? 'is-ai' : ''}`}
                        style={{ '--stage-color': stage.color } as React.CSSProperties}
                      >
                        <div className="stage-icon-wrapper">
                          <span className="stage-icon">{stage.icon}</span>
                          {isCurrent && <div className="stage-pulse" />}
                          {isCompleted && <div className="stage-check">✓</div>}
                        </div>
                        <span className="stage-label">{stage.label}</span>
                        {isCurrent && stage.isAI && (
                          <span className="ai-badge">AI</span>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div 
                  className="stages-progress-bar"
                  style={{ 
                    width: `${Math.max(0, ((currentStageIndex + 0.5) / EVOLUTION_STAGES.length) * 100)}%`
                  }}
                />
              </div>

              {/* 当前阶段详情卡片 */}
              <div className={`current-stage-card ${isCurrentStageAI ? 'ai-stage' : ''} ${isLikelyStuck ? 'stuck-warning' : ''}`}>
                <div className="stage-card-left">
                  <span className="stage-emoji">
                    {currentStageIndex >= 0 ? EVOLUTION_STAGES[currentStageIndex]?.icon : "📖"}
                  </span>
                  <div className="stage-info">
                    <span className="stage-name">{currentStage}</span>
                    {stageElapsedSeconds > 0 && (
                      <span className="stage-time">
                        已耗时 {formatTime(stageElapsedSeconds)}
                        {currentStageIndex >= 0 && EVOLUTION_STAGES[currentStageIndex]?.estimatedSeconds && (
                          <span className="estimated">
                            {" "}/ 预计 {formatTime(EVOLUTION_STAGES[currentStageIndex].estimatedSeconds)}
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                </div>
                <div className="stage-card-right">
                  {isCurrentStageAI && (
                    <div className="ai-indicator">
                      <div className={`ai-pulse ${aiElapsedSeconds < 10 ? 'active' : 'slow'}`} />
                      <span>AI处理中</span>
                    </div>
                  )}
                  {isStreamingActive && <div className="streaming-indicator" />}
                </div>
              </div>

              {/* 卡住警告 */}
              {isLikelyStuck && (
                <div className="stuck-warning-banner">
                  <span className="warning-icon">⚠️</span>
                  <span className="warning-text">
                    AI响应时间较长，正在处理复杂任务...
                    {isVeryLongWait && " 如果持续无响应，可尝试重置连接。"}
                  </span>
                  <button 
                    className="reset-btn"
                    onClick={handleAbortTasks}
                    disabled={isAborting}
                  >
                    {isAborting ? "重置中..." : "🔄 重置"}
                  </button>
                </div>
              )}

              {/* 重置消息 */}
              {abortMessage && (
                <div className={`abort-message ${abortMessage.includes('✅') ? 'success' : 'error'}`}>
                  {abortMessage}
                </div>
              )}

              {/* AI并发处理进度 */}
              {aiProgress && aiProgress.total > 0 && (
                <div className="ai-progress-section">
                  <div className="ai-progress-header">
                    <div className="ai-progress-title">
                      <div className={`activity-dot ${aiElapsedSeconds < 10 ? 'active' : 'stale'}`} />
                      <span>🤖 AI 并行任务</span>
                    </div>
                    <div className="ai-progress-stats">
                      <span className="task-count">{aiProgress.completed}/{aiProgress.total}</span>
                      {aiElapsedSeconds > 0 && (
                        <span className={`elapsed ${aiElapsedSeconds > 30 ? 'warning' : ''}`}>
                          {aiElapsedSeconds}秒
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="ai-progress-bar-track">
                    <div 
                      className="ai-progress-bar-fill" 
                      style={{ width: `${(aiProgress.completed / aiProgress.total) * 100}%` }}
                    />
                  </div>
                  {aiProgress.current_task && (
                    <div className="ai-current-task">
                      <span className="task-label">当前:</span>
                      <span className="task-name">{aiProgress.current_task}</span>
                    </div>
                  )}
                </div>
              )}

              {/* 流式文本显示区域 */}
              {(streamingText || isStreamingActive) && (
                <div className="streaming-section">
                  <div className="streaming-header">
                    <div className="streaming-title">
                      <span className={`stream-dot ${isStreamingActive ? 'active' : ''}`} />
                      <span>📝 AI 正在生成报告</span>
                    </div>
                    {tokenCount > 0 && (
                      <span className="token-badge">{tokenCount} tokens</span>
                    )}
                  </div>
                  <div className="streaming-content" ref={streamingContainerRef}>
                    <div className="streaming-text">
                      {streamingText}
                      {isStreamingActive && <span className="cursor">▊</span>}
                    </div>
                  </div>
                </div>
              )}

              {/* 日志区域 */}
              <div className="logs-section" ref={logContainerRef}>
                <div className="logs-header" onClick={() => setShowLogs(!showLogs)}>
                  <span className="logs-title">📋 推演日志</span>
                  <div className="logs-meta">
                    {displayedLogs.length > 0 && (
                      <span className="log-count">{displayedLogs.length} 条</span>
                    )}
                    {logQueueRef.current.length > 0 && (
                      <span className="log-pending">+{logQueueRef.current.length}</span>
                    )}
                    <span className="toggle-icon">{showLogs ? '▼' : '▶'}</span>
                  </div>
                </div>
                {showLogs && (
                  displayedLogs.length === 0 ? (
                    <div className="logs-empty">
                      <span className="empty-icon">🌱</span>
                      <span>等待推演数据...</span>
                    </div>
                  ) : (
                    <div className="log-list">
                      {displayedLogs.map((log, idx) => (
                        <div
                          key={`${log.timestamp}-${idx}`}
                          className="log-entry"
                          style={{ '--log-color': getCategoryColor(log.category) } as React.CSSProperties}
                        >
                          <span className="log-icon">{log.icon}</span>
                          <span className="log-text">{log.text}</span>
                          <span className="log-cat">{log.category}</span>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </div>
      </div>
      
      <style>{`
        .evolution-overlay {
          position: fixed;
          inset: 0;
          background: radial-gradient(ellipse at center, rgba(5, 15, 10, 0.98), rgba(2, 8, 5, 0.99));
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10000;
          backdrop-filter: blur(16px);
          padding: 16px;
        }

        .evolution-panel {
          background: linear-gradient(160deg, rgba(12, 25, 18, 0.96), rgba(6, 14, 10, 0.98));
          border: 1px solid rgba(45, 212, 191, 0.25);
          border-radius: 24px;
          width: 100%;
          max-width: 800px;
          max-height: calc(100vh - 32px);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          box-shadow: 
            0 40px 120px rgba(0, 0, 0, 0.8),
            0 0 100px rgba(45, 212, 191, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }

        /* 顶部状态栏 */
        .top-status-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 14px 20px;
          background: rgba(0, 0, 0, 0.35);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .status-left, .status-right {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .connection-status {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.8rem;
          font-weight: 500;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          animation: pulse-dot 2s ease-in-out infinite;
        }

        @keyframes pulse-dot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.9); }
        }

        .heartbeat-indicator {
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          background: rgba(74, 222, 128, 0.1);
          padding: 3px 8px;
          border-radius: 10px;
        }

        .heartbeat-dot {
          width: 6px;
          height: 6px;
          background: #4ade80;
          border-radius: 50%;
          animation: heartbeat 1s ease-in-out infinite;
        }
        
        .heartbeat-dot.streaming {
          background: #60a5fa;
          animation: streaming-pulse 0.6s ease-in-out infinite;
        }

        @keyframes heartbeat {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.3); opacity: 0.6; }
        }
        
        @keyframes streaming-pulse {
          0%, 100% { transform: scale(1); opacity: 1; box-shadow: 0 0 4px #60a5fa; }
          50% { transform: scale(1.4); opacity: 0.8; box-shadow: 0 0 8px #60a5fa; }
        }
        
        .streaming-badge {
          font-size: 0.6rem;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          color: white;
          padding: 1px 5px;
          border-radius: 6px;
          margin-left: 4px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .elapsed-time {
          display: flex;
          align-items: center;
          gap: 5px;
          color: rgba(255, 255, 255, 0.7);
          font-size: 0.85rem;
          font-family: var(--font-mono, 'JetBrains Mono', monospace);
        }

        .time-icon {
          font-size: 0.9rem;
        }

        .remaining-time {
          color: rgba(45, 212, 191, 0.7);
          font-size: 0.75rem;
          padding: 2px 8px;
          background: rgba(45, 212, 191, 0.1);
          border-radius: 8px;
        }

        /* 主内容区 */
        .main-content {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        /* 头部区域 */
        .header-section {
          display: flex;
          align-items: center;
          gap: 20px;
          padding-bottom: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .dna-animation {
          position: relative;
          width: 60px;
          height: 80px;
          flex-shrink: 0;
        }

        .dna-helix {
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
          animation: dna-twist 2s ease-in-out infinite;
        }

        .dna-node {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          box-shadow: 0 0 10px currentColor;
        }

        .dna-node.left {
          background: #2dd4bf;
          color: #2dd4bf;
        }

        .dna-node.right {
          background: #22c55e;
          color: #22c55e;
        }

        .dna-bridge {
          width: 24px;
          height: 2px;
          background: linear-gradient(90deg, rgba(45, 212, 191, 0.8), rgba(34, 197, 94, 0.8));
          border-radius: 1px;
        }

        @keyframes dna-twist {
          0%, 100% { transform: translateX(-6px) rotateY(0deg); }
          50% { transform: translateX(6px) rotateY(180deg); }
        }

        .dna-glow {
          position: absolute;
          inset: -20px;
          background: radial-gradient(ellipse at center, rgba(45, 212, 191, 0.15), transparent 70%);
          animation: glow-pulse 3s ease-in-out infinite;
        }

        @keyframes glow-pulse {
          0%, 100% { opacity: 0.5; transform: scale(0.95); }
          50% { opacity: 1; transform: scale(1.05); }
        }

        .title-section {
          flex: 1;
        }

        .main-title {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 0 0 6px 0;
          font-size: 1.5rem;
          font-weight: 700;
          background: linear-gradient(135deg, #2dd4bf, #22c55e, #4ade80);
          background-size: 200% 200%;
          animation: gradient-shift 4s ease infinite;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .title-icon {
          font-size: 1.6rem;
          animation: bounce-rotate 3s ease-in-out infinite;
        }

        @keyframes bounce-rotate {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          25% { transform: translateY(-3px) rotate(-5deg); }
          75% { transform: translateY(-3px) rotate(5deg); }
        }

        @keyframes gradient-shift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }

        .sub-message {
          margin: 0;
          color: rgba(240, 244, 232, 0.65);
          font-size: 0.9rem;
        }

        /* 阶段进度条 */
        .stages-container {
          position: relative;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 16px;
          padding: 16px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .stages-track {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 4px;
          justify-content: center;
          position: relative;
          z-index: 1;
        }

        .stage-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          width: 62px;
          padding: 6px 4px;
          border-radius: 10px;
          transition: all 0.3s ease;
          opacity: 0.35;
        }

        .stage-item.completed {
          opacity: 1;
        }

        .stage-item.current {
          opacity: 1;
          background: rgba(var(--stage-color-rgb, 45, 212, 191), 0.15);
          transform: scale(1.05);
        }

        .stage-item.is-ai {
          border: 1px dashed rgba(168, 85, 247, 0.3);
        }

        .stage-icon-wrapper {
          position: relative;
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .stage-icon {
          font-size: 1.2rem;
          z-index: 1;
        }

        .stage-pulse {
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          background: var(--stage-color);
          opacity: 0.3;
          animation: stage-pulse 1.5s ease-out infinite;
        }

        @keyframes stage-pulse {
          0% { transform: scale(0.8); opacity: 0.4; }
          100% { transform: scale(1.5); opacity: 0; }
        }

        .stage-check {
          position: absolute;
          bottom: -2px;
          right: -2px;
          width: 14px;
          height: 14px;
          background: #4ade80;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.55rem;
          color: #000;
          font-weight: bold;
        }

        .stage-label {
          font-size: 0.6rem;
          color: rgba(255, 255, 255, 0.6);
          text-align: center;
          line-height: 1.2;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .stage-item.completed .stage-label,
        .stage-item.current .stage-label {
          color: rgba(255, 255, 255, 0.9);
        }

        .ai-badge {
          font-size: 0.5rem;
          background: rgba(168, 85, 247, 0.4);
          color: #c084fc;
          padding: 1px 4px;
          border-radius: 4px;
          font-weight: 600;
        }

        .stages-progress-bar {
          position: absolute;
          bottom: 0;
          left: 0;
          height: 3px;
          background: linear-gradient(90deg, #2dd4bf, #4ade80);
          border-radius: 0 0 16px 16px;
          transition: width 0.5s ease;
        }

        /* 当前阶段卡片 */
        .current-stage-card {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: linear-gradient(135deg, rgba(45, 212, 191, 0.08), rgba(34, 197, 94, 0.04));
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 14px;
          padding: 14px 18px;
          transition: all 0.3s ease;
        }

        .current-stage-card.ai-stage {
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(139, 92, 246, 0.05));
          border-color: rgba(168, 85, 247, 0.25);
        }

        .current-stage-card.stuck-warning {
          border-color: rgba(251, 191, 36, 0.4);
          background: linear-gradient(135deg, rgba(251, 191, 36, 0.08), rgba(245, 158, 11, 0.04));
        }

        .stage-card-left {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .stage-emoji {
          font-size: 1.8rem;
        }

        .stage-info {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }

        .stage-name {
          font-size: 0.95rem;
          color: #f0f4e8;
          font-weight: 500;
        }

        .stage-time {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: var(--font-mono, monospace);
        }

        .estimated {
          color: rgba(255, 255, 255, 0.35);
        }

        .stage-card-right {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .ai-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          color: #c084fc;
          font-size: 0.75rem;
          background: rgba(168, 85, 247, 0.15);
          padding: 4px 10px;
          border-radius: 8px;
        }

        .ai-pulse {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #a855f7;
        }

        .ai-pulse.active {
          animation: ai-active-pulse 0.8s ease-in-out infinite;
          box-shadow: 0 0 10px #a855f7;
        }

        .ai-pulse.slow {
          animation: ai-slow-pulse 2s ease-in-out infinite;
          background: #fbbf24;
        }

        @keyframes ai-active-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }

        @keyframes ai-slow-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .streaming-indicator {
          width: 10px;
          height: 10px;
          background: #4ade80;
          border-radius: 50%;
          animation: streaming-blink 0.6s ease-in-out infinite;
          box-shadow: 0 0 12px #4ade80;
        }

        @keyframes streaming-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* 卡住警告横幅 */
        .stuck-warning-banner {
          display: flex;
          align-items: center;
          gap: 12px;
          background: linear-gradient(135deg, rgba(251, 191, 36, 0.15), rgba(245, 158, 11, 0.08));
          border: 1px solid rgba(251, 191, 36, 0.3);
          border-radius: 12px;
          padding: 12px 16px;
          animation: warning-pulse 2s ease-in-out infinite;
        }

        @keyframes warning-pulse {
          0%, 100% { border-color: rgba(251, 191, 36, 0.3); }
          50% { border-color: rgba(251, 191, 36, 0.6); }
        }

        .warning-icon {
          font-size: 1.2rem;
        }

        .warning-text {
          flex: 1;
          color: #fbbf24;
          font-size: 0.82rem;
          line-height: 1.4;
        }

        .reset-btn {
          padding: 6px 12px;
          background: rgba(251, 191, 36, 0.2);
          border: 1px solid rgba(251, 191, 36, 0.4);
          border-radius: 8px;
          color: #fcd34d;
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.2s ease;
          white-space: nowrap;
        }

        .reset-btn:hover:not(:disabled) {
          background: rgba(251, 191, 36, 0.3);
          border-color: rgba(251, 191, 36, 0.6);
        }

        .reset-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* 重置消息 */
        .abort-message {
          padding: 10px 16px;
          border-radius: 10px;
          text-align: center;
          font-size: 0.85rem;
        }

        .abort-message.success {
          background: rgba(34, 197, 94, 0.15);
          color: #4ade80;
          border: 1px solid rgba(34, 197, 94, 0.3);
        }

        .abort-message.error {
          background: rgba(239, 68, 68, 0.15);
          color: #f87171;
          border: 1px solid rgba(239, 68, 68, 0.3);
        }

        /* AI进度区块 */
        .ai-progress-section {
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(168, 85, 247, 0.05));
          border: 1px solid rgba(139, 92, 246, 0.25);
          border-radius: 14px;
          padding: 14px 16px;
        }

        .ai-progress-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }

        .ai-progress-title {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #c084fc;
          font-size: 0.85rem;
          font-weight: 600;
        }

        .activity-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #a855f7;
        }

        .activity-dot.active {
          animation: activity-pulse 0.8s ease-in-out infinite;
          box-shadow: 0 0 8px #a855f7;
        }

        .activity-dot.stale {
          background: #fbbf24;
          animation: stale-blink 1.5s ease-in-out infinite;
        }

        @keyframes activity-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }

        @keyframes stale-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .ai-progress-stats {
          display: flex;
          gap: 10px;
          align-items: center;
        }

        .task-count {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.7);
          font-family: var(--font-mono, monospace);
          background: rgba(139, 92, 246, 0.2);
          padding: 2px 8px;
          border-radius: 6px;
        }

        .elapsed {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: var(--font-mono, monospace);
        }

        .elapsed.warning {
          color: #fbbf24;
        }

        .ai-progress-bar-track {
          height: 6px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 3px;
          overflow: hidden;
          margin-bottom: 10px;
        }

        .ai-progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #8b5cf6, #a855f7, #c084fc);
          border-radius: 3px;
          transition: width 0.5s ease-out;
          box-shadow: 0 0 8px rgba(139, 92, 246, 0.5);
        }

        .ai-current-task {
          font-size: 0.78rem;
          color: rgba(255, 255, 255, 0.6);
          display: flex;
          gap: 6px;
        }

        .task-label {
          color: rgba(255, 255, 255, 0.4);
        }

        .task-name {
          color: rgba(255, 255, 255, 0.8);
        }

        /* 流式文本区域 */
        .streaming-section {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.08), rgba(45, 212, 191, 0.04));
          border: 1px solid rgba(34, 197, 94, 0.2);
          border-radius: 14px;
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
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(34, 197, 94, 0.1);
        }

        .streaming-title {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #4ade80;
          font-size: 0.82rem;
          font-weight: 600;
        }

        .stream-dot {
          width: 8px;
          height: 8px;
          background: #4ade80;
          border-radius: 50%;
          opacity: 0.5;
        }

        .stream-dot.active {
          animation: stream-pulse 0.7s ease-in-out infinite;
          box-shadow: 0 0 10px #4ade80;
        }

        @keyframes stream-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.9); }
        }

        .token-badge {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          background: rgba(0, 0, 0, 0.3);
          padding: 3px 8px;
          border-radius: 6px;
          font-family: var(--font-mono, monospace);
        }

        .streaming-content {
          flex: 1;
          padding: 12px 14px;
          max-height: 25vh;
          overflow-y: auto;
          scroll-behavior: smooth;
        }

        .streaming-text {
          color: rgba(240, 244, 232, 0.9);
          font-size: 0.85rem;
          line-height: 1.65;
          white-space: pre-wrap;
          text-align: left;
        }

        .cursor {
          display: inline-block;
          color: #4ade80;
          animation: cursor-blink 0.55s step-end infinite;
          margin-left: 2px;
          font-weight: bold;
        }

        @keyframes cursor-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        /* 日志区域 */
        .logs-section {
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          overflow: hidden;
          flex-shrink: 0;
        }

        .logs-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          cursor: pointer;
          user-select: none;
          transition: background 0.2s ease;
        }

        .logs-header:hover {
          background: rgba(0, 0, 0, 0.3);
        }

        .logs-title {
          font-size: 0.82rem;
          color: rgba(240, 244, 232, 0.7);
          font-weight: 600;
        }

        .logs-meta {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .log-count {
          font-size: 0.65rem;
          color: rgba(240, 244, 232, 0.4);
          background: rgba(255, 255, 255, 0.05);
          padding: 2px 6px;
          border-radius: 8px;
        }

        .log-pending {
          font-size: 0.6rem;
          color: #fbbf24;
          background: rgba(251, 191, 36, 0.15);
          padding: 2px 5px;
          border-radius: 6px;
          animation: pending-pulse 1s ease-in-out infinite;
        }

        @keyframes pending-pulse {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 1; }
        }

        .toggle-icon {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .logs-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 24px;
          color: rgba(240, 244, 232, 0.3);
          font-size: 0.8rem;
        }

        .empty-icon {
          font-size: 1.4rem;
          opacity: 0.5;
        }

        .log-list {
          max-height: 140px;
          overflow-y: auto;
          padding: 6px;
        }

        .log-entry {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 10px;
          margin-bottom: 3px;
          background: rgba(45, 212, 191, 0.02);
          border-left: 2px solid var(--log-color);
          border-radius: 6px;
          animation: log-slide-in 0.2s ease-out both;
        }

        @keyframes log-slide-in {
          from { 
            opacity: 0; 
            transform: translateX(-12px);
            background: rgba(45, 212, 191, 0.1);
          }
          to { 
            opacity: 1; 
            transform: translateX(0);
            background: rgba(45, 212, 191, 0.02);
          }
        }

        .log-icon {
          font-size: 0.85rem;
          flex-shrink: 0;
        }

        .log-text {
          flex: 1;
          font-size: 0.75rem;
          color: rgba(240, 244, 232, 0.8);
          line-height: 1.35;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .log-cat {
          font-size: 0.6rem;
          padding: 2px 6px;
          border-radius: 4px;
          background: rgba(var(--log-color-rgb, 45, 212, 191), 0.2);
          color: rgba(255, 255, 255, 0.6);
          flex-shrink: 0;
        }

        /* 滚动条样式 */
        .streaming-content::-webkit-scrollbar,
        .log-list::-webkit-scrollbar,
        .main-content::-webkit-scrollbar {
          width: 5px;
        }

        .streaming-content::-webkit-scrollbar-track,
        .log-list::-webkit-scrollbar-track,
        .main-content::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 3px;
        }

        .streaming-content::-webkit-scrollbar-thumb,
        .log-list::-webkit-scrollbar-thumb,
        .main-content::-webkit-scrollbar-thumb {
          background: rgba(45, 212, 191, 0.3);
          border-radius: 3px;
        }

        .streaming-content::-webkit-scrollbar-thumb:hover,
        .log-list::-webkit-scrollbar-thumb:hover,
        .main-content::-webkit-scrollbar-thumb:hover {
          background: rgba(45, 212, 191, 0.5);
        }

        /* 响应式适配 */
        @media (max-height: 700px) {
          .evolution-panel {
            border-radius: 18px;
          }
          .main-content {
            padding: 14px;
            gap: 12px;
          }
          .header-section {
            padding-bottom: 12px;
          }
          .dna-animation {
            width: 50px;
            height: 65px;
          }
          .main-title {
            font-size: 1.3rem;
          }
          .stages-container {
            padding: 12px;
          }
          .stage-item {
            width: 54px;
          }
          .stage-icon {
            font-size: 1rem;
          }
          .stage-label {
            font-size: 0.55rem;
          }
          .current-stage-card {
            padding: 10px 14px;
          }
          .stage-emoji {
            font-size: 1.5rem;
          }
          .streaming-content {
            max-height: 20vh;
          }
          .log-list {
            max-height: 100px;
          }
        }

        @media (max-width: 600px) {
          .evolution-panel {
            border-radius: 16px;
          }
          .top-status-bar {
            padding: 10px 14px;
            flex-wrap: wrap;
            gap: 8px;
          }
          .header-section {
            flex-direction: column;
            text-align: center;
          }
          .dna-animation {
            margin: 0 auto;
          }
          .stages-container {
            padding: 10px;
          }
          .stage-item {
            width: 48px;
          }
          .current-stage-card {
            flex-direction: column;
            gap: 10px;
            text-align: center;
          }
          .stage-card-left {
            flex-direction: column;
          }
          .stuck-warning-banner {
            flex-direction: column;
            text-align: center;
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
    "生态": "#10b981",
    "紧急": "#ef4444",
    "其他": "rgba(45, 212, 191, 0.5)"
  };
  return colors[category] || colors["其他"];
}


