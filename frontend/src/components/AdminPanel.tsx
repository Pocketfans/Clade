import { useState, useEffect } from "react";
import { checkHealth, resetWorld, simulateTerrain } from "../services/api";

interface Props {
  onClose: () => void;
}

export function AdminPanel({ onClose }: Props) {
  const [activeTab, setActiveTab] = useState<"health" | "reset" | "terrain">("health");
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  // Reset State
  const [keepSaves, setKeepSaves] = useState(false);
  const [keepMap, setKeepMap] = useState(false);

  // Terrain State
  const [simTurns, setSimTurns] = useState(5);

  useEffect(() => {
    if (activeTab === "health") {
      runHealthCheck();
    }
  }, [activeTab]);

  const runHealthCheck = async () => {
    setLoading(true);
    try {
      const data = await checkHealth();
      setHealthStatus(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("警告：此操作将清除游戏数据！确定要继续吗？")) return;
    
    setLoading(true);
    try {
      const res = await resetWorld(keepSaves, keepMap);
      alert(res.message);
      window.location.reload(); // 刷新页面以重置状态
    } catch (err: any) {
      alert("重置失败: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTerrainSim = async () => {
    setLoading(true);
    setLogs(["开始模拟..."]);
    try {
      const res = await simulateTerrain(simTurns, 80, 40);
      if (res.success) {
        setLogs(res.logs);
      } else {
        setLogs((prev) => [...prev, "模拟失败: " + res.error]);
      }
    } catch (err: any) {
      setLogs((prev) => [...prev, "请求错误: " + err.message]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fullscreen-overlay" onClick={onClose}>
      <div className="fullscreen-panel" style={{ maxWidth: "800px" }} onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>开发者工具</h2>
          <button className="btn-icon btn-secondary" onClick={onClose}>×</button>
        </header>
        
        <div className="tabs">
          <button 
            className={`tab ${activeTab === "health" ? "active" : ""}`}
            onClick={() => setActiveTab("health")}
          >
            系统健康
          </button>
          <button 
            className={`tab ${activeTab === "reset" ? "active" : ""}`}
            onClick={() => setActiveTab("reset")}
          >
            重置世界
          </button>
          <button 
            className={`tab ${activeTab === "terrain" ? "active" : ""}`}
            onClick={() => setActiveTab("terrain")}
          >
            地形沙盒
          </button>
        </div>

        <div className="fullscreen-body">
          {activeTab === "health" && (
            <div className="card">
              <h3>系统状态诊断</h3>
              {loading ? <p>检查中...</p> : (
                <div className="health-report">
                  {healthStatus ? (
                    <pre>{JSON.stringify(healthStatus, null, 2)}</pre>
                  ) : (
                    <p>无法获取状态</p>
                  )}
                  <button className="btn-primary" onClick={runHealthCheck}>重新检查</button>
                </div>
              )}
            </div>
          )}

          {activeTab === "reset" && (
            <div className="card">
              <h3>危险操作区</h3>
              <p className="warning-text">此操作将重置数据库到初始状态。</p>
              
              <div className="form-group">
                <label>
                  <input 
                    type="checkbox" 
                    checked={keepSaves} 
                    onChange={(e) => setKeepSaves(e.target.checked)} 
                  />
                  保留存档文件 (data/saves)
                </label>
              </div>
              
              <div className="form-group">
                <label>
                  <input 
                    type="checkbox" 
                    checked={keepMap} 
                    onChange={(e) => setKeepMap(e.target.checked)} 
                  />
                  保留地图演化历史
                </label>
              </div>

              <button 
                className="btn-danger" 
                onClick={handleReset} 
                disabled={loading}
              >
                {loading ? "重置中..." : "执行重置"}
              </button>
            </div>
          )}

          {activeTab === "terrain" && (
            <div className="card">
              <h3>地形演化模拟器</h3>
              <div className="controls">
                <label>模拟回合数: 
                  <input 
                    type="number" 
                    value={simTurns} 
                    onChange={(e) => setSimTurns(parseInt(e.target.value))}
                    min={1} max={20}
                  />
                </label>
                <button className="btn-primary" onClick={handleTerrainSim} disabled={loading}>
                  {loading ? "运行中..." : "开始模拟"}
                </button>
              </div>
              
              <div className="logs-container" style={{ 
                marginTop: "1rem", 
                background: "#111", 
                padding: "1rem", 
                borderRadius: "4px",
                maxHeight: "300px",
                overflowY: "auto",
                fontFamily: "monospace"
              }}>
                {logs.map((log, i) => (
                  <div key={i}>{log}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

