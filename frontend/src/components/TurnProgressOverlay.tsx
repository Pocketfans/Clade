import { useEffect, useState, useRef, useCallback } from "react";
import { connectToEventStream } from "../services/api";

interface Props {
  message?: string;
  showDetails?: boolean;
}

// 连接状态类型
type ConnectionStatus = "connecting" | "connected" | "receiving" | "error" | "disconnected";

// 演化阶段定义
const EVOLUTION_STAGES = [
  { id: "pressure", icon: "🌡️", label: "环境压力", color: "#fb923c" },
  { id: "geology", icon: "🗺️", label: "地质演化", color: "#8b5cf6" },
  { id: "mortality", icon: "💀", label: "死亡计算", color: "#f43f5e" },
  { id: "reproduction", icon: "🐣", label: "繁殖增长", color: "#4ade80" },
  { id: "speciation", icon: "🔀", label: "物种分化", color: "#c084fc" },
  { id: "migration", icon: "🦅", label: "迁徙路径", color: "#38bdf8" },
  { id: "report", icon: "📝", label: "生成报告", color: "#2dd4bf" },
];

export function TurnProgressOverlay({ message = "推演进行中...", showDetails = true }: Props) {
  // 状态管理
  const [logs, setLogs] = useState<Array<{ icon: string; text: string; category: string; timestamp: number }>>([]);
  const [currentStage, setCurrentStage] = useState<string>("等待推演开始...");
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(-1);
  const [streamingText, setStreamingText] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [tokenCount, setTokenCount] = useState<number>(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [isStreamingActive, setIsStreamingActive] = useState<boolean>(false);
  
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

  // 根据阶段文本判断当前阶段索引
  const detectStageIndex = useCallback((stageText: string): number => {
    const lowerText = stageText.toLowerCase();
    if (lowerText.includes("压力") || lowerText.includes("pressure")) return 0;
    if (lowerText.includes("地图") || lowerText.includes("地质") || lowerText.includes("geology") || lowerText.includes("海平面")) return 1;
    if (lowerText.includes("死亡") || lowerText.includes("mortality") || lowerText.includes("灭绝")) return 2;
    if (lowerText.includes("繁殖") || lowerText.includes("reproduction") || lowerText.includes("种群")) return 3;
    if (lowerText.includes("分化") || lowerText.includes("speciation") || lowerText.includes("AI并发")) return 4;
    if (lowerText.includes("迁徙") || lowerText.includes("migration")) return 5;
    if (lowerText.includes("报告") || lowerText.includes("report") || lowerText.includes("叙事")) return 6;
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
      
      setLogs(prev => [...prev, { 
        icon, 
        text: cleanMessage, 
        category, 
        timestamp: Date.now() 
      }].slice(-50));
      
      // 更新当前阶段
      if (event.type === 'stage') {
        const stageText = cleanMessage.length > 60 ? cleanMessage.substring(0, 60) + '...' : cleanMessage;
        setCurrentStage(stageText);
        setCurrentStageIndex(detectStageIndex(cleanMessage));
        
        // 如果进入报告阶段，清空之前的流式文本
        if (cleanMessage.includes("报告") || cleanMessage.includes("叙事")) {
          setStreamingText("");
          setTokenCount(0);
          setIsStreamingActive(false);
        }
      }

      if (event.type === 'turn_complete') {
        setIsStreamingActive(false);
        setConnectionStatus("connected");
      }

      if (event.type === 'error') {
        setConnectionStatus("error");
      }
    });
    
    eventSourceRef.current = eventSource;

    // 自动滚动日志
    const scrollInterval = setInterval(() => {
      if (logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      }
    }, 500);

    return () => {
      console.log("[事件流] 断开连接");
      setConnectionStatus("disconnected");
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      clearInterval(scrollInterval);
    };
  }, [showDetails, detectStageIndex, scrollStreamingToBottom]);

  // 重置状态
  useEffect(() => {
    if (message.includes("开始")) {
      setLogs([]);
      setStreamingText("");
      setTokenCount(0);
      setCurrentStageIndex(-1);
      setIsStreamingActive(false);
      setStartTime(Date.now());
    }
  }, [message]);

  // 计算经过时间
  const elapsedTime = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0;
  const elapsedMinutes = Math.floor(elapsedTime / 60);
  const elapsedSeconds = elapsedTime % 60;

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
        </div>

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
                {logs.length > 0 && (
                  <span className="log-count">{logs.length} 条</span>
                )}
              </div>
              {logs.length === 0 ? (
                <div className="log-empty">
                  <span className="empty-icon">🌱</span>
                  <span>等待演化数据...</span>
                </div>
              ) : (
                <div className="log-list">
                  {logs.map((log, idx) => (
                    <div
                      key={idx}
                      className="log-item"
                      style={{ 
                        '--log-color': getCategoryColor(log.category),
                        animationDelay: `${idx * 0.02}s`
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
        }

        .evolution-panel {
          background: linear-gradient(145deg, rgba(15, 25, 20, 0.95), rgba(8, 16, 12, 0.98));
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 20px;
          padding: 32px 40px;
          text-align: center;
          max-width: 950px;
          width: 92%;
          box-shadow: 
            0 30px 100px rgba(0, 0, 0, 0.7),
            0 0 80px rgba(45, 212, 191, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 0.03);
          max-height: 90vh;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        /* 状态栏 */
        .status-bar {
          display: flex;
          justify-content: center;
          gap: 24px;
          margin-bottom: 20px;
          padding: 10px 16px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .status-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.8rem;
        }

        .status-icon {
          font-size: 0.9rem;
        }

        .status-text {
          color: rgba(255, 255, 255, 0.7);
          font-family: var(--font-mono, monospace);
        }

        /* DNA 加载动画 */
        .dna-loader {
          position: relative;
          margin: 0 auto 24px;
          width: 70px;
          height: 80px;
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
          height: 7px;
          animation: dna-wave 1.8s ease-in-out infinite;
        }

        .dna-node-left, .dna-node-right {
          width: 9px;
          height: 9px;
          border-radius: 50%;
          background: #2dd4bf;
          box-shadow: 0 0 12px rgba(45, 212, 191, 0.7);
        }

        .dna-node-right {
          background: #22c55e;
          box-shadow: 0 0 12px rgba(34, 197, 94, 0.7);
        }

        .dna-bridge {
          width: 28px;
          height: 2px;
          background: linear-gradient(90deg, rgba(45, 212, 191, 0.9), rgba(34, 197, 94, 0.9));
          border-radius: 2px;
        }

        @keyframes dna-wave {
          0%, 100% { transform: translateX(-12px) rotateY(0deg); }
          50% { transform: translateX(12px) rotateY(180deg); }
        }

        .dna-glow {
          position: absolute;
          inset: -25px;
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
          gap: 10px;
          margin-bottom: 12px;
        }

        .title-icon {
          font-size: 1.8rem;
          animation: title-bounce 2.5s ease-in-out infinite;
        }

        @keyframes title-bounce {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          25% { transform: translateY(-3px) rotate(-3deg); }
          75% { transform: translateY(-3px) rotate(3deg); }
        }

        .title-text {
          font-size: 1.7rem;
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
          font-size: 1rem;
          color: rgba(240, 244, 232, 0.7);
          margin-bottom: 24px;
          line-height: 1.5;
        }

        /* 进度阶段指示器 */
        .progress-stages {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 24px;
          padding: 0 10px;
          position: relative;
        }

        .progress-stage {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          z-index: 1;
          opacity: 0.4;
          transition: all 0.4s ease;
        }

        .progress-stage.active {
          opacity: 1;
        }

        .progress-stage.current .stage-circle {
          transform: scale(1.15);
          box-shadow: 0 0 20px var(--stage-color);
        }

        .stage-circle {
          width: 36px;
          height: 36px;
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
          font-size: 1.1rem;
        }

        .stage-label {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.5);
          max-width: 60px;
          text-align: center;
        }

        .progress-stage.active .stage-label {
          color: rgba(255, 255, 255, 0.9);
        }

        .progress-line {
          position: absolute;
          left: 28px;
          top: 18px;
          height: 2px;
          background: linear-gradient(90deg, #2dd4bf, #22c55e);
          transition: width 0.5s ease;
          z-index: 0;
        }

        /* 当前阶段卡片 */
        .current-stage-card {
          position: relative;
          background: linear-gradient(135deg, rgba(45, 212, 191, 0.08), rgba(34, 197, 94, 0.04));
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 14px;
          padding: 16px 20px;
          margin-bottom: 20px;
          display: flex;
          align-items: center;
          gap: 14px;
          overflow: hidden;
        }

        .stage-icon-large {
          font-size: 1.6rem;
          flex-shrink: 0;
        }

        .stage-text-main {
          font-size: 0.95rem;
          color: #f0f4e8;
          font-weight: 500;
          flex: 1;
          text-align: left;
        }

        .stage-pulse-indicator {
          width: 10px;
          height: 10px;
          background: #4ade80;
          border-radius: 50%;
          animation: pulse-indicator 1.2s ease-in-out infinite;
        }

        @keyframes pulse-indicator {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }

        /* 流式文本容器 - 大幅改进 */
        .streaming-container {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.06), rgba(45, 212, 191, 0.03));
          border: 1px solid rgba(34, 197, 94, 0.2);
          border-radius: 14px;
          margin-bottom: 20px;
          overflow: hidden;
        }

        .streaming-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(34, 197, 94, 0.1);
        }

        .streaming-title {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
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
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          font-family: var(--font-mono, monospace);
          background: rgba(0, 0, 0, 0.3);
          padding: 3px 8px;
          border-radius: 4px;
        }

        .streaming-content {
          padding: 16px;
          max-height: 180px;
          overflow-y: auto;
          scroll-behavior: smooth;
        }

        .streaming-text {
          color: rgba(240, 244, 232, 0.9);
          font-size: 0.9rem;
          line-height: 1.7;
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

        /* 日志容器 */
        .evolution-log-container {
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(45, 212, 191, 0.1);
          border-radius: 12px;
          flex: 1;
          min-height: 150px;
          max-height: 220px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .log-header {
          font-size: 0.85rem;
          color: rgba(240, 244, 232, 0.7);
          padding: 12px 16px;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(0, 0, 0, 0.2);
          flex-shrink: 0;
        }

        .log-count {
          font-size: 0.7rem;
          color: rgba(240, 244, 232, 0.4);
          background: rgba(255, 255, 255, 0.05);
          padding: 2px 8px;
          border-radius: 10px;
        }

        .log-list {
          padding: 8px;
          overflow-y: auto;
          flex: 1;
        }

        .log-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          height: 100%;
          color: rgba(240, 244, 232, 0.3);
          font-size: 0.85rem;
        }

        .empty-icon {
          font-size: 1.5rem;
          opacity: 0.5;
        }

        .log-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          margin-bottom: 4px;
          background: rgba(45, 212, 191, 0.02);
          border-left: 3px solid var(--log-color);
          border-radius: 6px;
          animation: log-slide-in 0.3s ease-out both;
        }

        @keyframes log-slide-in {
          from { 
            opacity: 0; 
            transform: translateX(-15px); 
          }
          to { 
            opacity: 1; 
            transform: translateX(0); 
          }
        }

        .log-icon {
          font-size: 0.9rem;
          flex-shrink: 0;
        }

        .log-text {
          flex: 1;
          font-size: 0.78rem;
          color: rgba(240, 244, 232, 0.85);
          text-align: left;
          line-height: 1.4;
        }

        .log-category {
          font-size: 0.6rem;
          padding: 2px 6px;
          border-radius: 4px;
          color: rgba(255, 255, 255, 0.7);
          flex-shrink: 0;
        }

        /* 滚动条样式 */
        .streaming-content::-webkit-scrollbar,
        .log-list::-webkit-scrollbar {
          width: 5px;
        }

        .streaming-content::-webkit-scrollbar-track,
        .log-list::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 3px;
        }

        .streaming-content::-webkit-scrollbar-thumb,
        .log-list::-webkit-scrollbar-thumb {
          background: rgba(45, 212, 191, 0.3);
          border-radius: 3px;
        }

        .streaming-content::-webkit-scrollbar-thumb:hover,
        .log-list::-webkit-scrollbar-thumb:hover {
          background: rgba(45, 212, 191, 0.5);
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
