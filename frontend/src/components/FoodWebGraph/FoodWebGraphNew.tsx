/**
 * FoodWebGraph - 食物网可视化（美化版）
 *
 * 特点：
 * - 三栏布局（左侧统计、中间图表、右侧信息）
 * - 丰富的统计卡片和健康度指示
 * - 美观的 emoji 图标装饰
 * - 流畅的动画效果
 */

import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { createPortal } from "react-dom";
import { forceX, forceY } from "d3-force";
import { useFoodWebData } from "./hooks/useFoodWebData";
import type { FoodWebGraphProps, GraphNode, GraphLink, FilterMode } from "./types";
import styles from "./FoodWebGraph.module.css";

// ============ 常量 ============
const MAX_NODES = 120;
const MAX_LINKS = 350;
const PERFORMANCE_THRESHOLD = 80; // 超过此数量时禁用粒子效果

// 营养级颜色配置
const TROPHIC_COLORS: Record<number, { main: string; glow: string; name: string }> = {
  1: { main: "#22c55e", glow: "rgba(34, 197, 94, 0.5)", name: "生产者" },
  2: { main: "#eab308", glow: "rgba(234, 179, 8, 0.5)", name: "初级消费者" },
  3: { main: "#f97316", glow: "rgba(249, 115, 22, 0.5)", name: "次级消费者" },
  4: { main: "#ef4444", glow: "rgba(239, 68, 68, 0.5)", name: "顶级捕食者" },
};

const KEYSTONE_COLOR = { main: "#ec4899", glow: "rgba(236, 72, 153, 0.6)" };

// 食性类型标签
function getDietTypeLabel(dietType: string): string {
  const labels: Record<string, string> = {
    autotroph: "🌱 自养生物",
    herbivore: "🌿 草食动物",
    carnivore: "🥩 肉食动物",
    omnivore: "🍽️ 杂食动物",
    detritivore: "🍂 腐食动物",
  };
  return labels[dietType] || dietType;
}

// ============ 主组件 ============
export function FoodWebGraph({ speciesList, onClose, onSelectSpecies }: FoodWebGraphProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<ForceGraphMethods<any, any>>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);

  // 使用 ref 存储悬停状态，避免重新渲染导致抖动
  const hoveredNodeRef = useRef<GraphNode | null>(null);
  const selectedNodeRef = useRef<GraphNode | null>(null);

  const [mounted, setMounted] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredLink, setHoveredLink] = useState<GraphLink | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // 同步选中状态到 ref
  selectedNodeRef.current = selectedNode;
  hoveredNodeRef.current = hoveredNode;

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
    const timer = setTimeout(() => setMounted(true), 50);
    document.body.style.overflow = "hidden";
    return () => {
      clearTimeout(timer);
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

  // 检查是否需要截断，并准备显示数据（使用批量处理优化）
  const displayData = useMemo(() => {
    const nodes = graphData.nodes;
    const links = graphData.links;
    const nodeCount = nodes.length;
    const linkCount = links.length;
    const isTruncated = nodeCount > MAX_NODES || linkCount > MAX_LINKS;
    
    // 1. 批量构建节点索引（使用 Map 实现 O(1) 查找）
    const nodeLimit = Math.min(nodeCount, MAX_NODES);
    const nodeIndexMap = new Map<string, number>();
    for (let i = 0; i < nodeLimit; i++) {
      nodeIndexMap.set(nodes[i].id, i);
    }
    
    // 2. 批量处理链接：使用位掩码数组标记有效链接，避免动态数组 push
    const linkLimit = Math.min(linkCount, MAX_LINKS);
    const validLinkIndices = new Uint16Array(linkLimit); // 存储有效链接的索引
    const needsRepair = new Uint8Array(linkLimit); // 标记是否需要修复 source/target
    let validCount = 0;
    
    for (let i = 0; i < linkCount && validCount < linkLimit; i++) {
      const l = links[i];
      // 内联获取 ID，避免函数调用开销
      const source = l.source;
      const target = l.target;
      const sourceId = typeof source === 'string' ? source : (source as { id: string }).id;
      const targetId = typeof target === 'string' ? target : (target as { id: string }).id;
      
      // 使用 Map 进行 O(1) 查找
      if (nodeIndexMap.has(sourceId) && nodeIndexMap.has(targetId)) {
        validLinkIndices[validCount] = i;
        needsRepair[validCount] = (typeof source !== 'string' || typeof target !== 'string') ? 1 : 0;
        validCount++;
      }
    }
    
    // 3. 批量构建结果数组（预分配大小）
    const displayLinks = new Array<GraphLink>(validCount);
    for (let i = 0; i < validCount; i++) {
      const l = links[validLinkIndices[i]];
      if (needsRepair[i]) {
        const source = l.source;
        const target = l.target;
        displayLinks[i] = {
          ...l,
          source: typeof source === 'string' ? source : (source as { id: string }).id,
          target: typeof target === 'string' ? target : (target as { id: string }).id,
        };
      } else {
        displayLinks[i] = l;
      }
    }
    
    // 4. 批量处理节点：检查是否有 D3 添加的属性需要清除
    const displayNodes = new Array<GraphNode>(nodeLimit);
    for (let i = 0; i < nodeLimit; i++) {
      const n = nodes[i];
      // 只在有 D3 属性时才创建新对象
      displayNodes[i] = n.x !== undefined 
        ? { ...n, x: undefined, y: undefined, vx: undefined, vy: undefined, fx: undefined, fy: undefined }
        : n;
    }

    return { displayNodes, displayLinks, isTruncated };
  }, [graphData]);

  const { displayNodes, displayLinks, isTruncated } = displayData;

  // 统计数据（单次遍历计算所有统计值）
  const stats = useMemo(() => {
    const nodes = graphData.nodes;
    const nodeCount = nodes.length;
    if (nodeCount === 0) return null;
    
    // 单次遍历计算所有统计值
    let keystoneCount = 0;
    let trophicSum = 0;
    let producerCount = 0;
    
    for (let i = 0; i < nodeCount; i++) {
      const n = nodes[i];
      if (n.isKeystone) keystoneCount++;
      trophicSum += n.trophicLevel;
      if (n.trophicLevel < 2) producerCount++;
    }
    
    const linkCount = graphData.links.length;
    
    return {
      total: nodeCount,
      links: linkCount,
      keystone: keystoneCount,
      avgTrophic: (trophicSum / nodeCount).toFixed(2),
      producers: producerCount,
      consumers: nodeCount - producerCount,
      connectivity: ((linkCount / nodeCount) * 100).toFixed(1),
    };
  }, [graphData]);

  // 配置力模拟
  useEffect(() => {
    if (graphRef.current && displayNodes.length > 0) {
      const isLargeGraph = displayNodes.length > PERFORMANCE_THRESHOLD;
      
      // 斥力 - 根据图大小调整，大图使用更弱的斥力和更小的范围
      const chargeForce = graphRef.current.d3Force("charge");
      if (chargeForce) {
        const strength = isLargeGraph ? -100 : -180;
        const maxDist = isLargeGraph ? 200 : 300;
        (chargeForce as any).strength(strength).distanceMax(maxDist);
      }
      
      // 连接力 - 大图使用更短的连接距离
      const linkDistance = isLargeGraph ? 60 : 100;
      graphRef.current.d3Force("link")?.distance(linkDistance);
      
      // 添加向心力 - 将所有节点拉向中心，防止孤立节点飘走
      const centerStrength = isLargeGraph ? 0.08 : 0.05;
      graphRef.current.d3Force("x", forceX(0).strength(centerStrength));
      graphRef.current.d3Force("y", forceY(0).strength(centerStrength));
      
      setTimeout(() => graphRef.current?.zoomToFit(400, 80), 600);
    }
  }, [displayNodes.length]);

  // 节点点击
  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      setSelectedNode(node);
      onSelectSpecies(node.id);
    },
    [onSelectSpecies]
  );

  // 重置视图
  const handleResetView = useCallback(() => {
    graphRef.current?.zoomToFit(400, 80);
  }, []);

  // 节点悬停
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node || null);
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? "pointer" : "grab";
    }
  }, []);

  // 链接悬停
  const handleLinkHover = useCallback((link: GraphLink | null) => {
    setHoveredLink(link || null);
  }, []);

  // 节点绘制
  const nodeCanvasObject = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) {
        return;
      }

      const isHovered = hoveredNodeRef.current?.id === node.id;
      const isSelected = selectedNodeRef.current?.id === node.id;
      const nodeSize = Math.max(4, Math.log10(node.population + 1) * 3) * (isHovered || isSelected ? 1.3 : 1);

      const trophicTier = Math.min(4, Math.max(1, Math.floor(node.trophicLevel)));
      const colorConfig = TROPHIC_COLORS[trophicTier];
      const color = node.isKeystone ? KEYSTONE_COLOR.main : colorConfig.main;

      const x = node.x || 0;
      const y = node.y || 0;

      // 光晕效果
      if (node.isKeystone || isHovered || isSelected) {
        const glowSize = nodeSize + (isHovered || isSelected ? 8 : 5);
        const innerRadius = Math.max(0.1, nodeSize * 0.5);
        const outerRadius = Math.max(innerRadius + 0.1, glowSize);

        try {
          const gradient = ctx.createRadialGradient(
            x, y, innerRadius,
            x, y, outerRadius
          );
          gradient.addColorStop(0, node.isKeystone ? KEYSTONE_COLOR.glow : `${color}60`);
          gradient.addColorStop(1, "transparent");
          ctx.beginPath();
          ctx.arc(x, y, glowSize, 0, 2 * Math.PI);
          ctx.fillStyle = gradient;
          ctx.fill();
        } catch {
          // 忽略渐变创建失败
        }
      }

      // 主节点
      ctx.beginPath();
      ctx.arc(x, y, nodeSize, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // 边框
      if (isSelected) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 3 / globalScale;
        ctx.stroke();
      } else if (isHovered) {
        ctx.strokeStyle = "rgba(255,255,255,0.8)";
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }

      // 关键物种标记
      if (node.isKeystone) {
        ctx.beginPath();
        ctx.arc(x, y, nodeSize + 4, 0, 2 * Math.PI);
        ctx.strokeStyle = KEYSTONE_COLOR.main;
        ctx.lineWidth = 2 / globalScale;
        ctx.setLineDash([4 / globalScale, 4 / globalScale]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // 标签
      if (globalScale > 0.6 || isHovered || isSelected) {
        const fontSize = Math.max(10, 14 / globalScale);
        ctx.font = `${isHovered || isSelected ? "bold " : ""}${fontSize}px "Segoe UI", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        const label = node.id;
        const textWidth = ctx.measureText(label).width;
        const padding = 4 / globalScale;
        const bgHeight = fontSize + padding * 2;
        const bgY = y + nodeSize + 4;

        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.beginPath();
        ctx.roundRect(
          x - textWidth / 2 - padding,
          bgY - padding,
          textWidth + padding * 2,
          bgHeight,
          3 / globalScale
        );
        ctx.fill();

        ctx.fillStyle = isHovered || isSelected ? "#fff" : "rgba(255,255,255,0.85)";
        ctx.fillText(label, x, bgY);
      }
    },
    []
  );

  // ESC 关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // 渲染内容
  const renderContent = () => {
    if (loading) {
      return (
        <div className={styles.loading}>
          <div className={styles.loadingSpinner} />
          <span>正在构建生态网络...</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className={styles.error}>
          <span className={styles.errorIcon}>⚠️</span>
          <span>加载失败: {error}</span>
          <button onClick={refresh} className={styles.retryBtn}>
            重试
          </button>
        </div>
      );
    }

    return (
      <>
        {/* 左侧控制面板 */}
        <div className={`${styles.sidebar} ${styles.sidebarLeft}`}>
          {/* 统计卡片 */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon}>📊</span>
              <span>网络统计</span>
            </div>
            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats?.total || 0}</span>
                <span className={styles.statLabel}>物种总数</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats?.links || 0}</span>
                <span className={styles.statLabel}>捕食关系</span>
              </div>
              <div className={`${styles.statItem} ${styles.highlightPink}`}>
                <span className={styles.statValue}>{stats?.keystone || 0}</span>
                <span className={styles.statLabel}>关键物种</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats?.connectivity}%</span>
                <span className={styles.statLabel}>连通密度</span>
              </div>
            </div>
            <div className={styles.divider} />
            <div className={styles.statsRow}>
              <div className={styles.miniStat}>
                <span className={`${styles.dot} ${styles.green}`} />
                <span>生产者 {stats?.producers}</span>
              </div>
              <div className={styles.miniStat}>
                <span className={`${styles.dot} ${styles.orange}`} />
                <span>消费者 {stats?.consumers}</span>
              </div>
            </div>
          </div>

          {/* 食物网健康度卡片 */}
          {analysis && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <span className={styles.cardIcon}>🏥</span>
                <span>食物网健康</span>
              </div>
              <div className={styles.healthScore}>
                <div
                  className={`${styles.healthIndicator} ${
                    (analysis.health_score ?? 0) >= 0.7
                      ? styles.healthy
                      : (analysis.health_score ?? 0) >= 0.4
                      ? styles.warning
                      : styles.critical
                  }`}
                >
                  <span className={styles.healthValue}>
                    {Math.round((analysis.health_score ?? 0) * 100)}%
                  </span>
                  <span className={styles.healthLabel}>
                    {(analysis.health_score ?? 0) >= 0.7
                      ? "健康"
                      : (analysis.health_score ?? 0) >= 0.4
                      ? "警告"
                      : "危险"}
                  </span>
                </div>
              </div>

              {/* 问题警告 */}
              {((analysis.orphaned_consumers?.length ?? 0) > 0 ||
                (analysis.starving_species?.length ?? 0) > 0) && (
                <div className={styles.issues}>
                  {(analysis.orphaned_consumers?.length ?? 0) > 0 && (
                    <div className={`${styles.issueItem} ${styles.warningItem}`}>
                      <span>⚠️ {analysis.orphaned_consumers?.length} 个消费者无猎物</span>
                    </div>
                  )}
                  {(analysis.starving_species?.length ?? 0) > 0 && (
                    <div className={`${styles.issueItem} ${styles.criticalItem}`}>
                      <span>🚨 {analysis.starving_species?.length} 个物种猎物灭绝</span>
                    </div>
                  )}
                </div>
              )}

              {/* 修复按钮 */}
              {((analysis.orphaned_consumers?.length ?? 0) > 0 ||
                (analysis.starving_species?.length ?? 0) > 0) && (
                <button
                  className={`${styles.repairBtn} ${repairing ? styles.repairing : ""}`}
                  onClick={repair}
                  disabled={repairing}
                >
                  {repairing ? "🔄 修复中..." : "🔧 自动修复食物链"}
                </button>
              )}

              {/* 更多统计 */}
              <div className={styles.healthStats}>
                <div className={styles.healthStatRow}>
                  <span>平均猎物种类</span>
                  <span>{(analysis.avg_prey_per_consumer ?? 0).toFixed(1)}</span>
                </div>
                <div className={styles.healthStatRow}>
                  <span>孤立物种</span>
                  <span>{analysis.isolated_species?.length ?? 0}</span>
                </div>
              </div>
            </div>
          )}

          {/* 筛选器 */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon}>🔍</span>
              <span>筛选视图</span>
            </div>
            <div className={styles.searchBox}>
              <input
                type="text"
                placeholder="搜索物种..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={styles.searchInput}
              />
              {searchQuery && (
                <button className={styles.searchClear} onClick={() => setSearchQuery("")}>
                  ×
                </button>
              )}
            </div>
            <div className={styles.filterButtons}>
              {[
                { id: "all", label: "全部", icon: "🌐" },
                { id: "producers", label: "生产者", icon: "🌿" },
                { id: "consumers", label: "消费者", icon: "🦊" },
                { id: "keystone", label: "关键物种", icon: "⭐" },
              ].map((filter) => (
                <button
                  key={filter.id}
                  className={`${styles.filterBtn} ${filterMode === filter.id ? styles.active : ""}`}
                  onClick={() => setFilterMode(filter.id as FilterMode)}
                >
                  <span>{filter.icon}</span>
                  <span>{filter.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 图例 */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span>🎨</span>
              <span>营养级图例</span>
            </div>
            <div className={styles.legendItems}>
              {Object.entries(TROPHIC_COLORS).map(([level, config]) => (
                <div key={level} className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ backgroundColor: config.main }} />
                  <span className={styles.legendLabel}>
                    T{level} {config.name}
                  </span>
                </div>
              ))}
              <div className={styles.legendDivider} />
              <div className={`${styles.legendItem} ${styles.keystone}`}>
                <span
                  className={`${styles.legendDot} ${styles.pulse}`}
                  style={{ backgroundColor: KEYSTONE_COLOR.main }}
                />
                <span className={styles.legendLabel}>⭐ 关键物种</span>
              </div>
            </div>
            <div className={styles.legendHint}>
              <div>→ 箭头 = 能量流动方向</div>
              <div>◉ 节点大小 = 生物量</div>
              <div>━ 线条粗细 = 捕食偏好</div>
            </div>
          </div>
        </div>

        {/* 主图区域 */}
        <div className={styles.graphContainer} ref={containerRef}>
          <ForceGraph2D
            ref={graphRef}
            graphData={{ nodes: displayNodes, links: displayLinks }}
            nodeLabel=""
            nodeColor="color"
            nodeRelSize={6}
            linkColor={() => "rgba(255,255,255,0.12)"}
            linkWidth={(link: GraphLink) => Math.max(1, (link.value || 0.5) * 3)}
            linkDirectionalArrowLength={5}
            linkDirectionalArrowRelPos={1}
            // 性能优化：节点/链接多时禁用粒子效果
            linkDirectionalParticles={displayNodes.length > PERFORMANCE_THRESHOLD ? 0 : 1}
            linkDirectionalParticleWidth={2}
            linkDirectionalParticleSpeed={0.003}
            linkDirectionalParticleColor={() => "rgba(255,255,255,0.5)"}
            onNodeClick={handleNodeClick}
            onNodeHover={handleNodeHover}
            onLinkHover={handleLinkHover}
            backgroundColor="transparent"
            width={Math.max(200, dimensions.width - 620)}
            height={Math.max(200, dimensions.height - 80)}
            nodeCanvasObject={nodeCanvasObject}
            linkCurvature={displayNodes.length > PERFORMANCE_THRESHOLD ? 0 : 0.15}
            // 性能优化：减少迭代次数
            cooldownTicks={displayNodes.length > PERFORMANCE_THRESHOLD ? 50 : 80}
            warmupTicks={displayNodes.length > PERFORMANCE_THRESHOLD ? 10 : 20}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.4}
            onEngineStop={() => graphRef.current?.zoomToFit(400, 80)}
          />

          {/* 控制按钮 */}
          <div className={styles.controls}>
            <button className={styles.controlBtn} onClick={handleResetView} title="重置视图">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </button>
            <button
              className={styles.controlBtn}
              onClick={() => graphRef.current?.zoom(1.5, 300)}
              title="放大"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35M11 8v6M8 11h6" />
              </svg>
            </button>
            <button
              className={styles.controlBtn}
              onClick={() => graphRef.current?.zoom(0.67, 300)}
              title="缩小"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35M8 11h6" />
              </svg>
            </button>
          </div>

          {/* 当前筛选状态 */}
          {(filterMode !== "all" || searchQuery || isTruncated) && (
            <div className={styles.filterBadge}>
              <span>
                显示 {displayNodes.length} / {graphData.nodes.length} 物种
                {isTruncated && (
                  <span style={{ color: "#fbbf24", marginLeft: 8 }}>
                    ⚠️ 已优化显示（物种过多）
                  </span>
                )}
              </span>
              <button
                onClick={() => {
                  setFilterMode("all");
                  setSearchQuery("");
                }}
              >
                清除筛选
              </button>
            </div>
          )}
        </div>

        {/* 右侧信息面板 */}
        <div className={`${styles.sidebar} ${styles.sidebarRight}`}>
          {/* 悬停/选中信息 */}
          {(hoveredNode || selectedNode) && (
            <div
              className={`${styles.infoCard} ${selectedNode ? styles.selected : ""}`}
              style={{
                borderColor: (hoveredNode || selectedNode)?.isKeystone
                  ? KEYSTONE_COLOR.main
                  : TROPHIC_COLORS[
                      Math.min(4, Math.max(1, Math.floor((hoveredNode || selectedNode)?.trophicLevel || 1)))
                    ]?.main,
              }}
            >
              <div className={styles.infoHeader}>
                <span
                  className={styles.infoDot}
                  style={{
                    backgroundColor: (hoveredNode || selectedNode)?.isKeystone
                      ? KEYSTONE_COLOR.main
                      : TROPHIC_COLORS[
                          Math.min(4, Math.max(1, Math.floor((hoveredNode || selectedNode)?.trophicLevel || 1)))
                        ]?.main,
                  }}
                />
                <div className={styles.infoTitle}>
                  <span className={styles.infoName}>{(hoveredNode || selectedNode)?.name}</span>
                  <span className={styles.infoId}>{(hoveredNode || selectedNode)?.id}</span>
                </div>
              </div>

              <div className={styles.infoBody}>
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>营养级</span>
                  <span className={styles.infoValue}>
                    T{(hoveredNode || selectedNode)?.trophicLevel.toFixed(2)}
                  </span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>食性类型</span>
                  <span className={styles.infoValue}>
                    {getDietTypeLabel((hoveredNode || selectedNode)?.dietType || "")}
                  </span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>生物量 (kg)</span>
                  <span className={styles.infoValue}>
                    {(hoveredNode || selectedNode)?.population.toLocaleString()}
                  </span>
                </div>
                <div className={styles.infoDivider} />
                <div className={styles.infoConnections}>
                  <div className={styles.connectionItem}>
                    <span className={styles.connectionIcon}>🌿</span>
                    <span className={styles.connectionCount}>
                      {(hoveredNode || selectedNode)?.preyCount}
                    </span>
                    <span className={styles.connectionLabel}>猎物种类</span>
                  </div>
                  <div className={styles.connectionItem}>
                    <span className={styles.connectionIcon}>🦅</span>
                    <span className={styles.connectionCount}>
                      {(hoveredNode || selectedNode)?.predatorCount}
                    </span>
                    <span className={styles.connectionLabel}>捕食者</span>
                  </div>
                </div>
                {(hoveredNode || selectedNode)?.isKeystone && (
                  <div className={styles.keystoneBadge}>
                    <span>⭐</span>
                    <span>关键物种</span>
                    <span className={styles.keystoneHint}>对生态系统稳定性影响重大</span>
                  </div>
                )}
              </div>

              {selectedNode && (
                <button
                  className={styles.viewDetailBtn}
                  onClick={() => onSelectSpecies(selectedNode.id)}
                >
                  查看详情 →
                </button>
              )}
            </div>
          )}

          {/* 链接悬停信息 */}
          {hoveredLink && !hoveredNode && (
            <div className={styles.linkCard}>
              <div className={styles.linkHeader}>捕食关系</div>
              <div className={styles.linkFlow}>
                <div className={`${styles.linkSpecies} ${styles.prey}`}>
                  <span className={styles.speciesIcon}>🌿</span>
                  <span className={styles.speciesName}>{hoveredLink.preyName}</span>
                </div>
                <div className={styles.linkArrow}>
                  <span className={styles.arrowLine} />
                  <span className={styles.arrowLabel}>{((hoveredLink.value || 0.5) * 100).toFixed(0)}%</span>
                  <span className={styles.arrowHead}>▼</span>
                </div>
                <div className={`${styles.linkSpecies} ${styles.predator}`}>
                  <span className={styles.speciesIcon}>🦊</span>
                  <span className={styles.speciesName}>{hoveredLink.predatorName}</span>
                </div>
              </div>
              <div className={styles.linkHint}>能量从被捕食者流向捕食者</div>
            </div>
          )}

          {/* 空状态提示 */}
          {!hoveredNode && !selectedNode && !hoveredLink && (
            <div className={styles.emptyHint}>
              <div className={styles.emptyHintIcon}>🔍</div>
              <div className={styles.emptyHintText}>
                <p>悬停或点击节点</p>
                <p>查看物种详情</p>
              </div>
            </div>
          )}
        </div>
      </>
    );
  };

  // 渲染
  return createPortal(
    <div className={`${styles.backdrop} ${mounted ? styles.visible : ""}`} onClick={onClose}>
      <div
        className={`${styles.panel} ${mounted ? styles.visible : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 装饰性光效 */}
        <div className={styles.glowTl} />
        <div className={styles.glowBr} />

        {/* 头部 */}
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>🕸️</div>
            <div className={styles.headerTitles}>
              <h1>生态食物网</h1>
              <p>Ecological Food Web Visualization</p>
            </div>
          </div>
          <div className={styles.headerRight}>
            <button className={styles.closeBtn} onClick={onClose}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </header>

        {/* 主内容区 */}
        <main className={styles.main}>{renderContent()}</main>
      </div>
    </div>,
    document.body
  );
}

export default FoodWebGraph;
