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
import { MapViewSelector, ViewMode } from "./MapViewSelector";
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

const clampZoom = (value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));

export function MapPanel({ map, onRefresh, selectedTile, onSelectTile, viewMode, onViewModeChange }: Props) {
  const [zoom, setZoom] = useState(INITIAL_ZOOM);
  const stageRef = useRef<HexStageHandle>(null);

  const handleZoomButton = (delta: number) => {
    stageRef.current?.zoomBy(delta);
  };

  const resetZoom = () => stageRef.current?.resetZoom();

  return (
    <div className="map-surface">
      <div className="map-toolbar">
        <span>世界地图 {map ? `(${map.tiles.length} 地块)` : ""}</span>
        <div className="toolbar-actions">
          <MapViewSelector currentMode={viewMode} onModeChange={onViewModeChange} />
          <div className="zoom-controls" aria-label="地图缩放控制">
            <button type="button" onClick={() => handleZoomButton(-0.1)} aria-label="缩小地图">
              -
            </button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => handleZoomButton(0.1)} aria-label="放大地图">
              +
            </button>
            <button type="button" onClick={resetZoom} aria-label="重置缩放">
              重置
            </button>
          </div>
          <button type="button" onClick={onRefresh}>
            刷新
          </button>
        </div>
      </div>
      {!map ? (
        <div className="placeholder" style={{ padding: "40px", textAlign: "center" }}>
          <p>正在加载地图数据...</p>
          <small>如果长时间未加载，请检查后端服务是否正常运行</small>
        </div>
      ) : map.tiles.length === 0 ? (
        <div className="card" style={{ padding: "40px", textAlign: "center", margin: "2rem" }}>
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

  const offsetRef = useRef({ x: 0, y: 0 });
  const basePanRef = useRef({ x: 0, y: 0 });
  const pointerStartRef = useRef({ x: 0, y: 0 });
  const draggingRef = useRef(false);
  const hasMovedRef = useRef(false);
  const [dragging, setDragging] = useState(false);

  const scaleRef = useRef(INITIAL_ZOOM);

  const layout = useMemo(() => {
    if (!map.tiles.length) {
      return {
        positions: new Map<number, { x: number; y: number }>(),
        width: 0,
        height: 0,
        wrapWidth: 0,
        wrapOffsets: [0],
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

    const wrapWidth = (maxCol + 1) * COLUMN_SPACING;
    const width = wrapWidth + PADDING * 2 + HEX_WIDTH;
    const height = (maxRow + 1) * ROW_SPACING + COLUMN_OFFSET + PADDING * 2 + HEX_HEIGHT;
    const wrapOffsets = wrapWidth > 0 ? [-wrapWidth, 0, wrapWidth] : [0];

    return { positions, width, height, wrapWidth, wrapOffsets };
  }, [map.tiles]);

  const panTo = useCallback(
    (x: number, y: number) => {
      if (!contentRef.current) return;
      offsetRef.current = {
        x: layout.wrapWidth ? wrapValue(x, layout.wrapWidth) : x,
        y,
      };
      const { x: px, y: py } = offsetRef.current;
      contentRef.current.style.transform = `translate(${px}px, ${py}px)`;
    },
    [layout.wrapWidth],
  );

  const applyZoom = useCallback(() => {
    if (!zoomLayerRef.current) return;
    zoomLayerRef.current.style.transform = `scale(${scaleRef.current})`;
  }, []);

  useEffect(() => {
    panTo(offsetRef.current.x, offsetRef.current.y);
    applyZoom();
    onZoomChange(scaleRef.current);
  }, [applyZoom, onZoomChange, panTo]);

  useEffect(() => {
    panTo(offsetRef.current.x, offsetRef.current.y);
  }, [layout.width, layout.height, panTo]);

  const zoomAtPoint = useCallback(
    (nextZoom: number, anchorClient: { x: number; y: number }) => {
      const clamped = clampZoom(nextZoom);
      const prevZoom = scaleRef.current;
      if (!containerRef.current || clamped === prevZoom) return;

      const rect = containerRef.current.getBoundingClientRect();
      const px = anchorClient.x - rect.left;
      const py = anchorClient.y - rect.top;

      const { x: offsetX, y: offsetY } = offsetRef.current;
      const mapX = (px - offsetX) / prevZoom;
      const mapY = (py - offsetY) / prevZoom;

      scaleRef.current = clamped;
      applyZoom();
      panTo(px - mapX * clamped, py - mapY * clamped);
      onZoomChange(clamped);
    },
    [applyZoom, onZoomChange, panTo],
  );

  const zoomBy = useCallback(
    (delta: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      zoomAtPoint(scaleRef.current + delta, {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      });
    },
    [zoomAtPoint],
  );

  const resetZoom = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    zoomAtPoint(1, {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
  }, [zoomAtPoint]);

  useImperativeHandle(
    ref,
    () => ({
      zoomBy,
      resetZoom,
    }),
    [resetZoom, zoomBy],
  );

  const handleMouseDown = (event: React.MouseEvent) => {
    if (event.button !== 0) return;
    draggingRef.current = true;
    hasMovedRef.current = false;
    setDragging(false);
    pointerStartRef.current = { x: event.clientX, y: event.clientY };
    basePanRef.current = { ...offsetRef.current };
  };

  const handleMouseMove = (event: React.MouseEvent) => {
    if (!draggingRef.current) return;
    const dx = event.clientX - pointerStartRef.current.x;
    const dy = event.clientY - pointerStartRef.current.y;
    panTo(basePanRef.current.x + dx, basePanRef.current.y + dy);
    if (
      !hasMovedRef.current &&
      (Math.abs(dx) > MOVEMENT_THRESHOLD || Math.abs(dy) > MOVEMENT_THRESHOLD)
    ) {
      hasMovedRef.current = true;
      setDragging(true);
    }
  };

  const stopDragging = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    hasMovedRef.current = false;
    setDragging(false);
  }, []);

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

  const handleTileClick = useCallback(
    (tile: MapTileInfo, event: React.MouseEvent<HTMLButtonElement>) => {
      if (hasMovedRef.current) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      onSelectTile(tile, { clientX: event.clientX, clientY: event.clientY });
    },
    [onSelectTile],
  );

  const tileElements = useMemo(() => {
    const selectedId = selectedTile?.id;
    const nodes: JSX.Element[] = [];
    for (const [wrapIndex, shift] of layout.wrapOffsets.entries()) {
      for (const tile of map.tiles) {
        const pos = layout.positions.get(tile.id);
        if (!pos) continue;
        const selected = selectedId === tile.id;
        nodes.push(
          <HexCell
            key={`${tile.id}-${wrapIndex}`}
            tile={tile}
            position={{ x: pos.x + shift, y: pos.y }}
            selected={selected}
            viewMode={viewMode}
            onClick={handleTileClick}
          />,
        );
      }
    }
    return nodes;
  }, [handleTileClick, layout.positions, layout.wrapOffsets, map.tiles, selectedTile?.id, viewMode]);

  return (
    <div
      ref={containerRef}
      className="hex-stage-container"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      style={{
        cursor: dragging ? "grabbing" : "grab",
      }}
    >
      <div
        ref={contentRef}
        className="hex-stage-content"
        style={{
          width: `${layout.width}px`,
          height: `${layout.height}px`,
        }}
      >
        <div
          ref={zoomLayerRef}
          className={`hex-zoom-layer ${dragging ? "dragging" : ""}`}
          style={{
            transformOrigin: "top left",
          }}
        >
          {tileElements}
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

// 优化的地块组件，使用memo减少不必要的重新渲染
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
  // 自定义比较函数，只在关键属性变化时重新渲染
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
