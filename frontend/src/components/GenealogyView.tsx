import { useState, useMemo, useEffect } from "react";
import { List, GitBranch } from "lucide-react";
import type { LineageNode, LineageTree } from "../services/api.types";
import { GenealogySkeletonLoader } from "./SkeletonLoader";
import { GenealogyGraphView } from "./GenealogyGraphView";
import { GenealogyFilters, type FilterOptions } from "./GenealogyFilters";
import { fetchSpeciesDetail } from "../services/api";
import { GamePanel } from "./common/GamePanel";

interface Props {
  tree: LineageTree | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose?: () => void; // Add onClose prop
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
      // 状态筛选
      if (filters.states.length > 0 && !filters.states.includes(node.state)) {
        return false;
      }
      
      // 生态角色筛选
      if (filters.ecologicalRoles.length > 0 && !filters.ecologicalRoles.includes(node.ecological_role)) {
        return false;
      }
      
      // 层级筛选
      if (filters.tiers.length > 0) {
        if (!node.tier && !filters.tiers.includes("none")) return false;
        if (node.tier && !filters.tiers.includes(node.tier)) return false;
      }
      
      // 回合范围筛选
      if (node.birth_turn < filters.turnRange[0] || node.birth_turn > filters.turnRange[1]) {
        return false;
      }
      
      // 搜索词筛选
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
      <div className="genealogy-error">
        <p>{error}</p>
        <button type="button" onClick={onRetry}>
          重试
        </button>
      </div>
    );
  }
  
  if (!tree || tree.nodes.length === 0) {
    return <p>暂无族谱数据，运行几轮推演后再试。</p>;
  }

  return (
    <GamePanel
      title="物种演化族谱 (Evolutionary Genealogy)"
      onClose={onClose}
      variant="modal"
      width="98vw"
      height="95vh"
    >
      <div className="genealogy-container" style={{ height: "100%", display: "flex", flexDirection: "column", padding: "16px" }}>
        <div className="genealogy-toolbar">
          <GenealogyFilters 
            filters={filters} 
            maxTurn={maxTurn}
            onChange={setFilters} 
          />
          
          <div className="view-mode-toggle">
            <button
              className={`chip-button ${viewMode === "graph" ? "active" : ""}`}
              onClick={() => setViewMode("graph")}
              title="图谱视图"
            >
              <GitBranch size={16} />
              <span>图谱</span>
            </button>
            <button
              className={`chip-button ${viewMode === "list" ? "active" : ""}`}
              onClick={() => setViewMode("list")}
              title="列表视图"
            >
              <List size={16} />
              <span>列表</span>
            </button>
          </div>
        </div>

        <div className="genealogy-stats" style={{ 
          padding: "0.75rem", 
          background: "rgba(255, 255, 255, 0.03)",
          borderRadius: "8px",
          marginBottom: "1rem",
          display: "flex",
          gap: "1.5rem",
          fontSize: "0.9rem"
        }}>
          <div>
            <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>总物种: </span>
            <strong>{tree.nodes.length}</strong>
          </div>
          <div>
            <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>筛选结果: </span>
            <strong>{filteredNodes.length}</strong>
          </div>
          <div>
            <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>存活: </span>
            <strong style={{ color: "#22c55e" }}>
              {filteredNodes.filter(n => n.state === "alive").length}
            </strong>
          </div>
          <div>
            <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>灭绝: </span>
            <strong style={{ color: "#f87171" }}>
              {filteredNodes.filter(n => n.state === "extinct").length}
            </strong>
          </div>
        </div>

        <div style={{ flex: 1, overflow: "hidden", position: "relative", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "8px" }}>
            {viewMode === "graph" ? (
                <GenealogyGraphView 
                nodes={filteredNodes}
                onNodeClick={setSelectedNode}
                />
            ) : (
                <div style={{ height: "100%", overflowY: "auto" }}>
                    <ListView nodes={filteredNodes} onSelectNode={setSelectedNode} />
                </div>
            )}
        </div>

        {selectedNode && (
          <NodeDetailCard 
            node={selectedNode} 
            onClose={() => setSelectedNode(null)} 
          />
        )}
      </div>
    </GamePanel>
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
    <div className="genealogy-grid" style={{ padding: "16px" }}>
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
  const stateClass = `state-${node.state.replace(/\s+/g, "").toLowerCase()}`;
  
  // 根据生态角色添加样式类
  const roleClass = `role-${node.ecological_role}`;
  
  return (
    <div 
      className={`genealogy-node species-card ${roleClass}`} 
      style={{ marginLeft: depth * 20 }}
      onClick={() => onSelect?.(node)}
    >
      <header>
        <div>
          <strong className="lineage-code">{node.lineage_code}</strong>
          <span style={{ marginLeft: '0.5rem' }}>
            {node.latin_name} / {node.common_name}
          </span>
        </div>
        <span className={`state ${stateClass}`}>{statusMap[node.state] || node.state}</span>
      </header>
      <div className="node-body">
        <div style={{ display: "flex", gap: "1rem", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          <span>出生: T{node.birth_turn}</span>
          {node.extinction_turn && <span>灭绝: T{node.extinction_turn}</span>}
          <span>后代: {node.descendant_count}</span>
        </div>
        <div style={{ fontSize: "0.85rem", marginTop: "0.3rem", color: "rgba(226, 236, 255, 0.7)" }}>
          当前人口: {node.current_population.toLocaleString()} | 峰值: {node.peak_population.toLocaleString()}
        </div>
        {node.major_events.length > 0 && (
          <ul style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            {node.major_events.slice(0, 3).map((event, idx) => (
              <li key={idx}>{event}</li>
            ))}
          </ul>
        )}
      </div>
      {children.length > 0 && (
        <div className="genealogy-children">
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

// 节点详情卡片（增强版） - 使用 sidebar-right 变体
function NodeDetailCard({ node, onClose }: { node: LineageNode; onClose: () => void }) {
  const [speciesDetail, setSpeciesDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // 获取物种完整详情
  useEffect(() => {
    setLoading(true);
    fetchSpeciesDetail(node.lineage_code)
      .then(setSpeciesDetail)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [node.lineage_code]);

  return (
    <GamePanel
      title="物种详情"
      onClose={onClose}
      variant="sidebar-right"
      width="400px"
    >
      <div style={{ padding: "20px" }}>
        {/* 标题栏 */}
        <div style={{ marginBottom: "1.5rem", borderBottom: "1px solid rgba(255, 255, 255, 0.1)", paddingBottom: "1rem" }}>
          <h2 className="lineage-code" style={{ margin: 0, fontSize: "1.5rem", color: "#60a5fa" }}>
            {node.lineage_code}
          </h2>
          <p style={{ margin: "0.5rem 0 0", fontSize: "1.1rem", color: "#e2ecff" }}>
            <em>{node.latin_name}</em>
          </p>
          <p style={{ margin: "0.25rem 0 0", color: "rgba(226, 236, 255, 0.7)", fontSize: "0.95rem" }}>
            {node.common_name}
          </p>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "2rem", color: "rgba(226, 236, 255, 0.6)" }}>
            <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>⏳</div>
            <p>加载物种详情中...</p>
          </div>
        ) : (
          <>
            {/* 物种描述 */}
            {speciesDetail?.description && (
              <div style={{ 
                marginBottom: "1.5rem", 
                padding: "1rem", 
                background: "rgba(100, 150, 255, 0.08)", 
                borderRadius: "12px",
                borderLeft: "4px solid #60a5fa"
              }}>
                <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.5rem", color: "#60a5fa", textTransform: "uppercase", letterSpacing: "1px" }}>
                  📝 物种描述
                </div>
                <p style={{ margin: 0, lineHeight: "1.6", color: "rgba(226, 236, 255, 0.9)", fontSize: "0.9rem" }}>
                  {speciesDetail.description}
                </p>
              </div>
            )}

            {/* 基础信息网格 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
              <InfoCard label="状态" value={statusMap[node.state] || node.state} color={node.state === "alive" ? "#22c55e" : "#f87171"} />
              <InfoCard label="生态角色" value={node.ecological_role} />
              <InfoCard label="出生回合" value={`T${node.birth_turn}`} />
              {node.extinction_turn && <InfoCard label="灭绝回合" value={`T${node.extinction_turn}`} color="#f87171" />}
              <InfoCard label="当前人口" value={node.current_population.toLocaleString()} />
              <InfoCard label="峰值人口" value={node.peak_population.toLocaleString()} color="#fbbf24" />
              <InfoCard label="后代数量" value={node.descendant_count.toString()} />
              <InfoCard label="分化类型" value={node.speciation_type} />
            </div>

            {/* 分类信息 */}
            <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "rgba(255, 255, 255, 0.03)", borderRadius: "12px" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.75rem", color: "#a78bfa", textTransform: "uppercase", letterSpacing: "1px" }}>
                🧬 分类学信息
              </div>
              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                {node.taxonomic_rank === "subspecies" && (
                  <Badge color="#fb923c" icon="🔸">亚种</Badge>
                )}
                {node.taxonomic_rank === "hybrid" && (
                  <Badge color="#a78bfa" icon="⚡">杂交种</Badge>
                )}
                {node.taxonomic_rank === "species" && (
                  <Badge color="#3b82f6">独立种</Badge>
                )}
                {node.genus_code && <Badge color="#8b5cf6">属: {node.genus_code}</Badge>}
                {speciesDetail?.trophic_level && (
                  <Badge color="#10b981">营养级: {speciesDetail.trophic_level.toFixed(2)}</Badge>
                )}
              </div>
            </div>

            {/* 器官系统 */}
            {speciesDetail?.organs && Object.keys(speciesDetail.organs).length > 0 && (
              <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "rgba(34, 197, 94, 0.08)", borderRadius: "12px" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.75rem", color: "#22c55e", textTransform: "uppercase", letterSpacing: "1px" }}>
                  🦴 器官系统
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.75rem" }}>
                  {Object.entries(speciesDetail.organs).map(([category, organ]: [string, any]) => (
                    <div key={category} style={{ 
                      padding: "0.75rem", 
                      background: "rgba(34, 197, 94, 0.1)", 
                      borderRadius: "8px", 
                      border: "1px solid rgba(34, 197, 94, 0.2)"
                    }}>
                      <div style={{ fontSize: "0.75rem", color: "rgba(226, 236, 255, 0.6)", marginBottom: "0.25rem" }}>
                        {organCategoryMap[category] || category}
                      </div>
                      <div style={{ fontWeight: "bold", color: "#22c55e", fontSize: "0.9rem" }}>
                        {organ.type || "未知"}
                      </div>
                      {organ.acquired_turn && (
                        <div style={{ fontSize: "0.7rem", color: "rgba(226, 236, 255, 0.5)", marginTop: "0.25rem" }}>
                          T{organ.acquired_turn}获得
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 能力标签 */}
            {speciesDetail?.capabilities && speciesDetail.capabilities.length > 0 && (
              <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "rgba(59, 130, 246, 0.08)", borderRadius: "12px" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.75rem", color: "#3b82f6", textTransform: "uppercase", letterSpacing: "1px" }}>
                  ⚡ 特殊能力
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {speciesDetail.capabilities.map((cap: string) => (
                    <Badge key={cap} color="#3b82f6">{cap}</Badge>
                  ))}
                </div>
              </div>
            )}

            {/* 杂交信息 */}
            {node.taxonomic_rank === "hybrid" && node.hybrid_parent_codes.length > 0 && (
              <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "rgba(167, 139, 250, 0.1)", borderRadius: "12px", border: "1px solid rgba(167, 139, 250, 0.3)" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.75rem", color: "#a78bfa", textTransform: "uppercase", letterSpacing: "1px" }}>
                  ⚡ 杂交信息
                </div>
                <div style={{ fontSize: "0.9rem" }}>
                  <div style={{ marginBottom: "0.5rem" }}>
                    <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>亲本物种: </span>
                    <strong>{node.hybrid_parent_codes.join(" × ")}</strong>
                  </div>
                  <div>
                    <span style={{ color: "rgba(226, 236, 255, 0.6)" }}>可育性: </span>
                    <strong style={{ color: node.hybrid_fertility > 0.7 ? "#22c55e" : node.hybrid_fertility > 0.3 ? "#fbbf24" : "#f87171" }}>
                      {(node.hybrid_fertility * 100).toFixed(0)}%
                    </strong>
                  </div>
                </div>
              </div>
            )}

            {/* 遗传距离 */}
            {node.genus_code && Object.keys(node.genetic_distances).length > 0 && (
              <div style={{ padding: "1rem", background: "rgba(251, 191, 36, 0.08)", borderRadius: "12px", border: "1px solid rgba(251, 191, 36, 0.2)" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "0.75rem", color: "#fbbf24", textTransform: "uppercase", letterSpacing: "1px" }}>
                  🧬 遗传距离 ({node.genus_code}属)
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "0.5rem" }}>
                  {Object.entries(node.genetic_distances).slice(0, 8).map(([code, distance]) => {
                    const color = distance < 0.2 ? "#22c55e" : distance < 0.4 ? "#fbbf24" : "#f87171";
                    return (
                      <div key={code} style={{ 
                        display: "flex", 
                        justifyContent: "space-between", 
                        padding: "0.5rem",
                        background: "rgba(255, 255, 255, 0.03)",
                        borderRadius: "6px"
                      }}>
                        <span style={{ fontSize: "0.85rem" }}>{code}</span>
                        <span style={{ color, fontWeight: "bold", fontSize: "0.85rem" }}>{distance.toFixed(3)}</span>
                      </div>
                    );
                  })}
                </div>
                {Object.keys(node.genetic_distances).length > 8 && (
                  <div style={{ color: "rgba(226, 236, 255, 0.5)", fontSize: "0.75rem", marginTop: "0.5rem", textAlign: "center" }}>
                    ...还有 {Object.keys(node.genetic_distances).length - 8} 个近缘物种
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </GamePanel>
  );
}

// 信息卡片组件
function InfoCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      padding: "0.75rem",
      background: "rgba(255, 255, 255, 0.03)",
      borderRadius: "8px",
      border: "1px solid rgba(255, 255, 255, 0.1)"
    }}>
      <div style={{ fontSize: "0.7rem", color: "rgba(226, 236, 255, 0.5)", textTransform: "uppercase", marginBottom: "0.25rem", letterSpacing: "0.5px" }}>
        {label}
      </div>
      <div style={{ fontWeight: "bold", fontSize: "0.95rem", color: color || "#e2ecff" }}>
        {value}
      </div>
    </div>
  );
}

// 徽章组件
function Badge({ children, color, icon }: { children: React.ReactNode; color: string; icon?: string }) {
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "0.25rem",
      padding: "0.35rem 0.75rem",
      background: `${color}22`,
      border: `1px solid ${color}44`,
      borderRadius: "6px",
      fontSize: "0.8rem",
      fontWeight: "600",
      color,
    }}>
      {icon && <span>{icon}</span>}
      {children}
    </span>
  );
}