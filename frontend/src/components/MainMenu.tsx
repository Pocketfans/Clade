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
  Clock,
  Users,
  Zap,
  RefreshCw,
  ChevronDown,
  Archive,
  Check,
  FolderOpen,
  PlusCircle
} from "lucide-react";

import type { UIConfig, SaveMetadata } from "@/services/api.types";
import { formatSaveName, formatRelativeTime } from "@/services/api.types";
import { listSaves, createSave, loadGame, deleteSave } from "@/services/api";
import { SpeciesInputCard, type SpeciesInputData } from "./SpeciesInputCard";

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

// 初始化物种输入数据
const createEmptySpeciesData = (): SpeciesInputData => ({ prompt: "" });

export function MainMenu({ onStart, onOpenSettings, uiConfig }: Props) {
  const [stage, setStage] = useState<"root" | "create" | "load" | "blank">("root");
  const [saves, setSaves] = useState<SaveMetadata[]>([]);
  const [saveName, setSaveName] = useState("");
  const [mapSeed, setMapSeed] = useState("");
  const [speciesInputs, setSpeciesInputs] = useState<SpeciesInputData[]>([
    createEmptySpeciesData(),
    createEmptySpeciesData(),
    createEmptySpeciesData(),
  ]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoSaveDrawerOpen, setAutoSaveDrawerOpen] = useState(false);
  
  // 分离手动存档和自动存档
  const manualSaves = saves.filter(s => {
    const name = s.name || s.save_name;
    return !name.toLowerCase().includes('autosave');
  });
  const autoSaves = saves.filter(s => {
    const name = s.name || s.save_name;
    return name.toLowerCase().includes('autosave');
  });

  useEffect(() => {
    if (stage === "load") {
      loadSavesList();
    }
  }, [stage]);

  async function loadSavesList(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    try {
      const data = await listSaves();
      setSaves(data);
    } catch (error: unknown) {
      console.error("加载存档列表失败:", error);
      setError(error instanceof Error ? error.message : "加载失败");
    } finally {
      if (isRefresh) setRefreshing(false);
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
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "操作失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateBlankSave() {
    if (!saveName.trim()) {
      setError("请输入存档名称");
      return;
    }

    // 过滤有效的物种输入
    const validInputs = speciesInputs.filter(input => input.prompt.trim());
    if (validInputs.length === 0) {
      setError("请至少输入一个物种描述");
      return;
    }

    // 构建物种描述（带有元数据提示）
    const speciesPrompts = validInputs.map(input => {
      let prompt = input.prompt;
      const hints: string[] = [];
      
      if (input.habitat_type) {
        const habitatNames: Record<string, string> = {
          marine: "海洋", deep_sea: "深海", coastal: "海岸",
          freshwater: "淡水", terrestrial: "陆地", amphibious: "两栖"
        };
        hints.push(`栖息地：${habitatNames[input.habitat_type] || input.habitat_type}`);
      }
      
      if (input.diet_type) {
        const dietNames: Record<string, string> = {
          autotroph: "自养生物", herbivore: "草食动物", 
          carnivore: "肉食动物", omnivore: "杂食动物"
        };
        hints.push(`食性：${dietNames[input.diet_type] || input.diet_type}`);
      }
      
      if (input.is_plant && input.plant_stage !== undefined) {
        const stageNames: Record<number, string> = {
          0: "原核光合生物", 1: "单细胞真核藻类", 
          2: "多细胞群体藻类", 3: "苔藓类"
        };
        hints.push(`植物阶段：${stageNames[input.plant_stage] || `阶段${input.plant_stage}`}`);
      }
      
      if (hints.length > 0) {
        prompt += `\n[预设: ${hints.join(', ')}]`;
      }
      
      return prompt;
    });

    setLoading(true);
    setError(null);
    try {
      await createSave({
        save_name: saveName,
        scenario: "空白剧本",
        species_prompts: speciesPrompts,
        map_seed: mapSeed.trim() ? parseInt(mapSeed) : undefined,
      });
      onStart({ mode: "create", scenario: "空白剧本", save_name: saveName });
    } catch (error: unknown) {
      console.error("[前端] 创建存档失败:", error);
      setError(error instanceof Error ? error.message : "创建失败");
    } finally {
      setLoading(false);
    }
  }
  
  // 更新物种输入数据
  const updateSpeciesInput = (index: number, data: SpeciesInputData) => {
    setSpeciesInputs(prev => {
      const newInputs = [...prev];
      newInputs[index] = data;
      return newInputs;
    });
  };
  
  // 添加新的物种槽位
  const addSpeciesSlot = () => {
    if (speciesInputs.length < 5) {
      setSpeciesInputs(prev => [...prev, createEmptySpeciesData()]);
    }
  };
  
  // 移除物种槽位
  const removeSpeciesSlot = (index: number) => {
    if (index > 0 && speciesInputs.length > 1) {
      setSpeciesInputs(prev => prev.filter((_, i) => i !== index));
    }
  };

  async function handleLoadSave(save_name: string) {
    setLoading(true);
    setError(null);
    try {
      await loadGame(save_name);
      onStart({ mode: "load", scenario: "已保存的游戏", save_name });
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "操作失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteSave(e: React.MouseEvent, save_name: string) {
    e.stopPropagation();
    const { displayName } = formatSaveName(save_name);
    if (!window.confirm(`确定要删除存档「${displayName}」吗？\n\n此操作无法撤销！`)) {
      return;
    }

    setLoading(true);
    try {
      await deleteSave(save_name);
      await loadSavesList();
    } catch (error: unknown) {
      console.error("删除存档失败:", error);
      setError(error instanceof Error ? error.message : "删除失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="main-menu">
      {/* 演化主题动态背景 */}
      <div className="animated-bg">
        {/* 细胞粒子 */}
        {Array.from({ length: 25 }).map((_, i) => (
          <div 
            key={`cell-${i}`} 
            className="bg-particle" 
            style={{
              left: `${Math.random() * 100}%`,
              width: `${Math.random() * 8 + 4}px`,
              height: `${Math.random() * 8 + 4}px`,
              animationDuration: `${Math.random() * 15 + 12}s`,
              animationDelay: `${Math.random() * 8}s`
            }}
          />
        ))}
        {/* 分裂粒子 */}
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={`mitosis-${i}`}
            className="mitosis-particle"
            style={{
              left: `${10 + Math.random() * 80}%`,
              top: `${10 + Math.random() * 80}%`,
              width: `${Math.random() * 40 + 20}px`,
              height: `${Math.random() * 40 + 20}px`,
              animationDelay: `${i * 1.5}s`,
              animationDuration: `${6 + Math.random() * 4}s`
            }}
          />
        ))}
        {/* 神经连接线 */}
        <div className="neural-connections">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={`neural-${i}`}
              className="neural-line"
              style={{
                top: `${15 + i * 10}%`,
                left: `${Math.random() * 30}%`,
                width: `${40 + Math.random() * 40}%`,
                animationDelay: `${i * 0.5}s`,
                transform: `rotate(${-10 + Math.random() * 20}deg)`
              }}
            />
          ))}
        </div>
        {/* 演化树背景 */}
        <div className="evolution-tree-bg" />
      </div>

      <div className="menu-hero fade-in">
        <div className="menu-crest" style={{ 
          background: 'linear-gradient(135deg, rgba(45, 212, 191, 0.2), rgba(34, 197, 94, 0.15))', 
          border: '2px solid rgba(45, 212, 191, 0.3)',
          boxShadow: '0 0 30px rgba(45, 212, 191, 0.15), inset 0 0 20px rgba(45, 212, 191, 0.1)'
        }}>
          <span style={{ 
            background: 'linear-gradient(135deg, #2dd4bf, #22c55e)', 
            WebkitBackgroundClip: 'text', 
            WebkitTextFillColor: 'transparent',
            fontWeight: 700
          }}>EVO</span>
        </div>
        <div>
          <h1 style={{ 
            fontSize: '2.5rem', 
            marginBottom: '0.5rem',
            background: 'linear-gradient(135deg, #f0f4e8 0%, #2dd4bf 50%, #22c55e 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            textShadow: '0 0 40px rgba(45, 212, 191, 0.3)'
          }}>Clade</h1>
          <p style={{ fontSize: '1.1rem', opacity: 0.8, color: 'rgba(240, 244, 232, 0.85)' }}>
            化身诸神视角，操控压力、塑造生态、见证族群谱系的沉浮。
          </p>
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
              {(() => {
                // 优先检查新配置格式
                if (uiConfig?.default_provider_id && uiConfig?.providers?.[uiConfig.default_provider_id]) {
                  const provider = uiConfig.providers[uiConfig.default_provider_id];
                  return `${provider.name} · ${uiConfig.default_model || "默认"}`;
                }
                // 回退到旧配置格式
                if (uiConfig?.ai_provider) {
                  return `${uiConfig.ai_provider} · ${uiConfig.ai_model || "默认"}`;
                }
                return "未配置";
              })()}
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

              {/* 物种输入卡片 */}
              <div className="species-inputs-section mb-xl">
                <div className="section-header mb-md">
                  <span className="section-title">初始物种设计</span>
                  <span className="section-hint">点击模板快速填充，或自由描述你的物种</span>
                </div>
                
                <div className="species-cards-list">
                  {speciesInputs.map((input, index) => (
                    <SpeciesInputCard
                      key={index}
                      index={index}
                      required={index === 0}
                      value={input}
                      onChange={(data) => updateSpeciesInput(index, data)}
                      onRemove={index > 0 ? () => removeSpeciesSlot(index) : undefined}
                    />
                  ))}
                </div>
                
                {speciesInputs.length < 5 && (
                  <button 
                    className="add-species-btn"
                    onClick={addSpeciesSlot}
                  >
                    <PlusCircle size={16} />
                    <span>添加更多物种</span>
                  </button>
                )}
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
              
              <style>{`
                .species-inputs-section {
                  display: flex;
                  flex-direction: column;
                  gap: 12px;
                }
                
                .section-header {
                  display: flex;
                  flex-direction: column;
                  gap: 4px;
                }
                
                .section-title {
                  font-size: 0.95rem;
                  font-weight: 500;
                  color: rgba(255, 255, 255, 0.9);
                }
                
                .section-hint {
                  font-size: 0.8rem;
                  color: rgba(255, 255, 255, 0.5);
                }
                
                .species-cards-list {
                  display: flex;
                  flex-direction: column;
                  gap: 12px;
                }
                
                .add-species-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  gap: 8px;
                  padding: 12px;
                  background: rgba(255, 255, 255, 0.03);
                  border: 2px dashed rgba(255, 255, 255, 0.15);
                  border-radius: 12px;
                  color: rgba(255, 255, 255, 0.5);
                  font-size: 0.9rem;
                  cursor: pointer;
                  transition: all 0.2s;
                  margin-top: 8px;
                }
                
                .add-species-btn:hover {
                  background: rgba(168, 85, 247, 0.1);
                  border-color: rgba(168, 85, 247, 0.3);
                  color: rgba(255, 255, 255, 0.8);
                }
              `}</style>
            </div>
          )}

          {/* 读取存档 */}
          {stage === "load" && (
            <div className="glass-card fade-in">
              <div className="saves-header-row">
                <h2 className="text-xl font-display">编年史记录</h2>
                <div className="saves-header-right">
                  <span className="saves-count-badge">
                    {manualSaves.length} 个存档
                    {autoSaves.length > 0 && <span className="count-auto"> + {autoSaves.length} 自动</span>}
                  </span>
                  <button 
                    className="refresh-icon-btn"
                    onClick={() => loadSavesList(true)}
                    disabled={refreshing}
                    title="刷新列表"
                  >
                    <RefreshCw size={14} className={refreshing ? 'spinning' : ''} />
                  </button>
                </div>
              </div>
              
              {saves.length === 0 ? (
                <div className="empty-saves-state">
                  <BookOpen size={48} strokeWidth={1.5} />
                  <p>暂无历史记录</p>
                  <span>开创新纪元后，您的存档将显示在这里</span>
                </div>
              ) : (
                <div className="saves-sections-wrapper">
                  {/* 手动存档列表 */}
                  {manualSaves.length > 0 && (
                    <div className="saves-grid">
                      {manualSaves.map((save, idx) => {
                        const rawName = save.name || save.save_name;
                        const { displayName } = formatSaveName(rawName);
                        const scenario = save.scenario || '未知剧本';
                        const relativeTime = save.last_saved ? formatRelativeTime(save.last_saved) : 
                          (save.timestamp ? formatRelativeTime(new Date(save.timestamp * 1000).toISOString()) : '未知');
                        const turnNum = (save.turn ?? save.turn_index ?? 0) + 1;
                        
                        return (
                          <div 
                            key={rawName} 
                            className="save-item"
                            style={{ animationDelay: `${idx * 0.04}s` }}
                          >
                            <div className="save-item-main">
                              <div className="save-item-title">
                                <span className="save-item-name">{displayName}</span>
                              </div>
                              
                              <div className="save-item-scenario">
                                <Globe size={11} />
                                <span>{scenario}</span>
                              </div>
                              
                              <div className="save-item-stats">
                                <span className="stat">
                                  <Clock size={11} />
                                  <strong>T{turnNum}</strong>
                                </span>
                                <span className="stat-sep">·</span>
                                <span className="stat">
                                  <Users size={11} />
                                  <strong>{save.species_count}</strong> 物种
                                </span>
                                <span className="stat-sep">·</span>
                                <span className="stat time">{relativeTime}</span>
                              </div>
                            </div>
                            
                            <div className="save-item-actions">
                              <button
                                onClick={() => handleLoadSave(rawName)}
                                disabled={loading}
                                className="save-action-btn primary"
                                title="读取存档"
                              >
                                <Play size={15} />
                              </button>
                              <button
                                onClick={(e) => handleDeleteSave(e, rawName)}
                                disabled={loading}
                                className="save-action-btn danger"
                                title="删除存档"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  
                  {/* 手动存档为空时的提示 */}
                  {manualSaves.length === 0 && autoSaves.length > 0 && (
                    <div className="no-manual-saves-hint">
                      <FolderOpen size={24} strokeWidth={1.5} />
                      <span>暂无手动存档</span>
                    </div>
                  )}
                  
                  {/* 自动存档抽屉 */}
                  {autoSaves.length > 0 && (
                    <div className="autosave-drawer-wrapper">
                      <button
                        type="button"
                        className={`autosave-drawer-toggle ${autoSaveDrawerOpen ? 'open' : ''}`}
                        onClick={() => setAutoSaveDrawerOpen(!autoSaveDrawerOpen)}
                      >
                        <div className="drawer-left">
                          <Archive size={14} />
                          <span>自动存档</span>
                          <span className="drawer-badge">{autoSaves.length}</span>
                        </div>
                        <ChevronDown size={16} className={`drawer-arrow ${autoSaveDrawerOpen ? 'open' : ''}`} />
                      </button>
                      
                      {autoSaveDrawerOpen && (
                        <div className="autosave-drawer-content">
                          {autoSaves.map((save, idx) => {
                            const rawName = save.name || save.save_name;
                            const { displayName } = formatSaveName(rawName);
                            const relativeTime = save.last_saved ? formatRelativeTime(save.last_saved) : 
                              (save.timestamp ? formatRelativeTime(new Date(save.timestamp * 1000).toISOString()) : '未知');
                            const turnNum = (save.turn ?? save.turn_index ?? 0) + 1;
                            
                            return (
                              <div 
                                key={rawName} 
                                className="autosave-item"
                                style={{ animationDelay: `${idx * 0.03}s` }}
                              >
                                <div className="autosave-item-main">
                                  <div className="autosave-item-title">
                                    <Zap size={11} className="zap-icon" />
                                    <span>{displayName}</span>
                                  </div>
                                  
                                  <div className="autosave-item-meta">
                                    <span><strong>T{turnNum}</strong></span>
                                    <span className="sep">·</span>
                                    <span><strong>{save.species_count}</strong> 物种</span>
                                    <span className="sep">·</span>
                                    <span className="time">{relativeTime}</span>
                                  </div>
                                </div>
                                
                                <div className="autosave-item-actions">
                                  <button
                                    onClick={() => handleLoadSave(rawName)}
                                    disabled={loading}
                                    className="save-action-btn primary small"
                                    title="读取存档"
                                  >
                                    <Play size={13} />
                                  </button>
                                  <button
                                    onClick={(e) => handleDeleteSave(e, rawName)}
                                    disabled={loading}
                                    className="save-action-btn danger small"
                                    title="删除存档"
                                  >
                                    <Trash2 size={11} />
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </section>
      </div>
    </div>
  );
}
