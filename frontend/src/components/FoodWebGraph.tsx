import React, { useMemo, useRef, useEffect } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { SpeciesSnapshot } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  speciesList: SpeciesSnapshot[];
  onClose: () => void;
  onSelectSpecies: (id: string) => void;
}

interface Node {
  id: string;
  name: string;
  val: number; // Size based on population/biomass
  color: string;
  group: number; // Trophic level floor
  details: SpeciesSnapshot;
}

interface Link {
  source: string;
  target: string;
  value: number; // Interaction strength
}

export function FoodWebGraph({ speciesList, onClose, onSelectSpecies }: Props) {
  const graphRef = useRef<ForceGraphMethods>();

  // 1. 构建图数据
  const data = useMemo(() => {
    const nodes: Node[] = [];
    const links: Link[] = [];

    // 1.1 创建节点
    speciesList.forEach((s) => {
      // 解析营养级 (T1.0, T2.5 etc)
      let trophicLevel = 1.0;
      if (s.tier) {
        const match = s.tier.match(/T(\d+(\.\d+)?)/);
        if (match) trophicLevel = parseFloat(match[1]);
      }

      // 颜色映射
      let color = "#4caf50"; // T1 绿色
      if (trophicLevel >= 2 && trophicLevel < 3) color = "#ffeb3b"; // T2 黄色
      else if (trophicLevel >= 3 && trophicLevel < 4) color = "#ff9800"; // T3 橙色
      else if (trophicLevel >= 4) color = "#f44336"; // T4+ 红色

      // 大小映射 (基于人口占比，对数缩放)
      const size = Math.max(2, Math.log10(s.population + 1) * 2);

      nodes.push({
        id: s.lineage_code,
        name: `${s.common_name} (${s.lineage_code})`,
        val: size,
        color: color,
        group: Math.floor(trophicLevel),
        details: s,
      });
    });

    // 1.2 创建连线 (模拟捕食关系)
    // 注意：真实捕食关系应由后端提供。这里我们基于营养级进行简单的启发式模拟用于演示。
    // 规则：高营养级物种捕食低营养级物种 (差值在 0.5 ~ 1.5 之间)
    nodes.forEach((predator) => {
      const pLevel = getTrophicLevel(predator.details.tier);
      
      // 仅处理消费者
      if (pLevel < 2.0) return;

      nodes.forEach((prey) => {
        if (predator.id === prey.id) return;
        const preyLevel = getTrophicLevel(prey.details.tier);

        // 检查是否符合捕食层级关系
        const diff = pLevel - preyLevel;
        if (diff >= 0.5 && diff <= 1.5) {
          // 简单的概率连接，避免全连接图
          // 实际应检查生态位重叠度
          const hash = stringHash(predator.id + prey.id);
          if (hash % 100 < 30) { // 30% 概率存在捕食关系
             links.push({
               source: prey.id, // 能量流向：猎物 -> 捕食者
               target: predator.id,
               value: 1,
             });
          }
        }
      });
    });

    return { nodes, links };
  }, [speciesList]);

  // 2. 自动缩放适配
  useEffect(() => {
    if (graphRef.current) {
      graphRef.current.d3Force("charge")?.strength(-100);
      graphRef.current.d3Force("link")?.distance(100);
      setTimeout(() => graphRef.current?.zoomToFit(400, 50), 500);
    }
  }, [data]);

  return (
    <GamePanel
      title="生态食物网 (Ecological Food Web)"
      onClose={onClose}
      variant="modal"
      width="98vw"
      height="95vh"
    >
      {/* Graph */}
      <div style={{ flex: 1, position: "relative", height: "100%", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: 10, left: 10, zIndex: 10, fontSize: "0.8rem", color: "rgba(255,255,255,0.6)" }}>
           节点大小: 种群数量 | 颜色: 营养级 | 连线: 能量流动
        </div>

        <ForceGraph2D
          ref={graphRef}
          graphData={data}
          nodeLabel="name"
          nodeColor="color"
          nodeRelSize={6}
          linkColor={() => "rgba(255,255,255,0.2)"}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          onNodeClick={(node) => onSelectSpecies(node.id as string)}
          backgroundColor="transparent"
          width={window.innerWidth * 0.95} // Approximate
          height={window.innerHeight * 0.85}
        />
        
        {/* Legend Overlay */}
        <div style={{
          position: "absolute",
          bottom: "20px",
          left: "20px",
          background: "rgba(15, 20, 30, 0.8)",
          padding: "16px",
          borderRadius: "12px",
          border: "1px solid rgba(255,255,255,0.1)",
          pointerEvents: "none",
          backdropFilter: "blur(4px)"
        }}>
          <div style={{ fontSize: "0.85rem", fontWeight: "bold", marginBottom: "8px", color: "#eef" }}>营养级图例</div>
          <LegendItem color="#4caf50" label="T1 生产者 (Producer)" />
          <LegendItem color="#ffeb3b" label="T2 初级消费者 (Primary)" />
          <LegendItem color="#ff9800" label="T3 次级消费者 (Secondary)" />
          <LegendItem color="#f44336" label="T4+ 顶级掠食者 (Apex)" />
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

// Helper
function getTrophicLevel(tier?: string | null): number {
  if (!tier) return 1.0;
  const match = tier.match(/T(\d+(\.\d+)?)/);
  return match ? parseFloat(match[1]) : 1.0;
}

function stringHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

