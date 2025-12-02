/**
 * FoodWebGraph - 食物网图（重构版）
 *
 * 使用模块化的 hooks、类型和 CSS Modules
 */

import { useRef, useEffect, useState, useCallback } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { createPortal } from "react-dom";
import { X, Search, Filter, RefreshCw, Wrench, AlertTriangle, Info } from "lucide-react";
import { useFoodWebData } from "./hooks/useFoodWebData";
import type { FoodWebGraphProps, GraphNode, GraphLink, FilterMode } from "./types";
import { TROPHIC_COLORS, KEYSTONE_COLOR } from "./types";
import styles from "./FoodWebGraph.module.css";

// ============ 常量 ============
const MAX_NODES = 150;
const MAX_LINKS = 500;

// ============ 节点信息卡片 ============
function NodeInfoCard({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  const trophicInfo = TROPHIC_COLORS[node.trophicLevel] || TROPHIC_COLORS[1];

  return (
    <div className={styles.nodeInfoCard}>
      <div className={styles.cardHeader}>
        <h3>{node.name}</h3>
        <button className={styles.closeBtn} onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <div className={styles.cardContent}>
        <div className={styles.infoRow}>
          <span className={styles.label}>编码</span>
          <span className={styles.value}>{node.id}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.label}>营养级</span>
          <span className={styles.value} style={{ color: trophicInfo.main }}>
            {trophicInfo.name} (Lv.{node.trophicLevel})
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.label}>种群</span>
          <span className={styles.value}>{node.population.toLocaleString()}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.label}>猎物数</span>
          <span className={styles.value}>{node.preyCount}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.label}>捕食者数</span>
          <span className={styles.value}>{node.predatorCount}</span>
        </div>
        {node.isKeystone && (
          <div className={styles.keystoneBadge}>⭐ 关键物种</div>
        )}
      </div>
    </div>
  );
}

// ============ 分析面板 ============
function AnalysisPanel({
  analysis,
  onRepair,
  repairing,
}: {
  analysis: { health_score?: number; issues?: string[]; recommendations?: string[] } | null;
  onRepair: () => void;
  repairing: boolean;
}) {
  if (!analysis) return null;

  const healthScore = analysis.health_score ?? 0;
  const issues = analysis.issues ?? [];
  const recommendations = analysis.recommendations ?? [];

  const healthColor =
    healthScore >= 0.7 ? "#22c55e" : healthScore >= 0.4 ? "#f59e0b" : "#ef4444";

  return (
    <div className={styles.analysisPanel}>
      <div className={styles.healthScore} style={{ borderColor: healthColor }}>
        <div className={styles.scoreValue} style={{ color: healthColor }}>
          {(healthScore * 100).toFixed(0)}%
        </div>
        <div className={styles.scoreLabel}>生态健康度</div>
      </div>

      {issues.length > 0 && (
        <div className={styles.issuesSection}>
          <h4>
            <AlertTriangle size={14} /> 问题
          </h4>
          <ul>
            {issues.slice(0, 3).map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className={styles.recommendationsSection}>
          <h4>
            <Info size={14} /> 建议
          </h4>
          <ul>
            {recommendations.slice(0, 2).map((rec, i) => (
              <li key={i}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      <button className={styles.repairBtn} onClick={onRepair} disabled={repairing}>
        <Wrench size={14} />
        {repairing ? "修复中..." : "自动修复"}
      </button>
    </div>
  );
}

// ============ 主组件 ============
export function FoodWebGraph({ speciesList, onClose, onSelectSpecies }: FoodWebGraphProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<ForceGraphMethods<any, any>>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [mounted, setMounted] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const {
    graphData,
    analysis,
    loading,
    error,
    repairing,
    filterMode,
    setFilterMode,
    searchQuery,
    setSearchQuery,
    refresh,
    repair,
  } = useFoodWebData({ speciesList });

  // 挂载动画
  useEffect(() => {
    setMounted(true);
    document.body.style.overflow = "hidden";
    return () => {
      setMounted(false);
      document.body.style.overflow = "";
    };
  }, []);

  // 响应式尺寸
  useEffect(() => {
    function updateDimensions() {
      setDimensions({
        width: window.innerWidth * 0.96,
        height: window.innerHeight * 0.88,
      });
    }
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // 节点点击
  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    onSelectSpecies(node.id);
  }, [onSelectSpecies]);

  // 节点悬停
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? "pointer" : "default";
    }
  }, []);

  // 检查是否需要截断
  const isTruncated = graphData.nodes.length > MAX_NODES || graphData.links.length > MAX_LINKS;
  const displayNodes = isTruncated ? graphData.nodes.slice(0, MAX_NODES) : graphData.nodes;
  const nodeIds = new Set(displayNodes.map(n => n.id));
  const displayLinks = (isTruncated 
    ? graphData.links.filter(l => nodeIds.has(l.source as string) && nodeIds.has(l.target as string)).slice(0, MAX_LINKS)
    : graphData.links);

  // 节点绘制
  const nodeCanvasObject = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D) => {
    const size = Math.max(4, Math.min(20, node.val));
    const isHovered = hoveredNode?.id === node.id;
    const isSelected = selectedNode?.id === node.id;
    const trophicColor = TROPHIC_COLORS[node.trophicLevel] || TROPHIC_COLORS[1];
    const color = node.isKeystone ? KEYSTONE_COLOR.main : trophicColor.main;
    const glow = node.isKeystone ? KEYSTONE_COLOR.glow : trophicColor.glow;

    // 发光效果
    if (isHovered || isSelected || node.isKeystone) {
      ctx.beginPath();
      ctx.arc(node.x || 0, node.y || 0, size * 1.5, 0, 2 * Math.PI);
      ctx.fillStyle = glow;
      ctx.fill();
    }

    // 节点圆
    ctx.beginPath();
    ctx.arc(node.x || 0, node.y || 0, size, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    // 边框
    if (isSelected) {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 标签
    if (isHovered || isSelected) {
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillStyle = "#fff";
      ctx.fillText(node.name, node.x || 0, (node.y || 0) + size + 12);
    }
  }, [hoveredNode, selectedNode]);

  // 连接绘制
  const linkCanvasObject = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D) => {
    const source = link.source as unknown as GraphNode;
    const target = link.target as unknown as GraphNode;
    if (!source.x || !target.x) return;

    ctx.beginPath();
    ctx.moveTo(source.x, source.y || 0);
    ctx.lineTo(target.x, target.y || 0);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
    ctx.lineWidth = Math.max(0.5, link.value * 0.5);
    ctx.stroke();
  }, []);

  // 渲染内容
  const content = (
    <div
      className={`${styles.overlay} ${mounted ? styles.visible : ""}`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className={styles.container} ref={containerRef}>
        {/* 头部 */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h2>🕸️ 食物网</h2>
            <span className={styles.nodeCount}>
              {displayNodes.length} 物种 / {displayLinks.length} 关系
            </span>
          </div>
          <div className={styles.headerRight}>
            <button className={styles.iconBtn} onClick={refresh} title="刷新">
              <RefreshCw size={18} />
            </button>
            <button className={`${styles.iconBtn} ${styles.close}`} onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* 控制栏 */}
        <div className={styles.controls}>
          {/* 搜索 */}
          <div className={styles.searchBox}>
            <Search size={16} />
            <input
              type="text"
              placeholder="搜索物种..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* 过滤 */}
          <div className={styles.filterGroup}>
            <Filter size={16} />
            <select
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value as FilterMode)}
            >
              <option value="all">全部</option>
              <option value="producers">生产者</option>
              <option value="consumers">消费者</option>
              <option value="keystone">关键物种</option>
            </select>
          </div>

          {/* 图例 */}
          <div className={styles.legend}>
            {Object.entries(TROPHIC_COLORS).map(([level, info]) => (
              <div key={level} className={styles.legendItem}>
                <span className={styles.legendDot} style={{ background: info.main }} />
                <span>{info.name}</span>
              </div>
            ))}
            <div className={styles.legendItem}>
              <span className={styles.legendDot} style={{ background: KEYSTONE_COLOR.main }} />
              <span>关键物种</span>
            </div>
          </div>
        </div>

        {/* 图表区域 */}
        <div className={styles.graphArea}>
          {loading ? (
            <div className={styles.loadingState}>
              <div className={styles.spinner} />
              <p>加载食物网数据...</p>
            </div>
          ) : error ? (
            <div className={styles.errorState}>
              <AlertTriangle size={48} />
              <p>{error}</p>
              <button onClick={refresh}>重试</button>
            </div>
          ) : displayNodes.length === 0 ? (
            <div className={styles.emptyState}>
              <p>暂无食物网数据</p>
            </div>
          ) : (
            <ForceGraph2D
              ref={graphRef}
              graphData={{ nodes: displayNodes, links: displayLinks }}
              width={dimensions.width}
              height={dimensions.height - 120}
              nodeCanvasObject={nodeCanvasObject}
              linkCanvasObject={linkCanvasObject}
              onNodeClick={handleNodeClick}
              onNodeHover={handleNodeHover}
              nodeLabel=""
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.8}
              cooldownTicks={100}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
            />
          )}

          {/* 截断警告 */}
          {isTruncated && (
            <div className={styles.truncationWarning}>
              ⚠️ 数据量过大，仅显示前 {MAX_NODES} 个物种
            </div>
          )}
        </div>

        {/* 分析面板 */}
        {analysis && <AnalysisPanel analysis={analysis} onRepair={repair} repairing={repairing} />}

        {/* 选中节点信息 */}
        {selectedNode && <NodeInfoCard node={selectedNode} onClose={() => setSelectedNode(null)} />}
      </div>
    </div>
  );

  return createPortal(content, document.body);
}

export default FoodWebGraph;

