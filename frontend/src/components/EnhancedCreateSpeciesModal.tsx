/**
 * EnhancedCreateSpeciesModal - 增强版创建物种面板
 * 
 * 完整集成：
 * - 丰富的物种模板（含植物演化阶段）
 * - 栖息地类型选择
 * - 食性类型选择
 * - 猎物选择器（可从现有物种中选择）
 * - 父代物种选择（神启分化模式）
 * - 与族谱系统集成
 */
import { useEffect, useState, useMemo } from "react";
import { 
  Sparkles, Dna, Leaf, Bug, Bird, Fish, Zap, RefreshCw, 
  AlertCircle, ChevronRight, ChevronDown, Mountain, Waves,
  Sun, Droplets, TreeDeciduous, Shrub, GitBranch, Crown,
  Search, X, Check, Info, Target, Link, PlusCircle
} from "lucide-react";
import { AnalysisPanel, ActionButton } from "./common/AnalysisPanel";
import { fetchSpeciesList, generateSpeciesAdvanced, fetchFoodWeb } from "../services/api";
import type { SpeciesListItem, FoodWebData, FoodWebNode } from "../services/api.types";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

// ========== 栖息地类型 ==========
const HABITAT_TYPES = [
  { id: "marine", name: "海洋", icon: <Waves size={18} />, color: "#0ea5e9", desc: "浅海、中层海域" },
  { id: "deep_sea", name: "深海", icon: <Waves size={18} />, color: "#1e40af", desc: "深海平原、热液喷口" },
  { id: "coastal", name: "海岸", icon: <Waves size={18} />, color: "#06b6d4", desc: "潮间带、滨海区" },
  { id: "freshwater", name: "淡水", icon: <Droplets size={18} />, color: "#22d3ee", desc: "湖泊、河流" },
  { id: "amphibious", name: "两栖", icon: <Droplets size={18} />, color: "#14b8a6", desc: "水陆两栖" },
  { id: "terrestrial", name: "陆生", icon: <Mountain size={18} />, color: "#84cc16", desc: "陆地环境" },
  { id: "aerial", name: "空中", icon: <Bird size={18} />, color: "#a855f7", desc: "飞行生物" },
];

// ========== 食性类型 ==========
const DIET_TYPES = [
  { id: "autotroph", name: "自养", icon: <Sun size={18} />, color: "#22c55e", desc: "光合/化能合成", trophicHint: "T1.0-1.5" },
  { id: "herbivore", name: "草食", icon: <Leaf size={18} />, color: "#84cc16", desc: "以植物为食", trophicHint: "T2.0-2.5" },
  { id: "carnivore", name: "肉食", icon: <Bird size={18} />, color: "#ef4444", desc: "以动物为食", trophicHint: "T3.0+" },
  { id: "omnivore", name: "杂食", icon: <Bug size={18} />, color: "#f59e0b", desc: "植物和动物", trophicHint: "T2.5-3.5" },
  { id: "detritivore", name: "腐食", icon: <Shrub size={18} />, color: "#78716c", desc: "有机碎屑", trophicHint: "T1.5" },
];

// ========== 植物演化阶段 ==========
const PLANT_STAGES = [
  { stage: 0, name: "原核光合", icon: "🦠", desc: "蓝藻、光合细菌", form: "aquatic" },
  { stage: 1, name: "单细胞真核", icon: "🔬", desc: "绿藻、硅藻", form: "aquatic" },
  { stage: 2, name: "群体藻类", icon: "🌿", desc: "多细胞藻类", form: "aquatic" },
  { stage: 3, name: "苔藓", icon: "🌱", desc: "首批登陆植物", form: "moss" },
  { stage: 4, name: "蕨类", icon: "🌿", desc: "维管植物先驱", form: "herb" },
  { stage: 5, name: "裸子植物", icon: "🌲", desc: "种子植物", form: "shrub" },
  { stage: 6, name: "被子植物", icon: "🌸", desc: "开花植物", form: "tree" },
];

// ========== 物种模板预设 ==========
const SPECIES_TEMPLATES = [
  // 生产者模板
  { 
    id: "algae",
    category: "producer",
    icon: <Leaf size={20} />,
    name: "浮游藻类",
    color: "#22c55e",
    habitat: "marine",
    diet: "autotroph",
    isPlant: true,
    plantStage: 1,
    prompt: "一种微小的浮游藻类，能够进行光合作用。漂浮在海洋表层，是海洋生态系统的基础生产者..."
  },
  { 
    id: "bacteria",
    category: "producer",
    icon: <Sun size={20} />,
    name: "化能细菌",
    color: "#f59e0b",
    habitat: "deep_sea",
    diet: "autotroph",
    isPlant: true,
    plantStage: 0,
    prompt: "一种生活在深海热泉附近的化能合成细菌，不依赖阳光，通过氧化硫化物获取能量..."
  },
  { 
    id: "moss",
    category: "producer",
    icon: <TreeDeciduous size={20} />,
    name: "苔藓植物",
    color: "#16a34a",
    habitat: "terrestrial",
    diet: "autotroph",
    isPlant: true,
    plantStage: 3,
    prompt: "一种低矮的苔藓植物，贴附在潮湿的岩石表面生长。没有真正的根系，通过假根固定在基质上..."
  },
  // 草食者模板
  { 
    id: "filter_feeder",
    category: "herbivore",
    icon: <Bug size={20} />,
    name: "滤食动物",
    color: "#3b82f6",
    habitat: "marine",
    diet: "herbivore",
    prompt: "一种小型滤食性动物，靠过滤海水中的浮游藻类和有机颗粒为生。身体透明，适应漂浮生活..."
  },
  { 
    id: "grazer",
    category: "herbivore",
    icon: <Bug size={20} />,
    name: "陆地食草者",
    color: "#84cc16",
    habitat: "terrestrial",
    diet: "herbivore",
    prompt: "一种以植物为食的陆生动物，拥有适合咀嚼植物纤维的口器或牙齿..."
  },
  // 肉食者模板
  { 
    id: "predator",
    category: "carnivore",
    icon: <Bird size={20} />,
    name: "小型捕食者",
    color: "#ef4444",
    habitat: "marine",
    diet: "carnivore",
    prompt: "一种敏捷的捕食者，以小型浮游动物为食。具有敏锐的感觉器官和快速的反应能力..."
  },
  { 
    id: "apex",
    category: "carnivore",
    icon: <Crown size={20} />,
    name: "顶级掠食者",
    color: "#dc2626",
    habitat: "terrestrial",
    diet: "carnivore",
    prompt: "一种强大的顶级捕食者，处于食物链顶端。拥有锋利的捕猎器官和高效的追踪能力..."
  },
  // 杂食者模板
  { 
    id: "opportunist",
    category: "omnivore",
    icon: <Fish size={20} />,
    name: "机会主义者",
    color: "#f59e0b",
    habitat: "coastal",
    diet: "omnivore",
    prompt: "一种适应性强的杂食动物，既能捕食小型动物，也能摄取植物和有机碎屑..."
  },
  // 腐食者模板
  { 
    id: "decomposer",
    category: "decomposer",
    icon: <Shrub size={20} />,
    name: "分解者",
    color: "#78716c",
    habitat: "terrestrial",
    diet: "detritivore",
    prompt: "一种以死亡有机物为食的分解者，在生态系统中扮演物质循环的重要角色..."
  },
];

// 模板类别
const TEMPLATE_CATEGORIES = [
  { id: "producer", name: "生产者", color: "#22c55e" },
  { id: "herbivore", name: "草食者", color: "#3b82f6" },
  { id: "carnivore", name: "肉食者", color: "#ef4444" },
  { id: "omnivore", name: "杂食者", color: "#f59e0b" },
  { id: "decomposer", name: "分解者", color: "#78716c" },
];

// ========== 创建模式 ==========
type CreateMode = "freeform" | "divine";

export function EnhancedCreateSpeciesModal({ onClose, onSuccess }: Props) {
  // 基础状态
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedCode, setSuggestedCode] = useState<string>("");
  const [charCount, setCharCount] = useState(0);
  
  // 创建模式
  const [createMode, setCreateMode] = useState<CreateMode>("freeform");
  
  // 高级选项
  const [showTemplates, setShowTemplates] = useState(true);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [selectedHabitat, setSelectedHabitat] = useState<string | null>(null);
  const [selectedDiet, setSelectedDiet] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [isPlant, setIsPlant] = useState(false);
  const [plantStage, setPlantStage] = useState<number | null>(null);
  
  // 猎物选择
  const [selectedPrey, setSelectedPrey] = useState<string[]>([]);
  const [preySearch, setPreySearch] = useState("");
  
  // 父代选择（神启分化模式）
  const [parentCode, setParentCode] = useState<string | null>(null);
  const [showParentSelector, setShowParentSelector] = useState(false);
  const [parentSearch, setParentSearch] = useState("");
  
  // 物种列表
  const [speciesList, setSpeciesList] = useState<SpeciesListItem[]>([]);
  const [foodWebData, setFoodWebData] = useState<FoodWebData | null>(null);
  const [loadingSpecies, setLoadingSpecies] = useState(true);

  // 加载物种数据
  useEffect(() => {
    async function loadData() {
      setLoadingSpecies(true);
      try {
        const [list, foodWeb] = await Promise.all([
          fetchSpeciesList(),
          fetchFoodWeb().catch(() => null)
        ]);
        setSpeciesList(list);
        setFoodWebData(foodWeb);
        
        // 计算下一个可用的 Lineage Code
        const usedCodes = new Set(list.map((s) => s.lineage_code));
        let bestPrefix = "S";
        let index = 1;
        while (usedCodes.has(`${bestPrefix}${index}`)) {
          index++;
        }
        setSuggestedCode(`${bestPrefix}${index}`);
      } catch (err) {
        console.error("加载物种数据失败:", err);
      } finally {
        setLoadingSpecies(false);
      }
    }
    loadData();
  }, []);

  useEffect(() => {
    setCharCount(prompt.length);
  }, [prompt]);

  // 过滤可选猎物（根据食性）
  const availablePrey = useMemo(() => {
    if (!foodWebData) return [];
    
    return foodWebData.nodes.filter(node => {
      // 自养生物不需要猎物
      if (selectedDiet === "autotroph") return false;
      // 草食者只能选营养级<2的
      if (selectedDiet === "herbivore") return node.trophic_level < 2.0;
      // 肉食者选营养级较低的动物
      if (selectedDiet === "carnivore") return node.trophic_level >= 1.5 && node.trophic_level < 4.0;
      // 杂食者范围更广
      if (selectedDiet === "omnivore") return node.trophic_level < 4.0;
      // 腐食者不需要特定猎物
      if (selectedDiet === "detritivore") return false;
      return true;
    });
  }, [foodWebData, selectedDiet]);

  // 过滤搜索结果
  const filteredPrey = useMemo(() => {
    if (!preySearch.trim()) return availablePrey;
    const search = preySearch.toLowerCase();
    return availablePrey.filter(
      n => n.name.toLowerCase().includes(search) || n.id.toLowerCase().includes(search)
    );
  }, [availablePrey, preySearch]);

  const filteredParents = useMemo(() => {
    const aliveSpecies = speciesList.filter(s => s.status === "alive");
    if (!parentSearch.trim()) return aliveSpecies;
    const search = parentSearch.toLowerCase();
    return aliveSpecies.filter(
      s => s.common_name.toLowerCase().includes(search) || 
           s.lineage_code.toLowerCase().includes(search) ||
           s.latin_name.toLowerCase().includes(search)
    );
  }, [speciesList, parentSearch]);

  // 选择模板
  const handleTemplateSelect = (template: typeof SPECIES_TEMPLATES[0]) => {
    setSelectedTemplate(template.id);
    setPrompt(template.prompt);
    setSelectedHabitat(template.habitat);
    setSelectedDiet(template.diet);
    setIsPlant(template.isPlant || false);
    setPlantStage(template.plantStage ?? null);
    setSelectedPrey([]);
  };

  // 随机模板
  const handleRandomize = () => {
    const randomTemplate = SPECIES_TEMPLATES[Math.floor(Math.random() * SPECIES_TEMPLATES.length)];
    handleTemplateSelect(randomTemplate);
  };

  // 切换猎物选择
  const togglePreySelection = (preyId: string) => {
    setSelectedPrey(prev => 
      prev.includes(preyId) 
        ? prev.filter(p => p !== preyId)
        : [...prev, preyId]
    );
  };

  // 创建物种
  async function handleCreate() {
    if (!prompt.trim()) {
      setError("请输入物种描述");
      return;
    }
    if (!suggestedCode) {
      setError("正在计算编号，请稍候...");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await generateSpeciesAdvanced({
        prompt,
        lineage_code: suggestedCode,
        habitat_type: selectedHabitat || undefined,
        diet_type: selectedDiet || undefined,
        prey_species: selectedPrey.length > 0 ? selectedPrey : undefined,
        parent_code: parentCode || undefined,
        is_plant: isPlant,
        plant_stage: plantStage ?? undefined,
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error(err);
      setError(err.message || "生成失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  // 获取选中父代的信息
  const selectedParent = useMemo(() => {
    if (!parentCode) return null;
    return speciesList.find(s => s.lineage_code === parentCode);
  }, [parentCode, speciesList]);

  return (
    <AnalysisPanel
      title={createMode === "divine" ? "神启分化" : "创造新物种"}
      icon={createMode === "divine" ? <GitBranch size={20} /> : <Sparkles size={20} />}
      accentColor={createMode === "divine" ? "#f59e0b" : "#a855f7"}
      onClose={onClose}
      size="large"
      footer={
        <>
          <ActionButton variant="ghost" onClick={onClose} disabled={loading}>
            取消
          </ActionButton>
          <ActionButton 
            variant="success" 
            icon={<Zap size={18} />}
            onClick={handleCreate} 
            loading={loading}
            disabled={!prompt.trim()}
          >
            {loading ? "创造中..." : "确认创造"}
          </ActionButton>
        </>
      }
    >
      <div className="enhanced-create-content">
        {/* 创建模式切换 */}
        <div className="mode-switcher">
          <button 
            className={`mode-btn ${createMode === 'freeform' ? 'active' : ''}`}
            onClick={() => { setCreateMode('freeform'); setParentCode(null); }}
          >
            <Sparkles size={16} />
            <span>自由创造</span>
            <small>全新物种</small>
          </button>
          <button 
            className={`mode-btn ${createMode === 'divine' ? 'active' : ''}`}
            onClick={() => setCreateMode('divine')}
          >
            <GitBranch size={16} />
            <span>神启分化</span>
            <small>从已有物种衍生</small>
          </button>
        </div>

        {/* 神启分化模式：选择父代 */}
        {createMode === "divine" && (
          <div className="parent-selector-section">
            <div className="section-header">
              <Link size={16} />
              <span>选择父代物种</span>
            </div>
            
            {selectedParent ? (
              <div className="selected-parent-card">
                <div className="parent-info">
                  <span className="parent-code">{selectedParent.lineage_code}</span>
                  <span className="parent-name">{selectedParent.common_name}</span>
                  <span className="parent-latin">{selectedParent.latin_name}</span>
                </div>
                <button 
                  className="change-parent-btn"
                  onClick={() => setShowParentSelector(true)}
                >
                  更换
                </button>
              </div>
            ) : (
              <button 
                className="select-parent-btn"
                onClick={() => setShowParentSelector(true)}
              >
                <PlusCircle size={18} />
                <span>选择一个父代物种</span>
              </button>
            )}

            {/* 父代选择弹窗 */}
            {showParentSelector && (
              <div className="selector-dropdown parent-dropdown">
                <div className="selector-header">
                  <div className="search-box">
                    <Search size={16} />
                    <input
                      type="text"
                      placeholder="搜索物种..."
                      value={parentSearch}
                      onChange={e => setParentSearch(e.target.value)}
                      autoFocus
                    />
                    {parentSearch && (
                      <button onClick={() => setParentSearch("")}><X size={14} /></button>
                    )}
                  </div>
                  <button className="close-selector" onClick={() => setShowParentSelector(false)}>
                    <X size={18} />
                  </button>
                </div>
                <div className="selector-list">
                  {loadingSpecies ? (
                    <div className="selector-loading">加载中...</div>
                  ) : filteredParents.length === 0 ? (
                    <div className="selector-empty">没有找到物种</div>
                  ) : (
                    filteredParents.map(sp => (
                      <button
                        key={sp.lineage_code}
                        className={`selector-item ${parentCode === sp.lineage_code ? 'selected' : ''}`}
                        onClick={() => {
                          setParentCode(sp.lineage_code);
                          setShowParentSelector(false);
                        }}
                      >
                        <span className="item-code">{sp.lineage_code}</span>
                        <span className="item-name">{sp.common_name}</span>
                        <span className="item-latin">{sp.latin_name}</span>
                        {parentCode === sp.lineage_code && <Check size={16} />}
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 物种编号预览 */}
        <div className="species-code-preview">
          <div className="code-label">
            <Dna size={16} />
            <span>物种编号</span>
          </div>
          <div className="code-value">
            {suggestedCode || <span className="loading-text">计算中...</span>}
          </div>
          {createMode === "divine" && parentCode && (
            <div className="lineage-hint">
              将作为 <strong>{parentCode}</strong> 的子代
            </div>
          )}
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="error-message">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* 物种描述输入 - 放在最前面 */}
        <div className="form-section">
          <div className="form-section-header">
            <Dna size={16} />
            <span>物种描述</span>
            <span className="required-tag">必填</span>
          </div>
          <div className="prompt-input-wrapper">
            <textarea
              className="prompt-textarea"
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述你想创造的物种...&#10;&#10;例如：一种体型巨大的陆行鸟类，拥有厚重的骨质装甲以防御捕食者。"
            />
            <div className="prompt-footer">
              <span className={`char-count ${charCount > 500 ? 'warning' : ''}`}>
                {charCount} / 500 字符
              </span>
            </div>
          </div>
        </div>

        {/* 快速模板选择 - 可折叠 */}
        <div className="form-section collapsible">
          <button 
            className="form-section-header clickable"
            onClick={() => setShowTemplates(prev => !prev)}
          >
            <Sparkles size={16} />
            <span>快速模板</span>
            <span className="optional-tag">可选</span>
            <span className="toggle-icon">{showTemplates ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
          </button>
          
          {showTemplates && (
            <div className="form-section-content">
              <div className="template-grid-compact">
                {SPECIES_TEMPLATES.map(template => (
                  <button
                    key={template.id}
                    className={`template-chip ${selectedTemplate === template.id ? 'selected' : ''}`}
                    style={{ '--template-color': template.color } as React.CSSProperties}
                    onClick={() => handleTemplateSelect(template)}
                  >
                    <span className="template-icon">{template.icon}</span>
                    <span className="template-name">{template.name}</span>
                  </button>
                ))}
                <button className="template-chip randomize" onClick={handleRandomize}>
                  <RefreshCw size={14} />
                  <span>随机</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 高级选项 - 独立可折叠区块 */}
        <div className="form-section collapsible">
          <button 
            className="form-section-header clickable"
            onClick={() => setShowAdvancedOptions(prev => !prev)}
          >
            <Target size={16} />
            <span>高级选项</span>
            <span className="optional-tag">可选</span>
            <span className="toggle-icon">{showAdvancedOptions ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
          </button>

          {showAdvancedOptions && (
            <div className="form-section-content advanced-grid">
              {/* 栖息地选择 */}
              <div className="option-group">
                <label>
                  <Mountain size={14} />
                  <span>栖息地</span>
                </label>
                <div className="option-chips-row">
                  {HABITAT_TYPES.map(habitat => (
                    <button
                      key={habitat.id}
                      className={`option-chip-sm ${selectedHabitat === habitat.id ? 'selected' : ''}`}
                      style={{ '--chip-color': habitat.color } as React.CSSProperties}
                      onClick={() => setSelectedHabitat(
                        selectedHabitat === habitat.id ? null : habitat.id
                      )}
                      title={habitat.desc}
                    >
                      {habitat.icon}
                      <span>{habitat.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 食性选择 */}
              <div className="option-group">
                <label>
                  <Target size={14} />
                  <span>食性</span>
                </label>
                <div className="option-chips-row">
                  {DIET_TYPES.map(diet => (
                    <button
                      key={diet.id}
                      className={`option-chip-sm ${selectedDiet === diet.id ? 'selected' : ''}`}
                      style={{ '--chip-color': diet.color } as React.CSSProperties}
                      onClick={() => {
                        setSelectedDiet(selectedDiet === diet.id ? null : diet.id);
                        setSelectedPrey([]);
                        setIsPlant(diet.id === "autotroph");
                      }}
                      title={`${diet.desc} (${diet.trophicHint})`}
                    >
                      {diet.icon}
                      <span>{diet.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 植物演化阶段（仅生产者） */}
              {isPlant && (
                <div className="option-group full-width">
                  <label>
                    <TreeDeciduous size={14} />
                    <span>植物阶段</span>
                  </label>
                  <div className="plant-stages-row">
                    {PLANT_STAGES.slice(0, 4).map(stage => (
                      <button
                        key={stage.stage}
                        className={`plant-stage-chip ${plantStage === stage.stage ? 'selected' : ''}`}
                        onClick={() => setPlantStage(
                          plantStage === stage.stage ? null : stage.stage
                        )}
                      >
                        <span>{stage.icon}</span>
                        <span>{stage.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 信息提示 */}
        <div className="create-info-banner">
          <Info size={18} />
          <div className="info-text">
            <strong>
              {createMode === "divine" 
                ? "神启分化 - 从已有物种衍生" 
                : "AI 驱动的物种创造"}
            </strong>
            <p>
              {createMode === "divine"
                ? "新物种将继承父代的部分特征，同时根据你的描述产生变异。适合模拟定向演化。"
                : "AI 将根据你的描述生成物种的外观、行为、生态位等详细属性，并将其投放到当前生态系统中。"}
            </p>
          </div>
        </div>
      </div>

      <style>{`
        .enhanced-create-content {
          padding: 16px 20px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-height: 65vh;
          overflow-y: auto;
          overflow-x: hidden;
        }

        /* 表单区块 */
        .form-section {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          overflow: hidden;
        }

        .form-section-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          font-size: 0.85rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.8);
        }

        .form-section-header.clickable {
          cursor: pointer;
          width: 100%;
          border: none;
          text-align: left;
          transition: all 0.15s;
        }

        .form-section-header.clickable:hover {
          background: rgba(255, 255, 255, 0.05);
        }

        .form-section-header svg {
          color: #a855f7;
          flex-shrink: 0;
        }

        .required-tag {
          margin-left: auto;
          padding: 2px 6px;
          background: rgba(239, 68, 68, 0.15);
          border-radius: 4px;
          font-size: 0.7rem;
          color: #fca5a5;
        }

        .optional-tag {
          margin-left: auto;
          padding: 2px 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 4px;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .toggle-icon {
          margin-left: 8px;
          color: rgba(255, 255, 255, 0.4);
        }

        .form-section-content {
          padding: 12px 14px;
        }

        /* 模式切换 */
        .mode-switcher {
          display: flex;
          gap: 8px;
          padding: 3px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 10px;
        }

        .mode-btn {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2px;
          padding: 10px 8px;
          background: transparent;
          border: 1px solid transparent;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.2s;
        }

        .mode-btn span {
          font-weight: 600;
          font-size: 0.85rem;
        }

        .mode-btn small {
          font-size: 0.7rem;
          opacity: 0.7;
        }

        .mode-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }

        .mode-btn.active {
          background: rgba(168, 85, 247, 0.15);
          border-color: rgba(168, 85, 247, 0.4);
          color: #e9d5ff;
        }

        .mode-btn.active:nth-child(2) {
          background: rgba(245, 158, 11, 0.15);
          border-color: rgba(245, 158, 11, 0.4);
          color: #fef3c7;
        }

        /* 父代选择器 */
        .parent-selector-section {
          padding: 16px;
          background: rgba(245, 158, 11, 0.08);
          border: 1px solid rgba(245, 158, 11, 0.2);
          border-radius: 12px;
        }

        .section-header {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #fcd34d;
          font-weight: 500;
          margin-bottom: 12px;
        }

        .selected-parent-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 10px;
        }

        .parent-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .parent-code {
          padding: 4px 10px;
          background: rgba(245, 158, 11, 0.2);
          border-radius: 6px;
          font-family: var(--font-mono);
          font-weight: 600;
          color: #fcd34d;
        }

        .parent-name {
          font-weight: 500;
          color: #fff;
        }

        .parent-latin {
          font-style: italic;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.85rem;
        }

        .change-parent-btn {
          padding: 6px 14px;
          background: rgba(255, 255, 255, 0.1);
          border: none;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.7);
          cursor: pointer;
          font-size: 0.85rem;
        }

        .change-parent-btn:hover {
          background: rgba(255, 255, 255, 0.15);
          color: #fff;
        }

        .select-parent-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          width: 100%;
          padding: 16px;
          background: rgba(0, 0, 0, 0.2);
          border: 2px dashed rgba(245, 158, 11, 0.3);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.2s;
        }

        .select-parent-btn:hover {
          background: rgba(245, 158, 11, 0.1);
          border-color: rgba(245, 158, 11, 0.5);
          color: #fcd34d;
        }

        /* 选择器下拉框 */
        .selector-dropdown {
          margin-top: 12px;
          background: rgba(0, 0, 0, 0.9);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 12px;
          overflow: hidden;
          max-height: 280px;
        }

        .selector-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .search-box {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 10px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 8px;
        }

        .search-box input {
          flex: 1;
          background: none;
          border: none;
          color: #fff;
          font-size: 0.9rem;
          outline: none;
        }

        .search-box input::placeholder {
          color: rgba(255, 255, 255, 0.4);
        }

        .search-box button {
          background: none;
          border: none;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          padding: 2px;
        }

        .close-selector {
          background: none;
          border: none;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          padding: 4px;
        }

        .selector-list {
          max-height: 220px;
          overflow-y: auto;
        }

        .selector-item {
          display: flex;
          align-items: center;
          gap: 10px;
          width: 100%;
          padding: 10px 14px;
          background: none;
          border: none;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          color: #fff;
          cursor: pointer;
          text-align: left;
          transition: all 0.15s;
        }

        .selector-item:hover {
          background: rgba(255, 255, 255, 0.08);
        }

        .selector-item.selected {
          background: rgba(168, 85, 247, 0.15);
        }

        .item-code {
          padding: 2px 8px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          font-family: var(--font-mono);
          font-size: 0.8rem;
        }

        .item-name {
          flex: 1;
          font-weight: 500;
        }

        .item-latin {
          font-style: italic;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.8rem;
        }

        .item-trophic {
          font-size: 0.75rem;
          padding: 2px 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 4px;
          color: rgba(255, 255, 255, 0.6);
        }

        .selector-empty, .selector-loading {
          padding: 24px;
          text-align: center;
          color: rgba(255, 255, 255, 0.4);
        }

        /* 物种编号预览 */
        .species-code-preview {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 20px;
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(168, 85, 247, 0.03) 100%);
          border: 1px solid rgba(168, 85, 247, 0.2);
          border-radius: 14px;
          text-align: center;
        }

        .code-label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          margin-bottom: 8px;
        }

        .code-label svg {
          color: #a855f7;
        }

        .code-value {
          font-family: var(--font-display, 'Cinzel', serif);
          font-size: 2rem;
          font-weight: 700;
          color: #a855f7;
          text-shadow: 0 0 30px rgba(168, 85, 247, 0.5);
          letter-spacing: 0.1em;
        }

        .loading-text {
          font-size: 1rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: var(--font-body);
        }

        .lineage-hint {
          margin-top: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .lineage-hint strong {
          color: #fcd34d;
        }

        /* 错误消息 */
        .error-message {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.25);
          border-radius: 10px;
          color: #fca5a5;
          font-size: 0.9rem;
        }

        .error-message svg {
          flex-shrink: 0;
          color: #ef4444;
        }

        .error-message span {
          flex: 1;
        }

        .error-message button {
          background: none;
          border: none;
          color: inherit;
          font-size: 1.3rem;
          cursor: pointer;
          opacity: 0.7;
          padding: 0 4px;
        }

        /* 紧凑模板网格 - 使用CSS Grid确保均匀分布 */
        .template-grid-compact {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
          gap: 8px;
        }

        .template-chip {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 8px 12px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.15s;
          color: rgba(255, 255, 255, 0.7);
          font-size: 0.8rem;
          white-space: nowrap;
        }

        .template-chip:hover {
          background: color-mix(in srgb, var(--template-color, #a855f7) 15%, transparent);
          border-color: var(--template-color, rgba(255, 255, 255, 0.2));
          color: #fff;
        }

        .template-chip.selected {
          background: color-mix(in srgb, var(--template-color) 20%, transparent);
          border-color: var(--template-color);
          color: #fff;
        }

        .template-chip .template-icon {
          color: var(--template-color, rgba(255, 255, 255, 0.7));
        }

        .template-chip.selected .template-icon {
          color: #fff;
        }

        .template-chip.randomize {
          --template-color: #f59e0b;
          border-style: dashed;
        }

        /* 描述输入 */
        .prompt-input-wrapper {
          padding: 12px 14px;
        }

        .prompt-textarea {
          width: 100%;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: #f1f5f9;
          font-size: 0.88rem;
          line-height: 1.5;
          resize: none;
          min-height: 80px;
          font-family: inherit;
          transition: all 0.2s;
        }

        .prompt-textarea:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
        }

        .prompt-textarea::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .prompt-footer {
          display: flex;
          justify-content: flex-end;
          margin-top: 6px;
        }

        .char-count {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: var(--font-mono, monospace);
        }

        .char-count.warning {
          color: #f59e0b;
        }

        /* 高级选项网格 */
        .advanced-grid {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .option-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .option-group.full-width {
          grid-column: 1 / -1;
        }

        .option-group > label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.8rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.6);
        }

        .option-group > label svg {
          color: rgba(255, 255, 255, 0.4);
        }

        .option-chips-row {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
          gap: 6px;
        }

        .option-chip-sm {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
          padding: 8px 10px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.15s;
          font-size: 0.78rem;
          white-space: nowrap;
        }

        .option-chip-sm svg {
          width: 14px;
          height: 14px;
          flex-shrink: 0;
        }

        .option-chip-sm:hover {
          background: color-mix(in srgb, var(--chip-color, #888) 15%, transparent);
          border-color: var(--chip-color, rgba(255, 255, 255, 0.2));
          color: rgba(255, 255, 255, 0.9);
        }

        .option-chip-sm.selected {
          background: color-mix(in srgb, var(--chip-color) 20%, transparent);
          border-color: var(--chip-color);
          color: #fff;
        }

        /* 植物阶段选择 - 紧凑版 */
        .plant-stages-row {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
          gap: 6px;
        }

        .plant-stage-chip {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
          padding: 8px 10px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.15s;
          font-size: 0.78rem;
          white-space: nowrap;
        }

        .plant-stage-chip:hover {
          background: rgba(34, 197, 94, 0.12);
          border-color: rgba(34, 197, 94, 0.3);
        }

        .plant-stage-chip.selected {
          background: rgba(34, 197, 94, 0.18);
          border-color: rgba(34, 197, 94, 0.5);
          color: #86efac;
        }

        .stage-info small {
          font-size: 0.75rem;
          opacity: 0.6;
        }

        /* 猎物选择 */
        .selected-prey {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .prey-tag {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: 16px;
          font-size: 0.8rem;
          color: #fca5a5;
        }

        .prey-tag button {
          background: none;
          border: none;
          color: inherit;
          cursor: pointer;
          padding: 0;
          opacity: 0.6;
        }

        .prey-tag button:hover {
          opacity: 1;
        }

        .add-prey-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 16px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px dashed rgba(255, 255, 255, 0.2);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.2s;
        }

        .add-prey-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: #fff;
        }

        .prey-dropdown {
          margin-top: 8px;
        }

        /* 信息横幅 */
        .create-info-banner {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 14px;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(168, 85, 247, 0.05) 100%);
          border: 1px solid rgba(59, 130, 246, 0.15);
          border-radius: 12px;
        }

        .create-info-banner svg {
          color: #60a5fa;
          flex-shrink: 0;
          margin-top: 2px;
        }

        .info-text {
          flex: 1;
          min-width: 0;
        }

        .info-text strong {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.9);
          display: block;
          margin-bottom: 4px;
        }

        .info-text p {
          margin: 0;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.55);
          line-height: 1.5;
        }
      `}</style>
    </AnalysisPanel>
  );
}

