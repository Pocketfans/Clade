import { useState, useMemo, useEffect } from "react";
import { List, GitBranch, Sparkles, TreeDeciduous, Layers, X } from "lucide-react";
import type { LineageNode, LineageTree } from "../services/api.types";
import { GenealogySkeletonLoader } from "./SkeletonLoader";
import { GenealogyGraphView } from "./GenealogyGraphView";
import { GenealogyFilters, type FilterOptions } from "./GenealogyFilters";
import { fetchSpeciesDetail } from "../services/api";

interface Props {
  tree: LineageTree | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose?: () => void;
}

const organCategoryMap: Record<string, string> = {
  metabolic: "代谢系统",
  locomotion: "运动系统",
  sensory: "感觉系统",
  digestive: "消化系统",
  defense: "防御系统",
  respiratory: "呼吸系统",
  nervous: "神经系统",
  circulatory: "循环系统",
  reproductive: "繁殖系统",
  excretory: "排泄系统",
};

const statusMap: Record<string, string> = {
  alive: "存活",
  extinct: "灭绝",
};

type ViewMode = "list" | "graph";

export function GenealogyView({ tree, loading, error, onRetry, onClose }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);
  const [spacingX, setSpacingX] = useState(200);
  const [spacingY, setSpacingY] = useState(60);
  const [filters, setFilters] = useState<FilterOptions>({
    states: [],
    ecologicalRoles: [],
    tiers: [],
    turnRange: [0, 1000],
    searchTerm: "",
  });

  const maxTurn = useMemo(() => {
    if (!tree) return 1000;
    return Math.max(...tree.nodes.map(n => n.birth_turn), 0);
  }, [tree]);

  const filteredNodes = useMemo(() => {
    if (!tree) return [];
    
    return tree.nodes.filter(node => {
      if (filters.states.length > 0 && !filters.states.includes(node.state)) {
        return false;
      }
      if (filters.ecologicalRoles.length > 0 && !filters.ecologicalRoles.includes(node.ecological_role)) {
        return false;
      }
      if (filters.tiers.length > 0) {
        if (!node.tier && !filters.tiers.includes("none")) return false;
        if (node.tier && !filters.tiers.includes(node.tier)) return false;
      }
      if (node.birth_turn < filters.turnRange[0] || node.birth_turn > filters.turnRange[1]) {
        return false;
      }
      if (filters.searchTerm) {
        const term = filters.searchTerm.toLowerCase();
        if (
          !node.lineage_code.toLowerCase().includes(term) &&
          !node.latin_name.toLowerCase().includes(term) &&
          !node.common_name.toLowerCase().includes(term)
        ) {
          return false;
        }
      }
      return true;
    });
  }, [tree, filters]);

  if (loading) {
    return <GenealogySkeletonLoader />;
  }
  
  if (error) {
    return (
      <div className="genealogy-error-container">
        <div className="error-content">
          <div className="error-icon">⚠️</div>
          <p className="error-text">{error}</p>
          <button className="retry-btn" onClick={onRetry}>重试</button>
        </div>
        <style>{genealogyStyles}</style>
      </div>
    );
  }
  
  if (!tree || tree.nodes.length === 0) {
    return (
      <div className="genealogy-empty-container">
        <div className="empty-content">
          <div className="empty-icon">🌱</div>
          <p className="empty-title">暂无族谱数据</p>
          <p className="empty-hint">运行几轮推演后再试</p>
        </div>
        <style>{genealogyStyles}</style>
      </div>
    );
  }

  const aliveCount = filteredNodes.filter(n => n.state === "alive").length;
  const extinctCount = filteredNodes.filter(n => n.state === "extinct").length;

  return (
    <div className="genealogy-modal-overlay" onClick={onClose}>
      <div className="genealogy-modal" onClick={e => e.stopPropagation()}>
        {/* 顶部标题栏 */}
        <header className="genealogy-header">
          <div className="header-left">
            <div className="header-icon">
              <TreeDeciduous size={24} />
            </div>
            <div className="header-titles">
              <h1>物种演化族谱</h1>
              <span className="header-subtitle">Evolutionary Genealogy</span>
            </div>
          </div>
          
          <div className="header-center">
            <div className="quick-stats">
              <div className="stat-badge alive">
                <span className="stat-dot" />
                <span className="stat-label">存活</span>
                <span className="stat-num">{aliveCount}</span>
              </div>
              <div className="stat-badge extinct">
                <span className="stat-dot" />
                <span className="stat-label">灭绝</span>
                <span className="stat-num">{extinctCount}</span>
              </div>
              <div className="stat-badge total">
                <Layers size={12} />
                <span className="stat-label">总计</span>
                <span className="stat-num">{tree.nodes.length}</span>
              </div>
            </div>
          </div>

          <div className="header-right">
            {onClose && (
              <button className="close-btn" onClick={onClose} title="关闭">
                <X size={20} />
              </button>
            )}
          </div>
        </header>

        {/* 工具栏 */}
        <div className="genealogy-toolbar">
          <div className="toolbar-left">
            <GenealogyFilters 
              filters={filters} 
              maxTurn={maxTurn}
              onChange={setFilters} 
            />
          </div>
          
          <div className="toolbar-right">
            {/* 间距控制 */}
            <div className="spacing-controls">
              <div className="spacing-item">
                <label>水平</label>
                <input 
                  type="range" 
                  min="100" 
                  max="400" 
                  value={spacingX} 
                  onChange={(e) => setSpacingX(Number(e.target.value))}
                />
                <span className="spacing-value">{spacingX}</span>
              </div>
              <div className="spacing-item">
                <label>垂直</label>
                <input 
                  type="range" 
                  min="30" 
                  max="150" 
                  value={spacingY} 
                  onChange={(e) => setSpacingY(Number(e.target.value))}
                />
                <span className="spacing-value">{spacingY}</span>
              </div>
            </div>

            {/* 视图切换 */}
            <div className="view-toggle">
              <button
                className={`toggle-btn ${viewMode === "graph" ? "active" : ""}`}
                onClick={() => setViewMode("graph")}
                title="图谱视图"
              >
                <GitBranch size={16} />
                <span>图谱</span>
              </button>
              <button
                className={`toggle-btn ${viewMode === "list" ? "active" : ""}`}
                onClick={() => setViewMode("list")}
                title="列表视图"
              >
                <List size={16} />
                <span>列表</span>
              </button>
            </div>
          </div>
        </div>

        {/* 主内容区域 */}
        <div className="genealogy-content">
          {viewMode === "graph" ? (
            <GenealogyGraphView 
              nodes={filteredNodes}
              spacingX={spacingX}
              spacingY={spacingY}
              onNodeClick={setSelectedNode}
            />
          ) : (
            <div className="list-view-container">
              <ListView nodes={filteredNodes} onSelectNode={setSelectedNode} />
            </div>
          )}
        </div>

        {/* 节点详情面板 */}
        {selectedNode && selectedNode.lineage_code !== "ROOT" && (
          <NodeDetailCard 
            node={selectedNode} 
            onClose={() => setSelectedNode(null)} 
          />
        )}
      </div>
      <style>{genealogyStyles}</style>
    </div>
  );
}

// 列表视图组件
function ListView({ nodes, onSelectNode }: { 
  nodes: LineageNode[]; 
  onSelectNode: (node: LineageNode) => void;
}) {
  const childrenMap = buildChildrenMap(nodes);
  const roots = nodes.filter((node) => !node.parent_code);
  
  return (
    <div className="genealogy-list">
      {roots.map((node) => (
        <TreeNode 
          key={node.lineage_code} 
          node={node} 
          childrenMap={childrenMap} 
          depth={0}
          onSelect={onSelectNode}
        />
      ))}
    </div>
  );
}

function buildChildrenMap(nodes: LineageNode[]): Map<string, LineageNode[]> {
  const map = new Map<string, LineageNode[]>();
  nodes.forEach((node) => {
    if (node.parent_code) {
      const list = map.get(node.parent_code) ?? [];
      list.push(node);
      map.set(node.parent_code, list);
    }
  });
  return map;
}

function TreeNode({
  node,
  childrenMap,
  depth,
  onSelect,
}: {
  node: LineageNode;
  childrenMap: Map<string, LineageNode[]>;
  depth: number;
  onSelect?: (node: LineageNode) => void;
}) {
  const children = childrenMap.get(node.lineage_code) ?? [];
  const isAlive = node.state === "alive";
  
  const roleColors: Record<string, string> = {
    producer: "#10b981",
    herbivore: "#fbbf24",
    carnivore: "#f43f5e",
    omnivore: "#f97316",
  };
  const roleColor = roleColors[node.ecological_role] || "#64748b";
  
  return (
    <div className="tree-node-wrapper" style={{ marginLeft: depth * 24 }}>
      <div 
        className={`tree-node ${isAlive ? "alive" : "extinct"}`}
        onClick={() => onSelect?.(node)}
      >
        <div className="node-indicator" style={{ background: roleColor }} />
        <div className="node-content">
          <div className="node-header">
            <span className="node-code">{node.lineage_code}</span>
            <span className={`node-status ${node.state}`}>
              {statusMap[node.state] || node.state}
            </span>
          </div>
          <div className="node-names">
            <span className="node-latin">{node.latin_name}</span>
            <span className="node-common">{node.common_name}</span>
          </div>
          <div className="node-meta">
            <span>T{node.birth_turn + 1}</span>
            {node.extinction_turn != null && <span>† T{node.extinction_turn + 1}</span>}
            <span>后代: {node.descendant_count}</span>
          </div>
        </div>
      </div>
      {children.length > 0 && (
        <div className="tree-children">
          {children.map((child) => (
            <TreeNode
              key={child.lineage_code}
              node={child}
              childrenMap={childrenMap}
              depth={depth + 1}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 节点详情卡片
function NodeDetailCard({ node, onClose }: { node: LineageNode; onClose: () => void }) {
  const [speciesDetail, setSpeciesDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchSpeciesDetail(node.lineage_code)
      .then(setSpeciesDetail)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [node.lineage_code]);

  const roleColors: Record<string, string> = {
    producer: "#10b981",
    herbivore: "#fbbf24",
    carnivore: "#f43f5e",
    omnivore: "#f97316",
  };
  const roleColor = roleColors[node.ecological_role] || "#64748b";

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <div className="detail-title-section">
          <div className="detail-icon" style={{ background: `${roleColor}20`, borderColor: `${roleColor}40` }}>
            <span style={{ color: roleColor }}>🧬</span>
          </div>
          <div className="detail-titles">
            <h2>{node.lineage_code}</h2>
            <p className="detail-latin">{node.latin_name}</p>
            <p className="detail-common">{node.common_name}</p>
          </div>
        </div>
        <button className="detail-close" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      <div className="detail-body">
        {loading ? (
          <div className="detail-loading">
            <div className="loading-spinner" />
            <p>加载物种详情...</p>
          </div>
        ) : (
          <>
            {/* 物种描述 */}
            {speciesDetail?.description && (
              <div className="detail-section description">
                <div className="section-header">
                  <Sparkles size={14} />
                  <span>物种描述</span>
                </div>
                <p>{speciesDetail.description}</p>
              </div>
            )}

            {/* 基础信息 */}
            <div className="detail-section">
              <div className="section-header">
                <span>📊</span>
                <span>基础信息</span>
              </div>
              <div className="info-grid">
                <InfoItem label="状态" value={statusMap[node.state] || node.state} color={node.state === "alive" ? "#22c55e" : "#ef4444"} />
                <InfoItem label="生态角色" value={node.ecological_role} />
                <InfoItem label="出生回合" value={`T${node.birth_turn + 1}`} />
                {node.extinction_turn != null && <InfoItem label="灭绝回合" value={`T${node.extinction_turn + 1}`} color="#ef4444" />}
                <InfoItem label="当前生物量" value={node.current_population?.toLocaleString() || "0"} />
                <InfoItem label="峰值生物量" value={node.peak_population?.toLocaleString() || "0"} color="#fbbf24" />
                <InfoItem label="后代数量" value={String(node.descendant_count || 0)} />
                <InfoItem label="分化类型" value={node.speciation_type || "N/A"} />
              </div>
            </div>

            {/* 分类信息 */}
            <div className="detail-section">
              <div className="section-header">
                <span>🏷️</span>
                <span>分类学信息</span>
              </div>
              <div className="tags-container">
                {node.taxonomic_rank === "subspecies" && <Tag color="#fb923c" icon="🔸">亚种</Tag>}
                {node.taxonomic_rank === "hybrid" && <Tag color="#a78bfa" icon="⚡">杂交种</Tag>}
                {node.taxonomic_rank === "species" && <Tag color="#3b82f6">独立种</Tag>}
                {node.genus_code && <Tag color="#8b5cf6">属: {node.genus_code}</Tag>}
                {speciesDetail?.trophic_level && <Tag color="#10b981">营养级: {speciesDetail.trophic_level.toFixed(2)}</Tag>}
              </div>
            </div>

            {/* 器官系统 */}
            {speciesDetail?.organs && Object.keys(speciesDetail.organs).length > 0 && (
              <div className="detail-section">
                <div className="section-header">
                  <span>🦴</span>
                  <span>器官系统</span>
                </div>
                <div className="organs-grid">
                  {Object.entries(speciesDetail.organs).map(([category, organ]: [string, any]) => (
                    <div key={category} className="organ-card">
                      <div className="organ-category">{organCategoryMap[category] || category}</div>
                      <div className="organ-type">{organ.type || "未知"}</div>
                      {organ.acquired_turn && <div className="organ-turn">T{organ.acquired_turn}获得</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 特殊能力 */}
            {speciesDetail?.capabilities && speciesDetail.capabilities.length > 0 && (
              <div className="detail-section">
                <div className="section-header">
                  <span>⚡</span>
                  <span>特殊能力</span>
                </div>
                <div className="tags-container">
                  {speciesDetail.capabilities.map((cap: string) => (
                    <Tag key={cap} color="#3b82f6">{cap}</Tag>
                  ))}
                </div>
              </div>
            )}

            {/* 杂交信息 */}
            {node.taxonomic_rank === "hybrid" && node.hybrid_parent_codes?.length > 0 && (
              <div className="detail-section hybrid">
                <div className="section-header">
                  <span>🔀</span>
                  <span>杂交信息</span>
                </div>
                <div className="hybrid-info">
                  <div className="hybrid-row">
                    <span className="hybrid-label">亲本物种</span>
                    <span className="hybrid-value">{node.hybrid_parent_codes.join(" × ")}</span>
                  </div>
                  <div className="hybrid-row">
                    <span className="hybrid-label">可育性</span>
                    <div className="fertility-bar">
                      <div className="fertility-fill" style={{ width: `${(node.hybrid_fertility || 0) * 100}%` }} />
                    </div>
                    <span className="fertility-value" style={{ 
                      color: node.hybrid_fertility > 0.7 ? "#22c55e" : node.hybrid_fertility > 0.3 ? "#fbbf24" : "#ef4444" 
                    }}>
                      {((node.hybrid_fertility || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* 遗传距离 */}
            {node.genus_code && Object.keys(node.genetic_distances || {}).length > 0 && (
              <div className="detail-section">
                <div className="section-header">
                  <span>🧬</span>
                  <span>遗传距离 ({node.genus_code}属)</span>
                </div>
                <div className="distances-grid">
                  {Object.entries(node.genetic_distances).slice(0, 8).map(([code, distance]) => {
                    const d = distance as number;
                    const color = d < 0.2 ? "#22c55e" : d < 0.4 ? "#fbbf24" : "#ef4444";
                    return (
                      <div key={code} className="distance-item">
                        <span className="distance-code">{code}</span>
                        <span className="distance-value" style={{ color }}>{d.toFixed(3)}</span>
                      </div>
                    );
                  })}
                </div>
                {Object.keys(node.genetic_distances).length > 8 && (
                  <div className="distances-more">
                    ...还有 {Object.keys(node.genetic_distances).length - 8} 个近缘物种
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// 信息项组件
function InfoItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="info-item">
      <span className="info-label">{label}</span>
      <span className="info-value" style={{ color }}>{value}</span>
    </div>
  );
}

// 标签组件
function Tag({ children, color, icon }: { children: React.ReactNode; color: string; icon?: string }) {
  return (
    <span className="tag" style={{ 
      background: `${color}15`,
      borderColor: `${color}40`,
      color 
    }}>
      {icon && <span className="tag-icon">{icon}</span>}
      {children}
    </span>
  );
}

// 样式
const genealogyStyles = `
  /* ========== 模态窗口 ========== */
  .genealogy-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(8px);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .genealogy-modal {
    width: 98vw;
    height: 95vh;
    max-width: 2000px;
    background: linear-gradient(145deg, rgba(8, 12, 21, 0.98) 0%, rgba(15, 23, 42, 0.98) 100%);
    border: 1px solid rgba(59, 130, 246, 0.15);
    border-radius: 20px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 
      0 0 0 1px rgba(255, 255, 255, 0.05),
      0 25px 50px -12px rgba(0, 0, 0, 0.6),
      0 0 100px rgba(59, 130, 246, 0.1);
    animation: scaleIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  }

  @keyframes scaleIn {
    from { 
      opacity: 0;
      transform: scale(0.95) translateY(10px);
    }
    to { 
      opacity: 1;
      transform: scale(1) translateY(0);
    }
  }

  /* ========== 标题栏 ========== */
  .genealogy-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    background: linear-gradient(180deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.3) 100%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .header-icon {
    width: 48px;
    height: 48px;
    background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(59, 130, 246, 0.2));
    border: 1px solid rgba(34, 197, 94, 0.3);
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #22c55e;
    box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
  }

  .header-titles h1 {
    margin: 0;
    font-size: 1.4rem;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.02em;
  }

  .header-subtitle {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.7);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 500;
  }

  .header-center {
    display: flex;
    align-items: center;
  }

  .quick-stats {
    display: flex;
    gap: 8px;
  }

  .stat-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    backdrop-filter: blur(4px);
  }

  .stat-badge .stat-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .stat-badge.alive .stat-dot {
    background: #22c55e;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
  }

  .stat-badge.extinct .stat-dot {
    background: #ef4444;
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
  }

  .stat-badge.total {
    color: #60a5fa;
  }

  .stat-badge .stat-label {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.8);
  }

  .stat-badge .stat-num {
    font-size: 0.95rem;
    font-weight: 700;
    color: #f1f5f9;
    font-family: 'JetBrains Mono', monospace;
  }

  .header-right {
    display: flex;
    align-items: center;
  }

  .close-btn {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: rgba(148, 163, 184, 0.8);
    cursor: pointer;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.3);
    color: #f87171;
    transform: scale(1.05);
  }

  /* ========== 工具栏 ========== */
  .genealogy-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px;
    background: rgba(15, 23, 42, 0.4);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .toolbar-left {
    flex: 1;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  .spacing-controls {
    display: flex;
    gap: 16px;
    padding: 8px 16px;
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
  }

  .spacing-item {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .spacing-item label {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.7);
    min-width: 28px;
  }

  .spacing-item input[type="range"] {
    width: 80px;
    height: 4px;
    -webkit-appearance: none;
    background: rgba(59, 130, 246, 0.2);
    border-radius: 2px;
    cursor: pointer;
  }

  .spacing-item input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    background: #3b82f6;
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(59, 130, 246, 0.4);
    cursor: pointer;
    transition: transform 0.15s;
  }

  .spacing-item input[type="range"]::-webkit-slider-thumb:hover {
    transform: scale(1.15);
  }

  .spacing-value {
    font-size: 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    color: #60a5fa;
    min-width: 32px;
    text-align: right;
  }

  .view-toggle {
    display: flex;
    gap: 4px;
    padding: 4px;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
  }

  .toggle-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: rgba(148, 163, 184, 0.7);
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .toggle-btn:hover {
    color: #e2e8f0;
    background: rgba(255, 255, 255, 0.05);
  }

  .toggle-btn.active {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2);
  }

  /* ========== 主内容区 ========== */
  .genealogy-content {
    flex: 1;
    position: relative;
    overflow: hidden;
  }

  .list-view-container {
    height: 100%;
    overflow-y: auto;
    padding: 20px;
  }

  /* ========== 列表视图 ========== */
  .genealogy-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .tree-node-wrapper {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .tree-node {
    display: flex;
    gap: 12px;
    padding: 12px 16px;
    background: rgba(30, 41, 59, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    overflow: hidden;
  }

  .tree-node:hover {
    background: rgba(59, 130, 246, 0.1);
    border-color: rgba(59, 130, 246, 0.2);
    transform: translateX(4px);
  }

  .tree-node.extinct {
    opacity: 0.6;
  }

  .node-indicator {
    width: 4px;
    border-radius: 2px;
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
  }

  .node-content {
    flex: 1;
    padding-left: 8px;
  }

  .node-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
  }

  .node-code {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 0.95rem;
    color: #f1f5f9;
  }

  .node-status {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 600;
  }

  .node-status.alive {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
  }

  .node-status.extinct {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }

  .node-names {
    display: flex;
    gap: 12px;
    font-size: 0.85rem;
    margin-bottom: 4px;
  }

  .node-latin {
    color: rgba(148, 163, 184, 0.8);
    font-style: italic;
  }

  .node-common {
    color: rgba(226, 232, 240, 0.9);
  }

  .node-meta {
    display: flex;
    gap: 16px;
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.6);
  }

  .tree-children {
    margin-left: 24px;
    padding-left: 16px;
    border-left: 2px solid rgba(59, 130, 246, 0.2);
  }

  /* ========== 详情面板 ========== */
  .detail-panel {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 420px;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.98) 0%, rgba(10, 15, 26, 0.98) 100%);
    border-left: 1px solid rgba(59, 130, 246, 0.2);
    display: flex;
    flex-direction: column;
    animation: slideIn 0.3s ease;
    box-shadow: -10px 0 40px rgba(0, 0, 0, 0.3);
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .detail-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 20px;
    background: rgba(30, 41, 59, 0.3);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .detail-title-section {
    display: flex;
    gap: 14px;
  }

  .detail-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    border: 1px solid;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    flex-shrink: 0;
  }

  .detail-titles h2 {
    margin: 0;
    font-size: 1.3rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    color: #60a5fa;
  }

  .detail-latin {
    margin: 4px 0 0;
    font-size: 0.9rem;
    font-style: italic;
    color: rgba(148, 163, 184, 0.8);
  }

  .detail-common {
    margin: 2px 0 0;
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.9);
  }

  .detail-close {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    color: rgba(148, 163, 184, 0.7);
    cursor: pointer;
    transition: all 0.2s;
  }

  .detail-close:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.3);
    color: #f87171;
  }

  .detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }

  .detail-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;
    color: rgba(148, 163, 184, 0.6);
  }

  .loading-spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(59, 130, 246, 0.2);
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 16px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .detail-section {
    margin-bottom: 20px;
    padding: 16px;
    background: rgba(30, 41, 59, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
  }

  .detail-section.description {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(139, 92, 246, 0.08) 100%);
    border-color: rgba(59, 130, 246, 0.2);
  }

  .detail-section.hybrid {
    background: rgba(168, 85, 247, 0.08);
    border-color: rgba(168, 85, 247, 0.2);
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.9);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 12px;
  }

  .detail-section.description p {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.6;
    color: rgba(226, 232, 240, 0.9);
  }

  .info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .info-item {
    padding: 10px 12px;
    background: rgba(15, 23, 42, 0.5);
    border-radius: 8px;
  }

  .info-label {
    display: block;
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.6);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 4px;
  }

  .info-value {
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
  }

  .tags-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 12px;
    border: 1px solid;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .tag-icon {
    font-size: 0.85rem;
  }

  .organs-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .organ-card {
    padding: 10px;
    background: rgba(34, 197, 94, 0.08);
    border: 1px solid rgba(34, 197, 94, 0.15);
    border-radius: 8px;
  }

  .organ-category {
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.7);
    margin-bottom: 2px;
  }

  .organ-type {
    font-size: 0.85rem;
    font-weight: 600;
    color: #22c55e;
  }

  .organ-turn {
    font-size: 0.65rem;
    color: rgba(148, 163, 184, 0.5);
    margin-top: 4px;
  }

  .hybrid-info {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .hybrid-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .hybrid-label {
    font-size: 0.8rem;
    color: rgba(168, 85, 247, 0.8);
    min-width: 70px;
  }

  .hybrid-value {
    font-weight: 600;
    color: #d8b4fe;
  }

  .fertility-bar {
    flex: 1;
    height: 6px;
    background: rgba(168, 85, 247, 0.2);
    border-radius: 3px;
    overflow: hidden;
  }

  .fertility-fill {
    height: 100%;
    background: linear-gradient(90deg, #a855f7, #c084fc);
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .fertility-value {
    font-size: 0.9rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    min-width: 40px;
    text-align: right;
  }

  .distances-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }

  .distance-item {
    display: flex;
    justify-content: space-between;
    padding: 8px 10px;
    background: rgba(15, 23, 42, 0.5);
    border-radius: 6px;
  }

  .distance-code {
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.9);
  }

  .distance-value {
    font-size: 0.85rem;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
  }

  .distances-more {
    text-align: center;
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.5);
    margin-top: 8px;
  }

  /* ========== 错误/空状态 ========== */
  .genealogy-error-container,
  .genealogy-empty-container {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 400px;
    background: rgba(15, 23, 42, 0.95);
    border-radius: 12px;
    padding: 40px;
  }

  .error-content,
  .empty-content {
    text-align: center;
    color: rgba(148, 163, 184, 0.8);
  }

  .error-icon,
  .empty-icon {
    font-size: 3rem;
    margin-bottom: 16px;
  }

  .error-text {
    font-size: 1rem;
    margin-bottom: 16px;
  }

  .empty-title {
    font-size: 1.2rem;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 8px;
  }

  .empty-hint {
    font-size: 0.9rem;
  }

  .retry-btn {
    padding: 10px 24px;
    background: rgba(59, 130, 246, 0.2);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 8px;
    color: #60a5fa;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .retry-btn:hover {
    background: rgba(59, 130, 246, 0.3);
    transform: translateY(-2px);
  }

  /* ========== 滚动条 ========== */
  .detail-body::-webkit-scrollbar,
  .list-view-container::-webkit-scrollbar {
    width: 6px;
  }

  .detail-body::-webkit-scrollbar-track,
  .list-view-container::-webkit-scrollbar-track {
    background: rgba(15, 23, 42, 0.5);
  }

  .detail-body::-webkit-scrollbar-thumb,
  .list-view-container::-webkit-scrollbar-thumb {
    background: rgba(59, 130, 246, 0.3);
    border-radius: 3px;
  }

  .detail-body::-webkit-scrollbar-thumb:hover,
  .list-view-container::-webkit-scrollbar-thumb:hover {
    background: rgba(59, 130, 246, 0.5);
  }
`;
