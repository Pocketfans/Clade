import { useEffect, useState } from "react";
import { 
  Play, 
  BookOpen, 
  Settings, 
  Plus, 
  Globe, 
  Cpu, 
  ArrowLeft, 
  Trash2, 
  Save,
  Clock
} from "lucide-react";

import type { UIConfig } from "../services/api.types";
import { listSaves, createSave, loadGame, deleteSave } from "../services/api";

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
  const [mapSeed, setMapSeed] = useState("");
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
        map_seed: mapSeed.trim() ? parseInt(mapSeed) : undefined,
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
      await createSave({
        save_name: saveName,
        scenario: "空白剧本",
        species_prompts: validPrompts,
        map_seed: mapSeed.trim() ? parseInt(mapSeed) : undefined,
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
      {/* 动态背景粒子 */}
      <div className="animated-bg">
        {Array.from({ length: 20 }).map((_, i) => (
          <div 
            key={i} 
            className="bg-particle" 
            style={{
              left: `${Math.random() * 100}%`,
              width: `${Math.random() * 4 + 1}px`,
              height: `${Math.random() * 4 + 1}px`,
              animationDuration: `${Math.random() * 10 + 10}s`,
              animationDelay: `${Math.random() * 5}s`
            }}
          />
        ))}
      </div>

      <div className="menu-hero fade-in">
        <div className="menu-crest" style={{ background: 'rgba(255,255,255,0.1)', border: 'none' }}>EVO</div>
        <div>
          <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>EvoSandbox</h1>
          <p style={{ fontSize: '1.1rem', opacity: 0.8 }}>化身诸神视角，操控压力、塑造生态、见证族群谱系的沉浮。</p>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="btn-icon-sm">×</button>
        </div>
      )}

      <div className="menu-shell fade-in" style={{ animationDelay: '0.1s', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
        
        {/* 侧边导航 */}
        <aside className="menu-sidebar" style={{ minWidth: '240px' }}>
          <button
            className={`menu-nav ${stage === "root" || stage === "create" || stage === "blank" ? "active" : ""}`}
            onClick={() => setStage("root")}
          >
            <Play size={18} style={{ marginRight: 8 }} /> 开始新纪元
          </button>
          <button
            className={`menu-nav ${stage === "load" ? "active" : ""}`}
            onClick={() => setStage("load")}
          >
            <BookOpen size={18} style={{ marginRight: 8 }} /> 读取编年史
          </button>
          <button className="menu-nav" onClick={onOpenSettings}>
            <Settings size={18} style={{ marginRight: 8 }} /> 设置与 AI
          </button>
          
          <div style={{ marginTop: 'auto', padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '12px' }}>
            <p className="hint" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Cpu size={14} />
              AI 引擎状态
            </p>
            <p style={{ fontSize: '0.85rem', margin: '0.5rem 0 0', opacity: 0.9 }}>
              {uiConfig?.ai_provider ? `${uiConfig.ai_provider} · ${uiConfig.ai_model || "默认"}` : "未配置"}
            </p>
          </div>
        </aside>

        {/* 主内容区 */}
        <section style={{ flex: 1 }}>
          
          {/* 首页：选择模式 */}
          {stage === "root" && (
            <div className="grid grid-cols-1 gap-6 fade-in">
              <div 
                className="menu-visual-card"
                onClick={() => setStage("create")}
              >
                <div className="menu-icon-wrapper">
                  <Globe />
                </div>
                <div>
                  <h3 className="menu-card-title">原初大陆 · 三族起源</h3>
                  <p className="menu-card-desc">经典开局。从三个基础物种开始，观察它们如何在标准环境中竞争与演化。</p>
                </div>
              </div>

              <div 
                className="menu-visual-card"
                onClick={() => setStage("blank")}
              >
                <div className="menu-icon-wrapper" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>
                  <Plus />
                </div>
                <div>
                  <h3 className="menu-card-title">空白剧本 · 从零塑造</h3>
                  <p className="menu-card-desc">完全自由。使用自然语言描述你想要的初始物种，由 AI 为你生成独一无二的开局。</p>
                </div>
              </div>
            </div>
          )}

          {/* 创建普通存档 */}
          {stage === "create" && (
            <div className="glass-card fade-in">
              <div className="flex justify-between items-center mb-lg">
                <h2 className="text-xl font-display">新纪元配置</h2>
                <button className="btn btn-ghost btn-sm" onClick={() => setStage("root")}>
                  <ArrowLeft size={16} style={{ marginRight: 4 }} /> 返回
                </button>
              </div>
              
              <div className="form-field mb-xl">
                <label className="field-label mb-xs">存档名称</label>
                <input
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="为这个新世界命名..."
                  className="input-visual"
                  autoFocus
                />
              </div>

              <div className="form-field mb-xl">
                <label className="field-label mb-xs">
                  地图种子
                  <span className="text-xs text-muted ml-2">(选填，留空则随机生成)</span>
                </label>
                <input
                  type="text"
                  value={mapSeed}
                  onChange={(e) => setMapSeed(e.target.value.replace(/\D/g, ''))}
                  placeholder="例如: 12345 (仅数字)"
                  className="input-visual"
                />
                <p className="text-xs text-muted mt-1">使用相同种子可以重现相同的地图形状</p>
              </div>

              <div className="p-lg rounded-lg bg-white/5 mb-xl border border-white/10">
                <h4 className="font-medium mb-sm text-info">剧本：原初大陆</h4>
                <p className="text-sm text-muted">包含生产者、食草动物和食肉动物的基本生态平衡。</p>
              </div>

              <button
                className="btn btn-primary btn-lg w-full justify-center"
                onClick={() => handleCreateSave("原初大陆 · 三族起源")}
                disabled={loading}
                style={{ width: '100%' }}
              >
                {loading ? <span className="spinner mr-sm"/> : <Play size={20} className="mr-sm" />}
                {loading ? "正在创世纪..." : "启动模拟"}
              </button>
            </div>
          )}

          {/* 空白剧本创建 */}
          {stage === "blank" && (
            <div className="glass-card fade-in">
              <div className="flex justify-between items-center mb-lg">
                <h2 className="text-xl font-display">智能物种生成</h2>
                <button className="btn btn-ghost btn-sm" onClick={() => setStage("root")}>
                  <ArrowLeft size={16} style={{ marginRight: 4 }} /> 返回
                </button>
              </div>

              <div className="form-field mb-xl">
                <label className="field-label mb-xs">存档名称</label>
                <input
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="为这个新世界命名..."
                  className="input-visual"
                />
              </div>

              <div className="form-field mb-xl">
                <label className="field-label mb-xs">
                  地图种子
                  <span className="text-xs text-muted ml-2">(选填，留空则随机生成)</span>
                </label>
                <input
                  type="text"
                  value={mapSeed}
                  onChange={(e) => setMapSeed(e.target.value.replace(/\D/g, ''))}
                  placeholder="例如: 12345 (仅数字)"
                  className="input-visual"
                />
                <p className="text-xs text-muted mt-1">使用相同种子可以重现相同的地图形状</p>
              </div>

              <div className="space-y-4 mb-xl">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="form-field fade-in" style={{ animationDelay: `${i * 0.1}s` }}>
                    <label className="field-label mb-xs flex justify-between">
                      <span>初始物种 {i + 1}</span>
                      <span className="text-xs text-muted">{i === 0 ? "必填" : "选填"}</span>
                    </label>
                    <textarea
                      value={speciesPrompts[i]}
                      onChange={(e) => {
                        const newPrompts = [...speciesPrompts];
                        newPrompts[i] = e.target.value;
                        setSpeciesPrompts(newPrompts);
                      }}
                      placeholder={i === 0 ? "例如：一种生活在深海的发光水母，靠捕食小型浮游生物为生..." : "描述另一个物种..."}
                      rows={2}
                      className="input-visual resize-y"
                    />
                  </div>
                ))}
              </div>

              <button
                className="btn btn-success btn-lg w-full justify-center"
                onClick={handleCreateBlankSave}
                disabled={loading}
                style={{ width: '100%' }}
              >
                {loading ? <span className="spinner mr-sm"/> : <Cpu size={20} className="mr-sm" />}
                {loading ? "AI 正在构思物种..." : "生成并开始"}
              </button>
            </div>
          )}

          {/* 读取存档 */}
          {stage === "load" && (
            <div className="glass-card fade-in">
              <h2 className="text-xl font-display mb-lg">编年史记录</h2>
              {saves.length === 0 ? (
                <div className="text-center p-xl text-muted border border-dashed border-white/20 rounded-lg">
                  <BookOpen size={48} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                  <p>暂无历史记录，请先开创新纪元。</p>
                </div>
              ) : (
                <div className="flex flex-col gap-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                  {saves.map((save, idx) => (
                    <div 
                      key={save.save_name} 
                      className="p-md rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 transition-all flex justify-between items-center list-item"
                      style={{ animationDelay: `${idx * 0.05}s` }}
                    >
                      <div>
                        <h4 className="font-medium text-lg mb-1">{save.save_name}</h4>
                        <div className="flex gap-4 text-sm text-muted">
                          <span className="flex items-center gap-1"><Globe size={12}/> {save.scenario}</span>
                          <span className="flex items-center gap-1"><Clock size={12}/> 回合 {save.turn_index}</span>
                          <span>{save.species_count} 物种</span>
                        </div>
                        <div className="text-xs text-muted mt-1 opacity-60">
                          {new Date(save.last_saved).toLocaleString("zh-CN")}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleLoadSave(save.save_name)}
                          disabled={loading}
                          className="btn btn-primary btn-sm"
                          title="读取存档"
                        >
                          <Play size={16} />
                        </button>
                        <button
                          onClick={(e) => handleDeleteSave(e, save.save_name)}
                          disabled={loading}
                          className="btn btn-danger btn-sm"
                          title="删除存档"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        </section>
      </div>
    </div>
  );
}
