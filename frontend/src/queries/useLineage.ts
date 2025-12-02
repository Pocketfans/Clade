/**
 * useLineage - 族谱数据查询 Hook
 */

import { useState, useCallback, useEffect } from "react";
import { useGame } from "@/providers/GameProvider";
import { useUI } from "@/providers/UIProvider";
import { fetchLineageTree, invalidateLineageCache } from "@/services/api";
import type { LineageTree, LineageQueryParams } from "@/services/api.types";

interface UseLineageResult {
  lineageTree: LineageTree | null;
  lineageLoading: boolean;
  lineageError: string | null;
  loadLineageTree: (params?: LineageQueryParams) => Promise<void>;
  clearLineageCache: () => void;
}

export function useLineage(): UseLineageResult {
  const { lineageTree, setLineageTree } = useGame();
  const { overlay } = useUI();
  
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);

  const loadLineageTree = useCallback(async (params?: LineageQueryParams) => {
    if (lineageLoading) return;
    
    setLineageLoading(true);
    setLineageError(null);
    
    try {
      const tree = await fetchLineageTree(params);
      setLineageTree(tree);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "未知错误";
      setLineageError(`族谱加载失败: ${message}`);
      console.error("族谱加载失败:", err);
    } finally {
      setLineageLoading(false);
    }
  }, [lineageLoading, setLineageTree]);

  const clearLineageCache = useCallback(() => {
    setLineageTree(null);
    invalidateLineageCache();
  }, [setLineageTree]);

  // 当切换到族谱视图时自动加载
  useEffect(() => {
    if (overlay === "genealogy" && !lineageTree && !lineageLoading) {
      loadLineageTree();
    }
  }, [overlay, lineageTree, lineageLoading, loadLineageTree]);

  return {
    lineageTree,
    lineageLoading,
    lineageError,
    loadLineageTree,
    clearLineageCache,
  };
}
