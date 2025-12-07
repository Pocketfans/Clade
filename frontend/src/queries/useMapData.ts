/**
 * useMapData - 地图数据查询 Hook
 */

import { useCallback, useRef } from "react";
import { useGame } from "@/providers/GameProvider";
import { useUI } from "@/providers/UIProvider";
import { fetchMapOverview } from "@/services/api";
import type { CameraState } from "@/components/CanvasMapPanel";

interface UseMapDataResult {
  mapData: ReturnType<typeof useGame>["mapData"];
  loading: boolean;
  error: string | null;
  refreshMap: () => Promise<void>;
  handleViewModeChange: (mode: string, options?: { preserveCamera?: boolean }) => void;
  mapPanelRef: React.MutableRefObject<{ getCameraState: () => CameraState | null; setCameraState: (state: CameraState) => void } | null>;
  captureCamera: () => CameraState | null;
  restoreCamera: (snapshot: CameraState | null) => void;
}

export function useMapData(): UseMapDataResult {
  const { mapData, setMapData, setError, loading, error } = useGame();
  const { viewMode, setViewMode, selectedTileId, selectTile } = useUI();
  const mapPanelRef = useRef<{ getCameraState: () => CameraState | null; setCameraState: (state: CameraState) => void } | null>(null);

  const captureCamera = useCallback((): CameraState | null => {
    return mapPanelRef.current?.getCameraState() ?? null;
  }, []);

  const restoreCamera = useCallback((snapshot: CameraState | null) => {
    if (!snapshot || !mapPanelRef.current) return;
    requestAnimationFrame(() => {
      mapPanelRef.current?.setCameraState(snapshot);
    });
  }, []);

  const refreshMap = useCallback(async () => {
    try {
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
      
      // 如果选中的地块不在新数据中，清除选择
      if (selectedTileId !== null) {
        const tileExists = data.tiles.some((t) => t.id === selectedTileId);
        if (!tileExists) {
          selectTile(null);
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "未知错误";
      setError(`地图加载失败: ${message}`);
    }
  }, [viewMode, setMapData, selectedTileId, selectTile, setError]);

  const handleViewModeChange = useCallback(
    (mode: string, options?: { preserveCamera?: boolean }) => {
      if (mode === viewMode) return;

      const snapshot = options?.preserveCamera ? captureCamera() : null;
      setViewMode(mode as ReturnType<typeof useUI>["viewMode"]);

      // 如果有预计算颜色，直接使用；否则需要重新获取
      if (mapData?.tiles[0]?.colors?.[mode as keyof typeof mapData.tiles[0]['colors']]) {
        // 直接使用预计算颜色，无需重新请求
        if (snapshot) {
          restoreCamera(snapshot);
        }
      } else {
        // 需要重新获取数据
        fetchMapOverview(mode).then((data) => {
          setMapData(data);
          if (snapshot) {
            restoreCamera(snapshot);
          }
        }).catch(console.error);
      }
    },
    [mapData, viewMode, captureCamera, setViewMode, setMapData, restoreCamera]
  );

  return {
    mapData,
    loading,
    error,
    refreshMap,
    handleViewModeChange,
    mapPanelRef,
    captureCamera,
    restoreCamera,
  };
}
