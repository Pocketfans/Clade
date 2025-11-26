import { useState, useEffect, useCallback } from "react";
import { 
  TrendingUp, TrendingDown, Minus, Skull, ArrowLeft, 
  RefreshCw, Edit2, Save, X, Zap, GitBranch, GitMerge,
  ChevronDown, ChevronRight, Eye
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
  refreshTrigger?: number; // 用于触发数据刷新
}

// 生态角色颜色和图标映射
const roleConfig: Record<string, { color: string; icon: string; label: string }> = {
  producer: { color: "#4ade80", icon: "🌿", label: "生产者" },
  herbivore: { color: "#facc15", icon: "🦌", label: "食草" },
  carnivore: { color: "#f43f5e", icon: "🦁", label: "食肉" },
  omnivore: { color: "#fb923c", icon: "🐻", label: "杂食" },
  decomposer: { color: "#c084fc", icon: "🍄", label: "分解者" },
  scavenger: { color: "#94a3b8", icon: "🦅", label: "食腐" },
  unknown: { color: "#2dd4bf", icon: "🧬", label: "未知" }
};

// 状态映射
const statusMap: Record<string, string> = {
  alive: "存活",
  extinct: "灭绝",
};

// 趋势判断
function getTrend(deathRate: number, status: string) {
  if (status === 'extinct') return { icon: Skull, color: "#94a3b8", label: "灭绝" };
  if (deathRate > 0.15) return { icon: TrendingDown, color: "#f43f5e", label: "危急" };
  if (deathRate > 0.08) return { icon: TrendingDown, color: "#fb923c", label: "衰退" };
  if (deathRate < 0.03) return { icon: TrendingUp, color: "#4ade80", label: "繁荣" };
  return { icon: Minus, color: "#94a3b8", label: "稳定" };
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
    if (listFilter === "alive") return s.status === "alive";
    if (listFilter === "extinct") return s.status === "extinct";
    return true;
  }).sort((a, b) => b.population - a.population);

  const aliveCount = speciesList.filter(s => s.status === "alive").length;
  const extinctCount = speciesList.length - aliveCount;

  // 渲染列表视图
  const renderListView = () => (
    <div className="species-panel-list">
      {/* 头部 */}
      <div className="species-panel-header">
        <div className="header-title">
          <span className="header-icon">🧬</span>
          <span>物种总览</span>
        </div>
        <div className="header-stats">
          <span className="stat-badge alive">{aliveCount} 存活</span>
          {extinctCount > 0 && <span className="stat-badge extinct">{extinctCount} 灭绝</span>}
        </div>
        {onCollapse && (
          <button className="btn-collapse" onClick={onCollapse} title="折叠">‹</button>
        )}
      </div>

      {/* 筛选器 */}
      <div className="list-filter">
        <button 
          className={`filter-btn ${listFilter === "all" ? "active" : ""}`}
          onClick={() => setListFilter("all")}
        >
          全部
        </button>
        <button 
          className={`filter-btn ${listFilter === "alive" ? "active" : ""}`}
          onClick={() => setListFilter("alive")}
        >
          存活
        </button>
        <button 
          className={`filter-btn ${listFilter === "extinct" ? "active" : ""}`}
          onClick={() => setListFilter("extinct")}
        >
          灭绝
        </button>
      </div>

      {/* 物种列表 */}
      <div className="species-list">
        {filteredList.map(s => {
          const role = roleConfig[s.ecological_role?.toLowerCase()] || roleConfig.unknown;
          const trend = getTrend(s.death_rate, s.status);
          const TrendIcon = trend.icon;
          const isExtinct = s.status === "extinct";
          const isSelected = s.lineage_code === selectedSpeciesId;

          return (
            <div 
              key={s.lineage_code}
              className={`species-item ${isSelected ? "selected" : ""} ${isExtinct ? "extinct" : ""}`}
              onClick={() => onSelectSpecies(s.lineage_code)}
              style={{ borderLeftColor: isSelected ? role.color : "transparent" }}
            >
              {/* 角色图标 */}
              <div className="species-role" style={{ 
                background: `linear-gradient(135deg, ${role.color}20, ${role.color}10)`,
                borderColor: `${role.color}40`
              }}>
                {role.icon}
              </div>

              {/* 名称信息 */}
              <div className="species-info">
                <div className="species-name">
                  {s.common_name}
                  {isExtinct && <span className="extinct-mark">†</span>}
                </div>
                <div className="species-latin">{s.latin_name}</div>
              </div>

              {/* 数据指标 */}
              <div className="species-stats">
                <div className="population">{formatPopulation(s.population)}</div>
                <div className="trend" style={{ 
                  color: trend.color,
                  background: `${trend.color}15`
                }}>
                  <TrendIcon size={10} />
                  <span>{trend.label}</span>
                </div>
              </div>

              {/* 选中指示器 */}
              {isSelected && <ChevronRight className="select-indicator" size={16} />}
            </div>
          );
        })}
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
          <div className="detail-header">
            <button className="btn-back" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} /> 返回列表
            </button>
          </div>
          <div className="detail-loading">
            <div className="loading-spinner" />
            <span>加载物种数据...</span>
          </div>
        </div>
      );
    }

    // 错误
    if (detailError) {
      return (
        <div className="species-panel-detail">
          <div className="detail-header">
            <button className="btn-back" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} /> 返回列表
            </button>
          </div>
          <div className="detail-error">
            <span>❌ {detailError}</span>
            <button className="btn-retry" onClick={handleRefresh}>重试</button>
          </div>
        </div>
      );
    }

    // 合并 snapshot 和 detail 数据
    const species = speciesDetail;
    const snapshot = selectedSnapshot;

    if (!species) return null;

    // 编辑模式
    if (isEditing) {
      return (
        <div className="species-panel-detail">
          <div className="detail-header">
            <h2>编辑物种数据</h2>
            <button className="btn-icon" onClick={() => setIsEditing(false)}>
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
              />
            </div>
            <div className="form-field">
              <label>形态参数 (JSON) <span className="label-warning">高级</span></label>
              <textarea
                rows={6}
                value={editForm.morphology}
                onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
                className="mono"
              />
            </div>
            <div className="form-field">
              <label>抽象特征 (JSON) <span className="label-warning">高级</span></label>
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
              {isSaving ? <span className="spinner" /> : <Save size={14} />}
              保存更改
            </button>
          </div>
        </div>
      );
    }

    // 准备雷达图数据（形态数据用1作为满值，抽象特质用15作为满值）
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

    return (
      <div className="species-panel-detail">
        {/* 详情头部 */}
        <div className="detail-header">
          <button className="btn-back" onClick={() => onSelectSpecies(null)}>
            <ArrowLeft size={16} /> 返回
          </button>
          <div className="header-actions">
            <button className="btn-icon" onClick={handleRefresh} title="刷新数据">
              <RefreshCw size={14} />
            </button>
            <button className="btn-icon" onClick={handleStartEdit} title="编辑">
              <Edit2 size={14} />
            </button>
          </div>
        </div>

        {/* 物种标题 */}
        <div className="detail-title">
          <div className="title-main">
            <div className="role-badge" style={{ 
              background: `${role.color}20`,
              borderColor: `${role.color}40`
            }}>
              <span className="role-icon">{role.icon}</span>
              <span className="role-label">{role.label}</span>
            </div>
            <h2>{species.common_name}</h2>
            <div className="title-meta">
              <span className="latin">{species.latin_name}</span>
              <span className="code">{species.lineage_code}</span>
            </div>
          </div>
          <div className="title-badges">
            <span className={`badge ${species.status === 'alive' ? 'alive' : 'extinct'}`}>
              {statusMap[species.status] || species.status}
            </span>
            {species.genus_code && <span className="badge genus">{species.genus_code}</span>}
            {species.taxonomic_rank && species.taxonomic_rank !== "species" && (
              <span className="badge rank">
                {species.taxonomic_rank === "subspecies" ? "亚种" : 
                 species.taxonomic_rank === "hybrid" ? "杂交种" : species.taxonomic_rank}
              </span>
            )}
          </div>
        </div>

        {/* 实时数据卡片 - 来自 snapshot */}
        {snapshot && (
          <div className="live-stats">
            <div className="stat-card">
              <div className="stat-label">种群规模</div>
              <div className="stat-value">{formatPopulation(snapshot.population)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">死亡率</div>
              <div className="stat-value" style={{ color: trend?.color }}>
                {(snapshot.death_rate * 100).toFixed(1)}%
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">生态位占比</div>
              <div className="stat-value">{(snapshot.population_share * 100).toFixed(1)}%</div>
            </div>
            {trend && (
              <div className="stat-card trend" style={{ borderColor: `${trend.color}40` }}>
                <div className="stat-label">趋势</div>
                <div className="stat-value" style={{ color: trend.color }}>
                  {trend.label}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 近期动态 */}
        {snapshot?.notes && snapshot.notes.length > 0 && (
          <div className="recent-notes">
            <h4>📋 近期动态</h4>
            <ul>
              {snapshot.notes.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          </div>
        )}

        {/* 标签页 */}
        <div className="detail-tabs">
          <button 
            className={activeTab === "overview" ? "active" : ""}
            onClick={() => setActiveTab("overview")}
          >
            总览
          </button>
          <button 
            className={activeTab === "traits" ? "active" : ""}
            onClick={() => setActiveTab("traits")}
          >
            特征
          </button>
          <button 
            className={activeTab === "organs" ? "active" : ""}
            onClick={() => setActiveTab("organs")}
          >
            器官
          </button>
          {(species.hybrid_parent_codes?.length || species.parent_code) && (
            <button 
              className={activeTab === "lineage" ? "active" : ""}
              onClick={() => setActiveTab("lineage")}
            >
              血统
            </button>
          )}
        </div>

        {/* 标签页内容 */}
        <div className="detail-content">
          {activeTab === "overview" && (
            <div className="tab-overview">
              <p className="description">{species.description || "暂无详细描述。"}</p>
              
              <div className="morphology-grid">
                {Object.entries(species.morphology_stats || {}).slice(0, 6).map(([key, value]) => (
                  <div key={key} className="morph-item">
                    <span className="morph-label">{key}</span>
                    <div className="morph-bar">
                      <div className="morph-fill" style={{ 
                        width: `${Math.min(Math.max((value as number) * 100, 0), 100)}%` 
                      }} />
                    </div>
                    <span className="morph-value">
                      {typeof value === 'number' ? value.toFixed(2) : value}
                    </span>
                  </div>
                ))}
              </div>

              {species.capabilities && species.capabilities.length > 0 && (
                <div className="capabilities">
                  <h4><Zap size={14} /> 特殊能力</h4>
                  <div className="cap-list">
                    {species.capabilities.map(cap => (
                      <span key={cap} className="cap-badge">
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
                <div className="radar-container">
                  <ResponsiveContainer width="100%" height={200}>
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                      <PolarGrid stroke="rgba(255,255,255,0.1)" />
                      <PolarAngleAxis dataKey="subject" tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} />
                      <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
                      <Radar name="Stats" dataKey="A" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f1329', borderColor: 'rgba(255,255,255,0.1)' }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="traits-list">
                <h4>抽象特质 <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>(最高15)</span></h4>
                {Object.entries(species.abstract_traits || {}).map(([key, value]) => {
                  const numValue = value as number;
                  const percent = Math.min((numValue / 15) * 100, 100);
                  // 颜色：>10 高(金色), <5 低(蓝色), 5-10 中等(绿色)
                  const color = numValue > 10 ? '#facc15' : numValue < 5 ? '#38bdf8' : '#4ade80';
                  return (
                    <div key={key} className="trait-item">
                      <span className="trait-label">{key}</span>
                      <div className="trait-bar">
                        <div 
                          className="trait-fill"
                          style={{ width: `${percent}%`, background: color }} 
                        />
                      </div>
                      <span className="trait-value">{numValue.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === "organs" && (
            <div className="tab-organs">
              <div className="organs-hint">
                <Eye size={16} /> 可视化的器官系统与生理结构
              </div>
              <OrganismBlueprint species={species} />
            </div>
          )}

          {activeTab === "lineage" && (
            <div className="tab-lineage">
              {species.parent_code && (
                <div className="lineage-card">
                  <h4><GitBranch size={14} /> 直系祖先</h4>
                  <div className="parent-code">{species.parent_code}</div>
                  <div className="birth-turn">诞生于第 {species.created_turn != null ? species.created_turn + 1 : '?'} 回合</div>
                </div>
              )}

              {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
                <div className="lineage-card hybrid">
                  <h4><GitMerge size={14} /> 杂交起源</h4>
                  <div className="hybrid-parents">
                    <span className="label">亲本物种</span>
                    <div className="parent-list">
                      {species.hybrid_parent_codes.map(code => (
                        <span key={code} className="parent-badge">{code}</span>
                      ))}
                    </div>
                  </div>
                  <div className="hybrid-fertility">
                    <span className="label">后代可育性</span>
                    <div className="fertility-bar">
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
          background: rgba(0, 0, 0, 0.2);
        }

        /* 列表视图 */
        .species-panel-list {
          display: flex;
          flex-direction: column;
          height: 100%;
        }

        .species-panel-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(0, 0, 0, 0.3);
        }

        .header-title {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 600;
          font-size: 1rem;
        }

        .header-icon { font-size: 1.2rem; }

        .header-stats {
          display: flex;
          gap: 8px;
          flex: 1;
        }

        .stat-badge {
          font-size: 0.7rem;
          padding: 2px 8px;
          border-radius: 12px;
        }

        .stat-badge.alive {
          background: rgba(74, 222, 128, 0.15);
          color: #4ade80;
        }

        .stat-badge.extinct {
          background: rgba(148, 163, 184, 0.15);
          color: #94a3b8;
        }

        .btn-collapse {
          width: 24px;
          height: 24px;
          border: 1px solid rgba(45, 212, 191, 0.2);
          background: rgba(45, 212, 191, 0.1);
          border-radius: 6px;
          cursor: pointer;
          color: #2dd4bf;
          font-size: 14px;
        }

        .list-filter {
          display: flex;
          gap: 4px;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.2);
        }

        .filter-btn {
          flex: 1;
          padding: 6px 8px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: transparent;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: rgba(255, 255, 255, 0.8);
        }

        .filter-btn.active {
          background: rgba(45, 212, 191, 0.15);
          border-color: rgba(45, 212, 191, 0.3);
          color: #2dd4bf;
        }

        .species-list {
          flex: 1;
          overflow-y: auto;
          padding: 8px;
        }

        .species-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          margin-bottom: 4px;
          border-radius: 8px;
          border-left: 3px solid transparent;
          background: rgba(255, 255, 255, 0.02);
          cursor: pointer;
          transition: all 0.2s;
        }

        .species-item:hover {
          background: rgba(255, 255, 255, 0.05);
        }

        .species-item.selected {
          background: rgba(45, 212, 191, 0.1);
        }

        .species-item.extinct {
          opacity: 0.5;
        }

        .species-role {
          width: 32px;
          height: 32px;
          border-radius: 8px;
          border: 1px solid;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          flex-shrink: 0;
        }

        .species-info {
          flex: 1;
          min-width: 0;
        }

        .species-name {
          font-weight: 600;
          font-size: 0.9rem;
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .extinct-mark {
          color: #94a3b8;
          font-size: 0.7rem;
        }

        .species-latin {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          font-style: italic;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .species-stats {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 4px;
        }

        .population {
          font-weight: 700;
          font-size: 0.95rem;
          font-family: var(--font-mono);
        }

        .trend {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 0.65rem;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .select-indicator {
          color: #2dd4bf;
          opacity: 0.7;
        }

        /* 详情视图 */
        .species-panel-detail {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }

        .detail-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(0, 0, 0, 0.3);
        }

        .btn-back {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: transparent;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.7);
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-back:hover {
          background: rgba(255, 255, 255, 0.05);
          color: white;
        }

        .header-actions {
          display: flex;
          gap: 8px;
        }

        .btn-icon {
          width: 32px;
          height: 32px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: transparent;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.6);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }

        .btn-icon:hover {
          background: rgba(255, 255, 255, 0.1);
          color: white;
        }

        .detail-loading, .detail-error {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          color: rgba(255, 255, 255, 0.5);
        }

        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 2px solid rgba(45, 212, 191, 0.2);
          border-top-color: #2dd4bf;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .btn-retry {
          padding: 6px 16px;
          border: 1px solid rgba(45, 212, 191, 0.3);
          background: rgba(45, 212, 191, 0.1);
          border-radius: 6px;
          color: #2dd4bf;
          cursor: pointer;
        }

        .detail-title {
          padding: 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .title-main {
          margin-bottom: 12px;
        }

        .role-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          border: 1px solid;
          border-radius: 20px;
          font-size: 0.75rem;
          margin-bottom: 8px;
        }

        .role-icon { font-size: 1rem; }
        .role-label { color: rgba(255, 255, 255, 0.8); }

        .detail-title h2 {
          font-size: 1.4rem;
          font-weight: 700;
          margin: 0 0 4px 0;
        }

        .title-meta {
          display: flex;
          gap: 8px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .latin { font-style: italic; }
        .code { font-family: var(--font-mono); }

        .title-badges {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .badge {
          padding: 3px 10px;
          border-radius: 12px;
          font-size: 0.7rem;
          font-weight: 500;
        }

        .badge.alive {
          background: rgba(74, 222, 128, 0.15);
          color: #4ade80;
        }

        .badge.extinct {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
        }

        .badge.genus {
          background: rgba(59, 130, 246, 0.15);
          color: #3b82f6;
          font-family: var(--font-mono);
        }

        .badge.rank {
          background: rgba(168, 85, 247, 0.15);
          color: #a855f7;
        }

        .live-stats {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.2);
        }

        .stat-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          padding: 10px 12px;
        }

        .stat-card.trend {
          border-left: 2px solid;
        }

        .stat-label {
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          margin-bottom: 4px;
        }

        .stat-value {
          font-size: 1.1rem;
          font-weight: 700;
          font-family: var(--font-mono);
        }

        .recent-notes {
          padding: 12px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .recent-notes h4 {
          font-size: 0.85rem;
          margin: 0 0 8px 0;
          color: rgba(255, 255, 255, 0.7);
        }

        .recent-notes ul {
          margin: 0;
          padding-left: 20px;
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .recent-notes li {
          margin-bottom: 4px;
        }

        .detail-tabs {
          display: flex;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding: 0 12px;
          background: rgba(0, 0, 0, 0.2);
        }

        .detail-tabs button {
          padding: 10px 16px;
          border: none;
          background: transparent;
          color: rgba(255, 255, 255, 0.5);
          font-size: 0.85rem;
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all 0.2s;
        }

        .detail-tabs button:hover {
          color: rgba(255, 255, 255, 0.8);
        }

        .detail-tabs button.active {
          color: #2dd4bf;
          border-bottom-color: #2dd4bf;
        }

        .detail-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        /* Tab: Overview */
        .tab-overview .description {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          padding: 12px;
          font-size: 0.9rem;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.8);
          margin-bottom: 16px;
        }

        .morphology-grid {
          display: grid;
          gap: 8px;
        }

        .morph-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 6px;
        }

        .morph-label {
          width: 80px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .morph-bar {
          flex: 1;
          height: 6px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
          overflow: hidden;
        }

        .morph-fill {
          height: 100%;
          background: #2dd4bf;
          border-radius: 3px;
        }

        .morph-value {
          width: 40px;
          text-align: right;
          font-size: 0.75rem;
          font-family: var(--font-mono);
          color: rgba(255, 255, 255, 0.7);
        }

        .capabilities {
          margin-top: 16px;
        }

        .capabilities h4 {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 10px;
        }

        .cap-list {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .cap-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          background: rgba(251, 191, 36, 0.1);
          border: 1px solid rgba(251, 191, 36, 0.2);
          border-radius: 12px;
          font-size: 0.7rem;
          color: #fbbf24;
        }

        /* Tab: Traits */
        .tab-traits .radar-container {
          margin-bottom: 20px;
        }

        .traits-list h4 {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.6);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 8px;
          margin-bottom: 12px;
        }

        .trait-item {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 10px;
        }

        .trait-label {
          width: 80px;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .trait-bar {
          flex: 1;
          height: 8px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          overflow: hidden;
        }

        .trait-fill {
          height: 100%;
          border-radius: 4px;
        }

        .trait-value {
          width: 36px;
          text-align: right;
          font-size: 0.7rem;
          font-family: var(--font-mono);
        }

        /* Tab: Organs */
        .tab-organs .organs-hint {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          background: rgba(59, 130, 246, 0.1);
          border: 1px solid rgba(59, 130, 246, 0.2);
          border-radius: 8px;
          font-size: 0.8rem;
          color: #60a5fa;
          margin-bottom: 16px;
        }

        /* Tab: Lineage */
        .lineage-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          padding: 16px;
          margin-bottom: 12px;
        }

        .lineage-card h4 {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.7);
          margin: 0 0 12px 0;
        }

        .lineage-card.hybrid {
          background: rgba(168, 85, 247, 0.05);
          border-color: rgba(168, 85, 247, 0.2);
        }

        .lineage-card.hybrid h4 {
          color: #c084fc;
        }

        .parent-code {
          font-size: 1.2rem;
          font-family: var(--font-mono);
          font-weight: 600;
        }

        .birth-turn {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          margin-top: 4px;
        }

        .hybrid-parents, .hybrid-fertility {
          margin-bottom: 12px;
        }

        .hybrid-parents .label, .hybrid-fertility .label {
          font-size: 0.7rem;
          color: rgba(168, 85, 247, 0.7);
          margin-bottom: 6px;
        }

        .parent-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .parent-badge {
          background: rgba(168, 85, 247, 0.15);
          border: 1px solid rgba(168, 85, 247, 0.3);
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 0.8rem;
          font-family: var(--font-mono);
          color: #d8b4fe;
        }

        .fertility-bar {
          flex: 1;
          height: 6px;
          background: rgba(168, 85, 247, 0.2);
          border-radius: 3px;
          overflow: hidden;
          margin: 8px 0;
        }

        .fertility-fill {
          height: 100%;
          background: #c084fc;
          border-radius: 3px;
        }

        .fertility-value {
          font-size: 0.9rem;
          font-weight: 600;
          color: #c084fc;
        }

        /* 编辑表单 */
        .edit-form {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }

        .form-field {
          margin-bottom: 16px;
        }

        .form-field label {
          display: block;
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 6px;
        }

        .label-warning {
          color: #facc15;
          font-size: 0.7rem;
          margin-left: 8px;
        }

        .form-field textarea {
          width: 100%;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: white;
          font-size: 0.85rem;
          resize: vertical;
        }

        .form-field textarea.mono {
          font-family: var(--font-mono);
          font-size: 0.75rem;
        }

        .form-field textarea:focus {
          outline: none;
          border-color: #2dd4bf;
        }

        .edit-actions {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
          padding: 16px;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        .btn-secondary, .btn-primary {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          border-radius: 8px;
          font-size: 0.85rem;
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
        }

        .btn-primary {
          background: #2dd4bf;
          border: none;
          color: #0a0f0d;
          font-weight: 600;
        }

        .btn-primary:hover {
          background: #5eead4;
        }

        .btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(0, 0, 0, 0.2);
          border-top-color: #0a0f0d;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        /* 滚动条 */
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
          background: rgba(45, 212, 191, 0.3);
          border-radius: 3px;
        }
      `}</style>
    </div>
  );
}

