import { useEffect, useState, useMemo } from "react";
import { 
  Play, 
  BookOpen, 
  Settings, 
  Plus, 
  Globe, 
  Cpu, 
  ArrowLeft, 
  Trash2, 
  Clock,
  Users,
  Zap,
  RefreshCw,
  ChevronDown,
  Archive,
  FolderOpen,
  PlusCircle,
  Sparkles,
  Dna,
  Leaf,
  GitBranch,
  ChevronRight,
  Check,
  Star,
  Info,
  ExternalLink,
  TreeDeciduous,
} from "lucide-react";

import type { UIConfig, SaveMetadata } from "@/services/api.types";
import { formatSaveName, formatRelativeTime } from "@/services/api.types";
import { listSaves, createSave, loadGame, deleteSave } from "@/services/api";
import { SpeciesInputCard, type SpeciesInputData } from "./SpeciesInputCard";
import "./MainMenu.css";

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

// 特色功能提示
const FEATURES = [
  { icon: <Dna size={14} />, text: "AI驱动的物种进化" },
  { icon: <GitBranch size={14} />, text: "分支谱系追踪" },
  { icon: <Leaf size={14} />, text: "生态系统模拟" },
];

export function MainMenu({ onStart, onOpenSettings, uiConfig }: Props) {
  const [stage, setStage] = useState<"root" | "create" | "load" | "blank" | "thriving">("root");
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

  // AI 状态信息
  const aiStatus = useMemo(() => {
    if (uiConfig?.default_provider_id && uiConfig?.providers?.[uiConfig.default_provider_id]) {
      const provider = uiConfig.providers[uiConfig.default_provider_id];
      return {
        configured: true,
        provider: provider.name,
        model: uiConfig.default_model || "默认模型",
      };
    }
    if (uiConfig?.ai_provider) {
      return {
        configured: true,
        provider: uiConfig.ai_provider,
        model: uiConfig.ai_model || "默认模型",
      };
    }
    return { configured: false, provider: "", model: "" };
  }, [uiConfig]);

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

    const validInputs = speciesInputs.filter(input => input.prompt.trim());
    if (validInputs.length === 0) {
      setError("请至少输入一个物种描述");
      return;
    }

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
  
  const updateSpeciesInput = (index: number, data: SpeciesInputData) => {
    setSpeciesInputs(prev => {
      const newInputs = [...prev];
      newInputs[index] = data;
      return newInputs;
    });
  };
  
  const addSpeciesSlot = () => {
    if (speciesInputs.length < 5) {
      setSpeciesInputs(prev => [...prev, createEmptySpeciesData()]);
    }
  };
  
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
    <div className="mm-container">
      {/* 动态背景 */}
      <div className="mm-bg">
        <div className="mm-bg-gradient" />
        <div className="mm-bg-grid" />
        {/* 浮动粒子 */}
        {Array.from({ length: 20 }).map((_, i) => (
          <div key={i} className="mm-particle" style={{
            left: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 10}s`,
            animationDuration: `${15 + Math.random() * 10}s`,
          }} />
        ))}
        {/* DNA螺旋装饰 */}
        <div className="mm-dna-decoration">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="mm-dna-dot" style={{
              top: `${i * 8}%`,
              animationDelay: `${i * 0.2}s`,
            }} />
          ))}
        </div>
      </div>

      {/* 主内容 */}
      <div className="mm-content">
        {/* Hero区域 */}
        <header className="mm-hero">
          <div className="mm-logo">
            <div className="mm-logo-ring">
              <div className="mm-logo-inner">
                <Sparkles className="mm-logo-icon" />
              </div>
            </div>
            <div className="mm-logo-glow" />
          </div>
          <div className="mm-hero-text">
            <h1 className="mm-title">
              <span className="mm-title-main">Clade</span>
              <span className="mm-title-badge">BETA</span>
            </h1>
            <p className="mm-subtitle">化身诸神视角，操控压力、塑造生态、见证族群谱系的沉浮</p>
            <div className="mm-features">
              {FEATURES.map((f, i) => (
                <span key={i} className="mm-feature" style={{ animationDelay: `${0.5 + i * 0.1}s` }}>
                  {f.icon}
                  <span>{f.text}</span>
                </span>
              ))}
            </div>
          </div>
        </header>

        {/* 错误提示 */}
        {error && (
          <div className="mm-error">
            <Info size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* 主面板 */}
        <div className="mm-main">
          {/* 侧边栏 */}
          <nav className="mm-sidebar">
            <button
              className={`mm-nav-btn ${stage === "root" || stage === "create" || stage === "blank" ? "active" : ""}`}
              onClick={() => setStage("root")}
            >
              <span className="mm-nav-icon"><Play size={18} /></span>
              <span className="mm-nav-text">开始新纪元</span>
              <ChevronRight size={14} className="mm-nav-arrow" />
            </button>
            <button
              className={`mm-nav-btn ${stage === "load" ? "active" : ""}`}
              onClick={() => setStage("load")}
            >
              <span className="mm-nav-icon"><BookOpen size={18} /></span>
              <span className="mm-nav-text">读取编年史</span>
              <ChevronRight size={14} className="mm-nav-arrow" />
            </button>
            <button className="mm-nav-btn" onClick={onOpenSettings}>
              <span className="mm-nav-icon"><Settings size={18} /></span>
              <span className="mm-nav-text">设置与 AI</span>
              <ChevronRight size={14} className="mm-nav-arrow" />
            </button>

            {/* AI状态卡片 */}
            <div className="mm-ai-card">
              <div className="mm-ai-header">
                <Cpu size={14} />
                <span>AI 引擎</span>
                <span className={`mm-ai-status ${aiStatus.configured ? "online" : "offline"}`}>
                  {aiStatus.configured ? "在线" : "离线"}
                </span>
              </div>
              {aiStatus.configured ? (
                <div className="mm-ai-info">
                  <div className="mm-ai-provider">{aiStatus.provider}</div>
                  <div className="mm-ai-model">{aiStatus.model}</div>
                </div>
              ) : (
                <div className="mm-ai-warning">
                  <span>请先配置 AI 服务</span>
                  <button onClick={onOpenSettings}>前往设置</button>
                </div>
              )}
            </div>

            {/* 版本信息 */}
            <div className="mm-version">
              <span>v0.9.0</span>
              <a href="https://github.com" target="_blank" rel="noopener noreferrer">
                <ExternalLink size={12} />
              </a>
            </div>
          </nav>

          {/* 内容区域 */}
          <section className="mm-panel">
            
            {/* 首页：选择模式 */}
            {stage === "root" && (
              <div className="mm-cards">
                <div className="mm-card" onClick={() => setStage("create")}>
                  <div className="mm-card-bg" />
                  <div className="mm-card-content">
                    <div className="mm-card-icon">
                      <Globe size={28} />
                    </div>
                    <div className="mm-card-text">
                      <h3>原初大陆 · 三族起源</h3>
                      <p>经典开局。从三个基础物种开始，观察它们如何在标准环境中竞争与演化。</p>
                    </div>
                    <div className="mm-card-tag">推荐</div>
                  </div>
                  <div className="mm-card-shine" />
                </div>

                <div className="mm-card thriving" onClick={() => setStage("thriving")}>
                  <div className="mm-card-bg" />
                  <div className="mm-card-content">
                    <div className="mm-card-icon thriving">
                      <TreeDeciduous size={28} />
                    </div>
                    <div className="mm-card-text">
                      <h3>繁荣生态 · 万物竞生</h3>
                      <p>成熟生态系统。15个物种覆盖海陆深海，含顶级掠食者与共生关系，体验复杂食物网。</p>
                    </div>
                    <div className="mm-card-tag thriving">高级</div>
                  </div>
                  <div className="mm-card-shine" />
                </div>

                <div className="mm-card variant" onClick={() => setStage("blank")}>
                  <div className="mm-card-bg" />
                  <div className="mm-card-content">
                    <div className="mm-card-icon variant">
                      <Plus size={28} />
                    </div>
                    <div className="mm-card-text">
                      <h3>空白剧本 · 从零塑造</h3>
                      <p>完全自由。使用自然语言描述你想要的初始物种，由 AI 为你生成独一无二的开局。</p>
                    </div>
                    <div className="mm-card-tag ai">AI 驱动</div>
                  </div>
                  <div className="mm-card-shine" />
                </div>
              </div>
            )}

            {/* 创建普通存档 */}
            {stage === "create" && (
              <div className="mm-form">
                <div className="mm-form-header">
                  <h2>新纪元配置</h2>
                  <button className="mm-back-btn" onClick={() => setStage("root")}>
                    <ArrowLeft size={16} />
                    <span>返回</span>
                  </button>
                </div>
                
                <div className="mm-form-body">
                  <div className="mm-field">
                    <label>存档名称</label>
                    <input
                      type="text"
                      value={saveName}
                      onChange={(e) => setSaveName(e.target.value)}
                      placeholder="为这个新世界命名..."
                      autoFocus
                    />
                  </div>

                  <div className="mm-field">
                    <label>
                      地图种子
                      <span className="mm-field-hint">选填，留空则随机生成</span>
                    </label>
                    <input
                      type="text"
                      value={mapSeed}
                      onChange={(e) => setMapSeed(e.target.value.replace(/\D/g, ''))}
                      placeholder="例如: 12345"
                    />
                  </div>

                  <div className="mm-scenario-preview">
                    <div className="mm-scenario-icon"><Globe size={20} /></div>
                    <div className="mm-scenario-info">
                      <span className="mm-scenario-title">剧本：原初大陆</span>
                      <span className="mm-scenario-desc">包含初级生产者、和初级消费者的基本生态平衡</span>
                    </div>
                  </div>
                </div>

                <button
                  className="mm-submit-btn"
                  onClick={() => handleCreateSave("原初大陆 · 三族起源")}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="mm-spinner" />
                      <span>正在创世纪...</span>
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      <span>启动模拟</span>
                    </>
                  )}
                </button>
              </div>
            )}

            {/* 繁荣生态剧本创建 */}
            {stage === "thriving" && (
              <div className="mm-form">
                <div className="mm-form-header">
                  <h2>繁荣生态配置</h2>
                  <button className="mm-back-btn" onClick={() => setStage("root")}>
                    <ArrowLeft size={16} />
                    <span>返回</span>
                  </button>
                </div>
                
                <div className="mm-form-body">
                  <div className="mm-field">
                    <label>存档名称</label>
                    <input
                      type="text"
                      value={saveName}
                      onChange={(e) => setSaveName(e.target.value)}
                      placeholder="为这个繁荣世界命名..."
                      autoFocus
                    />
                  </div>

                  <div className="mm-field">
                    <label>
                      地图种子
                      <span className="mm-field-hint">选填，留空则随机生成</span>
                    </label>
                    <input
                      type="text"
                      value={mapSeed}
                      onChange={(e) => setMapSeed(e.target.value.replace(/\D/g, ''))}
                      placeholder="例如: 12345"
                    />
                  </div>

                  <div className="mm-scenario-preview thriving">
                    <div className="mm-scenario-icon"><TreeDeciduous size={20} /></div>
                    <div className="mm-scenario-info">
                      <span className="mm-scenario-title">剧本：繁荣生态</span>
                      <span className="mm-scenario-desc">
                        15个物种的成熟生态系统，包括：
                        <br />• 4种生产者（海洋藻类、陆地苔藓、淡水蓝藻、深海热泉菌）
                        <br />• 4种初级消费者（纤毛虫、腹足类、水蚤、节肢动物）
                        <br />• 3种次级消费者（水母、鹦鹉螺、两栖蠕虫）
                        <br />• 2种顶级掠食者（奇虾、巨型蜈蚣）
                        <br />• 2种特殊生态位（分解细菌、深海管虫）
                      </span>
                    </div>
                  </div>
                </div>

                <button
                  className="mm-submit-btn thriving"
                  onClick={() => handleCreateSave("繁荣生态")}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="mm-spinner" />
                      <span>正在构建生态...</span>
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      <span>启动模拟</span>
                    </>
                  )}
                </button>
              </div>
            )}

            {/* 空白剧本创建 */}
            {stage === "blank" && (
              <div className="mm-form">
                <div className="mm-form-header">
                  <h2>智能物种生成</h2>
                  <button className="mm-back-btn" onClick={() => setStage("root")}>
                    <ArrowLeft size={16} />
                    <span>返回</span>
                  </button>
                </div>

                <div className="mm-form-body">
                  <div className="mm-field">
                    <label>存档名称</label>
                    <input
                      type="text"
                      value={saveName}
                      onChange={(e) => setSaveName(e.target.value)}
                      placeholder="为这个新世界命名..."
                    />
                  </div>

                  <div className="mm-field">
                    <label>
                      地图种子
                      <span className="mm-field-hint">选填</span>
                    </label>
                    <input
                      type="text"
                      value={mapSeed}
                      onChange={(e) => setMapSeed(e.target.value.replace(/\D/g, ''))}
                      placeholder="例如: 12345"
                    />
                  </div>

                  <div className="mm-species-section">
                    <div className="mm-species-header">
                      <span className="mm-species-title">初始物种设计</span>
                      <span className="mm-species-hint">点击模板快速填充，或自由描述</span>
                    </div>
                    
                    <div className="mm-species-list">
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
                      <button className="mm-add-species" onClick={addSpeciesSlot}>
                        <PlusCircle size={16} />
                        <span>添加更多物种</span>
                      </button>
                    )}
                  </div>
                </div>

                <button
                  className="mm-submit-btn success"
                  onClick={handleCreateBlankSave}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="mm-spinner" />
                      <span>AI 正在构思物种...</span>
                    </>
                  ) : (
                    <>
                      <Cpu size={18} />
                      <span>生成并开始</span>
                    </>
                  )}
                </button>
              </div>
            )}

            {/* 读取存档 */}
            {stage === "load" && (
              <div className="mm-saves">
                <div className="mm-saves-header">
                  <h2>编年史记录</h2>
                  <div className="mm-saves-actions">
                    <span className="mm-saves-count">
                      {manualSaves.length} 个存档
                      {autoSaves.length > 0 && <span className="mm-saves-auto">+{autoSaves.length}</span>}
                    </span>
                    <button 
                      className="mm-refresh-btn"
                      onClick={() => loadSavesList(true)}
                      disabled={refreshing}
                    >
                      <RefreshCw size={14} className={refreshing ? "spinning" : ""} />
                    </button>
                  </div>
                </div>
                
                {saves.length === 0 ? (
                  <div className="mm-saves-empty">
                    <div className="mm-empty-icon">
                      <BookOpen size={48} strokeWidth={1} />
                    </div>
                    <h3>暂无历史记录</h3>
                    <p>开创新纪元后，您的存档将显示在这里</p>
                  </div>
                ) : (
                  <div className="mm-saves-content">
                    {/* 手动存档 */}
                    {manualSaves.length > 0 && (
                      <div className="mm-saves-list">
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
                              className="mm-save-item"
                              style={{ animationDelay: `${idx * 0.05}s` }}
                              onClick={() => handleLoadSave(rawName)}
                            >
                              <div className="mm-save-icon">
                                <Globe size={18} />
                              </div>
                              <div className="mm-save-info">
                                <span className="mm-save-name">{displayName}</span>
                                <div className="mm-save-meta">
                                  <span><Clock size={11} /> T{turnNum}</span>
                                  <span><Users size={11} /> {save.species_count} 物种</span>
                                  <span className="mm-save-time">{relativeTime}</span>
                                </div>
                                <span className="mm-save-scenario">{scenario}</span>
                              </div>
                              <div className="mm-save-actions" onClick={e => e.stopPropagation()}>
                                <button
                                  className="mm-save-play"
                                  onClick={() => handleLoadSave(rawName)}
                                  disabled={loading}
                                >
                                  <Play size={14} />
                                </button>
                                <button
                                  className="mm-save-delete"
                                  onClick={(e) => handleDeleteSave(e, rawName)}
                                  disabled={loading}
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    
                    {/* 无手动存档提示 */}
                    {manualSaves.length === 0 && autoSaves.length > 0 && (
                      <div className="mm-no-manual">
                        <FolderOpen size={20} />
                        <span>暂无手动存档</span>
                      </div>
                    )}
                    
                    {/* 自动存档折叠区 */}
                    {autoSaves.length > 0 && (
                      <div className="mm-autosave-section">
                        <button
                          className={`mm-autosave-toggle ${autoSaveDrawerOpen ? "open" : ""}`}
                          onClick={() => setAutoSaveDrawerOpen(!autoSaveDrawerOpen)}
                        >
                          <Archive size={14} />
                          <span>自动存档</span>
                          <span className="mm-autosave-badge">{autoSaves.length}</span>
                          <ChevronDown size={14} className={`mm-toggle-arrow ${autoSaveDrawerOpen ? "open" : ""}`} />
                        </button>
                        
                        {autoSaveDrawerOpen && (
                          <div className="mm-autosave-list">
                            {autoSaves.map((save, idx) => {
                              const rawName = save.name || save.save_name;
                              const { displayName } = formatSaveName(rawName);
                              const relativeTime = save.last_saved ? formatRelativeTime(save.last_saved) : 
                                (save.timestamp ? formatRelativeTime(new Date(save.timestamp * 1000).toISOString()) : '未知');
                              const turnNum = (save.turn ?? save.turn_index ?? 0) + 1;
                              
                              return (
                                <div 
                                  key={rawName} 
                                  className="mm-autosave-item"
                                  style={{ animationDelay: `${idx * 0.03}s` }}
                                  onClick={() => handleLoadSave(rawName)}
                                >
                                  <div className="mm-autosave-info">
                                    <div className="mm-autosave-name">
                                      <Zap size={11} />
                                      <span>{displayName}</span>
                                    </div>
                                    <div className="mm-autosave-meta">
                                      <span>T{turnNum}</span>
                                      <span>{save.species_count} 物种</span>
                                      <span>{relativeTime}</span>
                                    </div>
                                  </div>
                                  <div className="mm-autosave-actions" onClick={e => e.stopPropagation()}>
                                    <button onClick={() => handleLoadSave(rawName)} disabled={loading}>
                                      <Play size={12} />
                                    </button>
                                    <button onClick={(e) => handleDeleteSave(e, rawName)} disabled={loading}>
                                      <Trash2 size={10} />
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
    </div>
  );
}
