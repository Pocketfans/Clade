import {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
} from "react";
import type { MapOverview, MapTileInfo } from "../services/api.types";
import { ViewMode } from "./MapViewSelector";

interface Props {
  map?: MapOverview | null;
  onRefresh: () => void;
  selectedTile?: MapTileInfo | null;
  onSelectTile: (tile: MapTileInfo, point: { clientX: number; clientY: number }) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  highlightSpeciesId?: string | null;
}

const HEX_WIDTH = 40;
const HEX_HEIGHT = 34;
const COLUMN_SPACING = HEX_WIDTH * 0.75;
const ROW_SPACING = HEX_HEIGHT;
const COLUMN_OFFSET = HEX_HEIGHT / 2;
const PADDING = HEX_WIDTH;

// 样式配置
const HEX_STROKE_COLOR = "rgba(255, 255, 255, 0.15)";
const HEX_STROKE_WIDTH = 1;
const SELECTED_STROKE_COLOR = "#ffffff";
const SELECTED_STROKE_WIDTH = 3;
const HOVER_STROKE_COLOR = "rgba(255, 255, 255, 0.6)";

// 惯性参数
const FRICTION = 0.92;
const STOP_VELOCITY = 0.1;

export function CanvasMapPanel({
  map,
  onRefresh,
  selectedTile,
  onSelectTile,
  viewMode,
  onViewModeChange,
  highlightSpeciesId,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const cameraRef = useRef({ x: 0, y: 0, zoom: 1 });
  const [uiZoom, setUiZoom] = useState(1);
  
  const [hoveredTile, setHoveredTile] = useState<MapTileInfo | null>(null);
  
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const velocity = useRef({ x: 0, y: 0 });
  const lastMoveTime = useRef(0);
  const inertiaReqRef = useRef<number>();
  const drawReqRef = useRef<number>();

  // 布局计算缓存
  const layout = useMemo(() => {
    if (!map?.tiles.length) return null;
    
    let maxCol = 0;
    let maxRow = 0;
    const positions = new Map<number, { x: number; y: number }>();
    const tileMap = new Map<string, MapTileInfo>(); 

    for (const tile of map.tiles) {
      const col = tile.x;
      const row = tile.y;
      const px = col * COLUMN_SPACING + PADDING;
      const py = row * ROW_SPACING + (col % 2 ? COLUMN_OFFSET : 0) + PADDING;
      positions.set(tile.id, { x: px, y: py });
      tileMap.set(`${col},${row}`, tile);
      maxCol = Math.max(maxCol, col);
      maxRow = Math.max(maxRow, row);
    }

    const worldWidth = (maxCol + 1) * COLUMN_SPACING;
    const worldHeight = (maxRow + 1) * ROW_SPACING + COLUMN_OFFSET + PADDING * 2;

    return { positions, tileMap, worldWidth, worldHeight, maxCol, maxRow };
  }, [map?.tiles]);

  // 适宜度颜色缓存
  const suitabilityColors = useMemo(() => {
    const colorMap = new Map<number, string>();
    if (viewMode === "suitability" && highlightSpeciesId && map?.habitats) {
      for (const hab of map.habitats) {
        if (hab.lineage_code === highlightSpeciesId) {
          const s = Math.max(0, Math.min(1, hab.suitability));
          const r = s < 0.5 ? 255 : Math.round((1 - s) * 2 * 255);
          const g = s < 0.5 ? Math.round(s * 2 * 255) : 255;
          colorMap.set(hab.tile_id, `rgb(${r}, ${g}, 0)`);
        }
      }
    }
    return colorMap;
  }, [map?.habitats, viewMode, highlightSpeciesId]);

  // 绘制函数
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !layout || !map) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const { width, height } = canvas;
    const { x: camX, y: camY, zoom } = cameraRef.current;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    // 背景色改为更深的深蓝色
    ctx.fillStyle = "#030510"; 
    ctx.fillRect(0, 0, width, height);

    ctx.scale(dpr, dpr);
    ctx.translate(camX, camY);
    ctx.scale(zoom, zoom);

    const buffer = HEX_WIDTH * 5;
    const visibleL = -camX / zoom;
    const visibleR = (width - camX) / zoom;
    const visibleT = -camY / zoom;
    const visibleB = (height - camY) / zoom;

    const startK = Math.floor((visibleL - buffer) / layout.worldWidth);
    const endK = Math.floor((visibleR + buffer) / layout.worldWidth);

    const drawHexPath = (cx: number, cy: number) => {
      ctx.beginPath();
      const w2 = HEX_WIDTH / 2;
      const h2 = HEX_HEIGHT / 2;
      const w4 = HEX_WIDTH / 4;
      ctx.moveTo(cx + w2, cy);
      ctx.lineTo(cx + w4, cy + h2);
      ctx.lineTo(cx - w4, cy + h2);
      ctx.lineTo(cx - w2, cy);
      ctx.lineTo(cx - w4, cy - h2);
      ctx.lineTo(cx + w4, cy - h2);
      ctx.closePath();
    };

    ctx.lineWidth = HEX_STROKE_WIDTH;
    ctx.lineJoin = "round";

    for (let k = startK; k <= endK; k++) {
      const offsetX = k * layout.worldWidth;
      
      map.tiles.forEach(tile => {
        const pos = layout.positions.get(tile.id);
        if (!pos) return;
        
        const drawX = pos.x + offsetX;
        const drawY = pos.y;

        if (drawY < visibleT - buffer || drawY > visibleB + buffer) return;
        if (drawX < visibleL - buffer || drawX > visibleR + buffer) return;

        let fillStyle = tile.color || "#1f2937";
        if (viewMode === "suitability") {
          if (highlightSpeciesId) {
            fillStyle = suitabilityColors.get(tile.id) || "rgba(255, 255, 255, 0.03)";
          } else {
            fillStyle = "#1f2937";
          }
        }

        drawHexPath(drawX, drawY);
        ctx.fillStyle = fillStyle;
        ctx.fill();
        ctx.strokeStyle = HEX_STROKE_COLOR;
        ctx.stroke();
        
        if (zoom > 0.8 && viewMode === "terrain_type") {
           ctx.fillStyle = "rgba(255,255,255,0.4)";
           ctx.font = "10px Inter, sans-serif";
           ctx.textAlign = "center";
           ctx.textBaseline = "middle";
           ctx.fillText(tile.terrain_type.slice(0, 2), drawX, drawY);
        }
      });
    }

    // Hover
    if (hoveredTile && hoveredTile.id !== selectedTile?.id) {
      const pos = layout.positions.get(hoveredTile.id);
      if (pos) {
        for (let k = startK; k <= endK; k++) {
          const drawX = pos.x + k * layout.worldWidth;
          if (drawX < visibleL - HEX_WIDTH || drawX > visibleR + HEX_WIDTH) continue;
          
          drawHexPath(drawX, pos.y);
          ctx.strokeStyle = HOVER_STROKE_COLOR;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
    }

    // Selected
    if (selectedTile) {
      const pos = layout.positions.get(selectedTile.id);
      if (pos) {
        for (let k = startK; k <= endK; k++) {
          const drawX = pos.x + k * layout.worldWidth;
          if (drawX < visibleL - HEX_WIDTH || drawX > visibleR + HEX_WIDTH) continue;

          drawHexPath(drawX, pos.y);
          ctx.strokeStyle = SELECTED_STROKE_COLOR;
          ctx.lineWidth = SELECTED_STROKE_WIDTH;
          ctx.shadowColor = "rgba(255, 255, 255, 0.8)";
          ctx.shadowBlur = 15;
          ctx.stroke();
          ctx.shadowBlur = 0;
        }
      }
    }
  }, [layout, map, selectedTile, hoveredTile, viewMode, highlightSpeciesId, suitabilityColors]);

  const requestDraw = useCallback(() => {
    if (drawReqRef.current) cancelAnimationFrame(drawReqRef.current);
    drawReqRef.current = requestAnimationFrame(draw);
  }, [draw]);

  const updateInertia = useCallback(() => {
    const v = velocity.current;
    if (Math.abs(v.x) < STOP_VELOCITY && Math.abs(v.y) < STOP_VELOCITY) {
      inertiaReqRef.current = undefined;
      return;
    }
    
    v.x *= FRICTION;
    v.y *= FRICTION;
    
    cameraRef.current.x += v.x;
    cameraRef.current.y += v.y;
    
    if (layout && containerRef.current) {
      const { height } = containerRef.current.getBoundingClientRect();
      const { y, zoom } = cameraRef.current;
      const worldH = layout.worldHeight;
      
      const margin = height * 0.2;
      const minY = height - worldH * zoom - margin;
      const maxY = margin;
      
      if (y < minY) {
        cameraRef.current.y = minY;
        v.y = 0;
      } else if (y > maxY) {
        cameraRef.current.y = maxY;
        v.y = 0;
      }
    }
    
    requestDraw();
    inertiaReqRef.current = requestAnimationFrame(updateInertia);
  }, [requestDraw, layout]);

  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current && canvasRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        canvasRef.current.width = width * dpr;
        canvasRef.current.height = height * dpr;
        canvasRef.current.style.width = `${width}px`;
        canvasRef.current.style.height = `${height}px`;
        
        if (layout && cameraRef.current.x === 0 && cameraRef.current.y === 0) {
           cameraRef.current.x = (width - layout.worldWidth) / 2;
           cameraRef.current.y = (height - layout.worldHeight) / 2;
           requestDraw();
        } else {
           requestDraw();
        }
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [layout, requestDraw]);
  
  useEffect(() => {
    requestDraw();
  }, [requestDraw]);

  const getTileAtScreenPos = (clientX: number, clientY: number) => {
    if (!canvasRef.current || !layout) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const { x: camX, y: camY, zoom } = cameraRef.current;
    
    const rawWorldX = (x - camX) / zoom;
    const worldY = (y - camY) / zoom;
    const normalizedWorldX = ((rawWorldX % layout.worldWidth) + layout.worldWidth) % layout.worldWidth;
    
    const approxCol = Math.round((normalizedWorldX - PADDING) / COLUMN_SPACING);
    const approxRow = Math.round((worldY - PADDING) / ROW_SPACING);
    
    let closestDist = Infinity;
    let closestTile = null;

    for (let cOffset = -1; cOffset <= 1; cOffset++) {
      let c = approxCol + cOffset;
      if (c < 0) c = layout.maxCol + 1 + c;
      if (c > layout.maxCol) c = c - (layout.maxCol + 1);

      for (let r = approxRow - 1; r <= approxRow + 1; r++) {
        const tile = layout.tileMap.get(`${c},${r}`);
        if (tile) {
          const pos = layout.positions.get(tile.id);
          if (pos) {
            let dx = Math.abs(pos.x - normalizedWorldX);
            if (dx > layout.worldWidth / 2) {
              dx = layout.worldWidth - dx;
            }
            const dy = pos.y - worldY;
            const dist = Math.sqrt(dx*dx + dy*dy);
            if (dist < HEX_WIDTH / 2 && dist < closestDist) {
              closestDist = dist;
              closestTile = tile;
            }
          }
        }
      }
    }
    return closestTile;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    isDragging.current = true;
    lastMousePos.current = { x: e.clientX, y: e.clientY };
    lastMoveTime.current = Date.now();
    velocity.current = { x: 0, y: 0 };
    if (inertiaReqRef.current) {
      cancelAnimationFrame(inertiaReqRef.current);
      inertiaReqRef.current = undefined;
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging.current || inertiaReqRef.current) {
      if (isDragging.current) {
        const now = Date.now();
        const dt = now - lastMoveTime.current;
        const dx = e.clientX - lastMousePos.current.x;
        const dy = e.clientY - lastMousePos.current.y;
        
        if (dt > 0) {
           velocity.current = { x: dx, y: dy }; 
        }
        lastMoveTime.current = now;
        lastMousePos.current = { x: e.clientX, y: e.clientY };
        
        cameraRef.current.x += dx;
        cameraRef.current.y += dy;
        
        if (layout && containerRef.current) {
          const { height } = containerRef.current.getBoundingClientRect();
          const { y, zoom } = cameraRef.current;
          const worldH = layout.worldHeight;
          const margin = height * 0.2; // Reverted to 0.2
          const minY = height - worldH * zoom - margin;
          const maxY = margin;
          
          if (y < minY) cameraRef.current.y = minY;
          if (y > maxY) cameraRef.current.y = maxY;
        }

        requestDraw();
      }
      return;
    }

    const tile = getTileAtScreenPos(e.clientX, e.clientY);
    if (tile?.id !== hoveredTile?.id) {
      setHoveredTile(tile || null);
    }
  };

  const handleMouseUp = () => {
    if (isDragging.current) {
      isDragging.current = false;
      if (Math.abs(velocity.current.x) > 1 || Math.abs(velocity.current.y) > 1) {
        updateInertia();
      }
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    if (Math.abs(velocity.current.x) > 1 || Math.abs(velocity.current.y) > 1) return;
    
    const tile = getTileAtScreenPos(e.clientX, e.clientY);
    if (tile) {
      onSelectTile(tile, { clientX: e.clientX, clientY: e.clientY });
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (inertiaReqRef.current) {
      cancelAnimationFrame(inertiaReqRef.current);
      inertiaReqRef.current = undefined;
    }
    
    const zoomSensitivity = 0.001;
    const delta = -e.deltaY * zoomSensitivity;
    const prevZoom = cameraRef.current.zoom;
    const newZoom = Math.max(0.8, Math.min(3.0, prevZoom + delta)); // Reverted to 0.8 - 3.0
    
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const worldX = (mouseX - cameraRef.current.x) / prevZoom;
    const worldY = (mouseY - cameraRef.current.y) / prevZoom;
    
    const newCamX = mouseX - worldX * newZoom;
    const newCamY = mouseY - worldY * newZoom;
    
    cameraRef.current = { x: newCamX, y: newCamY, zoom: newZoom };
    
    if (layout) {
      const { height } = rect;
      const worldH = layout.worldHeight;
      const margin = height * 0.2;
      const minY = height - worldH * newZoom - margin;
      const maxY = margin;
      
      if (cameraRef.current.y < minY) cameraRef.current.y = minY;
      if (cameraRef.current.y > maxY) cameraRef.current.y = maxY;
    }

    setUiZoom(newZoom);
    requestDraw();
  };

  return (
    <div className="map-surface" style={{ padding: 0, position: "relative" }}>
      {!map ? (
        <div className="h-full flex flex-col items-center justify-center text-muted space-y-4">
          <div className="spinner w-8 h-8 border-t-primary border-4"></div>
          <p className="text-sm tracking-widest uppercase opacity-70">Initializing World Map...</p>
        </div>
      ) : (
        <div 
          ref={containerRef} 
          style={{ width: "100%", height: "100%", overflow: "hidden", cursor: isDragging.current ? "grabbing" : "default" }}
        >
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onClick={handleClick}
            onWheel={handleWheel}
            style={{ display: "block" }}
          />
        </div>
      )}
    </div>
  );
}
