import { useState, useEffect, useCallback } from "react";
import { 
  TrendingUp, TrendingDown, Minus, Skull, ArrowLeft, 
  RefreshCw, Edit2, Save, X, Zap, GitBranch, GitMerge,
  ChevronRight, ChevronDown, Eye, Search, BarChart3, Sparkles,
  Activity, Target, Dna, Crown, Shield, Heart, Leaf, Flame,
  Users, MapPin, Clock, Award, Star, Layers
} from "lucide-react";
import { 
  ResponsiveContainer, RadarChart, PolarGrid, 
  PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip,
  AreaChart, Area, XAxis, YAxis
} from "recharts";

import type { SpeciesDetail, SpeciesSnapshot } from "../services/api.types";
import { fetchSpeciesDetail, editSpecies } from "../services/api";
import { OrganismBlueprint } from "./OrganismBlueprint";
import { SpeciesAITab } from "./SpeciesAITab";

interface Props {
  speciesList: SpeciesSnapshot[];
  selectedSpeciesId: string | null;
  onSelectSpecies: (id: string | null) => void;
  onCollapse?: () => void;
  refreshTrigger?: number;
  previousPopulations?: Map<string, number>;
}

// 生态角色配置 - 更丰富的视觉
const roleConfig: Record<string, { 
  color: string; 
  gradient: string; 
  bgGradient: string;
  icon: string; 
  label: string;
  description: string;
}> = {
  producer: { 
    color: "#22c55e", 
    gradient: "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(22, 163, 74, 0.08) 100%)",
    icon: "🌿", 
    label: "生产者",
    description: "光合作用的基石"
  },
  herbivore: { 
    color: "#eab308", 
    gradient: "linear-gradient(135deg, #eab308 0%, #ca8a04 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(234, 179, 8, 0.15) 0%, rgba(202, 138, 4, 0.08) 100%)",
    icon: "🦌", 
    label: "食草动物",
    description: "植被的消费者"
  },
  carnivore: { 
    color: "#ef4444", 
    gradient: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(220, 38, 38, 0.08) 100%)",
    icon: "🦁", 
    label: "食肉动物",
    description: "顶级掠食者"
  },
  omnivore: { 
    color: "#f97316", 
    gradient: "linear-gradient(135deg, #f97316 0%, #ea580c 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(249, 115, 22, 0.15) 0%, rgba(234, 88, 12, 0.08) 100%)",
    icon: "🐻", 
    label: "杂食动物",
    description: "适应性强的觅食者"
  },
  decomposer: { 
    color: "#a855f7", 
    gradient: "linear-gradient(135deg, #a855f7 0%, #9333ea 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(147, 51, 234, 0.08) 100%)",
    icon: "🍄", 
    label: "分解者",
    description: "生态循环的清道夫"
  },
  scavenger: { 
    color: "#64748b", 
    gradient: "linear-gradient(135deg, #64748b 0%, #475569 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(100, 116, 139, 0.15) 0%, rgba(71, 85, 105, 0.08) 100%)",
    icon: "🦅", 
    label: "食腐动物",
    description: "资源的回收者"
  },
  unknown: { 
    color: "#3b82f6", 
    gradient: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)", 
    bgGradient: "linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(37, 99, 235, 0.08) 100%)",
    icon: "🧬", 
    label: "未知",
    description: "神秘的生命形式"
  }
};

// 状态配置
const statusConfig: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  alive: { label: "存活", color: "#22c55e", bg: "rgba(34, 197, 94, 0.12)", icon: <Heart size={12} /> },
  extinct: { label: "灭绝", color: "#94a3b8", bg: "rgba(148, 163, 184, 0.12)", icon: <Skull size={12} /> },
  endangered: { label: "濒危", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.12)", icon: <Shield size={12} /> }
};

// 趋势判断
function getTrend(currentPop: number, previousPop: number | undefined, status: string) {
  if (status === 'extinct') {
    return { icon: Skull, color: "#64748b", label: "灭绝", bg: "rgba(100, 116, 139, 0.12)", emoji: "💀" };
  }
  if (previousPop === undefined || previousPop === 0) {
    return { icon: Minus, color: "#94a3b8", label: "稳定", bg: "rgba(148, 163, 184, 0.12)", emoji: "➖" };
  }
  const changeRate = (currentPop - previousPop) / previousPop;
  if (changeRate > 0.5) return { icon: TrendingUp, color: "#22c55e", label: "繁荣", bg: "rgba(34, 197, 94, 0.15)", emoji: "🚀" };
  if (changeRate > 0.1) return { icon: TrendingUp, color: "#4ade80", label: "增长", bg: "rgba(74, 222, 128, 0.12)", emoji: "📈" };
  if (changeRate < -0.5) return { icon: TrendingDown, color: "#ef4444", label: "危急", bg: "rgba(239, 68, 68, 0.15)", emoji: "🔥" };
  if (changeRate < -0.2) return { icon: TrendingDown, color: "#f97316", label: "衰退", bg: "rgba(249, 115, 22, 0.12)", emoji: "📉" };
  if (changeRate < -0.1) return { icon: TrendingDown, color: "#fbbf24", label: "下降", bg: "rgba(251, 191, 36, 0.12)", emoji: "⚠️" };
  return { icon: Minus, color: "#94a3b8", label: "稳定", bg: "rgba(148, 163, 184, 0.12)", emoji: "➖" };
}

function formatPopulation(pop: number): string {
  if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
  if (pop >= 1_000) return `${(pop / 1_000).toFixed(1)}K`;
  return pop.toString();
}

function formatNumber(num: number, decimals = 1): string {
  return num.toFixed(decimals);
}

export function SpeciesPanel({ 
  speciesList, 
  selectedSpeciesId, 
  onSelectSpecies, 
  onCollapse,
  refreshTrigger = 0,
  previousPopulations = new Map()
}: Props) {
  const [speciesDetail, setSpeciesDetail] = useState<SpeciesDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ description: "", morphology: "", traits: "" });
  const [isSaving, setIsSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "traits" | "organs" | "lineage" | "ai">("overview");
  const [listFilter, setListFilter] = useState<"all" | "alive" | "extinct">("all");
  const [searchText, setSearchText] = useState("");
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["stats", "morphology"]));

  const selectedSnapshot = speciesList.find(s => s.lineage_code === selectedSpeciesId);

  const toggleSection = (section: string) => {
    const newSet = new Set(expandedSections);
    if (newSet.has(section)) {
      newSet.delete(section);
    } else {
      newSet.add(section);
    }
    setExpandedSections(newSet);
  };

  const loadDetail = useCallback(async (speciesId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await fetchSpeciesDetail(speciesId);
      setSpeciesDetail(detail);
    } catch (err: any) {
      setDetailError(err.message || "加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedSpeciesId) {
      loadDetail(selectedSpeciesId);
      setActiveTab("overview");
    } else {
      setSpeciesDetail(null);
    }
  }, [selectedSpeciesId, refreshTrigger, loadDetail]);

  const handleRefresh = () => {
    if (selectedSpeciesId) loadDetail(selectedSpeciesId);
  };

  const handleStartEdit = () => {
    if (!speciesDetail) return;
    setEditForm({
      description: speciesDetail.description || "",
      morphology: JSON.stringify(speciesDetail.morphology_stats, null, 2),
      traits: JSON.stringify(speciesDetail.abstract_traits, null, 2),
    });
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!speciesDetail) return;
    setIsSaving(true);
    try {
      const updated = await editSpecies(speciesDetail.lineage_code, {
        description: editForm.description,
        morphology: editForm.morphology,
        traits: editForm.traits,
      });
      setSpeciesDetail(updated);
      setIsEditing(false);
    } catch (error) {
      console.error("保存失败:", error);
      alert("保存物种信息失败");
    } finally {
      setIsSaving(false);
    }
  };

  const filteredList = speciesList.filter(s => {
    if (listFilter === "alive" && s.status !== "alive") return false;
    if (listFilter === "extinct" && s.status !== "extinct") return false;
    if (searchText) {
      const search = searchText.toLowerCase();
      return s.common_name.toLowerCase().includes(search) ||
             s.latin_name.toLowerCase().includes(search) ||
             s.lineage_code.toLowerCase().includes(search);
    }
    return true;
  }).sort((a, b) => b.population - a.population);

  const aliveCount = speciesList.filter(s => s.status === "alive").length;
  const extinctCount = speciesList.length - aliveCount;
  const totalPopulation = speciesList.reduce((sum, s) => sum + s.population, 0);

  // ========== 列表视图 ==========
  const renderListView = () => (
    <div className="sp-list-view">
      {/* 精美头部 */}
      <div className="sp-header">
        <div className="sp-header-bg" />
        <div className="sp-header-content">
          <div className="sp-header-icon">
            <Dna size={24} />
            <div className="sp-header-pulse" />
          </div>
          <div className="sp-header-text">
            <h2 className="sp-title">物种图鉴</h2>
            <p className="sp-subtitle">Species Compendium</p>
          </div>
          <div className="sp-header-stats">
            <div className="sp-stat alive">
              <Activity size={14} />
              <span className="sp-stat-value">{aliveCount}</span>
              <span className="sp-stat-label">存活</span>
            </div>
            {extinctCount > 0 && (
              <div className="sp-stat extinct">
                <Skull size={14} />
                <span className="sp-stat-value">{extinctCount}</span>
                <span className="sp-stat-label">灭绝</span>
              </div>
            )}
          </div>
          {onCollapse && (
            <button className="sp-collapse-btn" onClick={onCollapse}>
              <ChevronRight size={18} />
            </button>
          )}
        </div>
      </div>

      {/* 总种群概览条 */}
      <div className="sp-population-banner">
        <div className="sp-pop-icon">
          <Users size={16} />
        </div>
        <div className="sp-pop-info">
          <span className="sp-pop-label">总生物量 (kg)</span>
          <span className="sp-pop-value">{formatPopulation(totalPopulation)}</span>
        </div>
        <div className="sp-pop-bar">
          <div className="sp-pop-bar-fill" style={{ width: '100%' }} />
        </div>
      </div>

      {/* 搜索和筛选 */}
      <div className="sp-toolbar">
        <div className="sp-search">
          <Search size={14} />
          <input
            type="text"
            placeholder="搜索物种名称或代码..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          {searchText && (
            <button className="sp-search-clear" onClick={() => setSearchText("")}>
              <X size={12} />
            </button>
          )}
        </div>
        <div className="sp-filter-group">
          {[
            { key: "all", label: "全部", count: speciesList.length },
            { key: "alive", label: "存活", count: aliveCount },
            { key: "extinct", label: "灭绝", count: extinctCount }
          ].map(({ key, label, count }) => (
            <button
              key={key}
              className={`sp-filter-btn ${listFilter === key ? "active" : ""}`}
              onClick={() => setListFilter(key as any)}
            >
              <span>{label}</span>
              <span className="sp-filter-count">{count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 物种卡片列表 */}
      <div className="sp-card-list">
        {filteredList.map((s, index) => {
          const role = roleConfig[s.ecological_role?.toLowerCase()] || roleConfig.unknown;
          const prevPop = previousPopulations.get(s.lineage_code);
          const trend = getTrend(s.population, prevPop, s.status);
          const TrendIcon = trend.icon;
          const isExtinct = s.status === "extinct";
          const isSelected = s.lineage_code === selectedSpeciesId;
          const isHovered = hoveredItem === s.lineage_code;

          return (
            <div 
              key={s.lineage_code}
              className={`sp-card ${isSelected ? "selected" : ""} ${isExtinct ? "extinct" : ""} ${isHovered ? "hovered" : ""}`}
              onClick={() => onSelectSpecies(s.lineage_code)}
              onMouseEnter={() => setHoveredItem(s.lineage_code)}
              onMouseLeave={() => setHoveredItem(null)}
              style={{ 
                animationDelay: `${index * 40}ms`,
                '--role-color': role.color,
              } as React.CSSProperties}
            >
              {/* 背景装饰 */}
              <div className="sp-card-bg" style={{ background: role.bgGradient }} />
              <div className="sp-card-accent" style={{ background: role.gradient }} />
              
              {/* 角色图标 */}
              <div className="sp-card-avatar" style={{ 
                background: `${role.color}18`,
                borderColor: `${role.color}40`
              }}>
                <span className="sp-card-emoji">{role.icon}</span>
                {!isExtinct && s.population_share > 0.1 && (
                  <div className="sp-card-crown">
                    <Crown size={10} />
                  </div>
                )}
              </div>

              {/* 物种信息 */}
              <div className="sp-card-body">
                <div className="sp-card-header-row">
                  <span className="sp-card-name">{s.common_name}</span>
                  {isExtinct && <span className="sp-card-extinct-mark">†</span>}
                </div>
                <div className="sp-card-meta">
                  <span className="sp-card-latin">{s.latin_name}</span>
                </div>
                <div className="sp-card-tags">
                  <span className="sp-card-code">{s.lineage_code}</span>
                  <span className="sp-card-role" style={{ 
                    background: `${role.color}15`,
                    color: role.color,
                    borderColor: `${role.color}30`
                  }}>
                    {role.label}
                  </span>
                </div>
              </div>

              {/* 数据区 */}
              <div className="sp-card-data">
                <div className="sp-card-pop">
                  <span className="sp-card-pop-value">{formatPopulation(s.population)}</span>
                  <div className="sp-card-pop-bar">
                    <div 
                      className="sp-card-pop-fill" 
                      style={{ 
                        width: `${Math.min(s.population_share * 100 * 3, 100)}%`,
                        background: role.gradient
                      }} 
                    />
                  </div>
                </div>
                <div className="sp-card-trend" style={{ background: trend.bg, color: trend.color }}>
                  <TrendIcon size={12} />
                  <span>{trend.label}</span>
                </div>
              </div>

              {/* 选中箭头 */}
              <div className={`sp-card-arrow ${isSelected ? "visible" : ""}`}>
                <ChevronRight size={16} />
              </div>
            </div>
          );
        })}

        {filteredList.length === 0 && (
          <div className="sp-empty">
            <div className="sp-empty-icon">🔍</div>
            <h4>没有找到物种</h4>
            <p>尝试调整搜索条件或筛选器</p>
          </div>
        )}
      </div>
    </div>
  );

  // ========== 详情视图 ==========
  const renderDetailView = () => {
    if (!selectedSpeciesId) return null;

    if (detailLoading) {
      return (
        <div className="sp-detail-view">
          <div className="sp-detail-nav">
            <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回图鉴</span>
            </button>
          </div>
          <div className="sp-loading">
            <div className="sp-loading-spinner" />
            <span>正在加载物种档案...</span>
          </div>
        </div>
      );
    }

    if (detailError) {
      return (
        <div className="sp-detail-view">
          <div className="sp-detail-nav">
            <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回图鉴</span>
            </button>
          </div>
          <div className="sp-error">
            <div className="sp-error-icon">⚠️</div>
            <h4>加载失败</h4>
            <p>{detailError}</p>
            <button className="sp-retry-btn" onClick={handleRefresh}>
              <RefreshCw size={14} /> 重试
            </button>
          </div>
        </div>
      );
    }

    const species = speciesDetail;
    const snapshot = selectedSnapshot;
    if (!species) return null;

    // 编辑模式
    if (isEditing) {
      return (
        <div className="sp-detail-view">
          <div className="sp-detail-nav">
            <h3>编辑物种档案</h3>
            <button className="sp-close-btn" onClick={() => setIsEditing(false)}>
              <X size={18} />
            </button>
          </div>
          <div className="sp-edit-form">
            <div className="sp-form-field">
              <label>物种描述</label>
              <textarea
                rows={5}
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                placeholder="描述这个物种的特征、习性、演化历程..."
              />
            </div>
            <div className="sp-form-field">
              <label>
                形态参数 (JSON)
                <span className="sp-form-tag">高级</span>
              </label>
              <textarea
                rows={6}
                value={editForm.morphology}
                onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
                className="mono"
              />
            </div>
            <div className="sp-form-field">
              <label>
                抽象特征 (JSON)
                <span className="sp-form-tag">高级</span>
              </label>
              <textarea
                rows={6}
                value={editForm.traits}
                onChange={(e) => setEditForm({ ...editForm, traits: e.target.value })}
                className="mono"
              />
            </div>
          </div>
          <div className="sp-edit-actions">
            <button className="sp-btn-secondary" onClick={() => setIsEditing(false)}>取消</button>
            <button className="sp-btn-primary" onClick={handleSaveEdit} disabled={isSaving}>
              {isSaving ? <span className="sp-btn-spinner" /> : <Save size={14} />}
              <span>保存更改</span>
            </button>
          </div>
        </div>
      );
    }

    // 准备图表数据
    const chartData = [
      ...Object.entries(species.morphology_stats || {}).slice(0, 6).map(([k, v]) => ({ 
        subject: k, A: typeof v === 'number' ? v : 0, fullMark: 1 
      })),
    ];

    const role = roleConfig[snapshot?.ecological_role?.toLowerCase() || "unknown"] || roleConfig.unknown;
    const prevPop = previousPopulations.get(species.lineage_code);
    const trend = snapshot ? getTrend(snapshot.population, prevPop, snapshot.status) : null;
    const statusCfg = statusConfig[species.status] || statusConfig.alive;

    return (
      <div className="sp-detail-view">
        {/* 导航栏 */}
        <div className="sp-detail-nav">
          <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
            <ArrowLeft size={16} />
            <span>返回</span>
          </button>
          <div className="sp-nav-actions">
            <button className="sp-action-btn" onClick={handleRefresh} title="刷新数据">
              <RefreshCw size={14} />
            </button>
            <button className="sp-action-btn" onClick={handleStartEdit} title="编辑">
              <Edit2 size={14} />
            </button>
          </div>
        </div>

        {/* 物种英雄区 */}
        <div className="sp-hero" style={{ '--hero-color': role.color } as React.CSSProperties}>
          <div className="sp-hero-bg" style={{ background: role.bgGradient }} />
          <div className="sp-hero-pattern" />
          
          <div className="sp-hero-content">
            <div className="sp-hero-avatar" style={{ 
              background: role.gradient,
              boxShadow: `0 8px 32px ${role.color}50`
            }}>
              <span className="sp-hero-emoji">{role.icon}</span>
              <div className="sp-hero-avatar-ring" style={{ borderColor: role.color }} />
            </div>
            
            <div className="sp-hero-info">
              <div className="sp-hero-badges">
                <span className="sp-badge role" style={{ 
                  background: `${role.color}20`, 
                  color: role.color,
                  borderColor: `${role.color}40`
                }}>
                  {role.label}
                </span>
                <span className="sp-badge status" style={{ 
                  background: statusCfg.bg, 
                  color: statusCfg.color 
                }}>
                  {statusCfg.icon}
                  {statusCfg.label}
                </span>
                {species.genus_code && (
                  <span className="sp-badge genus">
                    <Layers size={10} />
                    {species.genus_code}
                  </span>
                )}
              </div>
              <h1 className="sp-hero-name">{species.common_name}</h1>
              <div className="sp-hero-meta">
                <span className="sp-meta-latin">{species.latin_name}</span>
                <span className="sp-meta-divider">•</span>
                <span className="sp-meta-code">{species.lineage_code}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 实时数据仪表板 */}
        {snapshot && (
          <div className="sp-dashboard">
            <div className="sp-dash-card">
              <div className="sp-dash-icon">
                <Users size={18} />
              </div>
              <div className="sp-dash-content">
                <span className="sp-dash-label">生物量 (kg)</span>
                <span className="sp-dash-value">{formatPopulation(snapshot.population)}</span>
              </div>
              <div className="sp-dash-sparkline" style={{ background: role.gradient }} />
            </div>

            <div className="sp-dash-card">
              <div className="sp-dash-icon death">
                <Activity size={18} />
              </div>
              <div className="sp-dash-content">
                <span className="sp-dash-label">死亡率</span>
                <span className="sp-dash-value" style={{ 
                  color: snapshot.death_rate > 0.3 ? '#ef4444' : snapshot.death_rate > 0.15 ? '#f59e0b' : '#22c55e'
                }}>
                  {(snapshot.death_rate * 100).toFixed(1)}%
                </span>
              </div>
            </div>

            <div className="sp-dash-card">
              <div className="sp-dash-icon">
                <Target size={18} />
              </div>
              <div className="sp-dash-content">
                <span className="sp-dash-label">生态占比</span>
                <span className="sp-dash-value">{(snapshot.population_share * 100).toFixed(1)}%</span>
              </div>
            </div>

            {trend && (
              <div className="sp-dash-card trend" style={{ borderColor: `${trend.color}40` }}>
                <div className="sp-dash-icon" style={{ color: trend.color }}>
                  <trend.icon size={18} />
                </div>
                <div className="sp-dash-content">
                  <span className="sp-dash-label">发展趋势</span>
                  <span className="sp-dash-value" style={{ color: trend.color }}>{trend.label}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 近期动态 */}
        {snapshot?.notes && snapshot.notes.length > 0 && (
          <div className="sp-events">
            <div className="sp-events-header">
              <Clock size={14} />
              <span>近期动态</span>
            </div>
            <div className="sp-events-list">
              {snapshot.notes.map((note, i) => (
                <div key={i} className="sp-event-item">
                  <div className="sp-event-dot" />
                  <span>{note}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 标签页导航 */}
        <div className="sp-tabs">
          {[
            { key: "overview", label: "总览", icon: <BarChart3 size={14} /> },
            { key: "traits", label: "特征", icon: <Target size={14} /> },
            { key: "organs", label: "器官", icon: <Eye size={14} /> },
            ...(species.hybrid_parent_codes?.length || species.parent_code 
              ? [{ key: "lineage", label: "血统", icon: <GitBranch size={14} /> }] 
              : []),
            { key: "ai", label: "AI 分析", icon: <Sparkles size={14} /> }
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              className={`sp-tab ${activeTab === key ? "active" : ""}`}
              onClick={() => setActiveTab(key as any)}
            >
              {icon}
              <span>{label}</span>
            </button>
          ))}
        </div>

        {/* 标签页内容 */}
        <div className="sp-content">
          {activeTab === "overview" && (
            <div className="sp-tab-content">
              {/* 描述卡片 */}
              <div className="sp-desc-card">
                <div className="sp-desc-icon">
                  <Leaf size={16} />
                </div>
                <p>{species.description || `${species.common_name}是一个神秘的物种，它的故事正等待被书写...`}</p>
              </div>

              {/* 形态参数 - 可折叠 */}
              <div className="sp-section">
                <button 
                  className="sp-section-header"
                  onClick={() => toggleSection('morphology')}
                >
                  <div className="sp-section-title">
                    <BarChart3 size={16} />
                    <span>形态参数</span>
                    <span className="sp-section-count">{Object.keys(species.morphology_stats || {}).length}</span>
                  </div>
                  <ChevronDown 
                    size={16} 
                    className={`sp-section-chevron ${expandedSections.has('morphology') ? 'expanded' : ''}`}
                  />
                </button>
                
                {expandedSections.has('morphology') && (
                  <div className="sp-section-body">
                    <div className="sp-morph-grid">
                      {Object.entries(species.morphology_stats || {}).slice(0, 8).map(([key, value]) => {
                        const numValue = value as number;
                        const percent = Math.min(Math.max(numValue * 100, 0), 100);
                        return (
                          <div key={key} className="sp-morph-item">
                            <div className="sp-morph-header">
                              <span className="sp-morph-label">{key}</span>
                              <span className="sp-morph-value">{numValue.toFixed(2)}</span>
                            </div>
                            <div className="sp-morph-bar">
                              <div 
                                className="sp-morph-fill" 
                                style={{ width: `${percent}%` }} 
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* 特殊能力 */}
              {species.capabilities && species.capabilities.length > 0 && (
                <div className="sp-section">
                  <div className="sp-section-header static">
                    <div className="sp-section-title">
                      <Zap size={16} />
                      <span>特殊能力</span>
                    </div>
                  </div>
                  <div className="sp-capabilities">
                    {species.capabilities.map(cap => (
                      <span key={cap} className="sp-capability">
                        <Star size={12} />
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "traits" && (
            <div className="sp-tab-content">
              {/* 雷达图 */}
              {chartData.length > 0 && (
                <div className="sp-radar-container">
                  <ResponsiveContainer width="100%" height={240}>
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                      <PolarGrid stroke="rgba(255,255,255,0.06)" />
                      <PolarAngleAxis 
                        dataKey="subject" 
                        tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }} 
                      />
                      <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
                      <Radar 
                        name="Stats" 
                        dataKey="A" 
                        stroke={role.color}
                        fill={role.color}
                        fillOpacity={0.2}
                        strokeWidth={2}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'rgba(15, 23, 42, 0.95)', 
                          borderColor: `${role.color}40`,
                          borderRadius: '12px',
                          boxShadow: '0 8px 32px rgba(0,0,0,0.4)'
                        }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* 抽象特质列表 */}
              <div className="sp-section">
                <div className="sp-section-header static">
                  <div className="sp-section-title">
                    <Target size={16} />
                    <span>抽象特质</span>
                    <span className="sp-section-hint">最高值 15</span>
                  </div>
                </div>
                <div className="sp-traits-list">
                  {Object.entries(species.abstract_traits || {}).map(([key, value]) => {
                    const numValue = value as number;
                    const percent = Math.min((numValue / 15) * 100, 100);
                    const getColor = () => {
                      if (numValue > 10) return '#f59e0b';
                      if (numValue < 5) return '#3b82f6';
                      return '#22c55e';
                    };
                    return (
                      <div key={key} className="sp-trait-row">
                        <span className="sp-trait-label">{key}</span>
                        <div className="sp-trait-bar">
                          <div 
                            className="sp-trait-fill" 
                            style={{ 
                              width: `${percent}%`, 
                              background: `linear-gradient(90deg, ${getColor()}, ${getColor()}80)`
                            }} 
                          />
                          <div className="sp-trait-markers">
                            {[3, 6, 9, 12].map(m => (
                              <div key={m} className="sp-trait-marker" style={{ left: `${(m/15)*100}%` }} />
                            ))}
                          </div>
                        </div>
                        <span className="sp-trait-value" style={{ color: getColor() }}>
                          {numValue.toFixed(1)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {activeTab === "organs" && (
            <div className="sp-tab-content">
              <div className="sp-organs-intro">
                <Eye size={16} />
                <span>生理结构与器官系统可视化</span>
              </div>
              <OrganismBlueprint species={species} />
            </div>
          )}

          {activeTab === "lineage" && (
            <div className="sp-tab-content">
              {species.parent_code && (
                <div className="sp-lineage-card">
                  <div className="sp-lineage-icon">
                    <GitBranch size={20} />
                  </div>
                  <div className="sp-lineage-content">
                    <span className="sp-lineage-label">直系祖先</span>
                    <span className="sp-lineage-code">{species.parent_code}</span>
                    <span className="sp-lineage-turn">
                      诞生于第 <strong>{species.created_turn != null ? species.created_turn + 1 : '?'}</strong> 回合
                    </span>
                  </div>
                </div>
              )}

              {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
                <div className="sp-lineage-card hybrid">
                  <div className="sp-lineage-icon hybrid">
                    <GitMerge size={20} />
                  </div>
                  <div className="sp-lineage-content">
                    <span className="sp-lineage-label">杂交起源</span>
                    <div className="sp-hybrid-parents">
                      {species.hybrid_parent_codes.map(code => (
                        <span key={code} className="sp-parent-badge">{code}</span>
                      ))}
                    </div>
                    <div className="sp-fertility">
                      <span className="sp-fertility-label">后代可育性</span>
                      <div className="sp-fertility-bar">
                        <div 
                          className="sp-fertility-fill" 
                          style={{ width: `${(species.hybrid_fertility || 0) * 100}%` }}
                        />
                      </div>
                      <span className="sp-fertility-value">
                        {((species.hybrid_fertility || 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "ai" && (
            <div className="sp-tab-content">
              <SpeciesAITab 
                speciesCode={species.lineage_code}
                speciesName={species.common_name}
              />
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="species-panel-v2">
      {selectedSpeciesId ? renderDetailView() : renderListView()}
      
      <style>{`
        .species-panel-v2 {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: linear-gradient(180deg, rgba(8, 12, 24, 0.98) 0%, rgba(12, 18, 32, 0.99) 100%);
          color: #e2e8f0;
          font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
          overflow: hidden;
        }

        /* ==================== 列表视图 ==================== */
        .sp-list-view {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }

        /* 头部 */
        .sp-header {
          position: relative;
          padding: 20px 16px;
          overflow: hidden;
        }

        .sp-header-bg {
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(139, 92, 246, 0.06) 100%);
          pointer-events: none;
        }

        .sp-header-content {
          position: relative;
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .sp-header-icon {
          position: relative;
          width: 48px;
          height: 48px;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.15));
          border: 1px solid rgba(59, 130, 246, 0.25);
          border-radius: 14px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #60a5fa;
        }

        .sp-header-pulse {
          position: absolute;
          inset: -4px;
          border: 2px solid rgba(59, 130, 246, 0.3);
          border-radius: 18px;
          animation: pulse-ring 2s ease-out infinite;
        }

        @keyframes pulse-ring {
          0% { transform: scale(0.95); opacity: 1; }
          100% { transform: scale(1.1); opacity: 0; }
        }

        .sp-header-text {
          flex: 1;
        }

        .sp-title {
          margin: 0;
          font-size: 1.25rem;
          font-weight: 700;
          background: linear-gradient(120deg, #f1f5f9, #60a5fa);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .sp-subtitle {
          margin: 0;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.35);
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }

        .sp-header-stats {
          display: flex;
          gap: 8px;
        }

        .sp-stat {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 0.8rem;
          font-weight: 600;
        }

        .sp-stat.alive {
          background: rgba(34, 197, 94, 0.12);
          color: #4ade80;
        }

        .sp-stat.extinct {
          background: rgba(148, 163, 184, 0.12);
          color: #94a3b8;
        }

        .sp-stat-value {
          font-family: 'JetBrains Mono', monospace;
        }

        .sp-stat-label {
          font-size: 0.7rem;
          opacity: 0.7;
        }

        .sp-collapse-btn {
          width: 32px;
          height: 32px;
          border: 1px solid rgba(59, 130, 246, 0.25);
          background: rgba(59, 130, 246, 0.08);
          border-radius: 10px;
          color: #60a5fa;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }

        .sp-collapse-btn:hover {
          background: rgba(59, 130, 246, 0.15);
          transform: translateX(2px);
        }

        /* 总种群条 */
        .sp-population-banner {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          margin: 0 12px 12px;
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(59, 130, 246, 0.05));
          border: 1px solid rgba(139, 92, 246, 0.15);
          border-radius: 12px;
        }

        .sp-pop-icon {
          width: 36px;
          height: 36px;
          background: rgba(139, 92, 246, 0.15);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #a78bfa;
        }

        .sp-pop-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .sp-pop-label {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .sp-pop-value {
          font-size: 1.1rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
          color: #c4b5fd;
        }

        .sp-pop-bar {
          flex: 1;
          height: 6px;
          background: rgba(139, 92, 246, 0.1);
          border-radius: 3px;
          overflow: hidden;
        }

        .sp-pop-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #8b5cf6, #a78bfa);
          border-radius: 3px;
        }

        /* 工具栏 */
        .sp-toolbar {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 0 12px 12px;
        }

        .sp-search {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 10px;
          transition: all 0.2s;
        }

        .sp-search:focus-within {
          border-color: rgba(59, 130, 246, 0.4);
          background: rgba(15, 23, 42, 1);
        }

        .sp-search input {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: #f1f5f9;
          font-size: 0.9rem;
        }

        .sp-search input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .sp-search svg {
          color: rgba(255, 255, 255, 0.3);
        }

        .sp-search-clear {
          width: 20px;
          height: 20px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 50%;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .sp-filter-group {
          display: flex;
          gap: 6px;
        }

        .sp-filter-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 8px 12px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-filter-btn:hover {
          background: rgba(255, 255, 255, 0.06);
          color: rgba(255, 255, 255, 0.8);
        }

        .sp-filter-btn.active {
          background: rgba(59, 130, 246, 0.15);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }

        .sp-filter-count {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          padding: 2px 6px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
        }

        .sp-filter-btn.active .sp-filter-count {
          background: rgba(59, 130, 246, 0.2);
        }

        /* 物种卡片列表 */
        .sp-card-list {
          flex: 1;
          overflow-y: auto;
          padding: 0 12px 12px;
        }

        .sp-card-list::-webkit-scrollbar {
          width: 5px;
        }

        .sp-card-list::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }

        .sp-card-list::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 3px;
        }

        /* 物种卡片 */
        .sp-card {
          position: relative;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px;
          margin-bottom: 8px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 14px;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          overflow: hidden;
          animation: cardSlideIn 0.35s ease forwards;
          opacity: 0;
        }

        @keyframes cardSlideIn {
          from {
            opacity: 0;
            transform: translateX(-12px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        .sp-card:hover, .sp-card.hovered {
          background: rgba(59, 130, 246, 0.06);
          border-color: var(--role-color, rgba(59, 130, 246, 0.3));
          transform: translateX(4px);
        }

        .sp-card.selected {
          background: rgba(59, 130, 246, 0.1);
          border-color: rgba(59, 130, 246, 0.4);
          box-shadow: 0 0 20px rgba(59, 130, 246, 0.15);
        }

        .sp-card.extinct {
          opacity: 0.55;
        }

        .sp-card.extinct:hover {
          opacity: 0.75;
        }

        .sp-card-bg {
          position: absolute;
          inset: 0;
          opacity: 0;
          transition: opacity 0.3s;
        }

        .sp-card:hover .sp-card-bg,
        .sp-card.selected .sp-card-bg {
          opacity: 1;
        }

        .sp-card-accent {
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 3px;
          border-radius: 3px 0 0 3px;
        }

        .sp-card-avatar {
          position: relative;
          width: 44px;
          height: 44px;
          border: 1px solid;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          margin-left: 4px;
        }

        .sp-card-emoji {
          font-size: 1.3rem;
        }

        .sp-card-crown {
          position: absolute;
          top: -6px;
          right: -6px;
          width: 18px;
          height: 18px;
          background: linear-gradient(135deg, #fbbf24, #f59e0b);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #0f172a;
          box-shadow: 0 2px 6px rgba(251, 191, 36, 0.4);
        }

        .sp-card-body {
          flex: 1;
          min-width: 0;
        }

        .sp-card-header-row {
          display: flex;
          align-items: center;
          gap: 4px;
          margin-bottom: 3px;
        }

        .sp-card-name {
          font-weight: 600;
          font-size: 0.95rem;
          color: #f1f5f9;
        }

        .sp-card-extinct-mark {
          color: #94a3b8;
          font-size: 0.75rem;
        }

        .sp-card-meta {
          margin-bottom: 6px;
        }

        .sp-card-latin {
          font-size: 0.75rem;
          font-style: italic;
          color: rgba(255, 255, 255, 0.4);
        }

        .sp-card-tags {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .sp-card-code {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          padding: 2px 6px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          color: rgba(255, 255, 255, 0.5);
        }

        .sp-card-role {
          font-size: 0.65rem;
          padding: 2px 8px;
          border-radius: 10px;
          border: 1px solid;
          font-weight: 500;
        }

        .sp-card-data {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 6px;
        }

        .sp-card-pop {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 4px;
        }

        .sp-card-pop-value {
          font-weight: 700;
          font-size: 1rem;
          font-family: 'JetBrains Mono', monospace;
        }

        .sp-card-pop-bar {
          width: 50px;
          height: 3px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 2px;
          overflow: hidden;
        }

        .sp-card-pop-fill {
          height: 100%;
          border-radius: 2px;
        }

        .sp-card-trend {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          border-radius: 10px;
          font-size: 0.65rem;
          font-weight: 600;
        }

        .sp-card-arrow {
          opacity: 0;
          color: #60a5fa;
          transition: opacity 0.2s, transform 0.2s;
        }

        .sp-card-arrow.visible {
          opacity: 1;
          transform: translateX(4px);
        }

        /* 空状态 */
        .sp-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 48px 24px;
          text-align: center;
        }

        .sp-empty-icon {
          font-size: 3rem;
          margin-bottom: 16px;
          opacity: 0.5;
        }

        .sp-empty h4 {
          margin: 0 0 8px;
          color: rgba(255, 255, 255, 0.7);
        }

        .sp-empty p {
          margin: 0;
          color: rgba(255, 255, 255, 0.4);
          font-size: 0.9rem;
        }

        /* ==================== 详情视图 ==================== */
        .sp-detail-view {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }

        .sp-detail-nav {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .sp-back-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 14px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.8);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-back-btn:hover {
          background: rgba(255, 255, 255, 0.1);
          color: white;
        }

        .sp-nav-actions {
          display: flex;
          gap: 8px;
        }

        .sp-action-btn {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-action-btn:hover {
          background: rgba(59, 130, 246, 0.15);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }

        /* 加载/错误状态 */
        .sp-loading, .sp-error {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
          color: rgba(255, 255, 255, 0.5);
        }

        .sp-loading-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid rgba(59, 130, 246, 0.2);
          border-top-color: #3b82f6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .sp-error-icon {
          font-size: 2.5rem;
        }

        .sp-error h4 {
          margin: 0;
          color: rgba(255, 255, 255, 0.8);
        }

        .sp-error p {
          margin: 0;
          color: rgba(255, 255, 255, 0.5);
        }

        .sp-retry-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 20px;
          background: rgba(59, 130, 246, 0.15);
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 10px;
          color: #60a5fa;
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-retry-btn:hover {
          background: rgba(59, 130, 246, 0.25);
        }

        /* 英雄区 */
        .sp-hero {
          position: relative;
          padding: 24px 20px;
          overflow: hidden;
        }

        .sp-hero-bg {
          position: absolute;
          inset: 0;
        }

        .sp-hero-pattern {
          position: absolute;
          inset: 0;
          background-image: radial-gradient(circle at 20% 80%, var(--hero-color, #3b82f6) 0%, transparent 50%);
          opacity: 0.1;
        }

        .sp-hero-content {
          position: relative;
          display: flex;
          gap: 18px;
        }

        .sp-hero-avatar {
          position: relative;
          width: 72px;
          height: 72px;
          border-radius: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .sp-hero-emoji {
          font-size: 2.2rem;
        }

        .sp-hero-avatar-ring {
          position: absolute;
          inset: -4px;
          border: 2px solid;
          border-radius: 22px;
          opacity: 0.3;
        }

        .sp-hero-info {
          flex: 1;
          min-width: 0;
        }

        .sp-hero-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 10px;
        }

        .sp-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 0.7rem;
          font-weight: 600;
          border: 1px solid transparent;
        }

        .sp-badge.role {
          border-width: 1px;
          border-style: solid;
        }

        .sp-badge.genus {
          background: rgba(59, 130, 246, 0.12);
          color: #60a5fa;
        }

        .sp-hero-name {
          margin: 0 0 6px;
          font-size: 1.6rem;
          font-weight: 700;
          color: #f8fafc;
          line-height: 1.2;
        }

        .sp-hero-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .sp-meta-latin {
          font-style: italic;
        }

        .sp-meta-divider {
          opacity: 0.3;
        }

        .sp-meta-code {
          font-family: 'JetBrains Mono', monospace;
          padding: 2px 8px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 6px;
        }

        /* 仪表板 */
        .sp-dashboard {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 10px;
          padding: 16px;
          background: rgba(0, 0, 0, 0.2);
        }

        .sp-dash-card {
          position: relative;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          overflow: hidden;
        }

        .sp-dash-card.trend {
          border-left-width: 3px;
        }

        .sp-dash-icon {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          color: #64748b;
        }

        .sp-dash-content {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .sp-dash-label {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .sp-dash-value {
          font-size: 1.1rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
        }

        .sp-dash-sparkline {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 3px;
          opacity: 0.5;
        }

        /* 近期动态 */
        .sp-events {
          padding: 14px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .sp-events-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .sp-events-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .sp-event-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .sp-event-dot {
          width: 6px;
          height: 6px;
          background: #60a5fa;
          border-radius: 50%;
          margin-top: 6px;
          flex-shrink: 0;
        }

        /* 标签页 */
        .sp-tabs {
          display: flex;
          gap: 4px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          overflow-x: auto;
        }

        .sp-tab {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 10px 16px;
          background: transparent;
          border: none;
          border-radius: 10px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
        }

        .sp-tab:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }

        .sp-tab.active {
          background: rgba(59, 130, 246, 0.12);
          color: #60a5fa;
        }

        /* 内容区 */
        .sp-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        .sp-content::-webkit-scrollbar {
          width: 5px;
        }

        .sp-content::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }

        .sp-content::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 3px;
        }

        .sp-tab-content {
          animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* 描述卡片 */
        .sp-desc-card {
          display: flex;
          gap: 14px;
          padding: 16px;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.06), rgba(139, 92, 246, 0.04));
          border: 1px solid rgba(59, 130, 246, 0.12);
          border-radius: 14px;
          margin-bottom: 16px;
        }

        .sp-desc-icon {
          width: 36px;
          height: 36px;
          background: rgba(59, 130, 246, 0.1);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #60a5fa;
          flex-shrink: 0;
        }

        .sp-desc-card p {
          margin: 0;
          font-size: 0.9rem;
          line-height: 1.7;
          color: rgba(255, 255, 255, 0.8);
        }

        /* 折叠区域 */
        .sp-section {
          margin-bottom: 16px;
        }

        .sp-section-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          padding: 12px 14px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          color: rgba(255, 255, 255, 0.8);
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-section-header.static {
          cursor: default;
          margin-bottom: 12px;
        }

        .sp-section-header:not(.static):hover {
          background: rgba(255, 255, 255, 0.05);
        }

        .sp-section-title {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.9rem;
          font-weight: 600;
        }

        .sp-section-count {
          padding: 2px 8px;
          background: rgba(59, 130, 246, 0.15);
          border-radius: 10px;
          font-size: 0.7rem;
          color: #60a5fa;
        }

        .sp-section-hint {
          font-size: 0.7rem;
          font-weight: 400;
          color: rgba(255, 255, 255, 0.4);
          margin-left: auto;
        }

        .sp-section-chevron {
          transition: transform 0.2s;
          color: rgba(255, 255, 255, 0.4);
        }

        .sp-section-chevron.expanded {
          transform: rotate(180deg);
        }

        .sp-section-body {
          margin-top: 12px;
          animation: slideDown 0.2s ease;
        }

        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* 形态网格 */
        .sp-morph-grid {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .sp-morph-item {
          padding: 12px;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 10px;
        }

        .sp-morph-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .sp-morph-label {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .sp-morph-value {
          font-size: 0.8rem;
          font-family: 'JetBrains Mono', monospace;
          color: rgba(255, 255, 255, 0.8);
        }

        .sp-morph-bar {
          height: 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 3px;
          overflow: hidden;
        }

        .sp-morph-fill {
          height: 100%;
          background: linear-gradient(90deg, #3b82f6, #60a5fa);
          border-radius: 3px;
          transition: width 0.4s ease;
        }

        /* 能力标签 */
        .sp-capabilities {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          padding: 12px 0;
        }

        .sp-capability {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: linear-gradient(135deg, rgba(251, 191, 36, 0.12), rgba(245, 158, 11, 0.08));
          border: 1px solid rgba(251, 191, 36, 0.25);
          border-radius: 20px;
          font-size: 0.8rem;
          color: #fbbf24;
        }

        /* 雷达图容器 */
        .sp-radar-container {
          padding: 20px;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 14px;
          margin-bottom: 16px;
        }

        /* 特质列表 */
        .sp-traits-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .sp-trait-row {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .sp-trait-label {
          width: 80px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .sp-trait-bar {
          flex: 1;
          position: relative;
          height: 10px;
          background: rgba(255, 255, 255, 0.06);
          border-radius: 5px;
          overflow: hidden;
        }

        .sp-trait-fill {
          height: 100%;
          border-radius: 5px;
          transition: width 0.4s ease;
        }

        .sp-trait-markers {
          position: absolute;
          inset: 0;
        }

        .sp-trait-marker {
          position: absolute;
          top: 0;
          bottom: 0;
          width: 1px;
          background: rgba(255, 255, 255, 0.15);
        }

        .sp-trait-value {
          width: 40px;
          text-align: right;
          font-size: 0.85rem;
          font-weight: 600;
          font-family: 'JetBrains Mono', monospace;
        }

        /* 器官介绍 */
        .sp-organs-intro {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px;
          background: rgba(59, 130, 246, 0.08);
          border: 1px solid rgba(59, 130, 246, 0.2);
          border-radius: 12px;
          font-size: 0.85rem;
          color: #60a5fa;
          margin-bottom: 16px;
        }

        /* 血统卡片 */
        .sp-lineage-card {
          display: flex;
          gap: 16px;
          padding: 18px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          margin-bottom: 12px;
        }

        .sp-lineage-card.hybrid {
          background: rgba(168, 85, 247, 0.06);
          border-color: rgba(168, 85, 247, 0.15);
        }

        .sp-lineage-icon {
          width: 44px;
          height: 44px;
          background: rgba(59, 130, 246, 0.1);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #60a5fa;
          flex-shrink: 0;
        }

        .sp-lineage-icon.hybrid {
          background: rgba(168, 85, 247, 0.15);
          color: #a855f7;
        }

        .sp-lineage-content {
          flex: 1;
        }

        .sp-lineage-label {
          display: block;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 6px;
        }

        .sp-lineage-code {
          display: block;
          font-size: 1.3rem;
          font-family: 'JetBrains Mono', monospace;
          font-weight: 600;
          color: #f1f5f9;
        }

        .sp-lineage-turn {
          display: block;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
          margin-top: 6px;
        }

        .sp-lineage-turn strong {
          color: #60a5fa;
        }

        .sp-hybrid-parents {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 14px;
        }

        .sp-parent-badge {
          padding: 6px 14px;
          background: rgba(168, 85, 247, 0.12);
          border: 1px solid rgba(168, 85, 247, 0.25);
          border-radius: 10px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          color: #c4b5fd;
        }

        .sp-fertility {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .sp-fertility-label {
          font-size: 0.75rem;
          color: rgba(168, 85, 247, 0.7);
        }

        .sp-fertility-bar {
          flex: 1;
          height: 8px;
          background: rgba(168, 85, 247, 0.15);
          border-radius: 4px;
          overflow: hidden;
        }

        .sp-fertility-fill {
          height: 100%;
          background: linear-gradient(90deg, #a855f7, #c084fc);
          border-radius: 4px;
        }

        .sp-fertility-value {
          font-size: 0.9rem;
          font-weight: 600;
          font-family: 'JetBrains Mono', monospace;
          color: #c084fc;
        }

        /* 编辑表单 */
        .sp-edit-form {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        .sp-form-field {
          margin-bottom: 20px;
        }

        .sp-form-field label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 8px;
        }

        .sp-form-tag {
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 0.65rem;
          text-transform: uppercase;
          background: rgba(251, 191, 36, 0.15);
          color: #fbbf24;
        }

        .sp-form-field textarea {
          width: 100%;
          padding: 12px 14px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          color: #f1f5f9;
          font-size: 0.9rem;
          resize: vertical;
          transition: all 0.2s;
        }

        .sp-form-field textarea.mono {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
        }

        .sp-form-field textarea:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
          background: rgba(15, 23, 42, 1);
        }

        .sp-edit-actions {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
          padding: 16px;
          background: rgba(0, 0, 0, 0.2);
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .sp-btn-secondary, .sp-btn-primary {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 20px;
          border-radius: 12px;
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-btn-secondary {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: rgba(255, 255, 255, 0.7);
        }

        .sp-btn-secondary:hover {
          background: rgba(255, 255, 255, 0.05);
          color: white;
        }

        .sp-btn-primary {
          background: linear-gradient(135deg, #3b82f6, #2563eb);
          border: none;
          color: white;
          font-weight: 600;
        }

        .sp-btn-primary:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35);
        }

        .sp-btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }

        .sp-btn-spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        .sp-close-btn {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: transparent;
          border: none;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          transition: all 0.2s;
        }

        .sp-close-btn:hover {
          color: #ef4444;
        }
      `}</style>
    </div>
  );
}
