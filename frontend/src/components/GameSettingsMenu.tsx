import { useState, useEffect } from "react";
import { 
  X, 
  Settings, 
  Wrench, 
  Save, 
  LogOut, 
  FolderOpen,
  ChevronLeft,
  Clock,
  Users,
  Play,
  Check
} from "lucide-react";
import type { SaveMetadata } from "../services/api.types";
import { listSaves, loadGame } from "../services/api";
import { AdminPanel } from "./AdminPanel";

interface Props {
  currentSaveName: string;
  onClose: () => void;
  onBackToMenu: () => void;
  onSaveGame: () => void;
  onLoadGame: (saveName: string) => void;
  onOpenAISettings: () => void;
  initialView?: "menu" | "load";
}

export function GameSettingsMenu({
  currentSaveName,
  onClose,
  onBackToMenu,
  onSaveGame,
  onLoadGame,
  onOpenAISettings,
  initialView = "menu",
}: Props) {
  const [saves, setSaves] = useState<SaveMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [showLoadPanel, setShowLoadPanel] = useState(initialView === "load");
  const [showAdminPanel, setShowAdminPanel] = useState(false);

  // Load saves immediately if initialView is 'load'
  useEffect(() => {
    if (initialView === "load") {
      handleLoadClick();
    }
  }, [initialView]);

  const handleLoadClick = async () => {
    setLoading(true);
    try {
      const data = await listSaves();
      setSaves(data);
      setShowLoadPanel(true);
    } catch (err) {
      console.error("加载存档列表失败:", err);
      alert("加载存档列表失败");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSave = async (saveName: string) => {
    setLoading(true);
    try {
      await loadGame(saveName);
      onLoadGame(saveName);
      onClose();
    } catch (err) {
      console.error("加载存档失败:", err);
      alert("加载存档失败");
    } finally {
      setLoading(false);
    }
  };

  const handleBackToMenu = () => {
    if (confirm("返回主菜单将不会保存当前进度，确定要继续吗？")) {
      onBackToMenu();
      onClose();
    }
  };

  const handleSaveAndExit = async () => {
    try {
      await onSaveGame();
      alert("保存成功！即将返回主菜单。");
      onBackToMenu();
      onClose();
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败");
    }
  };

  if (showAdminPanel) {
    return <AdminPanel onClose={() => setShowAdminPanel(false)} />;
  }

  return (
    <div className="game-settings-overlay" onClick={onClose}>
      <div className="game-settings-modal" onClick={(e) => e.stopPropagation()}>
        {/* 头部 */}
        <header className="game-settings-header">
          <div className="header-left">
            {showLoadPanel && (
              <button 
                type="button" 
                className="back-btn"
                onClick={() => setShowLoadPanel(false)}
              >
                <ChevronLeft size={20} />
              </button>
            )}
            <h2>{showLoadPanel ? "读取存档" : "游戏设置"}</h2>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </header>

        {/* 内容区 */}
        <div className="game-settings-body">
          {showLoadPanel ? (
            <div className="saves-container">
              {loading ? (
                <div className="loading-state">
                  <div className="spinner" />
                  <p>加载存档列表...</p>
                </div>
              ) : saves.length === 0 ? (
                <div className="empty-state">
                  <FolderOpen size={48} strokeWidth={1.5} />
                  <p>暂无存档</p>
                  <span>开始新游戏后可在此处保存进度</span>
                </div>
              ) : (
                <div className="saves-list">
                  {saves.map((save, idx) => {
                    const isCurrent = save.name === currentSaveName;
                    return (
                      <div 
                        key={save.name} 
                        className={`save-card ${isCurrent ? 'current' : ''}`}
                        style={{ animationDelay: `${idx * 0.05}s` }}
                      >
                        <div className="save-info">
                          <div className="save-name">
                            {save.name}
                            {isCurrent && (
                              <span className="current-badge">
                                <Check size={12} /> 当前
                              </span>
                            )}
                          </div>
                          <div className="save-meta">
                            <span><Clock size={14} /> 回合 {save.turn + 1}</span>
                            <span><Users size={14} /> {save.species_count} 物种</span>
                          </div>
                          <div className="save-time">
                            {new Date(save.timestamp * 1000).toLocaleString("zh-CN", {
                              year: 'numeric',
                              month: '2-digit',
                              day: '2-digit',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </div>
                        </div>
                        <button
                          type="button"
                          className={`load-btn ${isCurrent ? 'disabled' : ''}`}
                          onClick={() => handleLoadSave(save.name)}
                          disabled={loading || isCurrent}
                        >
                          {isCurrent ? (
                            <>已加载</>
                          ) : (
                            <><Play size={16} /> 读取</>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="menu-grid">
              <button
                type="button"
                className="menu-card"
                onClick={onOpenAISettings}
              >
                <div className="card-icon ai">
                  <Settings size={28} />
                </div>
                <div className="card-content">
                  <h3>AI 设置</h3>
                  <p>配置模型提供商、API密钥与向量服务</p>
                </div>
              </button>

              <button
                type="button"
                className="menu-card"
                onClick={handleLoadClick}
                disabled={loading}
              >
                <div className="card-icon load">
                  <FolderOpen size={28} />
                </div>
                <div className="card-content">
                  <h3>读取存档</h3>
                  <p>从之前保存的进度继续游戏</p>
                </div>
              </button>

              <button
                type="button"
                className="menu-card"
                onClick={() => setShowAdminPanel(true)}
              >
                <div className="card-icon dev">
                  <Wrench size={28} />
                </div>
                <div className="card-content">
                  <h3>开发者工具</h3>
                  <p>系统诊断、数据重置与调试选项</p>
                </div>
              </button>

              <button
                type="button"
                className="menu-card danger"
                onClick={handleBackToMenu}
              >
                <div className="card-icon exit">
                  <LogOut size={28} />
                </div>
                <div className="card-content">
                  <h3>返回主菜单</h3>
                  <p>不保存当前进度，直接返回</p>
                </div>
              </button>
            </div>
          )}
        </div>

        {/* 底部操作栏 */}
        {!showLoadPanel && (
          <footer className="game-settings-footer">
            <div className="current-save-info">
              <span className="label">当前存档</span>
              <span className="value">{currentSaveName || "未命名"}</span>
            </div>
            <button
              type="button"
              className="save-exit-btn"
              onClick={handleSaveAndExit}
              disabled={loading}
            >
              <Save size={18} />
              保存并退出
            </button>
          </footer>
        )}
      </div>

      <style>{`
        .game-settings-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 8, 4, 0.75);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 200;
          animation: fadeIn 0.2s ease;
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .game-settings-modal {
          width: min(95vw, 32rem);
          max-height: 85vh;
          background: linear-gradient(165deg, rgba(12, 24, 18, 0.98), rgba(8, 16, 12, 0.99));
          border-radius: 1.25rem;
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

        /* 头部 */
        .game-settings-header {
          padding: 1rem 1.25rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(45, 212, 191, 0.1);
          background: linear-gradient(to bottom, rgba(45, 212, 191, 0.05), transparent);
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .game-settings-header h2 {
          margin: 0;
          font-size: 1.15rem;
          font-weight: 600;
          color: #f0f4e8;
          font-family: var(--font-display);
          letter-spacing: 0.03em;
        }

        .back-btn {
          width: 2rem;
          height: 2rem;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(45, 212, 191, 0.1);
          border: 1px solid rgba(45, 212, 191, 0.2);
          border-radius: 0.5rem;
          color: rgba(240, 244, 232, 0.8);
          cursor: pointer;
          transition: all 0.2s;
        }

        .back-btn:hover {
          background: rgba(45, 212, 191, 0.2);
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

        /* 内容区 */
        .game-settings-body {
          flex: 1;
          padding: 1.25rem;
          overflow-y: auto;
        }

        /* 菜单网格 */
        .menu-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 0.875rem;
        }

        @media (max-width: 480px) {
          .menu-grid {
            grid-template-columns: 1fr;
          }
        }

        .menu-card {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 0.75rem;
          padding: 1rem;
          text-align: left;
          background: rgba(45, 212, 191, 0.03);
          border: 1px solid rgba(45, 212, 191, 0.1);
          border-radius: 0.875rem;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .menu-card:hover:not(:disabled) {
          background: rgba(45, 212, 191, 0.08);
          border-color: rgba(45, 212, 191, 0.25);
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }

        .menu-card.danger:hover:not(:disabled) {
          background: rgba(244, 63, 94, 0.08);
          border-color: rgba(244, 63, 94, 0.25);
        }

        .card-icon {
          width: 3rem;
          height: 3rem;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 0.75rem;
          transition: all 0.2s;
        }

        .card-icon.ai {
          background: linear-gradient(135deg, rgba(45, 212, 191, 0.2), rgba(34, 197, 94, 0.15));
          color: #2dd4bf;
        }

        .card-icon.load {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(99, 102, 241, 0.15));
          color: #60a5fa;
        }

        .card-icon.dev {
          background: linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(251, 146, 60, 0.15));
          color: #fbbf24;
        }

        .card-icon.exit {
          background: linear-gradient(135deg, rgba(244, 63, 94, 0.2), rgba(239, 68, 68, 0.15));
          color: #f87171;
        }

        .card-content h3 {
          margin: 0 0 0.25rem 0;
          font-size: 0.95rem;
          font-weight: 600;
          color: #f0f4e8;
        }

        .card-content p {
          margin: 0;
          font-size: 0.8rem;
          color: rgba(240, 244, 232, 0.55);
          line-height: 1.4;
        }

        /* 存档列表 */
        .saves-container {
          min-height: 12rem;
        }

        .loading-state,
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.75rem;
          padding: 2.5rem 1rem;
          color: rgba(240, 244, 232, 0.5);
          text-align: center;
        }

        .empty-state p {
          margin: 0;
          font-size: 1rem;
          font-weight: 500;
          color: rgba(240, 244, 232, 0.7);
        }

        .empty-state span {
          font-size: 0.85rem;
          color: rgba(240, 244, 232, 0.45);
        }

        .saves-list {
          display: flex;
          flex-direction: column;
          gap: 0.625rem;
        }

        .save-card {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.875rem 1rem;
          background: rgba(45, 212, 191, 0.03);
          border: 1px solid rgba(45, 212, 191, 0.08);
          border-radius: 0.75rem;
          transition: all 0.2s;
          animation: cardSlideIn 0.3s ease both;
        }

        @keyframes cardSlideIn {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        .save-card:hover {
          background: rgba(45, 212, 191, 0.06);
          border-color: rgba(45, 212, 191, 0.15);
        }

        .save-card.current {
          background: rgba(34, 197, 94, 0.08);
          border-color: rgba(34, 197, 94, 0.2);
        }

        .save-info {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .save-name {
          font-size: 0.95rem;
          font-weight: 600;
          color: #f0f4e8;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .current-badge {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.15rem 0.5rem;
          background: rgba(34, 197, 94, 0.2);
          border-radius: 999px;
          font-size: 0.7rem;
          font-weight: 500;
          color: #4ade80;
        }

        .save-meta {
          display: flex;
          gap: 0.875rem;
          font-size: 0.8rem;
          color: rgba(240, 244, 232, 0.6);
        }

        .save-meta span {
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }

        .save-time {
          font-size: 0.75rem;
          color: rgba(240, 244, 232, 0.4);
          font-family: var(--font-mono);
        }

        .load-btn {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.5rem 0.875rem;
          background: linear-gradient(135deg, #2dd4bf, #22c55e);
          border: none;
          border-radius: 0.5rem;
          color: #0a0d08;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }

        .load-btn:hover:not(:disabled) {
          background: linear-gradient(135deg, #14b8a6, #16a34a);
          transform: scale(1.02);
        }

        .load-btn.disabled,
        .load-btn:disabled {
          background: rgba(148, 163, 184, 0.2);
          color: rgba(240, 244, 232, 0.4);
          cursor: not-allowed;
          transform: none;
        }

        /* 底部 */
        .game-settings-footer {
          padding: 1rem 1.25rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-top: 1px solid rgba(45, 212, 191, 0.1);
          background: rgba(0, 0, 0, 0.2);
        }

        .current-save-info {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }

        .current-save-info .label {
          font-size: 0.7rem;
          color: rgba(240, 244, 232, 0.4);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .current-save-info .value {
          font-size: 0.9rem;
          font-weight: 500;
          color: rgba(240, 244, 232, 0.85);
        }

        .save-exit-btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.625rem 1.125rem;
          background: linear-gradient(135deg, #2dd4bf, #22c55e);
          border: none;
          border-radius: 0.625rem;
          color: #0a0d08;
          font-size: 0.9rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
          box-shadow: 0 2px 12px rgba(45, 212, 191, 0.25);
        }

        .save-exit-btn:hover:not(:disabled) {
          background: linear-gradient(135deg, #14b8a6, #16a34a);
          transform: translateY(-1px);
          box-shadow: 0 4px 16px rgba(45, 212, 191, 0.35);
        }

        .save-exit-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }

        .spinner {
          width: 2rem;
          height: 2rem;
          border: 3px solid rgba(45, 212, 191, 0.2);
          border-top-color: #2dd4bf;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

