import { useEffect, useState } from "react";

import type { UIConfig } from "../services/api.types";
import { listSaves, createSave, loadGame, generateSpecies, deleteSave } from "../services/api";

export interface StartPayload {
  mode: "create" | "load";
  scenario: string;
  save_name?: string;
}

interface Props {
  onStart: (payload: StartPayload) => void;
  onOpenSettings: () => void;
  uiConfig?: UIConfig | null;
}

export function MainMenu({ onStart, onOpenSettings, uiConfig }: Props) {
  const [stage, setStage] = useState<"root" | "create" | "load" | "blank">("root");
  const [saves, setSaves] = useState<any[]>([]);
  const [saveName, setSaveName] = useState("");
  const [selectedScenario, setSelectedScenario] = useState("");
  const [speciesPrompts, setSpeciesPrompts] = useState<string[]>(["", "", ""]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (stage === "load") {
      loadSavesList();
    }
  }, [stage]);

  async function loadSavesList() {
    try {
      const data = await listSaves();
      setSaves(data);
    } catch (error: any) {
      console.error("加载存档列表失败:", error);
      setError(error.message);
    }
  }

  async function handleCreateSave(scenario: string) {
    if (scenario === "空白剧本 · 从零塑造") {
      setSelectedScenario("空白剧本");
      setStage("blank");
      return;
    }

    if (!saveName.trim()) {
      setError("请输入存档名称");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await createSave({
        save_name: saveName,
        scenario,
        species_prompts: undefined,
      });
      onStart({ mode: "create", scenario, save_name: saveName });
    } catch (error: any) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateBlankSave() {
    if (!saveName.trim()) {
      setError("请输入存档名称");
      return;
    }

    const validPrompts = speciesPrompts.filter(p => p.trim());
    if (validPrompts.length === 0) {
      setError("请至少输入一个物种描述");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      console.log("[前端] 创建空白剧本存档，物种描述:", validPrompts);
      await createSave({
        save_name: saveName,
        scenario: "空白剧本",
        species_prompts: validPrompts,
      });
      onStart({ mode: "create", scenario: "空白剧本", save_name: saveName });
    } catch (error: any) {
      console.error("[前端] 创建存档失败:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadSave(save_name: string) {
    setLoading(true);
    setError(null);
    try {
      await loadGame(save_name);
      onStart({ mode: "load", scenario: "已保存的游戏", save_name });
    } catch (error: any) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteSave(e: React.MouseEvent, save_name: string) {
    e.stopPropagation();
    if (!window.confirm(`确定要删除存档 "${save_name}" 吗？此操作不可恢复。`)) {
      return;
    }

    setLoading(true);
    try {
      await deleteSave(save_name);
      await loadSavesList();
    } catch (error: any) {
      console.error("删除存档失败:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="main-menu">
      <div className="menu-hero">
        <div className="menu-crest">EVO</div>
        <div>
          <h1>EvoSandbox</h1>
          <p>化身诸神视角，操控压力、塑造生态、见证族群谱系的沉浮。</p>
          <p className="hint">
            当前 AI：
            {uiConfig?.ai_provider ? `${uiConfig.ai_provider} · ${uiConfig.ai_model || "默认模型"}` : "未配置"}
          </p>
        </div>
      </div>
      {error && (
        <div className="error-banner" style={{ position: 'relative', top: 'auto', left: 'auto', transform: 'none', margin: '0 1rem 1rem' }}>
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="btn-icon-sm"
            style={{ background: 'rgba(255,255,255,0.2)' }}
            aria-label="关闭错误提示"
          >
            ×
          </button>
        </div>
      )}
      <div className="menu-shell">
        <aside className="menu-sidebar">
          <button
            className={stage === "create" ? "menu-nav active" : "menu-nav"}
            onClick={() => setStage("create")}
          >
            开始新纪元
          </button>
          <button
            className={stage === "load" ? "menu-nav active" : "menu-nav"}
            onClick={() => setStage("load")}
          >
            读取编年史
          </button>
          <button className="menu-nav" onClick={onOpenSettings}>
            设置与 AI
          </button>
        </aside>
        <section className="menu-panel">
          {stage === "create" && (
            <div className="menu-card">
              <h2>成就新世界</h2>
              <p>选择一份起源设定，稍后可在游戏中继续雕刻细节。</p>
              <div style={{ marginBottom: "16px" }}>
                <label className="text-sm font-medium mb-xs" style={{ display: "block" }}>存档名称：</label>
                <input
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="输入存档名称..."
                  className="field-input"
                  style={{ width: "100%" }}
                />
              </div>
              <div className="menu-options">
                <button
                  className="menu-option"
                  onClick={() => handleCreateSave("原初大陆 · 三族起源")}
                  disabled={loading}
                >
                  原初大陆 · 三族起源
                </button>
                <button
                  className="menu-option"
                  onClick={() => handleCreateSave("空白剧本 · 从零塑造")}
                  disabled={loading}
                >
                  空白剧本 · 从零塑造
                </button>
              </div>
              <p className="hint">原初大陆包含3个默认物种，空白剧本可用AI生成物种。</p>
            </div>
          )}
          {stage === "blank" && (
            <div className="menu-card">
              <h2>空白剧本 - AI 生成物种</h2>
              <p>用自然语言描述你想要的物种，AI会帮你生成符合数据库要求的物种数据。</p>
              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", marginBottom: "8px" }}>存档名称：</label>
                <input
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="输入存档名称..."
                  style={{
                    width: "100%",
                    padding: "8px",
                    borderRadius: "4px",
                    border: "1px solid #444",
                    backgroundColor: "#222",
                    color: "white",
                    marginBottom: "16px",
                  }}
                />
                {[0, 1, 2].map((i) => (
                  <div key={i} style={{ marginBottom: "12px" }}>
                    <label style={{ display: "block", marginBottom: "4px" }}>
                      物种 {i + 1}：
                    </label>
                    <textarea
                      value={speciesPrompts[i]}
                      onChange={(e) => {
                        const newPrompts = [...speciesPrompts];
                        newPrompts[i] = e.target.value;
                        setSpeciesPrompts(newPrompts);
                      }}
                      placeholder="例如：一种生活在深海的发光水母，靠捕食小型浮游生物为生..."
                      rows={3}
                      style={{
                        width: "100%",
                        padding: "8px",
                        borderRadius: "4px",
                        border: "1px solid #444",
                        backgroundColor: "#222",
                        color: "white",
                        fontFamily: "inherit",
                        resize: "vertical",
                      }}
                    />
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: "12px" }}>
                <button
                  className="menu-option"
                  onClick={handleCreateBlankSave}
                  disabled={loading}
                  style={{ flex: 1 }}
                >
                  {loading ? "生成中..." : "创建并生成物种"}
                </button>
                <button
                  className="menu-option"
                  onClick={() => setStage("create")}
                  style={{ flex: 0, minWidth: "100px", backgroundColor: "#666" }}
                >
                  返回
                </button>
              </div>
              <p className="hint">至少输入1个物种描述，最多3个。生成可能需要几秒钟。</p>
            </div>
          )}
          {stage === "load" && (
            <div className="menu-card">
              <h2>编年史</h2>
              {saves.length === 0 ? (
                <p className="hint">还没有存档，请先创建新游戏。</p>
              ) : (
                <ul className="save-list">
                  {saves.map((save) => (
                    <li key={save.save_name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ flex: 1 }}>
                        <strong>{save.save_name}</strong>
                        <span>
                          {save.scenario} · 回合 {save.turn_index} · {save.species_count} 物种
                        </span>
                        <small>{new Date(save.last_saved).toLocaleString("zh-CN")}</small>
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          onClick={() => handleLoadSave(save.save_name)}
                          disabled={loading}
                          className="btn btn-primary btn-sm"
                        >
                          {loading ? "加载..." : "继续"}
                        </button>
                        <button
                          onClick={(e) => handleDeleteSave(e, save.save_name)}
                          disabled={loading}
                          className="btn btn-sm"
                          style={{ backgroundColor: '#d32f2f', color: 'white', border: 'none' }}
                          title="删除存档"
                        >
                          删除
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {stage === "root" && (
            <div className="menu-card">
              <h2>欢迎回来</h2>
              <p>在左侧选择"开始"或"读取"，也可以先配置 AI 服务商与模型。</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
