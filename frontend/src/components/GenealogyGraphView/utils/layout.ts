/**
 * 族谱布局计算工具
 */

import * as d3 from "d3";
import type { LineageNode } from "@/services/api.types";
import type { LayoutNode } from "../types";
import { ROOT_CODE, ROOT_NAME } from "../constants";

/**
 * 构建层级树数据结构
 */
export function buildHierarchy(
  nodes: LineageNode[],
  collapsedNodes: Set<string>
): LayoutNode {
  // 创建虚拟根节点
  const root: LayoutNode = {
    id: ROOT_CODE,
    parentId: null,
    data: null,
    children: [],
  };

  // 创建节点映射
  const nodeMap = new Map<string, LayoutNode>();
  nodeMap.set(ROOT_CODE, root);

  // 第一遍：创建所有 LayoutNode
  for (const node of nodes) {
    nodeMap.set(node.lineage_code, {
      id: node.lineage_code,
      parentId: node.parent_code || ROOT_CODE,
      data: node,
      children: [],
    });
  }

  // 第二遍：建立父子关系
  for (const node of nodes) {
    const layoutNode = nodeMap.get(node.lineage_code)!;
    const parentCode = node.parent_code || ROOT_CODE;
    const parent = nodeMap.get(parentCode);

    if (parent && !collapsedNodes.has(parentCode)) {
      if (!parent.children) parent.children = [];
      parent.children.push(layoutNode);
    } else if (!parent) {
      // 父节点不存在，挂到根节点
      root.children!.push(layoutNode);
    }
  }

  return root;
}

/**
 * 使用 D3 计算树布局
 */
export function calculateTreeLayout(
  root: LayoutNode,
  spacingX: number,
  spacingY: number
): d3.HierarchyPointNode<LayoutNode> {
  // 创建 D3 层级结构
  const hierarchy = d3.hierarchy(root, (d) => d.children);

  // 创建树布局
  const treeLayout = d3.tree<LayoutNode>().nodeSize([spacingX, spacingY]);

  // 计算布局
  return treeLayout(hierarchy);
}

/**
 * 获取节点位置映射
 */
export function getNodePositions(
  layoutRoot: d3.HierarchyPointNode<LayoutNode>
): Map<string, { x: number; y: number; depth: number }> {
  const positions = new Map<string, { x: number; y: number; depth: number }>();

  layoutRoot.each((d) => {
    if (d.data.id !== ROOT_CODE) {
      positions.set(d.data.id, {
        x: d.x,
        y: d.y,
        depth: d.depth,
      });
    }
  });

  return positions;
}

/**
 * 获取连线数据
 */
export interface LinkData {
  sourceCode: string;
  targetCode: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  isHybrid: boolean;
  isSecondary: boolean;
}

export function getLinks(
  nodes: LineageNode[],
  positions: Map<string, { x: number; y: number; depth: number }>,
  collapsedNodes: Set<string>
): LinkData[] {
  const links: LinkData[] = [];

  for (const node of nodes) {
    const targetPos = positions.get(node.lineage_code);
    if (!targetPos) continue;

    // 主连线（父节点）
    if (node.parent_code) {
      const sourcePos = positions.get(node.parent_code);
      if (sourcePos && !collapsedNodes.has(node.parent_code)) {
        links.push({
          sourceCode: node.parent_code,
          targetCode: node.lineage_code,
          sourceX: sourcePos.x,
          sourceY: sourcePos.y,
          targetX: targetPos.x,
          targetY: targetPos.y,
          isHybrid: false,
          isSecondary: false,
        });
      }
    }

    // 杂交连线
    if (node.hybrid_parent_codes && node.hybrid_parent_codes.length > 1) {
      for (const hybridParent of node.hybrid_parent_codes) {
        if (hybridParent !== node.parent_code) {
          const sourcePos = positions.get(hybridParent);
          if (sourcePos) {
            links.push({
              sourceCode: hybridParent,
              targetCode: node.lineage_code,
              sourceX: sourcePos.x,
              sourceY: sourcePos.y,
              targetX: targetPos.x,
              targetY: targetPos.y,
              isHybrid: true,
              isSecondary: true,
            });
          }
        }
      }
    }
  }

  return links;
}

/**
 * 计算布局边界
 */
export function getLayoutBounds(
  positions: Map<string, { x: number; y: number; depth: number }>
): { minX: number; maxX: number; minY: number; maxY: number; width: number; height: number } {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const pos of positions.values()) {
    minX = Math.min(minX, pos.x);
    maxX = Math.max(maxX, pos.x);
    minY = Math.min(minY, pos.y);
    maxY = Math.max(maxY, pos.y);
  }

  return {
    minX,
    maxX,
    minY,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

