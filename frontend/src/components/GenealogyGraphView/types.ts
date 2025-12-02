/**
 * GenealogyGraphView 类型定义
 */

import type { Container, Graphics } from "pixi.js";
import type { LineageNode } from "@/services/api.types";

// ============ 组件 Props ============
export interface GenealogyGraphViewProps {
  nodes: LineageNode[];
  spacingX?: number;
  spacingY?: number;
  onNodeClick?: (node: LineageNode) => void;
}

// ============ 节点可视化 ============
export interface NodeVisual {
  container: Container;
  innerGroup: Container;
  border: Graphics;
  shadow: Graphics;
  collapseBtn?: Container;

  baseX: number;
  baseY: number;

  targetX: number;
  targetY: number;

  targetLift: number;
  targetScale: number;
  targetShadowAlpha: number;
  targetShadowScale: number;

  hasChildren: boolean;
  lineageCode: string;
}

// ============ 连线可视化 ============
export interface LinkVisual {
  graphics: Graphics;
  sourceCode: string;
  targetCode: string;
  type: "solid" | "dashed";
  color: number;
  alpha: number;
  width: number;
  isSecondaryHybrid?: boolean;
}

// ============ 流动粒子 ============
export interface FlowParticle {
  t: number;
  speed: number;
  linkVisual: LinkVisual;
  graphics: Graphics;
  color: number;
}

// ============ 相机状态 ============
export interface CameraState {
  x: number;
  y: number;
  zoom: number;
}

// ============ 布局节点（D3） ============
export interface LayoutNode {
  id: string;
  parentId: string | null;
  data: LineageNode | null;
  children?: LayoutNode[];
  x?: number;
  y?: number;
  depth?: number;
}

// ============ 工具提示数据 ============
export interface TooltipData {
  node: LineageNode;
  x: number;
  y: number;
}

