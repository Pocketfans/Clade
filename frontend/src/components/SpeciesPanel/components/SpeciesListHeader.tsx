/**
 * SpeciesListHeader - 物种列表头部（搜索、过滤、统计）
 */

import { memo } from "react";
import { Search, X, ChevronLeft, RefreshCw } from "lucide-react";
import type { FilterOptions, SortField, SortOrder } from "../types";
import { ROLE_CONFIGS } from "../constants";

interface SpeciesListHeaderProps {
  stats: {
    total: number;
    alive: number;
    extinct: number;
    totalPopulation: number;
  };
  filters: FilterOptions;
  sortField: SortField;
  sortOrder: SortOrder;
  onSearchChange: (query: string) => void;
  onRoleFilterChange: (role: string | null) => void;
  onStatusFilterChange: (status: FilterOptions["statusFilter"]) => void;
  onSortFieldChange: (field: SortField) => void;
  onSortOrderToggle: () => void;
  onClearFilters: () => void;
  onCollapse?: () => void;
  onRefresh?: () => void;
}

export const SpeciesListHeader = memo(function SpeciesListHeader({
  stats,
  filters,
  sortField,
  sortOrder,
  onSearchChange,
  onRoleFilterChange,
  onStatusFilterChange,
  onSortFieldChange,
  onSortOrderToggle,
  onClearFilters,
  onCollapse,
  onRefresh,
}: SpeciesListHeaderProps) {
  const hasFilters = filters.searchQuery || filters.roleFilter || filters.statusFilter !== "all";

  // 格式化大数字
  const formatNumber = (n: number): string => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toString();
  };

  return (
    <div className="species-list-header">
      {/* 标题栏 */}
      <div className="header-title-bar">
        <div className="header-title">
          <span className="title-icon">🧬</span>
          <span>物种总览</span>
        </div>
        <div className="header-actions">
          {onRefresh && (
            <button className="btn-icon" onClick={onRefresh} title="刷新">
              <RefreshCw size={16} />
            </button>
          )}
          {onCollapse && (
            <button className="btn-icon" onClick={onCollapse} title="收起">
              <ChevronLeft size={16} />
            </button>
          )}
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-value">{stats.alive}</span>
          <span className="stat-label">存活</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item extinct">
          <span className="stat-value">{stats.extinct}</span>
          <span className="stat-label">灭绝</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item population">
          <span className="stat-value">{formatNumber(stats.totalPopulation)}</span>
          <span className="stat-label">总人口</span>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="search-bar">
        <Search size={16} className="search-icon" />
        <input
          type="text"
          placeholder="搜索物种..."
          value={filters.searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {filters.searchQuery && (
          <button className="clear-btn" onClick={() => onSearchChange("")}>
            <X size={14} />
          </button>
        )}
      </div>

      {/* 过滤器 */}
      <div className="filter-bar">
        {/* 状态过滤 */}
        <div className="filter-group">
          <select
            value={filters.statusFilter ?? "all"}
            onChange={(e) => onStatusFilterChange(e.target.value as FilterOptions["statusFilter"])}
          >
            <option value="all">全部状态</option>
            <option value="alive">存活</option>
            <option value="extinct">灭绝</option>
          </select>
        </div>

        {/* 角色过滤 */}
        <div className="filter-group">
          <select
            value={filters.roleFilter || ""}
            onChange={(e) => onRoleFilterChange(e.target.value || null)}
          >
            <option value="">全部角色</option>
            {Object.entries(ROLE_CONFIGS).map(([key, config]) => (
              <option key={key} value={key}>
                {config.icon} {config.label}
              </option>
            ))}
          </select>
        </div>

        {/* 排序 */}
        <div className="filter-group sort-group">
          <select
            value={sortField}
            onChange={(e) => onSortFieldChange(e.target.value as SortField)}
          >
            <option value="population">人口</option>
            <option value="name">名称</option>
            <option value="role">角色</option>
            <option value="status">状态</option>
          </select>
          <button className="sort-order-btn" onClick={onSortOrderToggle}>
            {sortOrder === "asc" ? "↑" : "↓"}
          </button>
        </div>

        {/* 清除过滤 */}
        {hasFilters && (
          <button className="clear-filters-btn" onClick={onClearFilters}>
            清除
          </button>
        )}
      </div>
    </div>
  );
});













