import { useState } from "react";
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
}

export function GameSettingsMenu({
  currentSaveName,
  onClose,
  onBackToMenu,
  onSaveGame,
  onLoadGame,
  onOpenAISettings,
}: Props) {
  const [saves, setSaves] = useState<SaveMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [showLoadPanel, setShowLoadPanel] = useState(false);
  const [showAdminPanel, setShowAdminPanel] = useState(false);

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
    <div className="fullscreen-overlay" onClick={onClose}>
      <div
        className="fullscreen-panel"
        style={{ maxWidth: "600px" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2>游戏设置</h2>
          <button type="button" className="btn-icon btn-secondary" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="fullscreen-body">
          {showLoadPanel ? (
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">读取存档</h3>
                <button
                  type="button"
                  className="btn-sm btn-secondary"
                  onClick={() => setShowLoadPanel(false)}
                >
                  返回
                </button>
              </div>
              <div className="card-body">
                {saves.length === 0 ? (
                  <p className="placeholder">暂无存档</p>
                ) : (
                  <ul className="save-list">
                    {saves.map((save) => (
                      <li key={save.name}>
                        <div>
                          <strong>{save.name}</strong>
                          {save.name === currentSaveName && (
                            <span style={{ marginLeft: "8px", color: "var(--color-success)" }}>
                              当前
                            </span>
                          )}
                          <br />
                          <small className="muted">
                            回合 {save.turn} · {save.species_count} 个物种 ·{" "}
                            {new Date(save.timestamp * 1000).toLocaleString()}
                          </small>
                        </div>
                        <button
                          type="button"
                          className="btn-sm btn-primary"
                          onClick={() => handleLoadSave(save.name)}
                          disabled={loading || save.name === currentSaveName}
                        >
                          {save.name === currentSaveName ? "已加载" : "读取"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <div className="settings-menu-grid">
              <button
                type="button"
                className="settings-menu-item btn-secondary"
                onClick={onSaveGame}
                disabled={loading}
              >
                <div className="menu-item-icon">💾</div>
                <div className="menu-item-content">
                  <h3>保存游戏</h3>
                  <p>保存当前游戏进度到 {currentSaveName}</p>
                </div>
              </button>

              <button
                type="button"
                className="settings-menu-item btn-secondary"
                onClick={handleLoadClick}
                disabled={loading}
              >
                <div className="menu-item-icon">📂</div>
                <div className="menu-item-content">
                  <h3>读取存档</h3>
                  <p>从已有存档恢复游戏进度</p>
                </div>
              </button>

              <button
                type="button"
                className="settings-menu-item btn-secondary"
                onClick={onOpenAISettings}
              >
                <div className="menu-item-icon">⚙️</div>
                <div className="menu-item-content">
                  <h3>AI设置</h3>
                  <p>配置模型与向量服务</p>
                </div>
              </button>

              <button
                type="button"
                className="settings-menu-item btn-secondary"
                onClick={() => setShowAdminPanel(true)}
              >
                <div className="menu-item-icon">🛠️</div>
                <div className="menu-item-content">
                  <h3>开发者工具</h3>
                  <p>系统诊断与重置</p>
                </div>
              </button>

              <button
                type="button"
                className="settings-menu-item btn-secondary"
                onClick={handleSaveAndExit}
                disabled={loading}
              >
                <div className="menu-item-icon">💾📤</div>
                <div className="menu-item-content">
                  <h3>保存并退出</h3>
                  <p>保存进度后返回主菜单</p>
                </div>
              </button>

              <button
                type="button"
                className="settings-menu-item btn-danger"
                onClick={handleBackToMenu}
              >
                <div className="menu-item-icon">🚪</div>
                <div className="menu-item-content">
                  <h3>返回主菜单</h3>
                  <p>不保存当前进度（谨慎使用）</p>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

