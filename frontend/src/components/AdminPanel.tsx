import { useState, useEffect } from "react";
import { checkHealth, dropDatabase } from "@/services/api";
import { 
  X, 
  RefreshCw, 
  Database, 
  AlertTriangle, 
  CheckCircle2,
  XCircle,
  Trash2,
  HardDrive,
  Activity
} from "lucide-react";

interface Props {
  onClose: () => void;
}

export function AdminPanel({ onClose }: Props) {
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [dropLoading, setDropLoading] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => {
    runHealthCheck();
  }, []);

  const runHealthCheck = async () => {
    setLoading(true);
    try {
      const data = await checkHealth();
      setHealthStatus(data);
    } catch (err) {
      console.error(err);
      setHealthStatus({ error: "无法连接服务器" });
    } finally {
      setLoading(false);
    }
  };

  const handleDropDatabase = async () => {
    if (confirmText !== "DELETE") {
      alert('请输入 DELETE 确认操作');
      return;
    }
    
    if (!confirm("⚠️ 最终确认\n\n此操作将：\n• 删除数据库中所有数据\n• 清空所有存档\n• 清空所有缓存\n\n这是不可逆的操作！确定要继续吗？")) {
      return;
    }
    
    setDropLoading(true);
    try {
      const res = await dropDatabase();
      alert("✅ " + res.message);
      window.location.reload();
    } catch (err: unknown) {
      alert("❌ 操作失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setDropLoading(false);
      setConfirmText("");
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === "ok") return <CheckCircle2 size={14} className="status-icon success" />;
    if (status === "missing" || status?.startsWith("error") || status?.startsWith("missing")) {
      return <XCircle size={14} className="status-icon error" />;
    }
    return <AlertTriangle size={14} className="status-icon warning" />;
  };

  return (
    <div className="admin-overlay" onClick={onClose}>
      <div className="admin-panel" onClick={(e) => e.stopPropagation()}>
        <header className="admin-header">
          <div className="header-title">
            <Database size={20} />
            <h2>开发者工具</h2>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        
        <div className="admin-body">
          {/* 系统状态卡片 */}
          <div className="admin-card">
            <div className="card-header">
              <div className="card-title">
                <Activity size={16} />
                <h3>系统状态</h3>
              </div>
              <button 
                className="refresh-btn"
                onClick={runHealthCheck}
                disabled={loading}
                title="刷新状态"
              >
                <RefreshCw size={14} className={loading ? 'spinning' : ''} />
              </button>
            </div>
            
            <div className="status-grid">
              {healthStatus?.error ? (
                <div className="status-error">
                  <XCircle size={20} />
                  <span>{healthStatus.error}</span>
                </div>
              ) : healthStatus ? (
                <>
                  <div className="status-item">
                    <span className="status-label">API 服务</span>
                    <span className="status-value">
                      {getStatusIcon(healthStatus.api)}
                      {healthStatus.api}
                    </span>
                  </div>
                  <div className="status-item">
                    <span className="status-label">数据库</span>
                    <span className="status-value">
                      {getStatusIcon(healthStatus.database)}
                      {healthStatus.database}
                    </span>
                  </div>
                  <div className="status-item">
                    <span className="status-label">初始物种</span>
                    <span className="status-value">
                      {getStatusIcon(healthStatus.initial_species)}
                      {healthStatus.initial_species}
                    </span>
                  </div>
                  {healthStatus.directories && (
                    <div className="status-item full-width">
                      <span className="status-label">数据目录</span>
                      <div className="dirs-grid">
                        {Object.entries(healthStatus.directories).map(([key, val]) => (
                          <span key={key} className="dir-item">
                            {getStatusIcon(val as string)}
                            <span className="dir-name">{key}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="status-loading">
                  <RefreshCw size={16} className="spinning" />
                  <span>检查中...</span>
                </div>
              )}
            </div>
          </div>

          {/* 危险操作区 */}
          <div className="admin-card danger">
            <div className="card-header">
              <div className="card-title">
                <AlertTriangle size={16} />
                <h3>危险操作</h3>
              </div>
            </div>
            
            <div className="danger-zone">
              <div className="danger-item">
                <div className="danger-info">
                  <div className="danger-icon">
                    <Trash2 size={20} />
                  </div>
                  <div className="danger-text">
                    <h4>清空数据库并重建</h4>
                    <p>删除所有表、存档和缓存，重新创建初始状态。此操作不可撤销。</p>
                  </div>
                </div>
                
                <div className="danger-action">
                  <div className="confirm-input-group">
                    <input
                      type="text"
                      placeholder="输入 DELETE 确认"
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value.toUpperCase())}
                      className="confirm-input"
                    />
                    <button 
                      className="danger-btn"
                      onClick={handleDropDatabase}
                      disabled={dropLoading || confirmText !== "DELETE"}
                    >
                      {dropLoading ? (
                        <>
                          <RefreshCw size={14} className="spinning" />
                          执行中...
                        </>
                      ) : (
                        <>
                          <HardDrive size={14} />
                          执行重置
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <style>{`
          .admin-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 8, 4, 0.85);
            backdrop-filter: blur(12px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 300;
            animation: fadeIn 0.2s ease;
          }

          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }

          .admin-panel {
            width: min(95vw, 520px);
            max-height: 85vh;
            background: linear-gradient(165deg, rgba(12, 24, 18, 0.98), rgba(8, 16, 12, 0.99));
            border-radius: 1rem;
            border: 1px solid rgba(45, 212, 191, 0.15);
            box-shadow: 
              0 0 0 1px rgba(0, 0, 0, 0.3),
              0 25px 80px rgba(0, 0, 0, 0.6),
              0 0 60px rgba(45, 212, 191, 0.08);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            animation: modalSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          }

          @keyframes modalSlideIn {
            from { 
              opacity: 0; 
              transform: scale(0.95) translateY(10px); 
            }
            to { 
              opacity: 1; 
              transform: scale(1) translateY(0); 
            }
          }

          .admin-header {
            padding: 1rem 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(45, 212, 191, 0.1);
            background: linear-gradient(to bottom, rgba(45, 212, 191, 0.05), transparent);
          }

          .header-title {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            color: #2dd4bf;
          }

          .header-title h2 {
            margin: 0;
            font-size: 1.1rem;
            font-weight: 600;
            color: #f0f4e8;
          }

          .close-btn {
            width: 2rem;
            height: 2rem;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 0.5rem;
            color: rgba(240, 244, 232, 0.6);
            cursor: pointer;
            transition: all 0.2s;
          }

          .close-btn:hover {
            background: rgba(244, 63, 94, 0.2);
            border-color: rgba(244, 63, 94, 0.4);
            color: #f43f5e;
          }

          .admin-body {
            flex: 1;
            padding: 1.25rem;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1rem;
          }

          .admin-card {
            background: rgba(45, 212, 191, 0.03);
            border: 1px solid rgba(45, 212, 191, 0.1);
            border-radius: 0.875rem;
            overflow: hidden;
          }

          .admin-card.danger {
            background: rgba(244, 63, 94, 0.03);
            border-color: rgba(244, 63, 94, 0.15);
          }

          .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.875rem 1rem;
            border-bottom: 1px solid rgba(45, 212, 191, 0.08);
          }

          .admin-card.danger .card-header {
            border-bottom-color: rgba(244, 63, 94, 0.1);
          }

          .card-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #2dd4bf;
          }

          .admin-card.danger .card-title {
            color: #f87171;
          }

          .card-title h3 {
            margin: 0;
            font-size: 0.9rem;
            font-weight: 600;
            color: #f0f4e8;
          }

          .refresh-btn {
            width: 1.75rem;
            height: 1.75rem;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(45, 212, 191, 0.1);
            border: 1px solid rgba(45, 212, 191, 0.2);
            border-radius: 0.375rem;
            color: rgba(240, 244, 232, 0.6);
            cursor: pointer;
            transition: all 0.2s;
          }

          .refresh-btn:hover:not(:disabled) {
            background: rgba(45, 212, 191, 0.2);
            color: #2dd4bf;
          }

          .refresh-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }

          .spinning {
            animation: spin 0.8s linear infinite;
          }

          @keyframes spin {
            to { transform: rotate(360deg); }
          }

          .status-grid {
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
          }

          .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0.75rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 0.5rem;
          }

          .status-item.full-width {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.625rem;
          }

          .status-label {
            font-size: 0.8rem;
            color: rgba(240, 244, 232, 0.6);
          }

          .status-value {
            display: flex;
            align-items: center;
            gap: 0.375rem;
            font-size: 0.85rem;
            font-weight: 500;
            color: #f0f4e8;
          }

          .status-icon.success {
            color: #4ade80;
          }

          .status-icon.error {
            color: #f87171;
          }

          .status-icon.warning {
            color: #fbbf24;
          }

          .dirs-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
          }

          .dir-item {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.25rem 0.5rem;
            background: rgba(45, 212, 191, 0.08);
            border-radius: 0.375rem;
            font-size: 0.75rem;
            color: rgba(240, 244, 232, 0.8);
          }

          .dir-name {
            font-family: 'SF Mono', monospace;
          }

          .status-loading,
          .status-error {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            padding: 1.5rem;
            color: rgba(240, 244, 232, 0.5);
          }

          .status-error {
            color: #f87171;
          }

          .danger-zone {
            padding: 1rem;
          }

          .danger-item {
            display: flex;
            flex-direction: column;
            gap: 1rem;
          }

          .danger-info {
            display: flex;
            gap: 0.875rem;
          }

          .danger-icon {
            width: 2.5rem;
            height: 2.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(244, 63, 94, 0.1);
            border-radius: 0.625rem;
            color: #f87171;
            flex-shrink: 0;
          }

          .danger-text h4 {
            margin: 0 0 0.25rem 0;
            font-size: 0.9rem;
            font-weight: 600;
            color: #f0f4e8;
          }

          .danger-text p {
            margin: 0;
            font-size: 0.8rem;
            color: rgba(240, 244, 232, 0.55);
            line-height: 1.5;
          }

          .danger-action {
            padding-top: 0.5rem;
          }

          .confirm-input-group {
            display: flex;
            gap: 0.625rem;
          }

          .confirm-input {
            flex: 1;
            padding: 0.625rem 0.875rem;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(244, 63, 94, 0.2);
            border-radius: 0.5rem;
            color: #f0f4e8;
            font-size: 0.85rem;
            font-family: 'SF Mono', monospace;
            letter-spacing: 0.1em;
            text-transform: uppercase;
          }

          .confirm-input::placeholder {
            color: rgba(240, 244, 232, 0.3);
            text-transform: none;
            letter-spacing: normal;
          }

          .confirm-input:focus {
            outline: none;
            border-color: rgba(244, 63, 94, 0.4);
            box-shadow: 0 0 0 2px rgba(244, 63, 94, 0.1);
          }

          .danger-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.625rem 1rem;
            background: linear-gradient(135deg, rgba(244, 63, 94, 0.15), rgba(239, 68, 68, 0.1));
            border: 1px solid rgba(244, 63, 94, 0.3);
            border-radius: 0.5rem;
            color: #f87171;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
          }

          .danger-btn:hover:not(:disabled) {
            background: linear-gradient(135deg, rgba(244, 63, 94, 0.25), rgba(239, 68, 68, 0.2));
            border-color: rgba(244, 63, 94, 0.5);
            transform: translateY(-1px);
          }

          .danger-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
          }
        `}</style>
      </div>
    </div>
  );
}
