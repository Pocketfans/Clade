/**
 * useCollapse - 节点折叠/展开 Hook
 */

import { useState, useCallback, useMemo } from "react";
import type { LineageNode } from "@/services/api.types";
import { ROOT_CODE } from "../constants";

interface UseCollapseOptions {
  nodes: LineageNode[];
}

interface UseCollapseResult {
  collapsedNodes: Set<string>;
  toggleCollapse: (lineageCode: string) => void;
  expandAll: () => void;
  collapseAll: () => void;
  isCollapsed: (lineageCode: string) => boolean;
  getVisibleNodes: () => LineageNode[];
}

export function useCollapse({ nodes }: UseCollapseOptions): UseCollapseResult {
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set());

  // 构建父子关系映射
  const parentChildMap = useMemo(() => {
    const map = new Map<string, string[]>();
    
    for (const node of nodes) {
      const parentCode = node.parent_code || ROOT_CODE;
      if (!map.has(parentCode)) {
        map.set(parentCode, []);
      }
      map.get(parentCode)!.push(node.lineage_code);
    }
    
    return map;
  }, [nodes]);

  // 获取所有可折叠的节点（有子节点的节点）
  const collapsibleNodes = useMemo(() => {
    const set = new Set<string>();
    for (const [parentCode] of parentChildMap) {
      if (parentCode !== ROOT_CODE) {
        set.add(parentCode);
      }
    }
    return set;
  }, [parentChildMap]);

  const toggleCollapse = useCallback((lineageCode: string) => {
    setCollapsedNodes((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(lineageCode)) {
        newSet.delete(lineageCode);
      } else {
        newSet.add(lineageCode);
      }
      return newSet;
    });
  }, []);

  const expandAll = useCallback(() => {
    setCollapsedNodes(new Set());
  }, []);

  const collapseAll = useCallback(() => {
    setCollapsedNodes(new Set(collapsibleNodes));
  }, [collapsibleNodes]);

  const isCollapsed = useCallback(
    (lineageCode: string) => collapsedNodes.has(lineageCode),
    [collapsedNodes]
  );

  // 获取所有被隐藏的节点（祖先被折叠）
  const getHiddenNodes = useCallback((): Set<string> => {
    const hidden = new Set<string>();

    const hideDescendants = (parentCode: string) => {
      const children = parentChildMap.get(parentCode) || [];
      for (const childCode of children) {
        hidden.add(childCode);
        hideDescendants(childCode);
      }
    };

    for (const collapsedCode of collapsedNodes) {
      hideDescendants(collapsedCode);
    }

    return hidden;
  }, [collapsedNodes, parentChildMap]);

  const getVisibleNodes = useCallback(() => {
    const hidden = getHiddenNodes();
    return nodes.filter((node) => !hidden.has(node.lineage_code));
  }, [nodes, getHiddenNodes]);

  return {
    collapsedNodes,
    toggleCollapse,
    expandAll,
    collapseAll,
    isCollapsed,
    getVisibleNodes,
  };
}

