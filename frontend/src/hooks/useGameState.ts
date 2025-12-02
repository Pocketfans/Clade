import { useState, useCallback } from "react";
import type { MapOverview, TurnReport, LineageTree, SpeciesDetail } from "@/services/api.types";
import { fetchMapOverview, fetchLineageTree, fetchSpeciesDetail } from "@/services/api";
import type { ViewMode } from "@/components/MapViewSelector";

export function useGameState() {
  const [mapData, setMapData] = useState<MapOverview | null>(null);
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [lineageTree, setLineageTree] = useState<LineageTree | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("terrain");

  const refreshMap = useCallback(async () => {
    try {
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
      console.log(`[前端] 地图加载成功: ${data.tiles.length} 个地块, ${data.habitats.length} 个栖息地, 视图模式: ${viewMode}`);
      if (data.tiles.length === 0) {
        console.warn("[前端] 地图没有地块数据");
        setError("地图数据为空，请检查后端是否正确初始化");
      }
    } catch (error: unknown) {
      console.error("[前端] 地图加载失败:", error);
      setError(`地图加载失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  }, [viewMode]);

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    if (mapData && mapData.tiles.length > 0 && mapData.tiles[0].colors) {
      // 直接使用缓存的颜色数据
      const updatedTiles = mapData.tiles.map(tile => ({
        ...tile,
        color: tile.colors?.[mode] || tile.color
      }));
      setMapData({
        ...mapData,
        tiles: updatedTiles
      });
    } else {
      // 需要重新请求后端
      fetchMapOverview(mode)
        .then(setMapData)
        .catch(console.error);
    }
  }, [mapData]);

  const loadLineageTree = useCallback(async () => {
    if (lineageTree || lineageLoading) return;
    
    setLineageLoading(true);
    try {
      const tree = await fetchLineageTree();
      setLineageTree(tree);
      setLineageError(null);
    } catch (err) {
      console.error(err);
      setLineageError("族谱数据加载失败");
    } finally {
      setLineageLoading(false);
    }
  }, [lineageTree, lineageLoading]);

  const addReports = useCallback((newReports: TurnReport[]) => {
    setReports(prev => [...prev, ...newReports]);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    // 状态
    mapData,
    reports,
    lineageTree,
    lineageLoading,
    lineageError,
    loading,
    error,
    viewMode,
    // 操作
    setMapData,
    setReports,
    setLineageTree,
    setLineageError,
    setLoading,
    setError,
    refreshMap,
    handleViewModeChange,
    loadLineageTree,
    addReports,
    clearError,
  };
}

