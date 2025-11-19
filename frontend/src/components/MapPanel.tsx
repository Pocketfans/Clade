import {
  useState,
  useRef,
  useMemo,
  useEffect,
  useCallback,
  useImperativeHandle,
  forwardRef,
  memo,
} from "react";
import type { JSX } from "react";
import type { MapOverview, MapTileInfo } from "../services/api.types";
import { ViewMode } from "./MapViewSelector";
import { MapLegend } from "./MapLegend";

interface Props {
  map?: MapOverview | null;
  onRefresh: () => void;
  selectedTile?: MapTileInfo | null;
  onSelectTile: (tile: MapTileInfo, point: { clientX: number; clientY: number }) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

const HEX_WIDTH = 40;
const HEX_HEIGHT = 34;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2;
const COLUMN_SPACING = HEX_WIDTH * 0.75;
const ROW_SPACING = HEX_HEIGHT;
const COLUMN_OFFSET = HEX_HEIGHT / 2;
const PADDING = HEX_WIDTH;
const INITIAL_ZOOM = 0.9;

// 惯性参数
const FRICTION = 0.92; // 摩擦系数 (0-1)，越小停得越快
const STOP_VELOCITY = 0.1; // 停止阈值

const clampZoom = (value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));

export function MapPanel({ map, onRefresh, selectedTile, onSelectTile, viewMode }: Props) {
  const [zoom, setZoom] = useState(INITIAL_ZOOM);
  const stageRef = useRef<HexStageHandle>(null);

  const handleZoomButton = (delta: number) => {
    stageRef.current?.zoomBy(delta);
  };

  const resetZoom = () => stageRef.current?.resetZoom();

  return (
    <div className="map-surface" style={{ padding: 0 }}>
      {!map ? (
        <div className="placeholder" style={{ padding: "40px", textAlign: "center", marginTop: "20vh" }}>
          <p>正在加载地图数据...</p>
        </div>
      ) : map.tiles.length === 0 ? (
        <div className="card" style={{ padding: "40px", textAlign: "center", margin: "2rem auto", maxWidth: "500px" }}>
          <div className="flex flex-col items-center gap-md">
            <span className="text-danger text-2xl">⚠️</span>
            <h3 className="text-xl font-semibold text-danger">地图未初始化</h3>
            <p className="text-secondary text-sm">
              后端可能未正确启动或数据库初始化失败，请检查后端日志
            </p>
            <button
              onClick={onRefresh}
              className="btn btn-primary mt-md"
            >
              重试
            </button>
          </div>
        </div>
      ) : (
        <>
          <HexStage
            ref={stageRef}
            map={map}
            selectedTile={selectedTile}
            onSelectTile={onSelectTile}
            onZoomChange={setZoom}
            viewMode={viewMode}
          />
          
          {/* Floating Zoom Controls */}
          <div className="map-zoom-controls">
            <div className="zoom-group">
              <button type="button" onClick={() => handleZoomButton(0.1)} title="放大">＋</button>
              <button type="button" onClick={() => handleZoomButton(-0.1)} title="缩小">－</button>
            </div>
            <button type="button" onClick={resetZoom} className="zoom-reset" title="重置视角">
              {Math.round(zoom * 100)}%
            </button>
          </div>

          <MapLegend 
            viewMode={viewMode} 
            seaLevel={map?.sea_level ?? 0} 
            temperature={map?.global_avg_temperature ?? 15}
          />
        </>
      )}
    </div>
  );
}

interface HexStageProps {
  map: MapOverview;
  selectedTile?: MapTileInfo | null;
  onSelectTile: (tile: MapTileInfo, point: { clientX: number; clientY: number }) => void;
  onZoomChange: (value: number) => void;
  viewMode: ViewMode;
}

interface HexStageHandle {
  zoomBy: (delta: number) => void;
  resetZoom: () => void;
}

const MOVEMENT_THRESHOLD = 4;

const HexStage = forwardRef<HexStageHandle, HexStageProps>(function HexStage(
  { map, selectedTile, onSelectTile, onZoomChange, viewMode },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const zoomLayerRef = useRef<HTMLDivElement>(null);

  // 相机绝对位置（世界坐标）
  const cameraRef = useRef({ x: 0, y: 0 });
  // 渲染用的相机坐标（用于触发 visibleTiles 更新）
  const [renderCamera, setRenderCamera] = useState({ x: 0, y: 0 });
  
  // 拖拽与惯性状态
  const pointerStartRef = useRef({ x: 0, y: 0 });
  const cameraStartRef = useRef({ x: 0, y: 0 });
  const draggingRef = useRef(false);
  const hasMovedRef = useRef(false);
  
  // 惯性相关
  const velocityRef = useRef({ x: 0, y: 0 });
  const lastMoveTimeRef = useRef(0);
  const inertiaFrameRef = useRef<number>();

  // 当前缩放
  const scaleRef = useRef(INITIAL_ZOOM);
  // 视口尺寸（用于计算剔除）
  const viewportRef = useRef({ width: 0, height: 0 });
  // 渲染调度
  const requestRef = useRef<number>();

  // 1. 计算世界基础布局
  const layout = useMemo(() => {
    if (!map.tiles.length) {
      return {
        positions: new Map<number, { x: number; y: number }>(),
        width: 0,
        height: 0,
        worldWidth: 0,
      };
    }

    let maxCol = 0;
    let maxRow = 0;
    const positions = new Map<number, { x: number; y: number }>();

    for (const tile of map.tiles) {
      const col = tile.x;
      const row = tile.y;
      const px = col * COLUMN_SPACING + PADDING;
      const py = row * ROW_SPACING + (col & 1 ? COLUMN_OFFSET : 0) + PADDING;
      positions.set(tile.id, { x: px, y: py });
      maxCol = Math.max(maxCol, col);
      maxRow = Math.max(maxRow, row);
    }

    // 世界的总宽度（用于循环）
    const worldWidth = (maxCol + 1) * COLUMN_SPACING;
    const width = worldWidth + PADDING * 2 + HEX_WIDTH;
    const height = (maxRow + 1) * ROW_SPACING + COLUMN_OFFSET + PADDING * 2 + HEX_HEIGHT;

    return { positions, width, height, worldWidth };
  }, [map.tiles]);

  // 2. 更新 DOM 变换
  const updateTransform = useCallback(() => {
    if (!contentRef.current || !zoomLayerRef.current) return;
    const { x, y } = cameraRef.current;
    const scale = scaleRef.current;
    
    contentRef.current.style.transform = `translate3d(${-x}px, ${-y}px, 0)`; // Force GPU
    zoomLayerRef.current.style.transform = `scale(${scale})`;
  }, []);

  // 初始化视口尺寸
  useEffect(() => {
    if (containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      viewportRef.current = { width, height };
      // 初始居中
      cameraRef.current = {
        x: (layout.width * scaleRef.current - width) / 2,
        y: (layout.height * scaleRef.current - height) / 2
      };
      updateTransform();
      setRenderCamera(cameraRef.current);
    }
    
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        viewportRef.current = { width: entry.contentRect.width, height: entry.contentRect.height };
        // 视口大小变化时，强制更新渲染
        setRenderCamera({ ...cameraRef.current });
      }
    });
    
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [layout.width, layout.height, updateTransform]);

  // 3. 缩放逻辑
  const zoomAtPoint = useCallback(
    (nextZoom: number, anchorClient: { x: number; y: number }) => {
      const clamped = clampZoom(nextZoom);
      const prevZoom = scaleRef.current;
      if (!containerRef.current || clamped === prevZoom) return;

      // 缩放时停止任何正在进行的惯性
      if (inertiaFrameRef.current) {
        cancelAnimationFrame(inertiaFrameRef.current);
        inertiaFrameRef.current = undefined;
      }

      const rect = containerRef.current.getBoundingClientRect();
      const viewportX = anchorClient.x - rect.left;
      const viewportY = anchorClient.y - rect.top;

      const worldX = (cameraRef.current.x + viewportX) / prevZoom;
      const worldY = (cameraRef.current.y + viewportY) / prevZoom;

      scaleRef.current = clamped;
      
      cameraRef.current = {
        x: worldX * clamped - viewportX,
        y: worldY * clamped - viewportY
      };

      updateTransform();
      onZoomChange(clamped);
      // 缩放时立即更新渲染，因为可见范围变化剧烈
      setRenderCamera({ ...cameraRef.current });
    },
    [updateTransform, onZoomChange],
  );

  const zoomBy = useCallback((delta: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    zoomAtPoint(scaleRef.current + delta, {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
  }, [zoomAtPoint]);

  const resetZoom = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    scaleRef.current = 1;
    cameraRef.current = {
      x: (layout.width - rect.width) / 2,
      y: (layout.height - rect.height) / 2
    };
    updateTransform();
    onZoomChange(1);
    setRenderCamera({ ...cameraRef.current });
  }, [layout.width, layout.height, updateTransform, onZoomChange]);

  useImperativeHandle(ref, () => ({ zoomBy, resetZoom }), [zoomBy, resetZoom]);

  // 4. 拖拽与惯性逻辑
  const handleMouseDown = (event: React.MouseEvent) => {
    if (event.button !== 0) return;
    draggingRef.current = true;
    hasMovedRef.current = false;
    
    // 停止惯性动画
    if (inertiaFrameRef.current) {
      cancelAnimationFrame(inertiaFrameRef.current);
      inertiaFrameRef.current = undefined;
    }
    
    pointerStartRef.current = { x: event.clientX, y: event.clientY };
    cameraStartRef.current = { ...cameraRef.current };
    velocityRef.current = { x: 0, y: 0 };
    lastMoveTimeRef.current = Date.now();
    
    // 光标样式
    if (containerRef.current) {
      containerRef.current.style.cursor = "grabbing";
    }
  };

  const handleMouseMove = (event: React.MouseEvent) => {
    if (!draggingRef.current) return;
    
    const now = Date.now();
    const dx = event.clientX - pointerStartRef.current.x;
    const dy = event.clientY - pointerStartRef.current.y;
    
    // 计算瞬时速度 (pixels/ms)
    const dt = now - lastMoveTimeRef.current;
    if (dt > 0) {
      // 使用更平滑的速度计算
      const vx = (event.movementX);
      const vy = (event.movementY);
      velocityRef.current = { x: vx, y: vy };
    }
    lastMoveTimeRef.current = now;

    cameraRef.current = {
      x: cameraStartRef.current.x - dx,
      y: cameraStartRef.current.y - dy
    };
    
    updateTransform();

    if (!hasMovedRef.current && (Math.abs(dx) > MOVEMENT_THRESHOLD || Math.abs(dy) > MOVEMENT_THRESHOLD)) {
      hasMovedRef.current = true;
    }
  };

  const runInertia = useCallback(() => {
    const { x: vx, y: vy } = velocityRef.current;
    
    // 摩擦力衰减
    velocityRef.current.x *= FRICTION;
    velocityRef.current.y *= FRICTION;

    // 更新位置
    cameraRef.current.x -= velocityRef.current.x;
    cameraRef.current.y -= velocityRef.current.y;
    
    updateTransform();

    // 检查是否停止
    if (Math.abs(velocityRef.current.x) > STOP_VELOCITY || Math.abs(velocityRef.current.y) > STOP_VELOCITY) {
      inertiaFrameRef.current = requestAnimationFrame(runInertia);
    } else {
      // 惯性停止，进行最终同步
      setRenderCamera({ ...cameraRef.current });
      inertiaFrameRef.current = undefined;
    }
  }, [updateTransform]);

  const stopDragging = useCallback(() => {
    draggingRef.current = false;
    
    if (containerRef.current) {
      containerRef.current.style.cursor = "grab";
    }

    // 如果速度足够大，启动惯性
    const timeSinceLastMove = Date.now() - lastMoveTimeRef.current;
    // 如果停顿太久（比如按住不放），则没有惯性
    if (timeSinceLastMove < 100 && (Math.abs(velocityRef.current.x) > 1 || Math.abs(velocityRef.current.y) > 1)) {
      runInertia();
    } else {
      // 没有惯性，直接同步
      setRenderCamera({ ...cameraRef.current });
    }
  }, [runInertia]);

  useEffect(() => {
    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, [stopDragging]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? -0.08 : 0.08;
      const multiplier = event.ctrlKey ? 2 : 1;
      zoomAtPoint(scaleRef.current + delta * multiplier, { x: event.clientX, y: event.clientY });
    };
    node.addEventListener("wheel", handleWheel, { passive: false });
    return () => node.removeEventListener("wheel", handleWheel);
  }, [zoomAtPoint]);

  // 5. 动态 Tile 生成（增加更大缓冲区）
  const visibleTiles = useMemo(() => {
    if (!layout.worldWidth) return [];

    const scale = scaleRef.current;
    const { width: vpW, height: vpH } = viewportRef.current;
    
    const { x: camX, y: camY } = renderCamera; 

    // 缓冲区扩大到 100% 屏幕宽度，以应对长距离快速拖拽
    const bufferX = (vpW / scale) * 1.0;
    const bufferY = (vpH / scale) * 0.5;

    const visibleWorldLeft = (camX / scale) - bufferX;
    const visibleWorldRight = ((camX + vpW) / scale) + bufferX;
    const visibleWorldTop = (camY / scale) - bufferY;
    const visibleWorldBottom = ((camY + vpH) / scale) + bufferY;

    const startPeriod = Math.floor(visibleWorldLeft / layout.worldWidth);
    const endPeriod = Math.floor(visibleWorldRight / layout.worldWidth);

    const nodes: JSX.Element[] = [];
    const selectedId = selectedTile?.id;

    for (let period = startPeriod; period <= endPeriod; period++) {
      const xOffset = period * layout.worldWidth;
      
      for (const tile of map.tiles) {
        const pos = layout.positions.get(tile.id);
        if (!pos) continue;

        if (pos.y < visibleWorldTop - HEX_HEIGHT || pos.y > visibleWorldBottom + HEX_HEIGHT) {
          continue;
        }

        const selected = selectedId === tile.id;
        nodes.push(
          <HexCell
            key={`${tile.id}_${period}`}
            tile={tile}
            position={{ x: pos.x + xOffset, y: pos.y }}
            selected={selected}
            viewMode={viewMode}
            onClick={(t, e) => {
              if (hasMovedRef.current) return;
              onSelectTile(t, { clientX: e.clientX, clientY: e.clientY });
            }}
          />
        );
      }
    }
    return nodes;
  }, [map.tiles, layout, selectedTile?.id, viewMode, onSelectTile, renderCamera]);

  return (
    <div
      ref={containerRef}
      className="hex-stage-container"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      style={{
        cursor: "grab", 
      }}
    >
      <div
        ref={contentRef} 
        className="hex-stage-content"
        style={{
          width: 0,
          height: 0,
          willChange: 'transform',
          transformOrigin: '0 0'
        }}
      >
        <div
          ref={zoomLayerRef} 
          className="hex-zoom-layer"
          style={{
            willChange: 'transform',
            transformOrigin: '0 0' 
          }}
        >
          {visibleTiles}
        </div>
      </div>
    </div>
  );
});

function wrapValue(value: number, width: number): number {
  if (!width) return value;
  const normalized = ((value % width) + width) % width;
  return normalized > width / 2 ? normalized - width : normalized;
}

interface HexCellProps {
  tile: MapTileInfo;
  position: { x: number; y: number };
  selected: boolean;
  viewMode: ViewMode;
  onClick: (tile: MapTileInfo, event: React.MouseEvent<HTMLButtonElement>) => void;
}

const HexCell = memo(function HexCell({ tile, position, selected, viewMode, onClick }: HexCellProps) {
  return (
    <button
      type="button"
      className={`hex-cell ${selected ? "selected" : ""}`}
      style={{
        position: "absolute",
        left: `${position.x}px`,
        top: `${position.y}px`,
        background: tile.color,
        color: "#000000",
      }}
      title={`${tile.terrain_type} | ${tile.climate_zone} | ${tile.elevation.toFixed(0)}m (${tile.x}, ${tile.y})`}
      onClick={(event) => onClick(tile, event)}
    >
      {viewMode === "terrain_type" ? tile.terrain_type.slice(0, 2) : ""}
    </button>
  );
}, (prevProps, nextProps) => {
  return (
    prevProps.tile.id === nextProps.tile.id &&
    prevProps.tile.color === nextProps.tile.color &&
    prevProps.selected === nextProps.selected &&
    prevProps.viewMode === nextProps.viewMode &&
    prevProps.position.x === nextProps.position.x && 
    prevProps.position.y === nextProps.position.y
  );
});

export type { HexStageHandle };
