/**
 * SpeciesPanel - 物种面板（重构版）
 *
 * 使用模块化的 hooks 和子组件
 * 原组件 2363 行 → 重构后 ~300 行
 */

import { useState, useEffect, useCallback } from "react";
import { ArrowLeft, RefreshCw, Edit2, Save, X, ChevronRight, Dna, Activity, Skull, Users } from "lucide-react";

import type { SpeciesDetail, SpeciesSnapshot } from "@/services/api.types";
import { fetchSpeciesDetail, editSpecies } from "@/services/api";
import { OrganismBlueprint } from "../OrganismBlueprint";
import { SpeciesAITab } from "../SpeciesAITab";

// 模块化组件
import { SpeciesListHeader } from "./components/SpeciesListHeader";
import { SpeciesListItem } from "./components/SpeciesListItem";
import { useSpeciesList } from "./hooks/useSpeciesList";
import { useSpeciesDetail } from "./hooks/useSpeciesDetail";
import { ROLE_CONFIGS, getRoleConfig, DETAIL_TABS } from "./constants";
import { formatPopulation, getTrend } from "./utils";
import type { SpeciesPanelProps, DetailTab } from "./types";

export function SpeciesPanelNew({
  speciesList,
  selectedSpeciesId,
  onSelectSpecies,
  onCollapse,
  refreshTrigger = 0,
  previousPopulations = new Map(),
}: SpeciesPanelProps) {
  // 使用模块化 hooks
  const {
    filteredList,
    filters,
    setSearchQuery,
    setRoleFilter,
    setStatusFilter,
    clearFilters,
    sortField,
    sortOrder,
    setSortField,
    toggleSortOrder,
    stats,
    getPopulationTrend,
    getPopulationChange,
  } = useSpeciesList({ speciesList, previousPopulations });

  const { detail: speciesDetail, loading: detailLoading, error: detailError, refresh: refreshDetail } = useSpeciesDetail({
    speciesId: selectedSpeciesId,
    refreshTrigger,
  });

  // 本地状态
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ description: "", morphology: "", traits: "" });
  const [isSaving, setIsSaving] = useState(false);

  // 编辑功能
  const handleStartEdit = useCallback(() => {
    if (!speciesDetail) return;
    setEditForm({
      description: speciesDetail.description || "",
      morphology: JSON.stringify(speciesDetail.morphology_stats, null, 2),
      traits: JSON.stringify(speciesDetail.abstract_traits, null, 2),
    });
    setIsEditing(true);
  }, [speciesDetail]);

  const handleSaveEdit = useCallback(async () => {
    if (!speciesDetail) return;
    setIsSaving(true);
    try {
      await editSpecies(speciesDetail.lineage_code, {
        description: editForm.description,
        morphology: editForm.morphology,
        traits: editForm.traits,
      });
      refreshDetail();
      setIsEditing(false);
    } catch (error) {
      console.error("保存失败:", error);
    } finally {
      setIsSaving(false);
    }
  }, [speciesDetail, editForm, refreshDetail]);

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
  }, []);

  // 重置 tab 当选择新物种
  useEffect(() => {
    if (selectedSpeciesId) {
      setActiveTab("overview");
      setIsEditing(false);
    }
  }, [selectedSpeciesId]);

  // ========== 列表视图 ==========
  const renderListView = () => (
    <div className="sp-list-view">
      {/* 头部 */}
      <SpeciesListHeader
        stats={stats}
        filters={filters}
        sortField={sortField}
        sortOrder={sortOrder}
        onSearchChange={setSearchQuery}
        onRoleFilterChange={setRoleFilter}
        onStatusFilterChange={setStatusFilter}
        onSortFieldChange={setSortField}
        onSortOrderToggle={toggleSortOrder}
        onClearFilters={clearFilters}
        onCollapse={onCollapse}
      />

      {/* 总种群概览 */}
      <div className="sp-population-banner">
        <div className="sp-pop-icon">
          <Users size={16} />
        </div>
        <div className="sp-pop-info">
          <span className="sp-pop-label">总生物量</span>
          <span className="sp-pop-value">{formatPopulation(stats.totalPopulation)}</span>
        </div>
      </div>

      {/* 物种列表 */}
      <div className="sp-card-list">
        {filteredList.map((species) => (
          <SpeciesListItem
            key={species.lineage_code}
            species={species}
            isSelected={species.lineage_code === selectedSpeciesId}
            trend={getPopulationTrend(species)}
            populationChange={getPopulationChange(species)}
            onClick={() => onSelectSpecies(species.lineage_code)}
          />
        ))}

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

    const selectedSnapshot = speciesList.find((s) => s.lineage_code === selectedSpeciesId);
    const role = getRoleConfig(selectedSnapshot?.ecological_role || "unknown");

    if (detailLoading) {
      return (
        <div className="sp-detail-view">
          <div className="sp-detail-nav">
            <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回</span>
            </button>
          </div>
          <div className="sp-loading">
            <div className="sp-loading-spinner" />
            <p>加载物种数据...</p>
          </div>
        </div>
      );
    }

    if (detailError || !speciesDetail) {
      return (
        <div className="sp-detail-view">
          <div className="sp-detail-nav">
            <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
              <ArrowLeft size={16} />
              <span>返回</span>
            </button>
          </div>
          <div className="sp-error">
            <p>{detailError || "加载失败"}</p>
            <button onClick={refreshDetail}>重试</button>
          </div>
        </div>
      );
    }

    return (
      <div className="sp-detail-view">
        {/* 导航栏 */}
        <div className="sp-detail-nav">
          <button className="sp-back-btn" onClick={() => onSelectSpecies(null)}>
            <ArrowLeft size={16} />
            <span>返回</span>
          </button>
          <div className="sp-detail-actions">
            <button className="sp-action-btn" onClick={refreshDetail} title="刷新">
              <RefreshCw size={16} />
            </button>
            {!isEditing ? (
              <button className="sp-action-btn" onClick={handleStartEdit} title="编辑">
                <Edit2 size={16} />
              </button>
            ) : (
              <>
                <button className="sp-action-btn save" onClick={handleSaveEdit} disabled={isSaving}>
                  <Save size={16} />
                </button>
                <button className="sp-action-btn" onClick={handleCancelEdit}>
                  <X size={16} />
                </button>
              </>
            )}
          </div>
        </div>

        {/* 物种头部 */}
        <div className="sp-detail-header" style={{ borderColor: role.color }}>
          <div className="sp-detail-avatar" style={{ background: role.gradient }}>
            <span>{role.icon}</span>
          </div>
          <div className="sp-detail-info">
            <h2>{speciesDetail.common_name}</h2>
            <p className="sp-detail-latin">{speciesDetail.latin_name}</p>
            <div className="sp-detail-tags">
              <span className="sp-tag code">{speciesDetail.lineage_code}</span>
              <span className="sp-tag role" style={{ background: `${role.color}20`, color: role.color }}>
                {role.label}
              </span>
              <span className={`sp-tag status ${speciesDetail.status}`}>{speciesDetail.status}</span>
            </div>
          </div>
        </div>

        {/* 标签页 */}
        <div className="sp-detail-tabs">
          {DETAIL_TABS.map((tab) => (
            <button
              key={tab.id}
              className={`sp-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* 标签页内容 */}
        <div className="sp-detail-content">
          {activeTab === "overview" && (
            <div className="sp-overview">
              {isEditing ? (
                <textarea
                  className="sp-edit-textarea"
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  placeholder="物种描述..."
                />
              ) : (
                <p className="sp-description">{speciesDetail.description || "暂无描述"}</p>
              )}
              <OrganismBlueprint species={speciesDetail} />
            </div>
          )}

          {activeTab === "stats" && (
            <div className="sp-stats">
              <div className="sp-stat-grid">
                <div className="sp-stat-item">
                  <span className="label">种群数量</span>
                  <span className="value">{formatPopulation(speciesDetail.population)}</span>
                </div>
                <div className="sp-stat-item">
                  <span className="label">生态位宽度</span>
                  <span className="value">{speciesDetail.niche_breadth?.toFixed(2) || "N/A"}</span>
                </div>
                <div className="sp-stat-item">
                  <span className="label">适应度</span>
                  <span className="value">{speciesDetail.fitness?.toFixed(2) || "N/A"}</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "ai" && <SpeciesAITab speciesCode={speciesDetail.lineage_code} />}

          {activeTab === "history" && (
            <div className="sp-history">
              <p className="sp-placeholder">进化历史记录</p>
              {speciesDetail.parent_code && (
                <div className="sp-lineage-info">
                  <span>父代：</span>
                  <button onClick={() => onSelectSpecies(speciesDetail.parent_code!)}>
                    {speciesDetail.parent_code}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  // ========== 主渲染 ==========
  return (
    <div className="species-panel">
      {selectedSpeciesId ? renderDetailView() : renderListView()}
    </div>
  );
}

export default SpeciesPanelNew;

