/**
 * useCamera - 相机控制 Hook
 */

import { useCallback, useRef } from "react";
import type { Container } from "pixi.js";
import type { CameraState } from "../types";
import { DEFAULT_CAMERA, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP } from "../constants";

interface UseCameraOptions {
  stageRef: React.RefObject<Container | null>;
}

interface UseCameraResult {
  cameraRef: React.MutableRefObject<CameraState>;
  resetView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  setZoom: (zoom: number) => void;
  panTo: (x: number, y: number) => void;
}

export function useCamera({ stageRef }: UseCameraOptions): UseCameraResult {
  const cameraRef = useRef<CameraState>({ ...DEFAULT_CAMERA });

  const applyCamera = useCallback(() => {
    if (stageRef.current) {
      stageRef.current.position.set(cameraRef.current.x, cameraRef.current.y);
      stageRef.current.scale.set(cameraRef.current.zoom);
    }
  }, [stageRef]);

  const resetView = useCallback(() => {
    cameraRef.current = { ...DEFAULT_CAMERA };
    applyCamera();
  }, [applyCamera]);

  const zoomIn = useCallback(() => {
    const newZoom = Math.min(ZOOM_MAX, cameraRef.current.zoom * ZOOM_STEP);
    cameraRef.current.zoom = newZoom;
    applyCamera();
  }, [applyCamera]);

  const zoomOut = useCallback(() => {
    const newZoom = Math.max(ZOOM_MIN, cameraRef.current.zoom / ZOOM_STEP);
    cameraRef.current.zoom = newZoom;
    applyCamera();
  }, [applyCamera]);

  const setZoom = useCallback(
    (zoom: number) => {
      cameraRef.current.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom));
      applyCamera();
    },
    [applyCamera]
  );

  const panTo = useCallback(
    (x: number, y: number) => {
      cameraRef.current.x = x;
      cameraRef.current.y = y;
      applyCamera();
    },
    [applyCamera]
  );

  return {
    cameraRef,
    resetView,
    zoomIn,
    zoomOut,
    setZoom,
    panTo,
  };
}




