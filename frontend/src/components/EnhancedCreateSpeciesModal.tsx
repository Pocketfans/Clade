/**
 * EnhancedCreateSpeciesModal - 重新设计的创建物种面板
 * 
 * 改进点：
 * - 简洁直观的向导式界面
 * - 清晰的步骤引导
 * - 更好的视觉层次
 * - 简化的选项展示
 */
import { useEffect, useState, useMemo, useCallback } from "react";
import { 
  Sparkles, Dna, Leaf, Bug, Bird, Fish, Zap, RefreshCw, 
  AlertCircle, ChevronRight, Mountain, Waves,
  Sun, Droplets, TreeDeciduous, Shrub, GitBranch, Crown,
  Search, X, Check, HelpCircle, ArrowRight, Wand2,
  PlusCircle, ChevronDown, Lightbulb
} from "lucide-react";
import { GamePanel } from "./common/GamePanel";
import { fetchSpeciesList, generateSpeciesAdvanced, fetchFoodWeb } from "@/services/api";
import type { SpeciesListItem, FoodWebData } from "@/services/api.types";
import "./EnhancedCreateSpeciesModal.css";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

// 栖息地类型
const HABITATS = [
  { id: "marine", name: "海洋", icon: <Waves size={16} />, color: "#0ea5e9" },
  { id: "deep_sea", name: "深海", icon: <Waves size={16} />, color: "#1e40af" },
  { id: "coastal", name: "海岸", icon: <Waves size={16} />, color: "#06b6d4" },
  { id: "freshwater", name: "淡水", icon: <Droplets size={16} />, color: "#22d3ee" },
  { id: "amphibious", name: "两栖", icon: <Droplets size={16} />, color: "#14b8a6" },
  { id: "terrestrial", name: "陆地", icon: <Mountain size={16} />, color: "#84cc16" },
  { id: "aerial", name: "空中", icon: <Bird size={16} />, color: "#a855f7" },
];

// 食性类型
const DIETS = [
  { id: "autotroph", name: "生产者", icon: <Sun size={16} />, color: "#22c55e", desc: "光合/化能合成", hint: "如藻类、植物" },
  { id: "herbivore", name: "食草", icon: <Leaf size={16} />, color: "#84cc16", desc: "以植物为食", hint: "如草食动物" },
  { id: "carnivore", name: "食肉", icon: <Bird size={16} />, color: "#ef4444", desc: "捕食动物", hint: "如捕食者" },
  { id: "omnivore", name: "杂食", icon: <Bug size={16} />, color: "#f59e0b", desc: "植物+动物", hint: "适应性强" },
  { id: "detritivore", name: "分解者", icon: <Shrub size={16} />, color: "#78716c", desc: "有机碎屑", hint: "清道夫" },
];

// 植物演化阶段
const PLANT_STAGES = [
  { stage: 0, name: "原核生物", emoji: "🦠", desc: "蓝藻等" },
  { stage: 1, name: "单细胞藻类", emoji: "🔬", desc: "绿藻等" },
  { stage: 2, name: "群体藻类", emoji: "🌿", desc: "多细胞藻" },
  { stage: 3, name: "苔藓", emoji: "🌱", desc: "首批登陆" },
];

// 快捷模板
const QUICK_TEMPLATES = [
  { id: "algae", name: "浮游藻类", icon: <Leaf size={16} />, color: "#22c55e", habitat: "marine", diet: "autotroph", isPlant: true, plantStage: 1, prompt: "一种微小的浮游藻类，漂浮在海洋表层进行光合作用，是食物链的基础" },
  { id: "filter", name: "滤食动物", icon: <Bug size={16} />, color: "#3b82f6", habitat: "marine", diet: "herbivore", prompt: "一种小型滤食性动物，通过过滤海水中的浮游生物为生" },
  { id: "predator", name: "捕食者", icon: <Bird size={16} />, color: "#ef4444", habitat: "marine", diet: "carnivore", prompt: "一种敏捷的捕食者，以小型动物为食，拥有敏锐的感官" },
  { id: "grazer", name: "陆地食草", icon: <Bug size={16} />, color: "#84cc16", habitat: "terrestrial", diet: "herbivore", prompt: "一种以植物为食的陆地动物，适应了陆地环境" },
  { id: "apex", name: "顶级掠食", icon: <Crown size={16} />, color: "#dc2626", habitat: "terrestrial", diet: "carnivore", prompt: "一种强大的顶级捕食者，处于食物链顶端" },
  { id: "decomposer", name: "分解者", icon: <Shrub size={16} />, color: "#78716c", habitat: "terrestrial", diet: "detritivore", prompt: "一种以有机碎屑为食的分解者，帮助物质循环" },
];

type CreateMode = "quick" | "custom" | "evolve";

export function EnhancedCreateSpeciesModal({ onClose, onSuccess }: Props) {
  // 状态
  const [mode, setMode] = useState<CreateMode>("quick");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedCode, setSuggestedCode] = useState("");
  
  // 选项
  const [selectedHabitat, setSelectedHabitat] = useState<string | null>(null);
  const [selectedDiet, setSelectedDiet] = useState<string | null>(null);
  const [isPlant, setIsPlant] = useState(false);
  const [plantStage, setPlantStage] = useState<number | null>(null);
  
  // 分化模式
  const [parentCode, setParentCode] = useState<string | null>(null);
  const [showParentList, setShowParentList] = useState(false);
  const [parentSearch, setParentSearch] = useState("");
  
  // 数据
  const [speciesList, setSpeciesList] = useState<SpeciesListItem[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  
  // 展开状态
  const [showOptions, setShowOptions] = useState(false);

  // 加载数据
  useEffect(() => {
    async function loadData() {
      setLoadingData(true);
      try {
        const list = await fetchSpeciesList();
        setSpeciesList(list);
        
        // 计算编号
        const usedCodes = new Set(list.map(s => s.lineage_code));
        let index = 1;
        while (usedCodes.has(`S${index}`)) index++;
        setSuggestedCode(`S${index}`);
      } catch (err) {
        console.error("加载失败:", err);
      } finally {
        setLoadingData(false);
      }
    }
    loadData();
  }, []);

  // 过滤可选父代
  const filteredParents = useMemo(() => {
    const alive = speciesList.filter(s => s.status === "alive");
    if (!parentSearch.trim()) return alive;
    const q = parentSearch.toLowerCase();
    return alive.filter(s => 
      s.common_name.toLowerCase().includes(q) || 
      s.lineage_code.toLowerCase().includes(q)
    );
  }, [speciesList, parentSearch]);

  // 选择模板
  const handleTemplateSelect = useCallback((template: typeof QUICK_TEMPLATES[0]) => {
    setPrompt(template.prompt);
    setSelectedHabitat(template.habitat);
    setSelectedDiet(template.diet);
    setIsPlant(template.isPlant || false);
    setPlantStage(template.plantStage ?? null);
  }, []);

  // 随机模板
  const handleRandomTemplate = useCallback(() => {
    const t = QUICK_TEMPLATES[Math.floor(Math.random() * QUICK_TEMPLATES.length)];
    handleTemplateSelect(t);
  }, [handleTemplateSelect]);

  // 创建物种
  const handleCreate = async () => {
    if (!prompt.trim()) {
      setError("请输入物种描述");
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
        parent_code: mode === "evolve" ? parentCode || undefined : undefined,
        is_plant: isPlant,
        plant_stage: plantStage ?? undefined,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setLoading(false);
    }
  };

  const selectedParent = parentCode ? speciesList.find(s => s.lineage_code === parentCode) : null;

  return (
    <GamePanel
      title="创造新物种"
      icon={<Wand2 size={20} />}
      onClose={onClose}
      width="680px"
      height="auto"
    >
      <div className="csm-content">
        {/* 模式选择 */}
        <div className="csm-mode-tabs">
          <button 
            className={`csm-mode-tab ${mode === "quick" ? "active" : ""}`}
            onClick={() => setMode("quick")}
          >
            <Sparkles size={16} />
            <span>快速创建</span>
          </button>
          <button 
            className={`csm-mode-tab ${mode === "custom" ? "active" : ""}`}
            onClick={() => setMode("custom")}
          >
            <Dna size={16} />
            <span>自定义</span>
          </button>
          <button 
            className={`csm-mode-tab ${mode === "evolve" ? "active" : ""}`}
            onClick={() => setMode("evolve")}
          >
            <GitBranch size={16} />
            <span>从现有分化</span>
          </button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="csm-error">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* 快速创建模式 */}
        {mode === "quick" && (
          <div className="csm-quick-mode">
            <div className="csm-section">
              <div className="csm-section-title">
                <Lightbulb size={16} />
                <span>选择一个模板开始</span>
              </div>
              <div className="csm-templates">
                {QUICK_TEMPLATES.map(t => (
                  <button
                    key={t.id}
                    className={`csm-template ${prompt === t.prompt ? "selected" : ""}`}
                    style={{ "--t-color": t.color } as React.CSSProperties}
                    onClick={() => handleTemplateSelect(t)}
                  >
                    <span className="csm-template-icon">{t.icon}</span>
                    <span className="csm-template-name">{t.name}</span>
                  </button>
                ))}
                <button className="csm-template random" onClick={handleRandomTemplate}>
                  <RefreshCw size={16} />
                  <span>随机</span>
                </button>
              </div>
            </div>

            <div className="csm-section">
              <div className="csm-section-title">
                <Dna size={16} />
                <span>描述你的物种</span>
                <span className="csm-required">必填</span>
              </div>
              <textarea
                className="csm-textarea"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="描述这个物种的外观、习性、特征...&#10;&#10;例如：一种生活在深海的发光水母，通过生物发光吸引猎物"
                rows={4}
              />
              <div className="csm-textarea-hint">
                <HelpCircle size={12} />
                <span>AI 会根据描述生成物种的详细属性</span>
              </div>
            </div>
          </div>
        )}

        {/* 自定义模式 */}
        {mode === "custom" && (
          <div className="csm-custom-mode">
            <div className="csm-section">
              <div className="csm-section-title">
                <Dna size={16} />
                <span>物种描述</span>
                <span className="csm-required">必填</span>
              </div>
              <textarea
                className="csm-textarea"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="详细描述你想创造的物种..."
                rows={4}
              />
            </div>

            {/* 可选参数 */}
            <div className="csm-section">
              <button 
                className="csm-expand-btn"
                onClick={() => setShowOptions(!showOptions)}
              >
                <span>指定生态位参数</span>
                <span className="csm-optional">可选</span>
                <ChevronDown size={16} className={showOptions ? "open" : ""} />
              </button>

              {showOptions && (
                <div className="csm-options">
                  {/* 栖息地 */}
                  <div className="csm-option-group">
                    <label>
                      <Mountain size={14} />
                      栖息地
                    </label>
                    <div className="csm-chips">
                      {HABITATS.map(h => (
                        <button
                          key={h.id}
                          className={`csm-chip ${selectedHabitat === h.id ? "selected" : ""}`}
                          style={{ "--c-color": h.color } as React.CSSProperties}
                          onClick={() => setSelectedHabitat(selectedHabitat === h.id ? null : h.id)}
                        >
                          {h.icon}
                          <span>{h.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 食性 */}
                  <div className="csm-option-group">
                    <label>
                      <Leaf size={14} />
                      食性类型
                    </label>
                    <div className="csm-chips">
                      {DIETS.map(d => (
                        <button
                          key={d.id}
                          className={`csm-chip ${selectedDiet === d.id ? "selected" : ""}`}
                          style={{ "--c-color": d.color } as React.CSSProperties}
                          onClick={() => {
                            const newDiet = selectedDiet === d.id ? null : d.id;
                            setSelectedDiet(newDiet);
                            setIsPlant(newDiet === "autotroph");
                            if (newDiet !== "autotroph") setPlantStage(null);
                          }}
                          title={d.hint}
                        >
                          {d.icon}
                          <span>{d.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 植物阶段 */}
                  {isPlant && (
                    <div className="csm-option-group">
                      <label>
                        <TreeDeciduous size={14} />
                        植物演化阶段
                      </label>
                      <div className="csm-chips">
                        {PLANT_STAGES.map(s => (
                          <button
                            key={s.stage}
                            className={`csm-chip plant ${plantStage === s.stage ? "selected" : ""}`}
                            onClick={() => setPlantStage(plantStage === s.stage ? null : s.stage)}
                            title={s.desc}
                          >
                            <span>{s.emoji}</span>
                            <span>{s.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 分化模式 */}
        {mode === "evolve" && (
          <div className="csm-evolve-mode">
            <div className="csm-section">
              <div className="csm-section-title">
                <GitBranch size={16} />
                <span>选择父代物种</span>
                <span className="csm-required">必填</span>
              </div>
              
              {selectedParent ? (
                <div className="csm-parent-card">
                  <div className="csm-parent-info">
                    <span className="csm-parent-code">{selectedParent.lineage_code}</span>
                    <span className="csm-parent-name">{selectedParent.common_name}</span>
                    <span className="csm-parent-latin">{selectedParent.latin_name}</span>
                  </div>
                  <button 
                    className="csm-change-btn"
                    onClick={() => setShowParentList(true)}
                  >
                    更换
                  </button>
                </div>
              ) : (
                <button 
                  className="csm-select-parent"
                  onClick={() => setShowParentList(true)}
                >
                  <PlusCircle size={18} />
                  <span>点击选择一个现有物种</span>
                </button>
              )}

              {/* 父代选择器 */}
              {showParentList && (
                <div className="csm-parent-list">
                  <div className="csm-parent-search">
                    <Search size={16} />
                    <input
                      type="text"
                      placeholder="搜索物种..."
                      value={parentSearch}
                      onChange={e => setParentSearch(e.target.value)}
                      autoFocus
                    />
                    <button onClick={() => setShowParentList(false)}>
                      <X size={16} />
                    </button>
                  </div>
                  <div className="csm-parent-items">
                    {loadingData ? (
                      <div className="csm-loading">加载中...</div>
                    ) : filteredParents.length === 0 ? (
                      <div className="csm-empty">没有找到物种</div>
                    ) : (
                      filteredParents.map(sp => (
                        <button
                          key={sp.lineage_code}
                          className={`csm-parent-item ${parentCode === sp.lineage_code ? "selected" : ""}`}
                          onClick={() => {
                            setParentCode(sp.lineage_code);
                            setShowParentList(false);
                          }}
                        >
                          <span className="csm-item-code">{sp.lineage_code}</span>
                          <span className="csm-item-name">{sp.common_name}</span>
                          {parentCode === sp.lineage_code && <Check size={16} />}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="csm-section">
              <div className="csm-section-title">
                <Dna size={16} />
                <span>描述变异方向</span>
                <span className="csm-required">必填</span>
              </div>
              <textarea
                className="csm-textarea"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="描述新物种与父代的不同之处...&#10;&#10;例如：进化出更大的体型和更强壮的前肢，适应了捕食更大猎物"
                rows={4}
              />
              <div className="csm-textarea-hint">
                <HelpCircle size={12} />
                <span>新物种会继承父代特征，同时根据描述产生变异</span>
              </div>
            </div>
          </div>
        )}

        {/* 底部：编号预览和创建按钮 */}
        <div className="csm-footer">
          <div className="csm-code-preview">
            <span className="csm-code-label">编号</span>
            <span className="csm-code-value">{suggestedCode || "..."}</span>
            {mode === "evolve" && parentCode && (
              <span className="csm-code-hint">← {parentCode} 的子代</span>
            )}
          </div>

          <div className="csm-actions">
            <button className="csm-cancel" onClick={onClose} disabled={loading}>
              取消
            </button>
            <button 
              className="csm-create"
              onClick={handleCreate}
              disabled={loading || !prompt.trim() || (mode === "evolve" && !parentCode)}
            >
              {loading ? (
                <>
                  <span className="csm-spinner" />
                  <span>创造中...</span>
                </>
              ) : (
                <>
                  <Zap size={18} />
                  <span>创造物种</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </GamePanel>
  );
}
