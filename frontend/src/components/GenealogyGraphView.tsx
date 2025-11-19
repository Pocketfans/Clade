import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import type { LineageNode } from "../services/api.types";

interface Props {
  nodes: LineageNode[];
  onNodeClick?: (node: LineageNode) => void;
}

interface TreeNode extends d3.HierarchyPointNode<LineageNode> {
  data: LineageNode;
}

export function GenealogyGraphView({ nodes, onNodeClick }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<LineageNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const transformRef = useRef({ x: 0, y: 0, k: 1 }); // 使用 ref 保持缩放位置
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    const svg = d3.select(svgRef.current);
    
    // 只在初次渲染时清空，后续更新保持节点
    const isFirstRender = !svg.select("g").node();
    if (isFirstRender) {
      svg.selectAll("*").remove();
    }

    // 构建层次结构
    const root = buildHierarchy(nodes);
    
    // 创建树布局
    const treeLayout = d3.tree<LineageNode>()
      .size([height - 100, width - 200])
      .separation((a, b) => (a.parent === b.parent ? 1 : 1.5));

    const treeData = treeLayout(root);

    // 设置SVG尺寸
    svg.attr("width", width).attr("height", height);

    // 获取或创建主画布组
    let g = svg.select<SVGGElement>("g.main-canvas");
    if (g.empty()) {
      g = svg.append("g")
        .attr("class", "main-canvas")
        .attr("transform", `translate(${transformRef.current.x + 100}, ${transformRef.current.y + 50}) scale(${transformRef.current.k})`);
    } else {
      // 清空已有内容但保持变换
      g.selectAll("*").remove();
    }

    const normalLinks = treeData.links();
    const hybridLinks: Array<{source: TreeNode; target: TreeNode; parent2: TreeNode}> = [];
    
    treeData.descendants().forEach(node => {
      if (node.data.hybrid_parent_codes && node.data.hybrid_parent_codes.length >= 2) {
        const parent1 = treeData.descendants().find(n => n.data.lineage_code === node.data.hybrid_parent_codes[0]);
        const parent2 = treeData.descendants().find(n => n.data.lineage_code === node.data.hybrid_parent_codes[1]);
        if (parent1 && parent2) {
          hybridLinks.push({ source: parent1, target: node, parent2 });
        }
      }
    });
    
    g.selectAll(".link")
      .data(normalLinks)
      .enter()
      .append("path")
      .attr("class", "genealogy-link")
      .attr("d", d3.linkHorizontal<any, TreeNode>()
        .x(d => d.y)
        .y(d => d.x)
      )
      .style("fill", "none")
      .style("stroke", (d) => {
        if (d.target.data.taxonomic_rank === "subspecies") return "#fb923c";
        const speciationType = d.target.data.speciation_type;
        if (speciationType === "rapid_radiation") return "#ffc857";
        if (speciationType === "adaptive") return "#22d3ee";
        return "rgba(255, 255, 255, 0.3)";
      })
      .style("stroke-width", 2)
      .style("stroke-dasharray", (d) => {
        if (d.target.data.taxonomic_rank === "subspecies") return "6,3";
        return d.target.data.speciation_type === "normal" ? "4,2" : "0";
      });
    
    hybridLinks.forEach(link => {
      g.append("path")
        .attr("class", "hybrid-link")
        .attr("d", () => {
          const midY = (link.source.y + link.parent2.y) / 2;
          const midX = (link.source.x + link.parent2.x) / 2;
          return `M ${link.source.y},${link.source.x} Q ${midY},${midX} ${link.target.y},${link.target.x}
                  M ${link.parent2.y},${link.parent2.x} Q ${midY},${midX} ${link.target.y},${link.target.x}`;
        })
        .style("fill", "none")
        .style("stroke", "#a78bfa")
        .style("stroke-width", 2)
        .style("stroke-dasharray", "4,4")
        .style("opacity", 0.7);
    });

    // 绘制节点
    const node = g.selectAll(".node")
      .data(treeData.descendants())
      .enter()
      .append("g")
      .attr("class", "genealogy-node-group")
      .attr("transform", d => `translate(${d.y},${d.x})`)
      .style("cursor", "pointer")
      .on("click", (event, d) => {
        event.stopPropagation();
        setSelectedNode(d.data.lineage_code);
        onNodeClick?.(d.data);
      })
      .on("mouseenter", (event, d) => {
        if (d.data.genus_code && Object.keys(d.data.genetic_distances).length > 0) {
          setHoveredNode(d.data);
          setTooltipPos({ x: event.pageX, y: event.pageY });
        }
      })
      .on("mousemove", (event, d) => {
        if (hoveredNode) {
          setTooltipPos({ x: event.pageX, y: event.pageY });
        }
      })
      .on("mouseleave", () => {
        setHoveredNode(null);
      });

    // 节点矩形
    node.append("rect")
      .attr("class", d => {
        const classes = ["genealogy-node-svg"];
        if (d.data.state === "alive") classes.push("alive");
        if (d.data.state === "extinct") classes.push("extinct");
        if (d.data.tier === "background") classes.push("background");
        if (d.data.current_population > 10000) classes.push("dominant");
        return classes.join(" ");
      })
      .attr("x", -60)
      .attr("y", -20)
      .attr("width", 120)
      .attr("height", 40)
      .attr("rx", 8)
      .style("fill", d => getNodeColor(d.data))
      .style("stroke", d => {
        if (selectedNode === d.data.lineage_code) return "#ffc857";
        if (d.data.state === "alive") return "#22c55e";
        if (d.data.state === "extinct") return "#f87171";
        return "rgba(255, 255, 255, 0.3)";
      })
      .style("stroke-width", d => selectedNode === d.data.lineage_code ? 3 : 2)
      .style("stroke-dasharray", d => d.data.state === "extinct" ? "4,2" : "0")
      .style("filter", d => {
        if (d.data.state === "alive") return "drop-shadow(0 0 8px rgba(34, 197, 94, 0.6))";
        return "none";
      });

    // 节点文字
    node.append("text")
      .attr("dy", -5)
      .attr("text-anchor", "middle")
      .style("fill", "#fff")
      .style("font-size", "11px")
      .style("font-weight", "bold")
      .style("pointer-events", "none")
      .text(d => d.data.lineage_code);

    node.append("text")
      .attr("dy", 10)
      .attr("text-anchor", "middle")
      .style("fill", "rgba(255, 255, 255, 0.8)")
      .style("font-size", "9px")
      .style("pointer-events", "none")
      .text(d => d.data.common_name.substring(0, 8));
    
    node.filter(d => d.data.taxonomic_rank === "subspecies")
      .append("text")
      .attr("x", 45)
      .attr("y", -15)
      .attr("text-anchor", "middle")
      .style("font-size", "14px")
      .style("pointer-events", "none")
      .text("🔸");
    
    node.filter(d => d.data.taxonomic_rank === "hybrid")
      .append("text")
      .attr("x", 45)
      .attr("y", -15)
      .attr("text-anchor", "middle")
      .style("font-size", "14px")
      .style("pointer-events", "none")
      .text("⚡");
    
    node.filter(d => d.data.taxonomic_rank === "subspecies")
      .append("rect")
      .attr("x", 40)
      .attr("y", -25)
      .attr("width", 20)
      .attr("height", 12)
      .attr("rx", 3)
      .style("fill", "#fb923c")
      .style("opacity", 0.8);
    
    node.filter(d => d.data.taxonomic_rank === "subspecies")
      .append("text")
      .attr("x", 50)
      .attr("y", -16)
      .attr("text-anchor", "middle")
      .style("fill", "#fff")
      .style("font-size", "8px")
      .style("font-weight", "bold")
      .style("pointer-events", "none")
      .text("SUB");
    
    node.filter(d => d.data.taxonomic_rank === "hybrid")
      .append("rect")
      .attr("x", 40)
      .attr("y", -25)
      .attr("width", 20)
      .attr("height", 12)
      .attr("rx", 3)
      .style("fill", "#a78bfa")
      .style("opacity", 0.8);
    
    node.filter(d => d.data.taxonomic_rank === "hybrid")
      .append("text")
      .attr("x", 50)
      .attr("y", -16)
      .attr("text-anchor", "middle")
      .style("fill", "#fff")
      .style("font-size", "8px")
      .style("font-weight", "bold")
      .style("pointer-events", "none")
      .text("HYB");

    // 缩放和平移功能（只在首次渲染时初始化）
    if (!zoomRef.current) {
      zoomRef.current = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on("zoom", (event) => {
          g.attr("transform", 
            `translate(${event.transform.x + 100}, ${event.transform.y + 50}) scale(${event.transform.k})`
          );
          transformRef.current = event.transform; // 保存到 ref
        });

      svg.call(zoomRef.current);
      
      // 点击背景关闭详情弹窗
      svg.on("click", (event) => {
        // 只有点击SVG背景（不是节点）时才关闭
        if (event.target === svgRef.current) {
          setSelectedNode(null);
          onNodeClick?.(null as any); // 通知父组件关闭
        }
      });
    }

  }, [nodes, selectedNode, onNodeClick]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "600px", position: "relative" }}>
      <svg ref={svgRef} style={{ width: "100%", height: "100%" }}></svg>
      
      {hoveredNode && (
        <div style={{
          position: "fixed",
          left: `${tooltipPos.x + 10}px`,
          top: `${tooltipPos.y + 10}px`,
          background: "rgba(10, 14, 32, 0.95)",
          padding: "0.75rem",
          borderRadius: "8px",
          border: "1px solid rgba(255, 255, 255, 0.2)",
          fontSize: "0.85rem",
          zIndex: 1000,
          pointerEvents: "none",
          maxWidth: "250px",
        }}>
          <div style={{ fontWeight: "bold", marginBottom: "0.5rem" }}>
            {hoveredNode.common_name} ({hoveredNode.genus_code}属)
          </div>
          <div style={{ fontSize: "0.8rem", color: "rgba(226, 236, 255, 0.8)" }}>遗传距离:</div>
          {Object.entries(hoveredNode.genetic_distances).map(([code, distance]) => {
            const color = distance < 0.2 ? "#22c55e" : distance < 0.4 ? "#fbbf24" : "#f87171";
            return (
              <div key={code} style={{ display: "flex", justifyContent: "space-between", marginTop: "0.25rem" }}>
                <span>{code}</span>
                <span style={{ color, fontWeight: "bold" }}>{distance.toFixed(3)}</span>
              </div>
            );
          })}
        </div>
      )}
      
      <div style={{
        position: "absolute",
        bottom: "1rem",
        right: "1rem",
        background: "rgba(10, 14, 32, 0.9)",
        padding: "0.75rem",
        borderRadius: "12px",
        border: "1px solid rgba(255, 255, 255, 0.1)",
        fontSize: "0.85rem",
      }}>
        <div style={{ marginBottom: "0.5rem", fontWeight: "bold" }}>图例</div>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{
              width: "20px",
              height: "20px",
              border: "2px solid #22c55e",
              borderRadius: "4px",
              background: "rgba(255, 255, 255, 0.08)",
            }}></div>
            <span>存活</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{
              width: "20px",
              height: "20px",
              border: "2px dashed #f87171",
              borderRadius: "4px",
              background: "rgba(255, 255, 255, 0.08)",
              opacity: 0.5,
            }}></div>
            <span>灭绝</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{
              width: "20px",
              height: "20px",
              border: "3px solid #ffc857",
              borderRadius: "4px",
              background: "rgba(255, 255, 255, 0.08)",
            }}></div>
            <span>优势种</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{
              width: "16px",
              height: "12px",
              background: "#fb923c",
              borderRadius: "3px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "7px",
              fontWeight: "bold",
            }}>SUB</div>
            <span>亚种</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{
              width: "16px",
              height: "12px",
              background: "#a78bfa",
              borderRadius: "3px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "7px",
              fontWeight: "bold",
            }}>HYB</div>
            <span>杂交</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function buildHierarchy(nodes: LineageNode[]): d3.HierarchyNode<LineageNode> {
  // 找到根节点 (没有parent的节点)
  const roots = nodes.filter(n => !n.parent_code);
  if (roots.length === 0) {
    // 如果没有根节点,使用第一个节点作为根
    return d3.hierarchy(nodes[0], () => []);
  }
  
  // 如果有多个根,创建一个虚拟根
  if (roots.length > 1) {
    const virtualRoot: LineageNode = {
      lineage_code: "ROOT",
      parent_code: null,
      latin_name: "Origin",
      common_name: "起源",
      state: "alive",
      population_share: 0,
      major_events: [],
      birth_turn: 0,
      extinction_turn: null,
      ecological_role: "unknown",
      tier: null,
      speciation_type: "normal",
      current_population: 0,
      peak_population: 0,
      descendant_count: roots.length,
      taxonomic_rank: "origin",
      genus_code: "",
      hybrid_parent_codes: [],
      hybrid_fertility: 0,
      genetic_distances: {},
    };
    
    return d3.hierarchy(virtualRoot, (d) => {
      if (d.lineage_code === "ROOT") return roots;
      return nodes.filter(n => n.parent_code === d.lineage_code);
    });
  }
  
  // 单个根节点
  return d3.hierarchy(roots[0], (d) => {
    return nodes.filter(n => n.parent_code === d.lineage_code);
  });
}

function getNodeColor(node: LineageNode): string {
  if (node.tier === "background") {
    return "rgba(107, 114, 128, 0.3)";
  }
  
  // 根据生态角色着色
  switch (node.ecological_role) {
    case "producer":
      return "rgba(16, 185, 129, 0.2)";
    case "herbivore":
      return "rgba(251, 191, 36, 0.2)";
    case "carnivore":
      return "rgba(239, 68, 68, 0.2)";
    case "omnivore":
      return "rgba(249, 115, 22, 0.2)";
    default:
      return "rgba(255, 255, 255, 0.08)";
  }
}

