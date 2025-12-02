import { useEffect, useRef, useState } from "react";
import { fetchLogs, fetchAIDiagnostics, resetAIDiagnostics, type AIDiagnostics } from "@/services/api";

interface LogPanelProps {
  onClose: () => void;
}

export function LogPanel({ onClose }: LogPanelProps) {
  const [activeTab, setActiveTab] = useState<"logs" | "ai-diagnostics">("logs");
  const [logs, setLogs] = useState<string[]>([]);
  const [lines, setLines] = useState(100);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [filterLevel, setFilterLevel] = useState<string>("ALL");
  const intervalRef = useRef<number | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  
  // AI 诊断状态
  const [diagnostics, setDiagnostics] = useState<AIDiagnostics | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);

  const loadLogs = async () => {
    try {
      const data = await fetchLogs(lines);
      setLogs(data);
    } catch (e) {
      console.error("Failed to load logs", e);
    }
  };
  
  const loadDiagnostics = async () => {
    setDiagLoading(true);
    try {
      const data = await fetchAIDiagnostics();
      setDiagnostics(data);
    } catch (e) {
      console.error("Failed to load AI diagnostics", e);
    } finally {
      setDiagLoading(false);
    }
  };
  
  const handleResetDiagnostics = async () => {
    try {
      await resetAIDiagnostics();
      await loadDiagnostics();
    } catch (e) {
      console.error("Failed to reset diagnostics", e);
    }
  };

  useEffect(() => {
    if (activeTab === "logs") {
      loadLogs();
      if (autoRefresh) {
        intervalRef.current = window.setInterval(loadLogs, 2000);
      }
    } else {
      loadDiagnostics();
      if (autoRefresh) {
        intervalRef.current = window.setInterval(loadDiagnostics, 2000);
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [lines, autoRefresh, activeTab]);

  useEffect(() => {
    // Scroll to bottom on new logs
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const filteredLogs = logs.filter(log => {
    if (filterLevel === "ALL") return true;
    return log.includes(`[${filterLevel}]`);
  });

  return (
    <div style={{
      position: "fixed",
      top: "10%",
      left: "10%",
      width: "80%",
      height: "80%",
      backgroundColor: "#1e1e1e",
      border: "1px solid #444",
      borderRadius: "8px",
      zIndex: 2000,
      display: "flex",
      flexDirection: "column",
      color: "#e0e0e0",
      fontFamily: "monospace",
      boxShadow: "0 0 20px rgba(0,0,0,0.5)"
    }}>
      {/* 标签栏 */}
      <div style={{
        display: "flex",
        borderBottom: "1px solid #444",
        backgroundColor: "#2d2d2d"
      }}>
        <button
          onClick={() => setActiveTab("logs")}
          style={{
            padding: "10px 20px",
            background: activeTab === "logs" ? "#333" : "transparent",
            border: "none",
            borderBottom: activeTab === "logs" ? "2px solid #4ade80" : "2px solid transparent",
            color: activeTab === "logs" ? "#4ade80" : "#aaa",
            cursor: "pointer",
            fontSize: "14px"
          }}
        >
          📋 系统日志
        </button>
        <button
          onClick={() => setActiveTab("ai-diagnostics")}
          style={{
            padding: "10px 20px",
            background: activeTab === "ai-diagnostics" ? "#333" : "transparent",
            border: "none",
            borderBottom: activeTab === "ai-diagnostics" ? "2px solid #facc15" : "2px solid transparent",
            color: activeTab === "ai-diagnostics" ? "#facc15" : "#aaa",
            cursor: "pointer",
            fontSize: "14px"
          }}
        >
          🤖 AI 诊断
        </button>
        <div style={{ flex: 1 }} />
        <button 
          onClick={onClose}
          style={{ 
            background: "none", 
            border: "none", 
            color: "#aaa", 
            fontSize: "20px", 
            cursor: "pointer",
            padding: "10px 15px"
          }}
        >
          ✕
        </button>
      </div>
      
      {/* 日志标签页 */}
      {activeTab === "logs" && (
        <>
          <div style={{
            padding: "10px",
            borderBottom: "1px solid #444",
            display: "flex",
            gap: "10px",
            alignItems: "center",
            backgroundColor: "#252525"
          }}>
            <select 
              value={filterLevel} 
              onChange={(e) => setFilterLevel(e.target.value)}
              style={{ background: "#333", color: "white", border: "1px solid #555", padding: "4px 8px", borderRadius: "4px" }}
            >
              <option value="ALL">全部等级</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="DEBUG">DEBUG</option>
            </select>
            <select 
              value={lines} 
              onChange={(e) => setLines(Number(e.target.value))}
              style={{ background: "#333", color: "white", border: "1px solid #555", padding: "4px 8px", borderRadius: "4px" }}
            >
              <option value={100}>100行</option>
              <option value={500}>500行</option>
              <option value={1000}>1000行</option>
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: "5px", cursor: "pointer" }}>
              <input 
                type="checkbox" 
                checked={autoRefresh} 
                onChange={(e) => setAutoRefresh(e.target.checked)} 
              />
              自动刷新
            </label>
            <button onClick={loadLogs} style={{ padding: "4px 12px", fontSize: "12px", background: "#444", border: "none", color: "#fff", borderRadius: "4px", cursor: "pointer" }}>
              刷新
            </button>
          </div>
          <div style={{
            flex: 1,
            overflowY: "auto",
            padding: "10px",
            backgroundColor: "#111"
          }}>
            {filteredLogs.map((log, index) => {
              let color = "#ccc";
              if (log.includes("[ERROR]")) color = "#ff6b6b";
              else if (log.includes("[WARNING]")) color = "#ffd93d";
              else if (log.includes("[INFO]")) color = "#6bff84";
              else if (log.includes("[DEBUG]")) color = "#4d96ff";

              return (
                <div key={index} style={{ color, marginBottom: "2px", whiteSpace: "pre-wrap", fontSize: "12px" }}>
                  {log}
                </div>
              );
            })}
            <div ref={logEndRef} />
          </div>
        </>
      )}
      
      {/* AI 诊断标签页 */}
      {activeTab === "ai-diagnostics" && (
        <>
          <div style={{
            padding: "10px",
            borderBottom: "1px solid #444",
            display: "flex",
            gap: "10px",
            alignItems: "center",
            backgroundColor: "#252525"
          }}>
            <label style={{ display: "flex", alignItems: "center", gap: "5px", cursor: "pointer" }}>
              <input 
                type="checkbox" 
                checked={autoRefresh} 
                onChange={(e) => setAutoRefresh(e.target.checked)} 
              />
              自动刷新 (2秒)
            </label>
            <button onClick={loadDiagnostics} disabled={diagLoading} style={{ padding: "4px 12px", fontSize: "12px", background: "#444", border: "none", color: "#fff", borderRadius: "4px", cursor: "pointer" }}>
              {diagLoading ? "加载中..." : "刷新"}
            </button>
            <button onClick={handleResetDiagnostics} style={{ padding: "4px 12px", fontSize: "12px", background: "#663333", border: "none", color: "#fff", borderRadius: "4px", cursor: "pointer" }}>
              重置统计
            </button>
          </div>
          <div style={{
            flex: 1,
            overflowY: "auto",
            padding: "20px",
            backgroundColor: "#111"
          }}>
            {diagnostics ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                {/* 建议区域 */}
                <div style={{ 
                  padding: "15px", 
                  background: "#1a1a2e", 
                  borderRadius: "8px",
                  border: "1px solid #333"
                }}>
                  <h4 style={{ margin: "0 0 10px 0", color: "#facc15" }}>💡 诊断建议</h4>
                  {diagnostics.advice.map((adv, i) => (
                    <div key={i} style={{ padding: "5px 0", fontSize: "14px" }}>{adv}</div>
                  ))}
                </div>
                
                {/* 实时状态 */}
                <div style={{ 
                  display: "grid", 
                  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", 
                  gap: "15px" 
                }}>
                  <StatCard 
                    label="并发限制" 
                    value={diagnostics.concurrency_limit} 
                    color="#4ade80" 
                  />
                  <StatCard 
                    label="活跃请求" 
                    value={diagnostics.active_requests} 
                    color={diagnostics.active_requests >= diagnostics.concurrency_limit * 0.8 ? "#ff6b6b" : "#4ade80"}
                    subtext={`${((diagnostics.active_requests / diagnostics.concurrency_limit) * 100).toFixed(0)}% 使用中`}
                  />
                  <StatCard 
                    label="排队请求" 
                    value={diagnostics.queued_requests} 
                    color={diagnostics.queued_requests > 5 ? "#ffd93d" : "#4ade80"} 
                  />
                  <StatCard 
                    label="总请求数" 
                    value={diagnostics.total_requests} 
                    color="#4d96ff" 
                  />
                  <StatCard 
                    label="超时次数" 
                    value={diagnostics.total_timeouts} 
                    color={diagnostics.total_timeouts > 0 ? "#ff6b6b" : "#4ade80"} 
                  />
                  <StatCard 
                    label="超时率" 
                    value={diagnostics.timeout_rate} 
                    color={parseFloat(diagnostics.timeout_rate) > 10 ? "#ff6b6b" : "#4ade80"} 
                  />
                </div>
                
                {/* 各能力统计 */}
                <div style={{ 
                  padding: "15px", 
                  background: "#1a1a2e", 
                  borderRadius: "8px",
                  border: "1px solid #333"
                }}>
                  <h4 style={{ margin: "0 0 15px 0", color: "#4d96ff" }}>📊 各能力调用统计</h4>
                  {Object.keys(diagnostics.request_stats).length === 0 ? (
                    <div style={{ color: "#666" }}>暂无调用记录</div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid #333" }}>
                          <th style={{ textAlign: "left", padding: "8px", color: "#888" }}>能力</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>总计</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>成功</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>超时</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>错误</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>平均耗时</th>
                          <th style={{ textAlign: "right", padding: "8px", color: "#888" }}>成功率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(diagnostics.request_stats).map(([cap, stats]) => {
                          const successRate = stats.total > 0 ? (stats.success / stats.total) * 100 : 0;
                          return (
                            <tr key={cap} style={{ borderBottom: "1px solid #222" }}>
                              <td style={{ padding: "8px", color: "#fff" }}>{cap}</td>
                              <td style={{ textAlign: "right", padding: "8px", color: "#4d96ff" }}>{stats.total}</td>
                              <td style={{ textAlign: "right", padding: "8px", color: "#4ade80" }}>{stats.success}</td>
                              <td style={{ textAlign: "right", padding: "8px", color: stats.timeout > 0 ? "#ff6b6b" : "#666" }}>{stats.timeout}</td>
                              <td style={{ textAlign: "right", padding: "8px", color: stats.error > 0 ? "#ff6b6b" : "#666" }}>{stats.error}</td>
                              <td style={{ textAlign: "right", padding: "8px", color: "#ffd93d" }}>{stats.avg_time.toFixed(2)}s</td>
                              <td style={{ textAlign: "right", padding: "8px", color: successRate >= 90 ? "#4ade80" : successRate >= 70 ? "#ffd93d" : "#ff6b6b" }}>
                                {successRate.toFixed(1)}%
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ textAlign: "center", color: "#666", padding: "40px" }}>
                {diagLoading ? "加载中..." : "无数据"}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, color, subtext }: { label: string; value: number | string; color: string; subtext?: string }) {
  return (
    <div style={{
      padding: "15px",
      background: "#1a1a2e",
      borderRadius: "8px",
      border: "1px solid #333",
      textAlign: "center"
    }}>
      <div style={{ fontSize: "12px", color: "#888", marginBottom: "5px" }}>{label}</div>
      <div style={{ fontSize: "24px", fontWeight: "bold", color }}>{value}</div>
      {subtext && <div style={{ fontSize: "11px", color: "#666", marginTop: "3px" }}>{subtext}</div>}
    </div>
  );
}

