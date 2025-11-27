import React, { useMemo, useRef, useEffect, useState } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { SpeciesSnapshot, FoodWebData } from "../services/api.types";
import { fetchFoodWeb } from "../services/api";
import { GamePanel } from "./common/GamePanel";

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
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
  predatorName: string;
  preyName: string;
}

export function FoodWebGraph({ speciesList, onClose, onSelectSpecies }: Props) {
  const graphRef = useRef<ForceGraphMethods>();
  const [foodWebData, setFoodWebData] = useState<FoodWebData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredLink, setHoveredLink] = useState<GraphLink | null>(null);

  // 1. 加载真实的食物网数据
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
    return () => { cancelled = true; };
  }, [speciesList]); // 当物种列表变化时重新加载

  // 2. 构建图数据
  const graphData = useMemo(() => {
    if (!foodWebData) {
      return { nodes: [], links: [] };
    }

    const keystoneSet = new Set(foodWebData.keystone_species);

    const nodes: GraphNode[] = foodWebData.nodes.map((node) => {
      // 颜色映射（基于营养级）
      let color = "#4caf50"; // T1 绿色
      if (node.trophic_level >= 2 && node.trophic_level < 3) color = "#ffeb3b"; // T2 黄色
      else if (node.trophic_level >= 3 && node.trophic_level < 4) color = "#ff9800"; // T3 橙色
      else if (node.trophic_level >= 4) color = "#f44336"; // T4+ 红色

      // 关键物种用特殊样式
      const isKeystone = keystoneSet.has(node.id);
      if (isKeystone) {
        color = "#e91e63"; // 粉红色表示关键物种
      }

      // 大小映射（基于种群数量的对数缩放）
      const size = Math.max(3, Math.log10(node.population + 1) * 2.5);

      return {
        id: node.id,
        name: `${node.name} (${node.id})`,
        val: size,
        color: color,
        group: Math.floor(node.trophic_level),
        trophicLevel: node.trophic_level,
        dietType: node.diet_type,
        preyCount: node.prey_count,
        predatorCount: node.predator_count,
        isKeystone,
      };
    });

    const links: GraphLink[] = foodWebData.links.map((link) => ({
      source: link.source,
      target: link.target,
      value: link.value,
      predatorName: link.predator_name,
      preyName: link.prey_name,
    }));

    return { nodes, links };
  }, [foodWebData]);

  // 3. 自动缩放适配
  useEffect(() => {
    if (graphRef.current && graphData.nodes.length > 0) {
      graphRef.current.d3Force("charge")?.strength(-150);
      graphRef.current.d3Force("link")?.distance(80);
      setTimeout(() => graphRef.current?.zoomToFit(400, 50), 500);
    }
  }, [graphData]);

  // 4. 渲染
  if (loading) {
    return (
      <GamePanel title="生态食物网" onClose={onClose} variant="modal" width="98vw" height="95vh">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#aaa" }}>
          <span>正在加载食物网数据...</span>
        </div>
      </GamePanel>
    );
  }

  if (error) {
    return (
      <GamePanel title="生态食物网" onClose={onClose} variant="modal" width="98vw" height="95vh">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#f44336" }}>
          <span>加载失败: {error}</span>
        </div>
      </GamePanel>
    );
  }

  return (
    <GamePanel
      title="生态食物网 (Ecological Food Web)"
      onClose={onClose}
      variant="modal"
      width="98vw"
      height="95vh"
    >
      <div style={{ flex: 1, position: "relative", height: "100%", overflow: "hidden" }}>
        {/* 统计信息 */}
        <div style={{ 
          position: "absolute", 
          top: 10, 
          left: 10, 
          zIndex: 10, 
          fontSize: "0.8rem", 
          color: "rgba(255,255,255,0.7)",
          background: "rgba(15, 20, 30, 0.8)",
          padding: "8px 12px",
          borderRadius: "8px",
          border: "1px solid rgba(255,255,255,0.1)",
        }}>
          <div>物种总数: <strong>{foodWebData?.total_species || 0}</strong></div>
          <div>捕食关系: <strong>{foodWebData?.total_links || 0}</strong></div>
          <div>关键物种: <strong style={{ color: "#e91e63" }}>{foodWebData?.keystone_species.length || 0}</strong></div>
        </div>

        {/* 悬停信息 */}
        {hoveredNode && (
          <div style={{
            position: "absolute",
            top: 10,
            right: 10,
            zIndex: 10,
            background: "rgba(15, 20, 30, 0.95)",
            padding: "12px 16px",
            borderRadius: "12px",
            border: `2px solid ${hoveredNode.color}`,
            minWidth: "200px",
          }}>
            <div style={{ fontWeight: "bold", marginBottom: "8px", color: hoveredNode.color }}>
              {hoveredNode.name}
            </div>
            <div style={{ fontSize: "0.85rem", color: "#aaa", lineHeight: 1.6 }}>
              <div>营养级: T{hoveredNode.trophicLevel.toFixed(1)}</div>
              <div>食性: {getDietTypeLabel(hoveredNode.dietType)}</div>
              <div>猎物数量: {hoveredNode.preyCount}</div>
              <div>捕食者数量: {hoveredNode.predatorCount}</div>
              {hoveredNode.isKeystone && (
                <div style={{ color: "#e91e63", marginTop: "4px" }}>⭐ 关键物种</div>
              )}
            </div>
          </div>
        )}

        {/* 悬停链接信息 */}
        {hoveredLink && !hoveredNode && (
          <div style={{
            position: "absolute",
            top: 10,
            right: 10,
            zIndex: 10,
            background: "rgba(15, 20, 30, 0.95)",
            padding: "12px 16px",
            borderRadius: "12px",
            border: "1px solid rgba(255,255,255,0.3)",
          }}>
            <div style={{ fontSize: "0.85rem", color: "#ddd" }}>
              <div><strong>{hoveredLink.preyName}</strong></div>
              <div style={{ color: "#888", margin: "4px 0" }}>↓ 被捕食 ({(hoveredLink.value * 100).toFixed(0)}%)</div>
              <div><strong>{hoveredLink.predatorName}</strong></div>
            </div>
          </div>
        )}

        {/* Force Graph */}
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeLabel=""
          nodeColor="color"
          nodeRelSize={6}
          linkColor={() => "rgba(255,255,255,0.15)"}
          linkWidth={(link: any) => Math.max(1, link.value * 3)}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={(link: any) => link.value * 2}
          linkDirectionalParticleSpeed={0.005}
          onNodeClick={(node: any) => onSelectSpecies(node.id)}
          onNodeHover={(node: any) => setHoveredNode(node || null)}
          onLinkHover={(link: any) => setHoveredLink(link || null)}
          backgroundColor="transparent"
          width={window.innerWidth * 0.95}
          height={window.innerHeight * 0.85}
          nodeCanvasObject={(node: any, ctx, globalScale) => {
            // 绘制节点
            const label = node.id;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            
            // 绘制圆圈
            ctx.beginPath();
            ctx.arc(node.x, node.y, node.val, 0, 2 * Math.PI);
            ctx.fillStyle = node.color;
            ctx.fill();
            
            // 关键物种添加光晕
            if (node.isKeystone) {
              ctx.beginPath();
              ctx.arc(node.x, node.y, node.val + 3, 0, 2 * Math.PI);
              ctx.strokeStyle = "#e91e63";
              ctx.lineWidth = 2 / globalScale;
              ctx.stroke();
            }
            
            // 绘制标签（只在缩放较大时显示）
            if (globalScale > 0.8) {
              ctx.fillStyle = "rgba(255,255,255,0.9)";
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.fillText(label, node.x, node.y + node.val + 2);
            }
          }}
        />
        
        {/* Legend Overlay */}
        <div style={{
          position: "absolute",
          bottom: "20px",
          left: "20px",
          background: "rgba(15, 20, 30, 0.9)",
          padding: "16px",
          borderRadius: "12px",
          border: "1px solid rgba(255,255,255,0.1)",
          pointerEvents: "none",
          backdropFilter: "blur(4px)"
        }}>
          <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "8px", color: "#eef" }}>
            营养级图例
          </div>
          <LegendItem color="#4caf50" label="T1 生产者" />
          <LegendItem color="#ffeb3b" label="T2 初级消费者" />
          <LegendItem color="#ff9800" label="T3 次级消费者" />
          <LegendItem color="#f44336" label="T4+ 顶级捕食者" />
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", marginTop: "8px", paddingTop: "8px" }}>
            <LegendItem color="#e91e63" label="⭐ 关键物种" />
          </div>
          <div style={{ marginTop: "8px", fontSize: "0.75rem", color: "#888" }}>
            箭头方向 = 能量流动<br/>
            线条粗细 = 捕食偏好
          </div>
        </div>
      </div>
    </GamePanel>
  );
}


function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
      <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: color }} />
      <span style={{ fontSize: "0.75rem", color: "#aaa" }}>{label}</span>
    </div>
  );
}

function getDietTypeLabel(dietType: string): string {
  const labels: Record<string, string> = {
    autotroph: "自养生物",
    herbivore: "草食动物",
    carnivore: "肉食动物",
    omnivore: "杂食动物",
    detritivore: "腐食动物",
  };
  return labels[dietType] || dietType;
}
