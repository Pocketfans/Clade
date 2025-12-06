/**
 * SpeciesDetailModal - 物种详情弹窗组件
 * 
 * Windows Aero 风格玻璃拟态设计
 * 包含：生存指标仪表盘、地块分布、压力分解、生态关系
 */

import { useState, useEffect, useCallback, CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  X, RefreshCw, Edit2, Save, Zap, GitBranch, GitMerge,
  Eye, BarChart3, Sparkles, Activity, Target, Dna, Shield,
  Heart, Leaf, Users, Star, Hexagon, Atom, TrendingUp, TrendingDown,
  Minus, Map, AlertTriangle, Skull, Baby, ChevronRight, Utensils,
  Swords, Handshake, TreePine
} from "lucide-react";

import type { SpeciesDetail, SpeciesSnapshot, SpeciesFoodChain } from "@/services/api.types";
import { fetchSpeciesDetail, editSpecies, fetchSpeciesFoodChain } from "@/services/api";
import { OrganismBlueprint } from "./OrganismBlueprint";
import { SpeciesAITab } from "./SpeciesAITab";
import "./SpeciesDetailModal.css";

// ============ 中英文字段映射表 ============
const fieldTranslations: Record<string, string> = {
  // 形态参数
  body_length_cm: "体长 (cm)",
  body_weight_g: "体重 (g)",
  body_surface_area_cm2: "体表面积 (cm²)",
  lifespan_days: "寿命 (天)",
  generation_time_days: "世代时间 (天)",
  population: "种群数量",
  metabolic_rate: "代谢率",
  growth_rate: "生长速率",
  reproduction_rate: "繁殖率",
  size: "体型",
  metabolism: "代谢",
  
  // 抽象特质（0-15范围）- 中文键
  耐热性: "耐热性",
  耐寒性: "耐寒性",
  耐旱性: "耐旱性",
  耐盐性: "耐盐性",
  耐酸碱性: "耐酸碱性",
  社会性: "社会性",
  免疫力: "免疫力",
  耐火性: "耐火性",
  挖掘能力: "挖掘能力",
  抗紫外线: "抗紫外线",
  解毒能力: "解毒能力",
  光照需求: "光照需求",
  氧气需求: "氧气需求",
  繁殖速度: "繁殖速度",
  运动能力: "运动能力",
  光合效率: "光合效率",
  固碳能力: "固碳能力",
  根系发达度: "根系发达度",
  保水能力: "保水能力",
  养分吸收: "养分吸收",
  多细胞程度: "多细胞程度",
  木质化程度: "木质化程度",
  种子化程度: "种子化程度",
  散布能力: "散布能力",
  
  // 英文键版本（兼容）
  adaptability: "适应性",
  aggression: "攻击性",
  intelligence: "智力",
  camouflage: "伪装能力",
  speed: "速度",
  endurance: "耐力",
  sensory_acuity: "感知敏锐度",
  nocturnal: "夜行性",
  heat_resistance: "耐热性",
  cold_resistance: "耐寒性",
  drought_resistance: "耐旱性",
  salinity_resistance: "耐盐性",
  sociality: "社会性",
  immunity: "免疫力",
  fire_resistance: "耐火性",
  burrowing_ability: "挖掘能力",
  uv_resistance: "抗紫外线",
  detoxification: "解毒能力",
  light_requirement: "光照需求",
  oxygen_requirement: "氧气需求",
  reproduction_speed: "繁殖速度",
  mobility: "运动能力",
  
  // 隐藏特质
  environment_sensitivity: "环境敏感度",
  mutation_rate: "突变率",
  genetic_stability: "基因稳定性",
  gene_diversity: "基因多样性",
  evolution_potential: "进化潜力",
  
  // 能力
  photosynthesis: "光合作用",
  chemosynthesis: "化学合成",
  flight: "飞行",
  swimming: "游泳",
  burrowing: "穴居",
  venom: "毒液",
  echolocation: "回声定位",
  bioluminescence: "生物发光",
  camouflage_ability: "变色伪装",
  regeneration: "再生",
  hibernation: "冬眠",
  migration: "迁徙",
  pack_hunting: "群体狩猎",
  tool_use: "工具使用",
  nitrogen_fixation: "固氮作用",
  spore_dispersal: "孢子散播",
  
  // 生态角色
  producer: "生产者",
  herbivore: "食草动物",
  carnivore: "食肉动物",
  omnivore: "杂食动物",
  decomposer: "分解者",
  scavenger: "食腐动物",
  mixotroph: "混合营养",
  detritivore: "腐食者",
  autotroph: "自养生物",
};

function translate(key: string): string {
  return fieldTranslations[key] || key;
}

interface Props {
  speciesId: string;
  snapshot?: SpeciesSnapshot;
  isOpen: boolean;
  onClose: () => void;
  previousPopulations?: Map<string, number>;
}

// 生态角色配置
const roleConfig: Record<string, {
  color: string;
  icon: string;
  label: string;
  description: string;
}> = {
  producer: { color: "#22c55e", icon: "🌿", label: "生产者", description: "光合作用的基石" },
  herbivore: { color: "#eab308", icon: "🦌", label: "食草动物", description: "植被的消费者" },
  carnivore: { color: "#ef4444", icon: "🦁", label: "食肉动物", description: "顶级掠食者" },
  omnivore: { color: "#f97316", icon: "🐻", label: "杂食动物", description: "适应性强的觅食者" },
  decomposer: { color: "#a855f7", icon: "🍄", label: "分解者", description: "生态循环的清道夫" },
  scavenger: { color: "#64748b", icon: "🦅", label: "食腐动物", description: "资源的回收者" },
  mixotroph: { color: "#22d3ee", icon: "🔬", label: "混合营养", description: "既能自养又能捕食" },
  unknown: { color: "#3b82f6", icon: "🧬", label: "未知", description: "神秘的生命形式" }
};

function getRoleFromTrophicLevel(trophicLevel: number | undefined): string {
  const t = trophicLevel ?? 1.0;
  if (t < 1.5) return 'producer';
  if (t < 2.0) return 'mixotroph';
  if (t < 2.8) return 'herbivore';
  if (t < 3.5) return 'omnivore';
  return 'carnivore';
}

function getRoleConfig(ecologicalRole: string | undefined, trophicLevel: number | undefined) {
  if (trophicLevel !== undefined && trophicLevel > 0) {
    const roleKey = getRoleFromTrophicLevel(trophicLevel);
    return roleConfig[roleKey] || roleConfig.unknown;
  }
  if (ecologicalRole) {
    const role = roleConfig[ecologicalRole.toLowerCase()];
    if (role) return role;
  }
  return roleConfig.unknown;
}

function formatPopulation(pop: number): string {
  if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
  if (pop >= 1_000) return `${(pop / 1_000).toFixed(1)}K`;
  return pop.toFixed(0);
}

function formatMorphology(key: string, value: number): { value: string; label: string } {
  const rawLabel = translate(key);
  
  if (key === 'body_length_cm') {
    const cleanLabel = "体长";
    if (value < 0.1 && value > 0) return { value: `${(value * 10000).toFixed(1)} µm`, label: cleanLabel };
    if (value < 1 && value > 0) return { value: `${(value * 10).toFixed(1)} mm`, label: cleanLabel };
    return { value: `${value.toFixed(2)} cm`, label: cleanLabel };
  }
  
  if (key === 'body_weight_g') {
    const cleanLabel = "体重";
    if (value < 0.001 && value > 0) return { value: `${(value * 1000000).toFixed(1)} µg`, label: cleanLabel };
    if (value < 1 && value > 0) return { value: `${(value * 1000).toFixed(1)} mg`, label: cleanLabel };
    return { value: `${value.toFixed(2)} g`, label: cleanLabel };
  }
  
  if (key === 'body_surface_area_cm2') {
    const cleanLabel = "体表面积";
    if (value < 0.01 && value > 0) {
      const mm2 = value * 100;
      if (mm2 < 0.1) return { value: `${(mm2 * 1000000).toFixed(1)} µm²`, label: cleanLabel };
      return { value: `${mm2.toFixed(2)} mm²`, label: cleanLabel };
    }
    return { value: `${value.toFixed(2)} cm²`, label: cleanLabel };
  }

  let formattedValue = value.toFixed(2);
  if (value >= 1000) formattedValue = formatPopulation(value);
  else if (value > 0 && value < 0.01) {
    formattedValue = value < 0.0001 ? value.toExponential(1) : value.toFixed(4);
  } else if (value === 0) {
    formattedValue = "0";
  }

  return { value: formattedValue, label: rawLabel };
}

// 计算健康评分 (0-100)
function calculateHealthScore(snapshot?: SpeciesSnapshot): number {
  if (!snapshot) return 50;
  
  let score = 100;
  
  // 死亡率惩罚
  const deathPenalty = Math.min(snapshot.death_rate * 200, 40);
  score -= deathPenalty;
  
  // 净变化率奖励/惩罚
  if (snapshot.net_change_rate !== undefined) {
    if (snapshot.net_change_rate < -0.1) score -= 20;
    else if (snapshot.net_change_rate < 0) score -= 10;
    else if (snapshot.net_change_rate > 0.1) score += 10;
  }
  
  // 危机地块惩罚
  if (snapshot.critical_tiles && snapshot.total_tiles) {
    const criticalRatio = snapshot.critical_tiles / snapshot.total_tiles;
    score -= criticalRatio * 30;
  }
  
  // 无避难所惩罚
  if (snapshot.has_refuge === false) score -= 10;
  
  return Math.max(0, Math.min(100, Math.round(score)));
}

// 获取健康评分颜色
function getHealthColor(score: number): string {
  if (score >= 70) return "#22c55e";
  if (score >= 40) return "#f59e0b";
  return "#ef4444";
}

// 获取健康评分标签
function getHealthLabel(score: number): string {
  if (score >= 80) return "优秀";
  if (score >= 60) return "良好";
  if (score >= 40) return "一般";
  if (score >= 20) return "危险";
  return "濒危";
}

interface CustomCSS extends CSSProperties {
  '--role-color'?: string;
  '--role-color-dim'?: string;
  '--role-color-alpha'?: string;
  '--healthy-deg'?: string;
  '--warning-deg'?: string;
  '--card-color'?: string;
  '--trait-color'?: string;
}

export function SpeciesDetailModal({
  speciesId,
  snapshot,
  isOpen,
  onClose,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  previousPopulations
}: Props) {
  const [species, setSpecies] = useState<SpeciesDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "traits" | "organs" | "ecology" | "lineage" | "ai">("overview");
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ description: "", morphology: "", traits: "" });
  const [isSaving, setIsSaving] = useState(false);
  const [foodChain, setFoodChain] = useState<SpeciesFoodChain | null>(null);
  const [foodChainLoading, setFoodChainLoading] = useState(false);

  // 加载物种详情
  const loadDetail = useCallback(async () => {
    if (!speciesId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await fetchSpeciesDetail(speciesId);
      setSpecies(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [speciesId]);

  // 加载食物链数据
  const [foodChainError, setFoodChainError] = useState<string | null>(null);
  
  const loadFoodChain = useCallback(async () => {
    // 如果已有数据或已有错误或正在加载，不重复请求
    if (!speciesId || foodChain || foodChainError || foodChainLoading) return;
    
    setFoodChainLoading(true);
    setFoodChainError(null);
    try {
      const data = await fetchSpeciesFoodChain(speciesId);
      setFoodChain(data);
    } catch (err) {
      console.warn("加载食物链失败:", err);
      setFoodChainError("无法加载生态关系数据");
    } finally {
      setFoodChainLoading(false);
    }
  }, [speciesId, foodChain, foodChainError, foodChainLoading]);

  useEffect(() => {
    if (isOpen && speciesId) {
      loadDetail();
      setFoodChain(null); // 重置食物链
      setFoodChainError(null); // 重置错误
    }
  }, [isOpen, speciesId, loadDetail]);

  // 切换到生态关系 Tab 时加载食物链
  useEffect(() => {
    if (activeTab === "ecology" && !foodChain && !foodChainLoading) {
      loadFoodChain();
    }
  }, [activeTab, foodChain, foodChainLoading, loadFoodChain]);

  const handleStartEdit = () => {
    if (!species) return;
    setEditForm({
      description: species.description || "",
      morphology: JSON.stringify(species.morphology_stats, null, 2),
      traits: JSON.stringify(species.abstract_traits, null, 2),
    });
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!species) return;
    
    setIsSaving(true);
    try {
      await editSpecies(species.lineage_code, {
        description: editForm.description,
        morphology: editForm.morphology,
        traits: editForm.traits,
      });
      
      await loadDetail();
      setIsEditing(false);
    } catch (err) {
      console.error("保存失败:", err);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  const role = getRoleConfig(snapshot?.ecological_role, snapshot?.trophic_level ?? species?.trophic_level);
  const healthScore = calculateHealthScore(snapshot);
  const healthColor = getHealthColor(healthScore);

  // 计算地块分布角度
  const totalTiles = snapshot?.total_tiles || 1;
  const healthyTiles = snapshot?.healthy_tiles || 0;
  const warningTiles = snapshot?.warning_tiles || 0;
  const criticalTiles = snapshot?.critical_tiles || 0;
  const healthyDeg = (healthyTiles / totalTiles) * 360;
  const warningDeg = (warningTiles / totalTiles) * 360;

  const dynamicStyles: CustomCSS = {
    '--role-color': role.color,
    '--role-color-dim': `${role.color}25`,
    '--role-color-alpha': `${role.color}60`,
    '--healthy-deg': `${healthyDeg}deg`,
    '--warning-deg': `${warningDeg}deg`,
  };

  // 计算净变化
  const netChangeRate = snapshot?.net_change_rate ?? 0;
  const netChangeClass = netChangeRate > 0.01 ? "up" : netChangeRate < -0.01 ? "down" : "stable";
  
  // 渲染变化图标
  const renderChangeIcon = () => {
    if (netChangeRate > 0.01) return <TrendingUp size={12} />;
    if (netChangeRate < -0.01) return <TrendingDown size={12} />;
    return <Minus size={12} />;
  };

  const modalContent = (
    <div className="sdm-overlay" onClick={onClose}>
      <div 
        className="sdm-modal" 
        onClick={(e) => e.stopPropagation()}
        style={dynamicStyles}
      >
        {/* 头部 */}
        <div className="sdm-header">
          <div className="sdm-avatar-wrapper">
            <div className="sdm-avatar-glow" />
            <div className="sdm-avatar">
              <span className="sdm-avatar-icon">{role.icon}</span>
            </div>
          </div>
          
          <div className="sdm-title-block">
            {loading ? (
              <div className="sdm-loading-title">分析生物信号...</div>
            ) : species ? (
              <>
                <h2 className="sdm-title">{species.common_name}</h2>
                <div className="sdm-subtitle">
                  <span>{species.latin_name}</span>
                  <span style={{ opacity: 0.3 }}>|</span>
                  <span className="font-mono opacity-70">{species.lineage_code}</span>
                </div>
                <div className="sdm-tags">
                  <span className="sdm-tag role">{role.label}</span>
                  {species.status === "extinct" && (
                    <span className="sdm-tag extinct">已灭绝</span>
                  )}
                </div>
              </>
            ) : (
              <div className="sdm-error-title">信号丢失</div>
            )}
          </div>
          
          <div className="sdm-header-actions">
            {!loading && species && !isEditing && (
              <>
                <button className="sdm-action-btn" onClick={loadDetail} title="刷新数据">
                  <RefreshCw size={16} />
                </button>
                <button className="sdm-action-btn" onClick={handleStartEdit} title="编辑档案">
                  <Edit2 size={16} />
                </button>
              </>
            )}
            <button className="sdm-close-btn" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 内容区 */}
        <div className="sdm-body">
          {loading ? (
            <div className="sdm-loading">
              <div className="sdm-spinner" />
              <span>正在解析基因序列...</span>
            </div>
          ) : error ? (
            <div className="sdm-error">
              <span className="sdm-error-icon">⚠️</span>
              <span>{error}</span>
              <button className="sdm-retry-btn" onClick={loadDetail}>
                <RefreshCw size={14} /> 重试连接
              </button>
            </div>
          ) : species ? (
            <>
              {isEditing ? (
                <div className="sdm-edit-form">
                  <div className="sdm-edit-group">
                    <label>物种描述</label>
                    <textarea
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      placeholder="描述这个物种..."
                      rows={4}
                    />
                  </div>
                  <div className="sdm-edit-group">
                    <label>形态参数 (JSON)</label>
                    <textarea
                      value={editForm.morphology}
                      onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
                      className="mono"
                      rows={6}
                    />
                  </div>
                  <div className="sdm-edit-group">
                    <label>抽象特质 (JSON)</label>
                    <textarea
                      value={editForm.traits}
                      onChange={(e) => setEditForm({ ...editForm, traits: e.target.value })}
                      className="mono"
                      rows={6}
                    />
                  </div>
                  <div className="sdm-edit-actions">
                    <button className="sdm-btn secondary" onClick={() => setIsEditing(false)}>
                      取消
                    </button>
                    <button className="sdm-btn primary" onClick={handleSaveEdit} disabled={isSaving}>
                      {isSaving ? <span className="sdm-btn-spinner" /> : <Save size={14} />}
                      <span>保存更改</span>
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {/* ========== 生存指标仪表盘 ========== */}
                  {snapshot && (
                    <div className="sdm-dashboard">
                      <div className="sdm-dashboard-main">
                        {/* 种群数量 */}
                        <div className="sdm-stat-card highlight">
                          <div className="sdm-stat-header">
                            <div className="sdm-stat-icon">
                              <Users size={16} />
                            </div>
                            <span className="sdm-stat-label">生物量</span>
                          </div>
                          <div className="sdm-stat-value">{formatPopulation(snapshot.population)}</div>
                          <div className={`sdm-stat-change ${netChangeClass}`}>
                            <span>{renderChangeIcon()}</span>
                            <span>{netChangeRate >= 0 ? "+" : ""}{(netChangeRate * 100).toFixed(1)}%</span>
                          </div>
                        </div>

                        {/* 死亡率 */}
                        <div className="sdm-stat-card">
                          <div className="sdm-stat-header">
                            <div className={`sdm-stat-icon ${snapshot.death_rate > 0.15 ? 'negative' : snapshot.death_rate > 0.08 ? 'warning' : ''}`}>
                              <Skull size={16} />
                            </div>
                            <span className="sdm-stat-label">死亡率</span>
                          </div>
                          <div className={`sdm-stat-value ${snapshot.death_rate > 0.15 ? 'negative' : snapshot.death_rate > 0.08 ? 'warning' : ''}`}>
                            {(snapshot.death_rate * 100).toFixed(1)}%
                          </div>
                        </div>

                        {/* 生态占比 */}
                        <div className="sdm-stat-card">
                          <div className="sdm-stat-header">
                            <div className="sdm-stat-icon">
                              <Target size={16} />
                            </div>
                            <span className="sdm-stat-label">生态占比</span>
                          </div>
                          <div className="sdm-stat-value">
                            {(snapshot.population_share * 100).toFixed(1)}%
                          </div>
                        </div>

                        {/* 健康评分 */}
                        <div className="sdm-stat-card">
                          <div className="sdm-stat-header">
                            <div className="sdm-stat-icon" style={{ color: healthColor }}>
                              <Heart size={16} />
                            </div>
                            <span className="sdm-stat-label">健康度</span>
                          </div>
                          <div className="sdm-stat-value" style={{ color: healthColor }}>
                            {healthScore}
                          </div>
                          <div className="sdm-stat-change" style={{ color: healthColor }}>
                            {getHealthLabel(healthScore)}
                          </div>
                        </div>
                      </div>

                      {/* 种群流水 */}
                      {(snapshot.initial_population !== undefined || snapshot.births !== undefined) && (
                        <div className="sdm-population-flow">
                          <div className="sdm-flow-header">
                            <Activity size={14} />
                            <span>本回合种群变化</span>
                          </div>
                          <div className="sdm-flow-chart">
                            <div className="sdm-flow-node">
                              <div className="sdm-flow-node-value">
                                {formatPopulation(snapshot.initial_population ?? snapshot.population)}
                              </div>
                              <div className="sdm-flow-node-label">期初</div>
                            </div>
                            <ChevronRight className="sdm-flow-arrow" size={16} />
                            <div className="sdm-flow-node deaths">
                              <div className="sdm-flow-node-value">
                                -{formatPopulation(snapshot.deaths ?? 0)}
                              </div>
                              <div className="sdm-flow-node-label">死亡</div>
                            </div>
                            <ChevronRight className="sdm-flow-arrow" size={16} />
                            <div className="sdm-flow-node">
                              <div className="sdm-flow-node-value">
                                {formatPopulation(snapshot.survivors ?? (snapshot.initial_population ?? snapshot.population) - (snapshot.deaths ?? 0))}
                              </div>
                              <div className="sdm-flow-node-label">存活</div>
                            </div>
                            <ChevronRight className="sdm-flow-arrow" size={16} />
                            <div className="sdm-flow-node births">
                              <div className="sdm-flow-node-value">
                                +{formatPopulation(snapshot.births ?? 0)}
                              </div>
                              <div className="sdm-flow-node-label">出生</div>
                            </div>
                            <ChevronRight className="sdm-flow-arrow" size={16} />
                            <div className="sdm-flow-node">
                              <div className="sdm-flow-node-value">
                                {formatPopulation(snapshot.population)}
                              </div>
                              <div className="sdm-flow-node-label">期末</div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* ========== 地块与压力双面板 ========== */}
                  {snapshot && (snapshot.total_tiles !== undefined || snapshot.niche_overlap !== undefined) && (
                    <div className="sdm-dual-panel">
                      {/* 地块分布面板 */}
                      {snapshot.total_tiles !== undefined && (
                        <div className="sdm-panel">
                          <div className="sdm-panel-header">
                            <Map size={16} />
                            <span>地块分布</span>
                          </div>
                          <div className="sdm-tile-distribution">
                            <div className="sdm-tile-pie">
                              <div 
                                className="sdm-tile-pie-bg"
                                style={{
                                  background: `conic-gradient(
                                    #22c55e 0deg ${healthyDeg}deg,
                                    #f59e0b ${healthyDeg}deg ${healthyDeg + warningDeg}deg,
                                    #ef4444 ${healthyDeg + warningDeg}deg 360deg
                                  )`
                                }}
                              />
                              <div className="sdm-tile-pie-center">
                                <div className="sdm-tile-pie-value">{totalTiles}</div>
                                <div className="sdm-tile-pie-label">地块</div>
                              </div>
                            </div>
                            <div className="sdm-tile-legend">
                              <div className="sdm-tile-legend-item">
                                <span className="sdm-tile-legend-dot healthy" />
                                <span className="sdm-tile-legend-label">健康</span>
                                <span className="sdm-tile-legend-value">{healthyTiles}</span>
                              </div>
                              <div className="sdm-tile-legend-item">
                                <span className="sdm-tile-legend-dot warning" />
                                <span className="sdm-tile-legend-label">警告</span>
                                <span className="sdm-tile-legend-value">{warningTiles}</span>
                              </div>
                              <div className="sdm-tile-legend-item">
                                <span className="sdm-tile-legend-dot critical" />
                                <span className="sdm-tile-legend-label">危机</span>
                                <span className="sdm-tile-legend-value">{criticalTiles}</span>
                              </div>
                            </div>
                          </div>
                          <div className="sdm-tile-extra">
                            {snapshot.best_tile_rate !== undefined && (
                              <div className="sdm-tile-extra-item">
                                <TrendingDown size={12} />
                                <span>最佳 {(snapshot.best_tile_rate * 100).toFixed(1)}%</span>
                              </div>
                            )}
                            {snapshot.worst_tile_rate !== undefined && (
                              <div className="sdm-tile-extra-item">
                                <TrendingUp size={12} />
                                <span>最差 {(snapshot.worst_tile_rate * 100).toFixed(1)}%</span>
                              </div>
                            )}
                            {snapshot.has_refuge !== undefined && (
                              <div className={`sdm-tile-extra-item ${snapshot.has_refuge ? 'has-refuge' : ''}`}>
                                <Shield size={12} />
                                <span>{snapshot.has_refuge ? "有避难所" : "无避难所"}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* 压力分解面板 */}
                      <div className="sdm-panel">
                        <div className="sdm-panel-header">
                          <AlertTriangle size={16} />
                          <span>生存压力</span>
                        </div>
                        <div className="sdm-pressure-bars">
                          {snapshot.niche_overlap !== undefined && (
                            <div className="sdm-pressure-item">
                              <div className="sdm-pressure-header">
                                <span className="sdm-pressure-label">生态位重叠</span>
                                <span className="sdm-pressure-value">{(snapshot.niche_overlap * 100).toFixed(0)}%</span>
                              </div>
                              <div className="sdm-pressure-bar">
                                <div 
                                  className={`sdm-pressure-fill ${snapshot.niche_overlap > 0.6 ? 'high' : snapshot.niche_overlap > 0.3 ? 'medium' : 'low'}`}
                                  style={{ width: `${snapshot.niche_overlap * 100}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {snapshot.resource_pressure !== undefined && (
                            <div className="sdm-pressure-item">
                              <div className="sdm-pressure-header">
                                <span className="sdm-pressure-label">资源压力</span>
                                <span className="sdm-pressure-value">{(snapshot.resource_pressure * 100).toFixed(0)}%</span>
                              </div>
                              <div className="sdm-pressure-bar">
                                <div 
                                  className={`sdm-pressure-fill ${snapshot.resource_pressure > 0.6 ? 'high' : snapshot.resource_pressure > 0.3 ? 'medium' : 'low'}`}
                                  style={{ width: `${snapshot.resource_pressure * 100}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {snapshot.predation_pressure !== undefined && (
                            <div className="sdm-pressure-item">
                              <div className="sdm-pressure-header">
                                <span className="sdm-pressure-label">捕食压力</span>
                                <span className="sdm-pressure-value">{(snapshot.predation_pressure * 100).toFixed(0)}%</span>
                              </div>
                              <div className="sdm-pressure-bar">
                                <div 
                                  className={`sdm-pressure-fill ${snapshot.predation_pressure > 0.5 ? 'high' : snapshot.predation_pressure > 0.2 ? 'medium' : 'low'}`}
                                  style={{ width: `${Math.min(snapshot.predation_pressure * 100, 100)}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {snapshot.grazing_pressure !== undefined && (
                            <div className="sdm-pressure-item">
                              <div className="sdm-pressure-header">
                                <span className="sdm-pressure-label">啃食压力</span>
                                <span className="sdm-pressure-value">{(snapshot.grazing_pressure * 100).toFixed(0)}%</span>
                              </div>
                              <div className="sdm-pressure-bar">
                                <div 
                                  className={`sdm-pressure-fill ${snapshot.grazing_pressure > 0.5 ? 'high' : snapshot.grazing_pressure > 0.2 ? 'medium' : 'low'}`}
                                  style={{ width: `${Math.min(snapshot.grazing_pressure * 100, 100)}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {/* 生态拟真数据 */}
                          {snapshot.ecological_realism?.disease_pressure !== undefined && snapshot.ecological_realism.disease_pressure > 0 && (
                            <div className="sdm-pressure-item">
                              <div className="sdm-pressure-header">
                                <span className="sdm-pressure-label">疾病压力</span>
                                <span className="sdm-pressure-value">{(snapshot.ecological_realism.disease_pressure * 100).toFixed(0)}%</span>
                              </div>
                              <div className="sdm-pressure-bar">
                                <div 
                                  className={`sdm-pressure-fill ${snapshot.ecological_realism.disease_pressure > 0.5 ? 'high' : snapshot.ecological_realism.disease_pressure > 0.2 ? 'medium' : 'low'}`}
                                  style={{ width: `${snapshot.ecological_realism.disease_pressure * 100}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* ========== 标签页 ========== */}
                  <div className="sdm-tabs">
                    {[
                      { key: "overview", label: "总览", icon: <Atom size={14} /> },
                      { key: "traits", label: "特质", icon: <Hexagon size={14} /> },
                      { key: "organs", label: "器官", icon: <Eye size={14} /> },
                      { key: "ecology", label: "生态", icon: <TreePine size={14} /> },
                      ...(species.hybrid_parent_codes?.length || species.parent_code
                        ? [{ key: "lineage", label: "族谱", icon: <GitBranch size={14} /> }]
                        : []),
                      { key: "ai", label: "AI", icon: <Sparkles size={14} /> }
                    ].map(({ key, label, icon }) => (
                      <button
                        key={key}
                        className={`sdm-tab ${activeTab === key ? "active" : ""}`}
                        onClick={() => setActiveTab(key as typeof activeTab)}
                      >
                        {icon}
                        <span>{label}</span>
                      </button>
                    ))}
                  </div>

                  {/* ========== 标签页内容 ========== */}
                  <div className="sdm-tab-content">
                    {activeTab === "overview" && (
                      <div className="sdm-overview">
                        <div className="sdm-section">
                          <div className="sdm-desc-card">
                            <p>{species.description || `${species.common_name}是一个神秘的物种，数据采集中...`}</p>
                          </div>
                        </div>

                        <div className="sdm-section">
                          <div className="sdm-section-header">
                            <BarChart3 size={16} />
                            <span>形态参数</span>
                          </div>
                          <div className="sdm-morph-cards">
                            {Object.entries(species.morphology_stats || {}).slice(0, 8).map(([key, value], index) => {
                              const numValue = value as number;
                              const { value: fmtValue, label: fmtLabel } = formatMorphology(key, numValue);
                              const colors = ['#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];
                              const color = colors[index % colors.length];
                              
                              return (
                                <div key={key} className="sdm-morph-card" style={{ '--card-color': color } as CustomCSS}>
                                  <div className="sdm-morph-card-value">{fmtValue}</div>
                                  <div className="sdm-morph-card-label">{fmtLabel}</div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {species.capabilities && species.capabilities.length > 0 && (
                          <div className="sdm-section">
                            <div className="sdm-section-header">
                              <Zap size={16} />
                              <span>特殊能力</span>
                            </div>
                            <div className="sdm-capabilities">
                              {species.capabilities.map(cap => (
                                <span key={cap} className="sdm-capability">
                                  <Star size={12} />
                                  {translate(cap)}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 营养级信息 */}
                        {species.trophic_level !== undefined && (
                          <div className="sdm-section">
                            <div className="sdm-section-header">
                              <Dna size={16} />
                              <span>生态位</span>
                            </div>
                            <div className="sdm-morph-cards">
                              <div className="sdm-morph-card" style={{ '--card-color': role.color } as CustomCSS}>
                                <div className="sdm-morph-card-value">{species.trophic_level.toFixed(2)}</div>
                                <div className="sdm-morph-card-label">营养级</div>
                              </div>
                              {species.taxonomic_rank && (
                                <div className="sdm-morph-card" style={{ '--card-color': '#8b5cf6' } as CustomCSS}>
                                  <div className="sdm-morph-card-value" style={{ fontSize: '1rem' }}>{species.taxonomic_rank}</div>
                                  <div className="sdm-morph-card-label">分类阶元</div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === "traits" && (
                      <div className="sdm-traits">
                        <div className="sdm-section">
                          <div className="sdm-trait-cards">
                            {Object.entries(species.abstract_traits || {}).map(([key, value]) => {
                              const numValue = value as number;
                              const getColor = () => {
                                if (numValue > 10) return '#f59e0b';
                                if (numValue < 5) return '#3b82f6';
                                return '#22c55e';
                              };
                              const color = getColor();
                              return (
                                <div key={key} className="sdm-trait-card">
                                  <div className="sdm-trait-card-header">
                                    <span className="sdm-trait-card-label">{translate(key)}</span>
                                    <span className="sdm-trait-card-level" style={{ color }}>
                                      {numValue.toFixed(1)}
                                    </span>
                                  </div>
                                  <div className="sdm-trait-bar">
                                    <div 
                                      className="sdm-trait-fill"
                                      style={{ 
                                        width: `${(numValue / 15) * 100}%`,
                                        background: color
                                      }}
                                    />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}

                    {activeTab === "organs" && (
                      <div className="sdm-organs">
                        <OrganismBlueprint species={species} />
                      </div>
                    )}

                    {activeTab === "ecology" && (
                      <div className="sdm-ecology">
                        {foodChainLoading ? (
                          <div className="sdm-loading" style={{ height: 150 }}>
                            <div className="sdm-spinner" />
                            <span>加载生态关系...</span>
                          </div>
                        ) : foodChainError ? (
                          <div className="sdm-ecology-empty" style={{ padding: 40, textAlign: 'center' }}>
                            <AlertTriangle size={24} style={{ marginBottom: 12, opacity: 0.5 }} />
                            <div style={{ marginBottom: 16 }}>{foodChainError}</div>
                            <button 
                              className="sdm-retry-btn"
                              onClick={() => {
                                setFoodChainError(null);
                                loadFoodChain();
                              }}
                            >
                              <RefreshCw size={14} /> 重试
                            </button>
                          </div>
                        ) : foodChain ? (
                          <>
                            {/* 食物来源 */}
                            <div className="sdm-ecology-card">
                              <div className="sdm-ecology-card-header">
                                <div className="sdm-ecology-card-icon">🍃</div>
                                <div>
                                  <div className="sdm-ecology-card-title">食物来源</div>
                                  <div className="sdm-ecology-card-subtitle">
                                    {foodChain.prey_chain.length > 0 
                                      ? `共 ${foodChain.prey_chain.length} 种猎物`
                                      : "无记录猎物"}
                                  </div>
                                </div>
                              </div>
                              {foodChain.prey_chain.length > 0 ? (
                                <div className="sdm-ecology-list">
                                  {foodChain.prey_chain.slice(0, 5).map((prey) => (
                                    <div key={prey.code} className="sdm-ecology-item">
                                      <Utensils size={14} style={{ color: '#22c55e' }} />
                                      <span className="sdm-ecology-item-name">{prey.name}</span>
                                      <span className="sdm-ecology-item-value prey">
                                        T{prey.trophic_level.toFixed(1)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="sdm-ecology-empty">
                                  {species.trophic_level && species.trophic_level < 1.5 
                                    ? "作为生产者，通过光合作用获取能量"
                                    : "暂无食物来源数据"}
                                </div>
                              )}
                            </div>

                            {/* 天敌 */}
                            <div className="sdm-ecology-card">
                              <div className="sdm-ecology-card-header">
                                <div className="sdm-ecology-card-icon">🦁</div>
                                <div>
                                  <div className="sdm-ecology-card-title">天敌</div>
                                  <div className="sdm-ecology-card-subtitle">
                                    {foodChain.predator_chain.length > 0 
                                      ? `共 ${foodChain.predator_chain.length} 种捕食者`
                                      : "无天敌记录"}
                                  </div>
                                </div>
                              </div>
                              {foodChain.predator_chain.length > 0 ? (
                                <div className="sdm-ecology-list">
                                  {foodChain.predator_chain.slice(0, 5).map((pred) => (
                                    <div key={pred.code} className="sdm-ecology-item">
                                      <Swords size={14} style={{ color: '#ef4444' }} />
                                      <span className="sdm-ecology-item-name">{pred.name}</span>
                                      <span className="sdm-ecology-item-value predator">
                                        T{pred.trophic_level.toFixed(1)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="sdm-ecology-empty">暂无天敌数据</div>
                              )}
                            </div>

                            {/* 互利共生 */}
                            {snapshot?.ecological_realism?.mutualism_partners && 
                             snapshot.ecological_realism.mutualism_partners.length > 0 && (
                              <div className="sdm-ecology-card">
                                <div className="sdm-ecology-card-header">
                                  <div className="sdm-ecology-card-icon">🤝</div>
                                  <div>
                                    <div className="sdm-ecology-card-title">互利共生</div>
                                    <div className="sdm-ecology-card-subtitle">
                                      收益: {snapshot.ecological_realism.mutualism_benefit > 0 ? '+' : ''}
                                      {(snapshot.ecological_realism.mutualism_benefit * 100).toFixed(1)}%
                                    </div>
                                  </div>
                                </div>
                                <div className="sdm-ecology-list">
                                  {snapshot.ecological_realism.mutualism_partners.map((code) => (
                                    <div key={code} className="sdm-ecology-item">
                                      <Handshake size={14} style={{ color: '#3b82f6' }} />
                                      <span className="sdm-ecology-item-name">{code}</span>
                                      <span className="sdm-ecology-item-value mutualist">共生</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* 生态指标 */}
                            <div className="sdm-ecology-card">
                              <div className="sdm-ecology-card-header">
                                <div className="sdm-ecology-card-icon">📊</div>
                                <div>
                                  <div className="sdm-ecology-card-title">生态指标</div>
                                </div>
                              </div>
                              <div className="sdm-morph-cards" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
                                <div className="sdm-morph-card" style={{ '--card-color': '#3b82f6' } as CustomCSS}>
                                  <div className="sdm-morph-card-value">
                                    {(foodChain.food_dependency * 100).toFixed(0)}%
                                  </div>
                                  <div className="sdm-morph-card-label">食物依赖度</div>
                                </div>
                                <div className="sdm-morph-card" style={{ '--card-color': '#ef4444' } as CustomCSS}>
                                  <div className="sdm-morph-card-value">
                                    {(foodChain.predation_pressure * 100).toFixed(0)}%
                                  </div>
                                  <div className="sdm-morph-card-label">被捕食压力</div>
                                </div>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="sdm-ecology-empty" style={{ padding: 40 }}>
                            暂无生态关系数据
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === "lineage" && (
                      <div className="sdm-lineage">
                        {species.parent_code && (
                          <div className="sdm-lineage-card">
                            <div className="sdm-lineage-icon">
                              <GitBranch size={18} />
                            </div>
                            <div className="sdm-lineage-content">
                              <span className="sdm-lineage-label">直系祖先</span>
                              <span className="sdm-lineage-code">{species.parent_code}</span>
                              <span className="sdm-lineage-turn">
                                诞生于第 <strong>{species.created_turn != null ? species.created_turn + 1 : '?'}</strong> 回合
                              </span>
                            </div>
                          </div>
                        )}

                        {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
                          <div className="sdm-lineage-card hybrid">
                            <div className="sdm-lineage-icon hybrid">
                              <GitMerge size={18} />
                            </div>
                            <div className="sdm-lineage-content">
                              <span className="sdm-lineage-label">杂交起源</span>
                              <div className="sdm-hybrid-parents">
                                {species.hybrid_parent_codes.map(code => (
                                  <span key={code} className="sdm-parent-badge">{code}</span>
                                ))}
                              </div>
                              <div className="sdm-fertility">
                                <span className="sdm-fertility-label">后代可育性</span>
                                <div className="sdm-fertility-bar">
                                  <div
                                    className="sdm-fertility-fill"
                                    style={{ width: `${(species.hybrid_fertility || 0) * 100}%` }}
                                  />
                                </div>
                                <span className="sdm-fertility-value">
                                  {((species.hybrid_fertility || 0) * 100).toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === "ai" && (
                      <div className="sdm-ai">
                        <SpeciesAITab
                          speciesCode={species.lineage_code}
                          speciesName={species.common_name}
                        />
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}

export default SpeciesDetailModal;
