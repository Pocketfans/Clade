import React, { useMemo, useRef, useEffect, useState, useCallback } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { SpeciesSnapshot, FoodWebData } from "../services/api.types";
import { fetchFoodWeb } from "../services/api";
import { createPortal } from "react-dom";

interface Props {
  speciesList: SpeciesSnapshot[];
  onClose: () => void;
  onSelectSpecies: (id: string) => void;
}

interface GraphNode {
  id: string;
  name: string;
  val: number;
  color: string;
  group: number;
  trophicLevel: number;
  dietType: string;
  preyCount: number;
  predatorCount: number;
  isKeystone: boolean;
  population: number;
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
  predatorName: string;
  preyName: string;
}

type FilterMode = "all" | "producers" | "consumers" | "keystone";

const TROPHIC_COLORS = {
  1: { main: "#22c55e", glow: "rgba(34, 197, 94, 0.5)", name: "生产者" },
  2: { main: "#eab308", glow: "rgba(234, 179, 8, 0.5)", name: "初级消费者" },
  3: { main: "#f97316", glow: "rgba(249, 115, 22, 0.5)", name: "次级消费者" },
  4: { main: "#ef4444", glow: "rgba(239, 68, 68, 0.5)", name: "顶级捕食者" },
};

const KEYSTONE_COLOR = { main: "#ec4899", glow: "rgba(236, 72, 153, 0.6)" };

export function FoodWebGraph({ speciesList, onClose, onSelectSpecies }: Props) {
  const graphRef = useRef<ForceGraphMethods>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [foodWebData, setFoodWebData] = useState<FoodWebData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredLink, setHoveredLink] = useState<GraphLink | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [mounted, setMounted] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Mount animation
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

  // 加载真实的食物网数据
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchFoodWeb();
        if (!cancelled) {
          setFoodWebData(data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || "加载食物网数据失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadData();
    return () => {
      cancelled = true;
    };
  }, [speciesList]);

  // 构建图数据
  const graphData = useMemo(() => {
    if (!foodWebData) {
      return { nodes: [], links: [] };
    }

    const keystoneSet = new Set(foodWebData.keystone_species);

    let filteredNodes = foodWebData.nodes;

    // 应用筛选
    if (filterMode === "producers") {
      filteredNodes = filteredNodes.filter((n) => n.trophic_level < 2);
    } else if (filterMode === "consumers") {
      filteredNodes = filteredNodes.filter((n) => n.trophic_level >= 2);
    } else if (filterMode === "keystone") {
      filteredNodes = filteredNodes.filter((n) => keystoneSet.has(n.id));
    }

    // 应用搜索
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filteredNodes = filteredNodes.filter(
        (n) => n.name.toLowerCase().includes(query) || n.id.toLowerCase().includes(query)
      );
    }

    const nodeIdSet = new Set(filteredNodes.map((n) => n.id));

    const nodes: GraphNode[] = filteredNodes.map((node) => {
      const trophicTier = Math.min(4, Math.max(1, Math.floor(node.trophic_level)));
      const colorConfig = TROPHIC_COLORS[trophicTier as keyof typeof TROPHIC_COLORS];
      const isKeystone = keystoneSet.has(node.id);

      const size = Math.max(4, Math.log10(node.population + 1) * 3);

      return {
        id: node.id,
        name: node.name,
        val: size,
        color: isKeystone ? KEYSTONE_COLOR.main : colorConfig.main,
        group: trophicTier,
        trophicLevel: node.trophic_level,
        dietType: node.diet_type,
        preyCount: node.prey_count,
        predatorCount: node.predator_count,
        isKeystone,
        population: node.population,
      };
    });

    const links: GraphLink[] = foodWebData.links
      .filter((link) => nodeIdSet.has(link.source) && nodeIdSet.has(link.target))
      .map((link) => ({
        source: link.source,
        target: link.target,
        value: link.value,
        predatorName: link.predator_name,
        preyName: link.prey_name,
      }));

    return { nodes, links };
  }, [foodWebData, filterMode, searchQuery]);

  // 自动缩放适配
  useEffect(() => {
    if (graphRef.current && graphData.nodes.length > 0) {
      graphRef.current.d3Force("charge")?.strength(-180);
      graphRef.current.d3Force("link")?.distance(100);
      setTimeout(() => graphRef.current?.zoomToFit(400, 80), 600);
    }
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNode(node);
      onSelectSpecies(node.id);
    },
    [onSelectSpecies]
  );

  const handleResetView = useCallback(() => {
    graphRef.current?.zoomToFit(400, 80);
  }, []);

  // 渲染节点
  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isHovered = hoveredNode?.id === node.id;
      const isSelected = selectedNode?.id === node.id;
      const nodeSize = node.val * (isHovered || isSelected ? 1.3 : 1);

      // 光晕效果
      if (node.isKeystone || isHovered || isSelected) {
        const glowSize = nodeSize + (isHovered || isSelected ? 8 : 5);
        const gradient = ctx.createRadialGradient(
          node.x,
          node.y,
          nodeSize * 0.5,
          node.x,
          node.y,
          glowSize
        );
        gradient.addColorStop(0, node.isKeystone ? KEYSTONE_COLOR.glow : `${node.color}60`);
        gradient.addColorStop(1, "transparent");
        ctx.beginPath();
        ctx.arc(node.x, node.y, glowSize, 0, 2 * Math.PI);
        ctx.fillStyle = gradient;
        ctx.fill();
      }

      // 主节点
      ctx.beginPath();
      ctx.arc(node.x, node.y, nodeSize, 0, 2 * Math.PI);
      ctx.fillStyle = node.color;
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
        ctx.arc(node.x, node.y, nodeSize + 4, 0, 2 * Math.PI);
        ctx.strokeStyle = KEYSTONE_COLOR.main;
        ctx.lineWidth = 2 / globalScale;
        ctx.setLineDash([4 / globalScale, 4 / globalScale]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // 标签（放大时显示）
      if (globalScale > 0.6 || isHovered || isSelected) {
        const fontSize = Math.max(10, 14 / globalScale);
        ctx.font = `${isHovered || isSelected ? "bold " : ""}${fontSize}px "Segoe UI", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        // 标签背景
        const label = node.id;
        const textWidth = ctx.measureText(label).width;
        const padding = 4 / globalScale;
        const bgHeight = fontSize + padding * 2;
        const bgY = node.y + nodeSize + 4;

        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.beginPath();
        ctx.roundRect(
          node.x - textWidth / 2 - padding,
          bgY - padding,
          textWidth + padding * 2,
          bgHeight,
          3 / globalScale
        );
        ctx.fill();

        ctx.fillStyle = isHovered || isSelected ? "#fff" : "rgba(255,255,255,0.85)";
        ctx.fillText(label, node.x, bgY);
      }
    },
    [hoveredNode, selectedNode]
  );

  // 统计数据
  const stats = useMemo(() => {
    if (!foodWebData) return null;
    const keystoneCount = foodWebData.keystone_species.length;
    const avgTrophic =
      foodWebData.nodes.reduce((sum, n) => sum + n.trophic_level, 0) / foodWebData.nodes.length;
    const producerCount = foodWebData.nodes.filter((n) => n.trophic_level < 2).length;
    const consumerCount = foodWebData.nodes.filter((n) => n.trophic_level >= 2).length;

    return {
      total: foodWebData.total_species,
      links: foodWebData.total_links,
      keystone: keystoneCount,
      avgTrophic: avgTrophic.toFixed(2),
      producers: producerCount,
      consumers: consumerCount,
      connectivity: ((foodWebData.total_links / foodWebData.total_species) * 100).toFixed(1),
    };
  }, [foodWebData]);

  // 渲染内容
  const renderContent = () => {
    if (loading) {
      return (
        <div className="foodweb-loading">
          <div className="foodweb-loading-spinner" />
          <span>正在构建生态网络...</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="foodweb-error">
          <span className="foodweb-error-icon">⚠️</span>
          <span>加载失败: {error}</span>
          <button onClick={() => window.location.reload()} className="foodweb-retry-btn">
            重试
          </button>
        </div>
      );
    }

    return (
      <>
        {/* 左侧控制面板 */}
        <div className="foodweb-sidebar foodweb-sidebar-left">
          {/* 统计卡片 */}
          <div className="foodweb-stats-card">
            <div className="foodweb-stats-header">
              <span className="foodweb-stats-icon">📊</span>
              <span>网络统计</span>
            </div>
            <div className="foodweb-stats-grid">
              <div className="foodweb-stat-item">
                <span className="foodweb-stat-value">{stats?.total || 0}</span>
                <span className="foodweb-stat-label">物种总数</span>
              </div>
              <div className="foodweb-stat-item">
                <span className="foodweb-stat-value">{stats?.links || 0}</span>
                <span className="foodweb-stat-label">捕食关系</span>
              </div>
              <div className="foodweb-stat-item highlight-pink">
                <span className="foodweb-stat-value">{stats?.keystone || 0}</span>
                <span className="foodweb-stat-label">关键物种</span>
              </div>
              <div className="foodweb-stat-item">
                <span className="foodweb-stat-value">{stats?.connectivity}%</span>
                <span className="foodweb-stat-label">连通密度</span>
              </div>
            </div>
            <div className="foodweb-stats-divider" />
            <div className="foodweb-stats-row">
              <div className="foodweb-mini-stat">
                <span className="dot green" />
                <span>生产者 {stats?.producers}</span>
              </div>
              <div className="foodweb-mini-stat">
                <span className="dot orange" />
                <span>消费者 {stats?.consumers}</span>
              </div>
            </div>
          </div>

          {/* 筛选器 */}
          <div className="foodweb-filter-card">
            <div className="foodweb-filter-header">
              <span className="foodweb-filter-icon">🔍</span>
              <span>筛选视图</span>
            </div>
            <div className="foodweb-search-box">
              <input
                type="text"
                placeholder="搜索物种..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="foodweb-search-input"
              />
              {searchQuery && (
                <button className="foodweb-search-clear" onClick={() => setSearchQuery("")}>
                  ×
                </button>
              )}
            </div>
            <div className="foodweb-filter-buttons">
              {[
                { id: "all", label: "全部", icon: "🌐" },
                { id: "producers", label: "生产者", icon: "🌿" },
                { id: "consumers", label: "消费者", icon: "🦊" },
                { id: "keystone", label: "关键物种", icon: "⭐" },
              ].map((filter) => (
                <button
                  key={filter.id}
                  className={`foodweb-filter-btn ${filterMode === filter.id ? "active" : ""}`}
                  onClick={() => setFilterMode(filter.id as FilterMode)}
                >
                  <span>{filter.icon}</span>
                  <span>{filter.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 图例 */}
          <div className="foodweb-legend-card">
            <div className="foodweb-legend-header">
              <span>🎨</span>
              <span>营养级图例</span>
            </div>
            <div className="foodweb-legend-items">
              {Object.entries(TROPHIC_COLORS).map(([level, config]) => (
                <div key={level} className="foodweb-legend-item">
                  <span className="foodweb-legend-dot" style={{ backgroundColor: config.main }} />
                  <span className="foodweb-legend-label">
                    T{level} {config.name}
                  </span>
                </div>
              ))}
              <div className="foodweb-legend-divider" />
              <div className="foodweb-legend-item keystone">
                <span
                  className="foodweb-legend-dot pulse"
                  style={{ backgroundColor: KEYSTONE_COLOR.main }}
                />
                <span className="foodweb-legend-label">⭐ 关键物种</span>
              </div>
            </div>
            <div className="foodweb-legend-hint">
              <div>→ 箭头 = 能量流动方向</div>
              <div>◉ 节点大小 = 生物量</div>
              <div>━ 线条粗细 = 捕食偏好</div>
            </div>
          </div>
        </div>

        {/* 主图区域 */}
        <div className="foodweb-graph-container" ref={containerRef}>
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            nodeLabel=""
            nodeColor="color"
            nodeRelSize={6}
            linkColor={() => "rgba(255,255,255,0.12)"}
            linkWidth={(link: any) => Math.max(1, link.value * 4)}
            linkDirectionalArrowLength={6}
            linkDirectionalArrowRelPos={1}
            linkDirectionalParticles={2}
            linkDirectionalParticleWidth={(link: any) => link.value * 2.5}
            linkDirectionalParticleSpeed={0.004}
            linkDirectionalParticleColor={() => "rgba(255,255,255,0.6)"}
            onNodeClick={handleNodeClick}
            onNodeHover={(node: any) => setHoveredNode(node || null)}
            onLinkHover={(link: any) => setHoveredLink(link || null)}
            backgroundColor="transparent"
            width={dimensions.width - 620}
            height={dimensions.height - 80}
            nodeCanvasObject={nodeCanvasObject}
            linkCurvature={0.15}
            cooldownTicks={100}
            onEngineStop={() => graphRef.current?.zoomToFit(400, 80)}
          />

          {/* 控制按钮 */}
          <div className="foodweb-controls">
            <button className="foodweb-control-btn" onClick={handleResetView} title="重置视图">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </button>
            <button
              className="foodweb-control-btn"
              onClick={() => graphRef.current?.zoom(1.5, 300)}
              title="放大"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35M11 8v6M8 11h6" />
              </svg>
            </button>
            <button
              className="foodweb-control-btn"
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
          {(filterMode !== "all" || searchQuery) && (
            <div className="foodweb-filter-badge">
              <span>
                显示 {graphData.nodes.length} / {foodWebData?.total_species || 0} 物种
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
        <div className="foodweb-sidebar foodweb-sidebar-right">
          {/* 悬停/选中信息 */}
          {(hoveredNode || selectedNode) && (
            <div
              className={`foodweb-info-card ${selectedNode ? "selected" : ""}`}
              style={{
                borderColor: (hoveredNode || selectedNode)?.color,
              }}
            >
              <div className="foodweb-info-header">
                <span
                  className="foodweb-info-dot"
                  style={{ backgroundColor: (hoveredNode || selectedNode)?.color }}
                />
                <div className="foodweb-info-title">
                  <span className="foodweb-info-name">{(hoveredNode || selectedNode)?.name}</span>
                  <span className="foodweb-info-id">{(hoveredNode || selectedNode)?.id}</span>
                </div>
              </div>

              <div className="foodweb-info-body">
                <div className="foodweb-info-row">
                  <span className="foodweb-info-label">营养级</span>
                  <span className="foodweb-info-value">
                    T{(hoveredNode || selectedNode)?.trophicLevel.toFixed(2)}
                  </span>
                </div>
                <div className="foodweb-info-row">
                  <span className="foodweb-info-label">食性类型</span>
                  <span className="foodweb-info-value">
                    {getDietTypeLabel((hoveredNode || selectedNode)?.dietType || "")}
                  </span>
                </div>
                <div className="foodweb-info-row">
                  <span className="foodweb-info-label">生物量 (kg)</span>
                  <span className="foodweb-info-value">
                    {(hoveredNode || selectedNode)?.population.toLocaleString()}
                  </span>
                </div>
                <div className="foodweb-info-divider" />
                <div className="foodweb-info-connections">
                  <div className="foodweb-connection-item">
                    <span className="connection-icon prey">🌿</span>
                    <span className="connection-count">
                      {(hoveredNode || selectedNode)?.preyCount}
                    </span>
                    <span className="connection-label">猎物种类</span>
                  </div>
                  <div className="foodweb-connection-item">
                    <span className="connection-icon predator">🦅</span>
                    <span className="connection-count">
                      {(hoveredNode || selectedNode)?.predatorCount}
                    </span>
                    <span className="connection-label">捕食者</span>
                  </div>
                </div>
                {(hoveredNode || selectedNode)?.isKeystone && (
                  <div className="foodweb-keystone-badge">
                    <span>⭐</span>
                    <span>关键物种</span>
                    <span className="keystone-hint">对生态系统稳定性影响重大</span>
                  </div>
                )}
              </div>

              {selectedNode && (
                <button
                  className="foodweb-view-detail-btn"
                  onClick={() => onSelectSpecies(selectedNode.id)}
                >
                  查看详情 →
                </button>
              )}
            </div>
          )}

          {/* 链接悬停信息 */}
          {hoveredLink && !hoveredNode && (
            <div className="foodweb-link-card">
              <div className="foodweb-link-header">捕食关系</div>
              <div className="foodweb-link-flow">
                <div className="foodweb-link-species prey">
                  <span className="species-icon">🌿</span>
                  <span className="species-name">{hoveredLink.preyName}</span>
                </div>
                <div className="foodweb-link-arrow">
                  <span className="arrow-line" />
                  <span className="arrow-label">{(hoveredLink.value * 100).toFixed(0)}%</span>
                  <span className="arrow-head">▼</span>
                </div>
                <div className="foodweb-link-species predator">
                  <span className="species-icon">🦊</span>
                  <span className="species-name">{hoveredLink.predatorName}</span>
                </div>
              </div>
              <div className="foodweb-link-hint">能量从被捕食者流向捕食者</div>
            </div>
          )}

          {/* 空状态提示 */}
          {!hoveredNode && !selectedNode && !hoveredLink && (
            <div className="foodweb-empty-hint">
              <div className="empty-hint-icon">🔍</div>
              <div className="empty-hint-text">
                <p>悬停或点击节点</p>
                <p>查看物种详情</p>
              </div>
            </div>
          )}
        </div>
      </>
    );
  };

  return createPortal(
    <div className={`foodweb-backdrop ${mounted ? "visible" : ""}`} onClick={onClose}>
      <div
        className={`foodweb-panel ${mounted ? "visible" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 装饰性光效 */}
        <div className="foodweb-glow-tl" />
        <div className="foodweb-glow-br" />

        {/* 头部 */}
        <header className="foodweb-header">
          <div className="foodweb-header-left">
            <div className="foodweb-header-icon">🕸️</div>
            <div className="foodweb-header-titles">
              <h1>生态食物网</h1>
              <p>Ecological Food Web Visualization</p>
            </div>
          </div>
          <div className="foodweb-header-right">
            <button className="foodweb-close-btn" onClick={onClose}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </header>

        {/* 主内容区 */}
        <main className="foodweb-main">{renderContent()}</main>
      </div>
    </div>,
    document.body
  );
}

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
