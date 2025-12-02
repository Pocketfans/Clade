/**
 * FoodWebGraph 类型定义
 */

import type { SpeciesSnapshot, FoodWebData, FoodWebAnalysis } from "@/services/api.types";

// ============ 图节点 ============
export interface GraphNode {
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
  // D3 force simulation 添加的属性
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

// ============ 图连接 ============
export interface GraphLink {
  source: string;
  target: string;
  value: number;
  predatorName: string;
  preyName: string;
}

// ============ 图数据 ============
export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// ============ 过滤模式 ============
export type FilterMode = "all" | "producers" | "consumers" | "keystone";

// ============ 组件 Props ============
export interface FoodWebGraphProps {
  speciesList: SpeciesSnapshot[];
  onClose: () => void;
  onSelectSpecies: (id: string) => void;
}

// ============ 营养级颜色 ============
export interface TrophicColor {
  main: string;
  glow: string;
  name: string;
}

export const TROPHIC_COLORS: Record<number, TrophicColor> = {
  1: { main: "#22c55e", glow: "rgba(34, 197, 94, 0.5)", name: "生产者" },
  2: { main: "#eab308", glow: "rgba(234, 179, 8, 0.5)", name: "初级消费者" },
  3: { main: "#f97316", glow: "rgba(249, 115, 22, 0.5)", name: "次级消费者" },
  4: { main: "#ef4444", glow: "rgba(239, 68, 68, 0.5)", name: "顶级捕食者" },
};

export const KEYSTONE_COLOR = {
  main: "#ec4899",
  glow: "rgba(236, 72, 153, 0.6)",
};

