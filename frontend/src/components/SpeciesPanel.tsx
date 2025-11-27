import { useState, useEffect, useCallback } from "react";
import { 
  TrendingUp, TrendingDown, Minus, Skull, ArrowLeft, 
  RefreshCw, Edit2, Save, X, Zap, GitBranch, GitMerge,
  ChevronRight, Eye, Search, Filter, BarChart3
} from "lucide-react";
import { 
  ResponsiveContainer, RadarChart, PolarGrid, 
  PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip
} from "recharts";

import type { SpeciesDetail, SpeciesSnapshot } from "../services/api.types";
import { fetchSpeciesDetail, editSpecies } from "../services/api";
import { OrganismBlueprint } from "./OrganismBlueprint";

interface Props {
  speciesList: SpeciesSnapshot[];
  selectedSpeciesId: string | null;
  onSelectSpecies: (id: string | null) => void;
  onCollapse?: () => void;
  refreshTrigger?: number;
}

// 生态角色颜色和图标映射
const roleConfig: Record<string, { color: string; gradient: string; icon: string; label: string }> = {
  producer: { color: "#10b981", gradient: "linear-gradient(135deg, #10b981, #059669)", icon: "🌿", label: "生产者" },
  herbivore: { color: "#fbbf24", gradient: "linear-gradient(135deg, #fbbf24, #f59e0b)", icon: "🦌", label: "食草动物" },
  carnivore: { color: "#f43f5e", gradient: "linear-gradient(135deg, #f43f5e, #e11d48)", icon: "🦁", label: "食肉动物" },
  omnivore: { color: "#f97316", gradient: "linear-gradient(135deg, #f97316, #ea580c)", icon: "🐻", label: "杂食动物" },
  decomposer: { color: "#a855f7", gradient: "linear-gradient(135deg, #a855f7, #9333ea)", icon: "🍄", label: "分解者" },
  scavenger: { color: "#64748b", gradient: "linear-gradient(135deg, #64748b, #475569)", icon: "🦅", label: "食腐动物" },
  unknown: { color: "#3b82f6", gradient: "linear-gradient(135deg, #3b82f6, #2563eb)", icon: "🧬", label: "未知" }
};

// 状态映射
const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  alive: { label: "存活", color: "#22c55e", bg: "rgba(34, 197, 94, 0.15)" },
  extinct: { label: "灭绝", color: "#ef4444", bg: "rgba(239, 68, 68, 0.15)" },
  endangered: { label: "濒危", color: "#fbbf24", bg: "rgba(251, 191, 36, 0.15)" }
};

// 趋势判断
function getTrend(deathRate: number, status: string) {
  if (status === 'extinct') return { icon: Skull, color: "#64748b", label: "灭绝", bg: "rgba(100, 116, 139, 0.15)" };
  if (deathRate > 0.15) return { icon: TrendingDown, color: "#ef4444", label: "危急", bg: "rgba(239, 68, 68, 0.15)" };
  if (deathRate > 0.08) return { icon: TrendingDown, color: "#f97316", label: "衰退", bg: "rgba(249, 115, 22, 0.15)" };
  if (deathRate < 0.03) return { icon: TrendingUp, color: "#22c55e", label: "繁荣", bg: "rgba(34, 197, 94, 0.15)" };
  return { icon: Minus, color: "#94a3b8", label: "稳定", bg: "rgba(148, 163, 184, 0.15)" };
}

// 格式化人口数量
function formatPopulation(pop: number): string {
  if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
  if (pop >= 1_000) return `${(pop / 1_000).toFixed(1)}K`;
  return pop.toString();
}

export function SpeciesPanel({ 
  speciesList, 
  selectedSpeciesId, 
  onSelectSpecies, 
  onCollapse,
  refreshTrigger = 0
}: Props) {
  // 详情数据
  const [speciesDetail, setSpeciesDetail] = useState<SpeciesDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  
  // 编辑状态
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ description: "", morphology: "", traits: "" });
  const [isSaving, setIsSaving] = useState(false);
  
  // UI 状态
  const [activeTab, setActiveTab] = useState<"overview" | "traits" | "organs" | "lineage">("overview");
  const [listFilter, setListFilter] = useState<"all" | "alive" | "extinct">("all");
  const [searchText, setSearchText] = useState("");
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);

  // 从列表中找到选中物种的快照数据
  const selectedSnapshot = speciesList.find(s => s.lineage_code === selectedSpeciesId);

  // 加载物种详情
  const loadDetail = useCallback(async (speciesId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await fetchSpeciesDetail(speciesId);
      setSpeciesDetail(detail);
    } catch (err: any) {
      setDetailError(err.message || "加载失败");
      console.error("加载物种详情失败:", err);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // 当选中物种变化或刷新触发器变化时，重新加载详情
  useEffect(() => {
    if (selectedSpeciesId) {
      loadDetail(selectedSpeciesId);
    } else {
      setSpeciesDetail(null);
    }
  }, [selectedSpeciesId, refreshTrigger, loadDetail]);

  // 手动刷新
  const handleRefresh = () => {
    if (selectedSpeciesId) {
      loadDetail(selectedSpeciesId);
    }
  };

  // 编辑处理
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

  // 筛选后的列表
  const filteredList = speciesList.filter(s => {
    // 状态筛选
    if (listFilter === "alive" && s.status !== "alive") return false;
    if (listFilter === "extinct" && s.status !== "extinct") return false;
    
    // 搜索筛选
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

  // 渲染列表视图
  const renderListView = () => (
    <div className="species-panel-list">
      {/* 头部 */}
      <div className="panel-header">
        <div className="header-left">
          <div className="header-icon-wrapper">
            <span className="header-icon">🧬</span>
          </div>
          <div className="header-text">
            <h3>物种总览</h3>
            <span className="header-subtitle">Species Overview</span>
          </div>
        </div>
        <div className="header-right">
          <div className="header-stats">
            <div className="stat-chip alive">
              <span className="stat-dot" />
              <span>{aliveCount}</span>
            </div>
            {extinctCount > 0 && (
              <div className="stat-chip extinct">
                <span className="stat-dot" />
                <span>{extinctCount}</span>
              </div>
            )}
          </div>
          {onCollapse && (
            <button className="btn-collapse" onClick={onCollapse} title="折叠面板">
              <ChevronRight size={16} />
            </button>
          )}
        </div>
      </div>

      {/* 搜索和筛选 */}
      <div className="panel-toolbar">
        <div className="search-box">
          <Search size={14} className="search-icon" />
          <input
            type="text"
            placeholder="搜索物种..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          {searchText && (
            <button className="clear-btn" onClick={() => setSearchText("")}>×</button>
          )}
        </div>
        <div className="filter-tabs">
          {[
            { key: "all", label: "全部" },
            { key: "alive", label: "存活" },
            { key: "extinct", label: "灭绝" }
          ].map(({ key, label }) => (
            <button
              key={key}
              className={`filter-tab ${listFilter === key ? "active" : ""}`}
              onClick={() => setListFilter(key as any)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 物种列表 */}
      <div className="species-list">
        {filteredList.map((s, index) => {
          const role = roleConfig[s.ecological_role?.toLowerCase()] || roleConfig.unknown;
          const trend = getTrend(s.death_rate, s.status);
          const TrendIcon = trend.icon;
          const isExtinct = s.status === "extinct";
          const isSelected = s.lineage_code === selectedSpeciesId;
          const isHovered = hoveredItem === s.lineage_code;

          return (
            <div 
              key={s.lineage_code}
              className={`species-card ${isSelected ? "selected" : ""} ${isExtinct ? "extinct" : ""}`}
              onClick={() => onSelectSpecies(s.lineage_code)}
              onMouseEnter={() => setHoveredItem(s.lineage_code)}
              onMouseLeave={() => setHoveredItem(null)}
              style={{ 
                animationDelay: `${index * 30}ms`,
                borderColor: isSelected || isHovered ? role.color : "transparent"
              }}
            >
              {/* 角色指示条 */}
              <div className="role-indicator" style={{ background: role.gradient }} />
              
              {/* 角色图标 */}
              <div className="role-icon-wrapper" style={{ 
                background: `${role.color}15`,
                borderColor: `${role.color}30`
              }}>
                <span className="role-emoji">{role.icon}</span>
              </div>

              {/* 物种信息 */}
              <div className="species-info">
                <div className="species-name">
                  <span className="name-text">{s.common_name}</span>
                  {isExtinct && <span className="extinct-mark">†</span>}
                </div>
                <div className="species-meta">
                  <span className="latin-name">{s.latin_name}</span>
                  <span className="lineage-code">{s.lineage_code}</span>
                </div>
              </div>

              {/* 数据区域 */}
              <div className="species-data">
                <div className="population-display">
                  <span className="pop-value">{formatPopulation(s.population)}</span>
                  <div className="pop-bar">
                    <div 
                      className="pop-fill" 
                      style={{ 
                        width: `${Math.min(s.population_share * 100 * 2, 100)}%`,
                        background: role.color
                      }} 
                    />
                  </div>
                </div>
                <div className="trend-badge" style={{ background: trend.bg, color: trend.color }}>
                  <TrendIcon size={10} />
                  <span>{trend.label}</span>
                </div>
              </div>

              {/* 选中指示器 */}
              <div className={`select-arrow ${isSelected ? "visible" : ""}`}>
                <ChevronRight size={16} />
              </div>
            </div>
          );
        })}

        {filteredList.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">🔍</div>
            <div className="empty-text">没有找到物种</div>
          </div>
        )}
      </div>
    </div>
  );

  // 渲染详情视图
  const renderDetailView = () => {
    if (!selectedSpeciesId) return null;

    // 加载中
    if (detailLoading) {
      return (
        <div className="species-panel-detail">
          <div className="detail-nav">
            <button className="btn-back" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回列表</span>
            </button>
          </div>
          <div className="loading-state">
            <div className="loading-spinner" />
            <span>正在加载物种数据...</span>
          </div>
        </div>
      );
    }

    // 错误
    if (detailError) {
      return (
        <div className="species-panel-detail">
          <div className="detail-nav">
            <button className="btn-back" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回列表</span>
            </button>
          </div>
          <div className="error-state">
            <span className="error-icon">❌</span>
            <span className="error-text">{detailError}</span>
            <button className="btn-retry" onClick={handleRefresh}>
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
        <div className="species-panel-detail">
          <div className="detail-nav">
            <h3>编辑物种数据</h3>
            <button className="btn-close" onClick={() => setIsEditing(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="edit-form">
            <div className="form-field">
              <label>物种描述</label>
              <textarea
                rows={5}
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                placeholder="描述这个物种的特征、习性等..."
              />
            </div>
            <div className="form-field">
              <label>
                形态参数 (JSON)
                <span className="label-tag advanced">高级</span>
              </label>
              <textarea
                rows={6}
                value={editForm.morphology}
                onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
                className="mono"
              />
            </div>
            <div className="form-field">
              <label>
                抽象特征 (JSON)
                <span className="label-tag advanced">高级</span>
              </label>
              <textarea
                rows={6}
                value={editForm.traits}
                onChange={(e) => setEditForm({ ...editForm, traits: e.target.value })}
                className="mono"
              />
            </div>
          </div>
          <div className="edit-actions">
            <button className="btn-secondary" onClick={() => setIsEditing(false)}>取消</button>
            <button className="btn-primary" onClick={handleSaveEdit} disabled={isSaving}>
              {isSaving ? <span className="btn-spinner" /> : <Save size={14} />}
              <span>保存更改</span>
            </button>
          </div>
        </div>
      );
    }

    // 准备雷达图数据
    const chartData = [
      ...Object.entries(species.morphology_stats || {}).map(([k, v]) => ({ 
        subject: k, A: typeof v === 'number' ? v : 0, fullMark: 1 
      })),
      ...Object.entries(species.abstract_traits || {}).map(([k, v]) => ({ 
        subject: k, A: typeof v === 'number' ? v : 0, fullMark: 15 
      }))
    ].slice(0, 6);

    const role = roleConfig[snapshot?.ecological_role?.toLowerCase() || "unknown"] || roleConfig.unknown;
    const trend = snapshot ? getTrend(snapshot.death_rate, snapshot.status) : null;
    const statusCfg = statusConfig[species.status] || statusConfig.alive;

    return (
      <div className="species-panel-detail">
        {/* 导航栏 */}
        <div className="detail-nav">
          <button className="btn-back" onClick={() => onSelectSpecies(null)}>
            <ArrowLeft size={16} />
            <span>返回</span>
          </button>
          <div className="nav-actions">
            <button className="btn-action" onClick={handleRefresh} title="刷新数据">
              <RefreshCw size={14} />
            </button>
            <button className="btn-action" onClick={handleStartEdit} title="编辑">
              <Edit2 size={14} />
            </button>
          </div>
        </div>

        {/* 物种头部卡片 */}
        <div className="species-hero">
          <div className="hero-bg" style={{ background: `${role.color}08` }} />
          <div className="hero-content">
            <div className="hero-icon" style={{ 
              background: role.gradient,
              boxShadow: `0 8px 24px ${role.color}40`
            }}>
              <span>{role.icon}</span>
            </div>
            <div className="hero-info">
              <div className="hero-badges">
                <span className="badge role" style={{ background: `${role.color}20`, color: role.color }}>
                  {role.label}
                </span>
                <span className="badge status" style={{ background: statusCfg.bg, color: statusCfg.color }}>
                  {statusCfg.label}
                </span>
                {species.genus_code && (
                  <span className="badge genus">{species.genus_code}</span>
                )}
              </div>
              <h2 className="hero-name">{species.common_name}</h2>
              <div className="hero-meta">
                <span className="meta-latin">{species.latin_name}</span>
                <span className="meta-divider">·</span>
                <span className="meta-code">{species.lineage_code}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 实时数据卡片 */}
        {snapshot && (
          <div className="live-stats-grid">
            <div className="stat-card">
              <div className="stat-icon">
                <BarChart3 size={16} />
              </div>
              <div className="stat-content">
                <span className="stat-label">种群规模</span>
                <span className="stat-value">{formatPopulation(snapshot.population)}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon death" style={{ color: trend?.color }}>
                {trend && <trend.icon size={16} />}
              </div>
              <div className="stat-content">
                <span className="stat-label">死亡率</span>
                <span className="stat-value" style={{ color: trend?.color }}>
                  {(snapshot.death_rate * 100).toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">📊</div>
              <div className="stat-content">
                <span className="stat-label">生态占比</span>
                <span className="stat-value">{(snapshot.population_share * 100).toFixed(1)}%</span>
              </div>
            </div>
            {trend && (
              <div className="stat-card trend" style={{ borderColor: `${trend.color}40` }}>
                <div className="stat-icon" style={{ color: trend.color }}>
                  <trend.icon size={16} />
                </div>
                <div className="stat-content">
                  <span className="stat-label">趋势</span>
                  <span className="stat-value" style={{ color: trend.color }}>{trend.label}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 近期动态 */}
        {snapshot?.notes && snapshot.notes.length > 0 && (
          <div className="recent-events">
            <h4>📋 近期动态</h4>
            <ul>
              {snapshot.notes.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          </div>
        )}

        {/* 标签页 */}
        <div className="detail-tabs">
          {[
            { key: "overview", label: "总览", icon: "📄" },
            { key: "traits", label: "特征", icon: "🎯" },
            { key: "organs", label: "器官", icon: "🔬" },
            ...(species.hybrid_parent_codes?.length || species.parent_code 
              ? [{ key: "lineage", label: "血统", icon: "🧬" }] 
              : [])
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              className={`tab-btn ${activeTab === key ? "active" : ""}`}
              onClick={() => setActiveTab(key as any)}
            >
              <span className="tab-icon">{icon}</span>
              <span className="tab-label">{label}</span>
            </button>
          ))}
        </div>

        {/* 标签页内容 */}
        <div className="detail-content">
          {activeTab === "overview" && (
            <div className="tab-overview">
              <div className="description-card">
                <p>{species.description || "暂无详细描述。这是一个神秘的物种，等待被探索..."}</p>
              </div>
              
              <div className="section-title">
                <span className="section-icon">📏</span>
                <span>形态参数</span>
              </div>
              <div className="morphology-list">
                {Object.entries(species.morphology_stats || {}).slice(0, 8).map(([key, value]) => {
                  const numValue = value as number;
                  const percent = Math.min(Math.max(numValue * 100, 0), 100);
                  return (
                    <div key={key} className="morph-item">
                      <span className="morph-label">{key}</span>
                      <div className="morph-track">
                        <div className="morph-fill" style={{ width: `${percent}%` }} />
                      </div>
                      <span className="morph-value">{numValue.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>

              {species.capabilities && species.capabilities.length > 0 && (
                <div className="capabilities-section">
                  <div className="section-title">
                    <Zap size={14} />
                    <span>特殊能力</span>
                  </div>
                  <div className="capabilities-grid">
                    {species.capabilities.map(cap => (
                      <span key={cap} className="capability-badge">
                        <Zap size={10} /> {cap}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "traits" && (
            <div className="tab-traits">
              {chartData.length > 0 && (
                <div className="radar-wrapper">
                  <ResponsiveContainer width="100%" height={220}>
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                      <PolarGrid stroke="rgba(255,255,255,0.08)" />
                      <PolarAngleAxis 
                        dataKey="subject" 
                        tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} 
                      />
                      <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
                      <Radar 
                        name="Stats" 
                        dataKey="A" 
                        stroke="#3b82f6" 
                        fill="#3b82f6" 
                        fillOpacity={0.25}
                        strokeWidth={2}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'rgba(15, 23, 42, 0.95)', 
                          borderColor: 'rgba(59, 130, 246, 0.3)',
                          borderRadius: '8px'
                        }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="section-title">
                <span className="section-icon">🎯</span>
                <span>抽象特质</span>
                <span className="section-hint">(最高15)</span>
              </div>
              <div className="traits-list">
                {Object.entries(species.abstract_traits || {}).map(([key, value]) => {
                  const numValue = value as number;
                  const percent = Math.min((numValue / 15) * 100, 100);
                  const color = numValue > 10 ? '#fbbf24' : numValue < 5 ? '#3b82f6' : '#22c55e';
                  return (
                    <div key={key} className="trait-item">
                      <span className="trait-label">{key}</span>
                      <div className="trait-track">
                        <div className="trait-fill" style={{ width: `${percent}%`, background: color }} />
                      </div>
                      <span className="trait-value" style={{ color }}>{numValue.toFixed(1)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === "organs" && (
            <div className="tab-organs">
              <div className="organs-intro">
                <Eye size={16} />
                <span>可视化的器官系统与生理结构</span>
              </div>
              <OrganismBlueprint species={species} />
            </div>
          )}

          {activeTab === "lineage" && (
            <div className="tab-lineage">
              {species.parent_code && (
                <div className="lineage-card">
                  <div className="lineage-header">
                    <GitBranch size={16} />
                    <span>直系祖先</span>
                  </div>
                  <div className="lineage-body">
                    <div className="parent-code">{species.parent_code}</div>
                    <div className="birth-info">
                      诞生于第 <strong>{species.created_turn != null ? species.created_turn + 1 : '?'}</strong> 回合
                    </div>
                  </div>
                </div>
              )}

              {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
                <div className="lineage-card hybrid">
                  <div className="lineage-header">
                    <GitMerge size={16} />
                    <span>杂交起源</span>
                  </div>
                  <div className="lineage-body">
                    <div className="hybrid-parents">
                      <span className="parents-label">亲本物种</span>
                      <div className="parents-list">
                        {species.hybrid_parent_codes.map(code => (
                          <span key={code} className="parent-badge">{code}</span>
                        ))}
                      </div>
                    </div>
                    <div className="fertility-section">
                      <span className="fertility-label">后代可育性</span>
                      <div className="fertility-display">
                        <div className="fertility-track">
                          <div 
                            className="fertility-fill" 
                            style={{ width: `${(species.hybrid_fertility || 0) * 100}%` }}
                          />
                        </div>
                        <span className="fertility-value">
                          {((species.hybrid_fertility || 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="species-panel">
      {selectedSpeciesId ? renderDetailView() : renderListView()}
      
      <style>{`
        .species-panel {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: linear-gradient(180deg, rgba(10, 15, 26, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
          color: #e2e8f0;
        }

        /* ========== 列表视图 ========== */
        .species-panel-list {
          display: flex;
          flex-direction: column;
          height: 100%;
        }

        .panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          background: rgba(0, 0, 0, 0.3);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .header-icon-wrapper {
          width: 40px;
          height: 40px;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2));
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.3rem;
        }

        .header-text h3 {
          margin: 0;
          font-size: 1rem;
          font-weight: 700;
          color: #f1f5f9;
        }

        .header-subtitle {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.4);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .header-right {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .header-stats {
          display: flex;
          gap: 6px;
        }

        .stat-chip {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 0.75rem;
          font-weight: 600;
        }

        .stat-chip .stat-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }

        .stat-chip.alive {
          background: rgba(34, 197, 94, 0.15);
          color: #22c55e;
        }

        .stat-chip.alive .stat-dot { background: #22c55e; }

        .stat-chip.extinct {
          background: rgba(148, 163, 184, 0.15);
          color: #94a3b8;
        }

        .stat-chip.extinct .stat-dot { background: #94a3b8; }

        .btn-collapse {
          width: 28px;
          height: 28px;
          border: 1px solid rgba(59, 130, 246, 0.3);
          background: rgba(59, 130, 246, 0.1);
          border-radius: 8px;
          color: #60a5fa;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }

        .btn-collapse:hover {
          background: rgba(59, 130, 246, 0.2);
          transform: translateX(2px);
        }

        .panel-toolbar {
          display: flex;
          gap: 10px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        .search-box {
          flex: 1;
          position: relative;
        }

        .search-box input {
          width: 100%;
          padding: 8px 28px 8px 32px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          color: #f1f5f9;
          font-size: 0.85rem;
          transition: all 0.2s;
        }

        .search-box input:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.4);
          background: rgba(15, 23, 42, 1);
        }

        .search-box input::placeholder {
          color: rgba(255, 255, 255, 0.3);
        }

        .search-icon {
          position: absolute;
          left: 10px;
          top: 50%;
          transform: translateY(-50%);
          color: rgba(255, 255, 255, 0.3);
        }

        .clear-btn {
          position: absolute;
          right: 6px;
          top: 50%;
          transform: translateY(-50%);
          width: 18px;
          height: 18px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 50%;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
          font-size: 12px;
          line-height: 1;
        }

        .filter-tabs {
          display: flex;
          gap: 2px;
          padding: 2px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 8px;
        }

        .filter-tab {
          padding: 6px 12px;
          border: none;
          background: transparent;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-tab:hover {
          color: rgba(255, 255, 255, 0.8);
        }

        .filter-tab.active {
          background: rgba(59, 130, 246, 0.2);
          color: #60a5fa;
        }

        .species-list {
          flex: 1;
          overflow-y: auto;
          padding: 8px;
        }

        .species-card {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          margin-bottom: 6px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid transparent;
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: relative;
          overflow: hidden;
          animation: cardFadeIn 0.3s ease forwards;
          opacity: 0;
        }

        @keyframes cardFadeIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .species-card:hover {
          background: rgba(59, 130, 246, 0.05);
          transform: translateX(4px);
        }

        .species-card.selected {
          background: rgba(59, 130, 246, 0.1);
          border-color: rgba(59, 130, 246, 0.3);
        }

        .species-card.extinct {
          opacity: 0.5;
        }

        .species-card.extinct:hover {
          opacity: 0.7;
        }

        .role-indicator {
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 4px;
          border-radius: 4px 0 0 4px;
        }

        .role-icon-wrapper {
          width: 36px;
          height: 36px;
          border: 1px solid;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          margin-left: 4px;
        }

        .role-emoji {
          font-size: 1.1rem;
        }

        .species-info {
          flex: 1;
          min-width: 0;
        }

        .species-name {
          display: flex;
          align-items: center;
          gap: 4px;
          margin-bottom: 2px;
        }

        .name-text {
          font-weight: 600;
          font-size: 0.95rem;
          color: #f1f5f9;
        }

        .extinct-mark {
          color: #94a3b8;
          font-size: 0.7rem;
        }

        .species-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .latin-name {
          font-style: italic;
          max-width: 120px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .lineage-code {
          font-family: 'JetBrains Mono', Monaco, monospace;
          padding: 1px 5px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 3px;
        }

        .species-data {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 6px;
        }

        .population-display {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 3px;
        }

        .pop-value {
          font-weight: 700;
          font-size: 1rem;
          font-family: 'JetBrains Mono', Monaco, monospace;
        }

        .pop-bar {
          width: 60px;
          height: 3px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 2px;
          overflow: hidden;
        }

        .pop-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        .trend-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          border-radius: 12px;
          font-size: 0.65rem;
          font-weight: 600;
        }

        .select-arrow {
          opacity: 0;
          transition: opacity 0.2s;
          color: #60a5fa;
        }

        .select-arrow.visible {
          opacity: 1;
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px;
          color: rgba(255, 255, 255, 0.4);
        }

        .empty-icon {
          font-size: 2rem;
          margin-bottom: 8px;
        }

        /* ========== 详情视图 ========== */
        .species-panel-detail {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }

        .detail-nav {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.3);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .btn-back {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.8);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-back:hover {
          background: rgba(255, 255, 255, 0.1);
          color: white;
        }

        .nav-actions {
          display: flex;
          gap: 8px;
        }

        .btn-action {
          width: 34px;
          height: 34px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-action:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: rgba(59, 130, 246, 0.3);
          color: #60a5fa;
        }

        .btn-close {
          width: 34px;
          height: 34px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: transparent;
          border: none;
          color: rgba(255, 255, 255, 0.5);
          cursor: pointer;
        }

        .loading-state, .error-state {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
          color: rgba(255, 255, 255, 0.5);
        }

        .loading-spinner {
          width: 36px;
          height: 36px;
          border: 3px solid rgba(59, 130, 246, 0.2);
          border-top-color: #3b82f6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .error-icon {
          font-size: 2rem;
        }

        .btn-retry {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          background: rgba(59, 130, 246, 0.2);
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 8px;
          color: #60a5fa;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-retry:hover {
          background: rgba(59, 130, 246, 0.3);
        }

        /* Hero Section */
        .species-hero {
          position: relative;
          padding: 20px 16px;
          overflow: hidden;
        }

        .hero-bg {
          position: absolute;
          inset: 0;
          opacity: 0.5;
        }

        .hero-content {
          position: relative;
          display: flex;
          gap: 16px;
        }

        .hero-icon {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 2rem;
          flex-shrink: 0;
        }

        .hero-info {
          flex: 1;
        }

        .hero-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 8px;
        }

        .badge {
          padding: 3px 10px;
          border-radius: 12px;
          font-size: 0.7rem;
          font-weight: 600;
        }

        .badge.genus {
          background: rgba(59, 130, 246, 0.15);
          color: #60a5fa;
          font-family: 'JetBrains Mono', Monaco, monospace;
        }

        .hero-name {
          margin: 0 0 6px 0;
          font-size: 1.5rem;
          font-weight: 700;
          color: #f8fafc;
        }

        .hero-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .meta-latin {
          font-style: italic;
        }

        .meta-divider {
          opacity: 0.3;
        }

        .meta-code {
          font-family: 'JetBrains Mono', Monaco, monospace;
          padding: 2px 6px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
        }

        /* Live Stats */
        .live-stats-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.2);
        }

        .stat-card {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 10px;
        }

        .stat-card.trend {
          border-left-width: 2px;
        }

        .stat-icon {
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          color: #64748b;
          font-size: 1rem;
        }

        .stat-content {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .stat-label {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .stat-value {
          font-size: 1.1rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', Monaco, monospace;
        }

        /* Recent Events */
        .recent-events {
          padding: 12px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .recent-events h4 {
          margin: 0 0 10px 0;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
        }

        .recent-events ul {
          margin: 0;
          padding-left: 20px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .recent-events li {
          margin-bottom: 4px;
        }

        /* Tabs */
        .detail-tabs {
          display: flex;
          gap: 4px;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .tab-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 10px 16px;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .tab-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }

        .tab-btn.active {
          background: rgba(59, 130, 246, 0.15);
          color: #60a5fa;
        }

        .tab-icon {
          font-size: 0.9rem;
        }

        /* Detail Content */
        .detail-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        .section-title {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 16px 0 12px 0;
          font-size: 0.9rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.8);
        }

        .section-title:first-child {
          margin-top: 0;
        }

        .section-hint {
          font-size: 0.7rem;
          font-weight: 400;
          color: rgba(255, 255, 255, 0.4);
        }

        /* Tab: Overview */
        .description-card {
          padding: 14px 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          font-size: 0.9rem;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.8);
        }

        .description-card p {
          margin: 0;
        }

        .morphology-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .morph-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 12px;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 8px;
        }

        .morph-label {
          width: 80px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .morph-track {
          flex: 1;
          height: 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 3px;
          overflow: hidden;
        }

        .morph-fill {
          height: 100%;
          background: linear-gradient(90deg, #3b82f6, #60a5fa);
          border-radius: 3px;
          transition: width 0.3s ease;
        }

        .morph-value {
          width: 45px;
          text-align: right;
          font-size: 0.75rem;
          font-family: 'JetBrains Mono', Monaco, monospace;
          color: rgba(255, 255, 255, 0.7);
        }

        .capabilities-section {
          margin-top: 20px;
        }

        .capabilities-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .capability-badge {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 6px 12px;
          background: rgba(251, 191, 36, 0.1);
          border: 1px solid rgba(251, 191, 36, 0.25);
          border-radius: 20px;
          font-size: 0.75rem;
          color: #fbbf24;
        }

        /* Tab: Traits */
        .radar-wrapper {
          margin-bottom: 20px;
          padding: 16px;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 12px;
        }

        .traits-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .trait-item {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .trait-label {
          width: 80px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .trait-track {
          flex: 1;
          height: 8px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 4px;
          overflow: hidden;
        }

        .trait-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s ease;
        }

        .trait-value {
          width: 36px;
          text-align: right;
          font-size: 0.75rem;
          font-weight: 600;
          font-family: 'JetBrains Mono', Monaco, monospace;
        }

        /* Tab: Organs */
        .organs-intro {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 14px;
          background: rgba(59, 130, 246, 0.1);
          border: 1px solid rgba(59, 130, 246, 0.2);
          border-radius: 10px;
          font-size: 0.85rem;
          color: #60a5fa;
          margin-bottom: 16px;
        }

        /* Tab: Lineage */
        .lineage-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          overflow: hidden;
          margin-bottom: 12px;
        }

        .lineage-card.hybrid {
          background: rgba(168, 85, 247, 0.05);
          border-color: rgba(168, 85, 247, 0.2);
        }

        .lineage-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          font-size: 0.9rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.8);
        }

        .lineage-card.hybrid .lineage-header {
          color: #c084fc;
        }

        .lineage-body {
          padding: 16px;
        }

        .parent-code {
          font-size: 1.3rem;
          font-family: 'JetBrains Mono', Monaco, monospace;
          font-weight: 600;
          color: #f1f5f9;
        }

        .birth-info {
          margin-top: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .birth-info strong {
          color: #60a5fa;
        }

        .hybrid-parents {
          margin-bottom: 16px;
        }

        .parents-label, .fertility-label {
          display: block;
          font-size: 0.7rem;
          color: rgba(168, 85, 247, 0.7);
          margin-bottom: 8px;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .parents-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .parent-badge {
          padding: 6px 12px;
          background: rgba(168, 85, 247, 0.15);
          border: 1px solid rgba(168, 85, 247, 0.3);
          border-radius: 8px;
          font-size: 0.85rem;
          font-family: 'JetBrains Mono', Monaco, monospace;
          color: #d8b4fe;
        }

        .fertility-display {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .fertility-track {
          flex: 1;
          height: 8px;
          background: rgba(168, 85, 247, 0.2);
          border-radius: 4px;
          overflow: hidden;
        }

        .fertility-fill {
          height: 100%;
          background: linear-gradient(90deg, #a855f7, #c084fc);
          border-radius: 4px;
        }

        .fertility-value {
          font-size: 1rem;
          font-weight: 600;
          font-family: 'JetBrains Mono', Monaco, monospace;
          color: #c084fc;
        }

        /* Edit Form */
        .edit-form {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        .form-field {
          margin-bottom: 20px;
        }

        .form-field label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 8px;
        }

        .label-tag {
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 0.65rem;
          text-transform: uppercase;
        }

        .label-tag.advanced {
          background: rgba(251, 191, 36, 0.15);
          color: #fbbf24;
        }

        .form-field textarea {
          width: 100%;
          padding: 12px 14px;
          background: rgba(15, 23, 42, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          color: #f1f5f9;
          font-size: 0.9rem;
          resize: vertical;
          transition: all 0.2s;
        }

        .form-field textarea.mono {
          font-family: 'JetBrains Mono', Monaco, monospace;
          font-size: 0.8rem;
        }

        .form-field textarea:focus {
          outline: none;
          border-color: rgba(59, 130, 246, 0.5);
          background: rgba(15, 23, 42, 1);
        }

        .edit-actions {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
          padding: 16px;
          background: rgba(0, 0, 0, 0.2);
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .btn-secondary, .btn-primary {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 20px;
          border-radius: 10px;
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-secondary {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: rgba(255, 255, 255, 0.7);
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.05);
          color: white;
        }

        .btn-primary {
          background: linear-gradient(135deg, #3b82f6, #2563eb);
          border: none;
          color: white;
          font-weight: 600;
        }

        .btn-primary:hover {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }

        .btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }

        .btn-spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        /* Scrollbar */
        .species-list::-webkit-scrollbar,
        .detail-content::-webkit-scrollbar,
        .edit-form::-webkit-scrollbar {
          width: 6px;
        }

        .species-list::-webkit-scrollbar-track,
        .detail-content::-webkit-scrollbar-track,
        .edit-form::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }

        .species-list::-webkit-scrollbar-thumb,
        .detail-content::-webkit-scrollbar-thumb,
        .edit-form::-webkit-scrollbar-thumb {
          background: rgba(59, 130, 246, 0.3);
          border-radius: 3px;
        }

        .species-list::-webkit-scrollbar-thumb:hover,
        .detail-content::-webkit-scrollbar-thumb:hover,
        .edit-form::-webkit-scrollbar-thumb:hover {
          background: rgba(59, 130, 246, 0.5);
        }
      `}</style>
    </div>
  );
}
