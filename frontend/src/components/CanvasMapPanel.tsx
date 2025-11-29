import {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import { Application, Container, Graphics, Sprite, Texture, Assets, BLEND_MODES } from "pixi.js";
import type { MapOverview, MapTileInfo, RiverSegment, VegetationInfo } from "../services/api.types";
import { ViewMode } from "./MapViewSelector";

// Fix import issue if necessary - Pixi v8 structure
// Ensure we are using correct imports.

export type CameraState = { x: number; y: number; zoom: number };

export interface CanvasMapPanelHandle {
  getCameraState: () => CameraState;
  setCameraState: (state: CameraState) => void;
}

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
const HEX_STROKE_COLOR = 0xffffff;
const HEX_STROKE_ALPHA = 0.15;
const SELECTED_STROKE_COLOR = 0xffffff;
const SELECTED_STROKE_WIDTH = 3;
const HOVER_STROKE_COLOR = 0xffffff;
const HOVER_STROKE_ALPHA = 0.6;

// 惯性参数
const FRICTION = 0.92;
const STOP_VELOCITY = 0.1;

export const CanvasMapPanel = forwardRef<CanvasMapPanelHandle, Props>(function CanvasMapPanel({
  map,
  onRefresh,
  selectedTile,
  onSelectTile,
  viewMode,
  onViewModeChange,
  highlightSpeciesId,
}: Props, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const worldLayerRef = useRef<Container | null>(null); // Container holding the map
  const selectionLayerRef = useRef<Container | null>(null);
  
  // Sprites Reference: map tile ID -> Array of 3 sprites (left, center, right)
  const tileSpritesRef = useRef<Map<number, Sprite[]>>(new Map());
  
  // Habitat indicator sprites: map tile ID -> Array of 3 sprites
  const habitatIndicatorsRef = useRef<Map<number, Sprite[]>>(new Map());
  
  // Graphics for dynamic updates
  const hoverGraphicsRef = useRef<Graphics | null>(null);
  const selectGraphicsRef = useRef<Graphics | null>(null);

  const cameraRef = useRef({ x: 0, y: 0, zoom: 1 });
  const [hoveredTile, setHoveredTile] = useState<MapTileInfo | null>(null);
  
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const velocity = useRef({ x: 0, y: 0 });
  const lastMoveTime = useRef(0);
  const inertiaReqRef = useRef<number>();

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

  // 适宜度颜色缓存 - 使用更直观的红-黄-绿渐变
  const suitabilityColors = useMemo(() => {
    const colorMap = new Map<number, number>(); // Store as hex number for Pixi
    if (viewMode === "suitability" && highlightSpeciesId && map?.habitats) {
      for (const hab of map.habitats) {
        if (hab.lineage_code === highlightSpeciesId) {
          const s = Math.max(0, Math.min(1, hab.suitability));
          
          // 新色阶: 红(0) -> 橙(0.3) -> 黄(0.5) -> 黄绿(0.7) -> 绿(1.0)
          // 使用更明亮、更易区分的颜色
          let r: number, g: number, b: number;
          
          if (s < 0.2) {
            // 0-0.2: 红色 #EF4444
            r = 239; g = 68; b = 68;
          } else if (s < 0.4) {
            // 0.2-0.4: 红橙渐变 -> 橙色 #F97316
            const t = (s - 0.2) / 0.2;
            r = Math.round(239 + (249 - 239) * t);
            g = Math.round(68 + (115 - 68) * t);
            b = Math.round(68 + (22 - 68) * t);
          } else if (s < 0.6) {
            // 0.4-0.6: 橙黄渐变 -> 黄色 #FBBF24
            const t = (s - 0.4) / 0.2;
            r = Math.round(249 + (251 - 249) * t);
            g = Math.round(115 + (191 - 115) * t);
            b = Math.round(22 + (36 - 22) * t);
          } else if (s < 0.8) {
            // 0.6-0.8: 黄绿渐变 -> 浅绿 #34D399
            const t = (s - 0.6) / 0.2;
            r = Math.round(251 + (52 - 251) * t);
            g = Math.round(191 + (211 - 191) * t);
            b = Math.round(36 + (153 - 36) * t);
          } else {
            // 0.8-1.0: 浅绿渐变 -> 翠绿 #10B981
            const t = (s - 0.8) / 0.2;
            r = Math.round(52 + (16 - 52) * t);
            g = Math.round(211 + (185 - 211) * t);
            b = Math.round(153 + (129 - 153) * t);
          }
          
          const hex = (r << 16) + (g << 8) + b;
          colorMap.set(hab.tile_id, hex);
        }
      }
    }
    return colorMap;
  }, [map?.habitats, viewMode, highlightSpeciesId]);

  // 计算每个地块的物种数量（用于显示生物指示器）
  const habitatInfo = useMemo(() => {
    const tileSpeciesCount = new Map<number, number>(); // tile ID -> 物种数量
    const tileHasHighlighted = new Map<number, boolean>(); // tile ID -> 是否有选中物种
    
    if (map?.habitats) {
      for (const hab of map.habitats) {
        const current = tileSpeciesCount.get(hab.tile_id) || 0;
        tileSpeciesCount.set(hab.tile_id, current + 1);
        
        if (highlightSpeciesId && hab.lineage_code === highlightSpeciesId) {
          tileHasHighlighted.set(hab.tile_id, true);
        }
      }
    }
    
    return { tileSpeciesCount, tileHasHighlighted };
  }, [map?.habitats, highlightSpeciesId]);

  // Create Blob Texture for Vegetation
  const createBlobTexture = (app: Application) => {
      const g = new Graphics();
      g.circle(0, 0, 8);
      g.fill({ color: 0xffffff, alpha: 1.0 });
      return app.renderer.generateTexture({
          target: g,
          resolution: 2,
          antialias: true,
      });
  };

  // 创建 Sprites 的辅助函数（必须在 useEffect 之前定义）
  const createSprites = useCallback((app: Application, layout: any, map: MapOverview) => {
    console.log('[CanvasMapPanel] 开始创建六边形纹理和 Sprites...');

    const worldLayer = worldLayerRef.current;
    if (!worldLayer) {
      console.error('[CanvasMapPanel] worldLayerRef.current 为 null，无法创建 Sprites');
      return;
    }

    // 1. Generate Hex Texture
    const g = new Graphics();
    const w2 = HEX_WIDTH / 2; // Exact width to prevent gaps
    const h2 = HEX_HEIGHT / 2;
    const w4 = HEX_WIDTH / 4;
    
    g.poly([
      w2, 0,
      w4, -h2,
      -w4, -h2,
      -w2, 0,
      -w4, h2,
      w4, h2
    ]);
    g.fill({ color: 0xffffff, alpha: 1.0 }); 
    
    const texture = app.renderer.generateTexture({
      target: g,
      resolution: 4, // Increase resolution for sharp rendering at high zoom
      antialias: true,
    });

    const blobTexture = createBlobTexture(app);
    
    console.log('[CanvasMapPanel] 纹理已生成');
    
    // 2. Setup World Containers
    worldLayer.removeChildren();
    tileSpritesRef.current.clear();

    // Create layers within the offset containers
    // We need 3 copies of everything
    const createWorldContainer = (offsetX: number) => {
      const container = new Container();
      container.x = offsetX;
      
      // A. Terrain Layer (Bottom)
      const terrainContainer = new Container();
      
      let createdCount = 0;
      map.tiles.forEach((tile, index) => {
        const pos = layout.positions.get(tile.id);
        if (!pos) return;
        
        const sprite = new Sprite(texture);
        sprite.anchor.set(0.5);
        sprite.position.set(pos.x, pos.y);
        
        const color = stringColorToHex(tile.color || "#1f2937");
        sprite.tint = color;
        
        sprite.visible = true;
        sprite.alpha = 1.0;

        terrainContainer.addChild(sprite);
        createdCount++;
        
        if (!tileSpritesRef.current.has(tile.id)) {
          tileSpritesRef.current.set(tile.id, []);
        }
        tileSpritesRef.current.get(tile.id)!.push(sprite);
      });

      container.addChild(terrainContainer);

      // B. Rivers Layer (Middle)
      // Only draw rivers if river data exists
      if (map.rivers) {
          const riverG = new Graphics();
          
          for (const [tileIdStr, segment] of Object.entries(map.rivers)) {
             const sourceId = Number(tileIdStr);
             const targetId = segment.target_id;
             const sourcePos = layout.positions.get(sourceId);
             const targetPos = layout.positions.get(targetId);
             
             if (sourcePos && targetPos) {
                 // Check for wrapping connection (if dist is too large)
                 const dx = targetPos.x - sourcePos.x;
                 const dy = targetPos.y - sourcePos.y;
                 
                 // If jump is > half world, it's a wrap. Skip drawing the line across map
                 // (Visual artifact, ideally we draw to the edge)
                 if (Math.abs(dx) > layout.worldWidth / 2) {
                     continue; 
                 }

                 const flux = segment.flux || 1;
                 const width = Math.min(8, 1 + Math.log(flux) * 0.8);
                 const alpha = Math.min(0.9, 0.4 + flux / 20);
                 
                 // Bezier curve for organic look
                 // Control point: Midpoint with random or noise offset? 
                 // Simple quadratic bezier to slight random side
                 // Deterministic "random"
                 const seed = sourceId * 12345;
                 const r1 = ((seed % 100) / 100 - 0.5) * 10;
                 const midX = (sourcePos.x + targetPos.x) / 2 + r1;
                 const midY = (sourcePos.y + targetPos.y) / 2 + r1;
                 
                 riverG.moveTo(sourcePos.x, sourcePos.y);
                 riverG.quadraticCurveTo(midX, midY, targetPos.x, targetPos.y);
                 riverG.stroke({ width, color: 0x4aa3df, alpha: alpha, cap: 'round' });
             }
          }
          container.addChild(riverG);
      }

      // C. Vegetation Layer (Top)
      if (map.vegetation) {
          const vegContainer = new Container();
          
          for (const [tileIdStr, info] of Object.entries(map.vegetation)) {
              const tileId = Number(tileIdStr);
              const pos = layout.positions.get(tileId);
              if (!pos || info.density <= 0.05) continue;
              
              // Determine color based on type - 30种覆盖物颜色
              let baseColor = 0x3a7048; // 默认阔叶林绿
              
              switch(info.type) {
                  // 森林类 (7种)
                  case 'rainforest': baseColor = 0x1a5030; break;   // 雨林 - 墨绿
                  case 'evergreen': baseColor = 0x2a6040; break;    // 常绿林 - 深绿
                  case 'forest': baseColor = 0x3a7048; break;       // 阔叶林 - 森林绿
                  case 'mixed': baseColor = 0x4a8058; break;        // 混合林 - 中绿
                  case 'taiga': baseColor = 0x3e6850; break;        // 针叶林 - 冷杉绿
                  case 'moss_forest': baseColor = 0x4a7858; break;  // 苔藓林 - 苔绿
                  case 'cloud_forest': baseColor = 0x3a6858; break; // 云雾林 - 雾林蓝绿
                  
                  // 草地类 (6种)
                  case 'savanna': baseColor = 0xc8d060; break;      // 稀树草原 - 黄绿
                  case 'grassland': baseColor = 0xa8d068; break;    // 草原 - 明亮草绿
                  case 'meadow': baseColor = 0x90c878; break;       // 草甸 - 草甸绿
                  case 'alpine_meadow': baseColor = 0x8cb878; break;// 高山草甸 - 冷草绿
                  case 'tundra': baseColor = 0x7a9e8a; break;       // 苔原 - 灰绿
                  case 'scrub': baseColor = 0x6a9a58; break;        // 灌木丛 - 灌木绿
                  
                  // 湿地类 (5种)
                  case 'swamp': baseColor = 0x3d5a45; break;        // 沼泽 - 深沼泽绿
                  case 'wetland': baseColor = 0x4a6a50; break;      // 湿地 - 湿地绿
                  case 'peatland': baseColor = 0x5a5a48; break;     // 泥炭地 - 泥炭褐绿
                  case 'mangrove': baseColor = 0x3a5840; break;     // 红树林 - 红树林绿
                  
                  // 草地默认
                  case 'grass': baseColor = 0xa8d068; break;        // 草地 - 草绿
                  default: baseColor = 0x4caf50;                     // 标准绿
              }
              
              // Number of blobs based on density and vegetation type
              let blobMultiplier = 5;
              if (info.type === 'rainforest' || info.type === 'cloud_forest') blobMultiplier = 8;
              else if (info.type === 'evergreen' || info.type === 'forest') blobMultiplier = 7;
              else if (info.type === 'savanna' || info.type === 'scrub' || info.type === 'tundra') blobMultiplier = 3;
              else if (info.type === 'grassland' || info.type === 'meadow') blobMultiplier = 4;
              
              const blobs = Math.ceil(info.density * blobMultiplier); // 1-8 blobs per tile
              
              for (let i = 0; i < blobs; i++) {
                  const sprite = new Sprite(blobTexture);
                  sprite.anchor.set(0.5);
                  
                  // Random offset within hex (approx radius 15)
                  // Deterministic based on ID and index
                  const seed = tileId * 17 + i * 31;
                  const angle = (seed % 360) * Math.PI / 180;
                  const dist = (seed % 15);
                  
                  sprite.x = pos.x + Math.cos(angle) * dist;
                  sprite.y = pos.y + Math.sin(angle) * dist;
                  
                  // Random scale
                  const scale = 0.8 + ((seed % 50) / 100);
                  sprite.scale.set(scale);
                  
                  sprite.tint = baseColor;
                  
                  // Alpha: varies by vegetation type
                  let alphaBase = 0.6;
                  if (info.type === 'rainforest' || info.type === 'cloud_forest') alphaBase = 0.85;
                  else if (info.type === 'evergreen' || info.type === 'swamp') alphaBase = 0.75;
                  else if (info.type === 'forest' || info.type === 'mixed') alphaBase = 0.70;
                  else if (info.type === 'savanna' || info.type === 'tundra') alphaBase = 0.50;
                  else if (info.type === 'scrub' || info.type === 'meadow') alphaBase = 0.55;
                  
                  sprite.alpha = alphaBase + info.density * 0.2; 
                  
                  vegContainer.addChild(sprite);
              }
          }
          container.addChild(vegContainer);
      }
      
      // D. Habitat Indicator Layer (生物栖息标记)
      // 柔和方案：默认用小圆点，只有选中物种时才高亮
      const habitatContainer = new Container();
      
      // 创建小圆点纹理（默认状态，低调不刺眼）
      const dotG = new Graphics();
      dotG.circle(0, 0, 4);
      dotG.fill({ color: 0xffffff, alpha: 1.0 });
      const dotTexture = app.renderer.generateTexture({
        target: dotG,
        resolution: 2,
        antialias: true,
      });
      
      // 创建高亮圆环纹理（选中物种时使用）
      const ringG = new Graphics();
      ringG.circle(0, 0, 10);
      ringG.stroke({ color: 0xffffff, width: 2.5, alpha: 1.0 });
      ringG.circle(0, 0, 6);
      ringG.fill({ color: 0xffffff, alpha: 0.8 });
      const ringTexture = app.renderer.generateTexture({
        target: ringG,
        resolution: 2,
        antialias: true,
      });
      
      // 计算每个地块的物种数量
      const localTileSpeciesCount = new Map<number, number>();
      if (map.habitats) {
        for (const hab of map.habitats) {
          const current = localTileSpeciesCount.get(hab.tile_id) || 0;
          localTileSpeciesCount.set(hab.tile_id, current + 1);
        }
      }
      
      map.tiles.forEach(tile => {
        const pos = layout.positions.get(tile.id);
        if (!pos) return;
        
        const speciesCount = localTileSpeciesCount.get(tile.id) || 0;
        if (speciesCount === 0) return;
        
        // 默认圆点（低调）
        const dot = new Sprite(dotTexture);
        dot.anchor.set(0.5);
        dot.position.set(pos.x, pos.y);
        
        // 高亮圆环（选中物种时显示）
        const ring = new Sprite(ringTexture);
        ring.anchor.set(0.5);
        ring.position.set(pos.x, pos.y);
        ring.visible = false; // 默认隐藏
        
        // 默认状态：柔和的颜色，根据物种数量调整
        const baseScale = Math.min(1.0, 0.6 + speciesCount * 0.08);
        dot.scale.set(baseScale);
        ring.scale.set(1.0);
        
        // 默认使用柔和的绿色系，低透明度
        if (speciesCount >= 5) {
          dot.tint = 0x4caf50; // 中绿
        } else if (speciesCount >= 3) {
          dot.tint = 0x66bb6a; // 浅绿
        } else if (speciesCount >= 2) {
          dot.tint = 0x81c784; // 更浅绿
        } else {
          dot.tint = 0x90a4ae; // 灰蓝色，最低调
        }
        dot.alpha = 0.5; // 低透明度，不刺眼
        
        habitatContainer.addChild(dot);
        habitatContainer.addChild(ring);
        
        // 存储格式: [dot, ring] 对
        if (!habitatIndicatorsRef.current.has(tile.id)) {
          habitatIndicatorsRef.current.set(tile.id, []);
        }
        habitatIndicatorsRef.current.get(tile.id)!.push(dot, ring);
      });
      
      container.addChild(habitatContainer);
      
      console.log(`[CanvasMapPanel] 创建世界容器 offset=${offsetX}, sprites=${createdCount}`);
      return container;
    };

    const left = createWorldContainer(-layout.worldWidth);
    const center = createWorldContainer(0);
    const right = createWorldContainer(layout.worldWidth);
    
    worldLayer.addChild(left, center, right);
    worldLayer.visible = true;
    worldLayer.alpha = 1.0;
    
    console.log('[CanvasMapPanel] 世界层设置完成');
  }, []);

  // Initialize Pixi App and Create Sprites (合并为一个 useEffect)
  useEffect(() => {
    console.log('[CanvasMapPanel] 主 useEffect 触发', {
      hasContainer: !!containerRef.current,
      hasApp: !!appRef.current,
      hasLayout: !!layout,
      hasMap: !!map,
      mapTilesCount: map?.tiles?.length
    });
    
    if (!containerRef.current) {
      console.warn('[CanvasMapPanel] containerRef.current 为空');
      return;
    }
    
    if (!layout || !map) {
      console.warn('[CanvasMapPanel] 等待 layout 或 map 加载');
      return;
    }
    
    // 如果 app 已经存在，直接创建/更新 Sprites
    if (appRef.current && worldLayerRef.current) {
      console.log('[CanvasMapPanel] PixiJS 应用已存在，创建/更新 Sprites');
      createSprites(appRef.current, layout, map);
      return;
    }

    // 防止重复初始化
    if (appRef.current && !worldLayerRef.current) {
      console.warn('[CanvasMapPanel] App 存在但 worldLayer 不存在，跳过');
      return;
    }

    // 首次初始化：创建 PixiJS 应用
    let mounted = true;
    
    const initPixi = async () => {
      console.log('[CanvasMapPanel] 开始初始化 PixiJS...');
      const app = new Application();
      await app.init({ 
        background: '#030510', 
        resizeTo: containerRef.current!,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
        preference: 'webgl',
      });
      
      if (!mounted) {
        console.log('[CanvasMapPanel] 组件已卸载，取消初始化');
        app.destroy(true);
        return;
      }
      
      console.log('[CanvasMapPanel] PixiJS 应用初始化完成');
      
      if (containerRef.current) {
        containerRef.current.appendChild(app.canvas);
        console.log('[CanvasMapPanel] Canvas 已添加到 DOM');
      }
      appRef.current = app;

      // Layers
      const worldLayer = new Container();
      const selectionLayer = new Container();
      app.stage.addChild(worldLayer, selectionLayer);
      worldLayerRef.current = worldLayer;
      selectionLayerRef.current = selectionLayer;

      // Animation Loop
      let time = 0;
      app.ticker.add((ticker) => {
        time += ticker.deltaTime;
        
        // Pulse effect for hover (subtle brightness/alpha)
        if (hoverGraphicsRef.current) {
           hoverGraphicsRef.current.alpha = 0.5 + Math.sin(time * 0.04) * 0.1;
        }
        
        // Stronger pulse for selection
        if (selectGraphicsRef.current) {
           selectGraphicsRef.current.alpha = 0.7 + Math.sin(time * 0.06) * 0.15;
        }
        
        // 只对选中物种的高亮圆环添加脉动效果
        if (habitatIndicatorsRef.current.size > 0) {
          const pulse = Math.sin(time * 0.06) * 0.1;
          const scalePulse = 1 + Math.sin(time * 0.06) * 0.08;
          
          habitatIndicatorsRef.current.forEach((sprites) => {
            for (let i = 0; i < sprites.length; i += 2) {
              const ring = sprites[i + 1]; // ring 是第二个元素
              if (ring && ring.visible) {
                // 只有可见的高亮圆环才脉动
                ring.alpha = 0.85 + pulse;
                ring.scale.set(1.2 * scalePulse);
              }
            }
          });
        }
      });

      // Initial Graphics for Selection/Hover
      const hoverG = new Graphics();
      const selectG = new Graphics();
      selectionLayer.addChild(hoverG, selectG);
      hoverGraphicsRef.current = hoverG;
      selectGraphicsRef.current = selectG;
      
      console.log('[CanvasMapPanel] 图层和 Graphics 对象已创建');
      
      // 创建 Sprites
      if (mounted && worldLayerRef.current) {
        createSprites(app, layout, map);
      }
    };

    initPixi();

    return () => {
      mounted = false;
      if (appRef.current) {
        console.log('[CanvasMapPanel] 清理 PixiJS 应用');
        appRef.current.destroy(true, { children: true, texture: true });
        appRef.current = null;
        worldLayerRef.current = null;
        selectionLayerRef.current = null;
        hoverGraphicsRef.current = null;
        selectGraphicsRef.current = null;
        tileSpritesRef.current.clear();
        habitatIndicatorsRef.current.clear();
      }
    };
  }, [layout, map, createSprites]); // 依赖 layout, map 和 createSprites

  // Update Tints
  useEffect(() => {
    if (!tileSpritesRef.current.size) return;
    if (!map) return;

    map.tiles.forEach(tile => {
      const sprites = tileSpritesRef.current.get(tile.id);
      if (!sprites) return;
      
      let color = 0x1f2937;
      
      if (viewMode === "suitability") {
        if (highlightSpeciesId) {
          const suitColor = suitabilityColors.get(tile.id);
          if (suitColor !== undefined) {
            color = suitColor;
          } else {
             // darker for non-suitable
             color = 0x1f2937; 
          }
        } else {
           color = 0x1f2937;
        }
      } else {
        color = stringColorToHex(tile.color || "#1f2937");
      }

      // Update all 3 copies
      for (const sprite of sprites) {
        sprite.tint = color;
        // Text Logic? For Terrain Type view mode, simple tints might not be enough if we want text.
        // For now, we skip text rendering in Pixi for perf, or we could use BitmapText.
        // Given the user wants GPU perf, let's stick to colors. 
      }
    });

  }, [map, viewMode, highlightSpeciesId, suitabilityColors]);

  // Update Habitat Indicators - 每个 tile 存储 [dot, ring] 对
  useEffect(() => {
    if (!habitatIndicatorsRef.current.size) return;
    
    habitatIndicatorsRef.current.forEach((sprites, tileId) => {
      const speciesCount = habitatInfo.tileSpeciesCount.get(tileId) || 0;
      const hasHighlighted = habitatInfo.tileHasHighlighted.get(tileId) || false;
      
      // sprites 格式: [dot1, ring1, dot2, ring2, ...] (每个世界副本两个)
      for (let i = 0; i < sprites.length; i += 2) {
        const dot = sprites[i];
        const ring = sprites[i + 1];
        if (!dot || !ring) continue;
        
        if (hasHighlighted) {
          // 选中物种所在地块 - 显示醒目的高亮圆环
          dot.visible = false;
          ring.visible = true;
          ring.tint = 0x00e5ff; // 亮青色
          ring.alpha = 0.95;
          ring.scale.set(1.2);
        } else {
          // 普通状态 - 只显示柔和的小圆点
          dot.visible = true;
          ring.visible = false;
          
          // 根据物种数量调整颜色深浅
          if (speciesCount >= 5) {
            dot.tint = 0x4caf50;
            dot.alpha = 0.6;
          } else if (speciesCount >= 3) {
            dot.tint = 0x66bb6a;
            dot.alpha = 0.5;
          } else if (speciesCount >= 2) {
            dot.tint = 0x81c784;
            dot.alpha = 0.45;
          } else {
            dot.tint = 0x90a4ae;
            dot.alpha = 0.4;
          }
          const baseScale = Math.min(1.0, 0.6 + speciesCount * 0.08);
          dot.scale.set(baseScale);
        }
      }
    });
  }, [habitatInfo]);

  // Camera Loop
  const updateCamera = useCallback(() => {
    if (!appRef.current || !worldLayerRef.current || !layout || !selectionLayerRef.current) return;

    const { x, y, zoom } = cameraRef.current;
    const worldLayer = worldLayerRef.current;
    const selectionLayer = selectionLayerRef.current;

    // Wrapping
    const W = layout.worldWidth * zoom;
    let effectiveX = x;
    while (effectiveX > 0) effectiveX -= W;
    while (effectiveX < -W) effectiveX += W;
    
    // Apply to layers
    worldLayer.position.set(effectiveX, y);
    worldLayer.scale.set(zoom);
    
    selectionLayer.position.set(effectiveX, y);
    selectionLayer.scale.set(zoom);
    
  }, [layout]);

  useImperativeHandle(
    ref,
    () => ({
      getCameraState: () => ({ ...cameraRef.current }),
      setCameraState: (state: CameraState) => {
        cameraRef.current = { ...state };
        updateCamera();
      },
    }),
    [updateCamera]
  );

  // Inertia Loop
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
    
    // Bounds check Y
    if (layout && containerRef.current) {
      const { height } = containerRef.current.getBoundingClientRect();
      const { y, zoom } = cameraRef.current;
      const worldH = layout.worldHeight;
      const margin = height * 0.2;
      const minY = height - worldH * zoom - margin;
      const maxY = margin;
      
      if (y < minY) { cameraRef.current.y = minY; v.y = 0; }
      if (y > maxY) { cameraRef.current.y = maxY; v.y = 0; }
    }
    
    updateCamera();
    inertiaReqRef.current = requestAnimationFrame(updateInertia);
  }, [layout, updateCamera]);

  // Initial positioning
  useEffect(() => {
    if (layout && containerRef.current && cameraRef.current.x === 0) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        cameraRef.current.x = (width - layout.worldWidth) / 2;
        cameraRef.current.y = (height - layout.worldHeight) / 2;
        
        console.log('[CanvasMapPanel] 初始相机位置:', {
          camera: cameraRef.current,
          container: { width, height },
          world: { width: layout.worldWidth, height: layout.worldHeight }
        });
        
        updateCamera();
    }
  }, [layout, updateCamera]);
  
  // Draw Selection/Hover Graphics
  useEffect(() => {
    const gH = hoverGraphicsRef.current;
    const gS = selectGraphicsRef.current;
    if (!gH || !gS || !layout) return;

    // Clear
    gH.clear();
    gS.clear();
    
    const drawHex = (g: Graphics, tileId: number, color: number, width: number, alpha: number) => {
       const pos = layout.positions.get(tileId);
       if (!pos) return;
       
       // We need to draw it 3 times for wrapping
       const offsets = [0, -layout.worldWidth, layout.worldWidth];
       const w2 = HEX_WIDTH / 2;
       const h2 = HEX_HEIGHT / 2;
       const w4 = HEX_WIDTH / 4;
       
       offsets.forEach(offsetX => {
           const cx = pos.x + offsetX;
           const cy = pos.y;
           
           // Draw hexagon outline using PixiJS v8 API
           g.poly([
             cx + w2, cy,
             cx + w4, cy - h2,
             cx - w4, cy - h2,
             cx - w2, cy,
             cx - w4, cy + h2,
             cx + w4, cy + h2,
             cx + w2, cy
           ]);
       });
       
       g.stroke({ width, color, alpha });
    };

    if (hoveredTile && hoveredTile.id !== selectedTile?.id) {
        drawHex(gH, hoveredTile.id, HOVER_STROKE_COLOR, 2, HOVER_STROKE_ALPHA);
    }

    if (selectedTile) {
        drawHex(gS, selectedTile.id, SELECTED_STROKE_COLOR, SELECTED_STROKE_WIDTH, 1);
    }

  }, [hoveredTile, selectedTile, layout]);

  // Input Handlers (Keep existing math logic)
  const getTileAtScreenPos = (clientX: number, clientY: number) => {
    if (!containerRef.current || !layout) return null;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const { x: camX, y: camY, zoom } = cameraRef.current;
    
    // Pixi Logic: 
    // WorldPos = (ScreenPos - CamPos) / Zoom
    // BUT: CamPos in my logic includes the wrapping offset (effectiveX).
    
    const W = layout.worldWidth * zoom;
    let effectiveX = camX;
    while (effectiveX > 0) effectiveX -= W;
    while (effectiveX < -W) effectiveX += W;

    const rawWorldX = (x - effectiveX) / zoom;
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
        
        // Bounds Check
        if (layout && containerRef.current) {
          const { height } = containerRef.current.getBoundingClientRect();
          const { y, zoom } = cameraRef.current;
          const worldH = layout.worldHeight;
          const margin = height * 0.2;
          const minY = height - worldH * zoom - margin;
          const maxY = margin;
          
          if (y < minY) cameraRef.current.y = minY;
          if (y > maxY) cameraRef.current.y = maxY;
        }

        updateCamera();
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

  // Handle Wheel (zoom) with passive: false
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    
    const handleWheelNative = (e: WheelEvent) => {
      e.preventDefault();
      if (inertiaReqRef.current) {
        cancelAnimationFrame(inertiaReqRef.current);
        inertiaReqRef.current = undefined;
      }
      
      const zoomSensitivity = 0.001;
      const delta = -e.deltaY * zoomSensitivity;
      const prevZoom = cameraRef.current.zoom;
      
      // Calculate dynamic limits based on screen size
      const rect = containerRef.current?.getBoundingClientRect();
      let minZoom = 0.2;
      if (rect && layout) {
        const fitX = rect.width / layout.worldWidth;
        const fitY = rect.height / layout.worldHeight;
        // Ensure minZoom isn't too small, but allows seeing full map with some margin
        minZoom = Math.max(0.2, Math.min(fitX, fitY) * 0.9); 
      }
      
      const newZoom = Math.max(minZoom, Math.min(3.0, prevZoom + delta));
      
      if (!rect) return;
      
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      
      // Calculate current effective cam
      const W = layout ? layout.worldWidth * prevZoom : 0;
      let effectiveX = cameraRef.current.x;
      if (W > 0) {
          while (effectiveX > 0) effectiveX -= W;
          while (effectiveX < -W) effectiveX += W;
      }

      const worldX = (mouseX - effectiveX) / prevZoom;
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

      updateCamera();
    };
    
    node.addEventListener("wheel", handleWheelNative, { passive: false });
    return () => node.removeEventListener("wheel", handleWheelNative);
  }, [layout, updateCamera]);

  // Handle Resize
  useEffect(() => {
    const handleResize = () => {
        if (appRef.current && containerRef.current) {
             // PixiJS v8: renderer.resize() 而不是 app.resize()
             const { width, height } = containerRef.current.getBoundingClientRect();
             appRef.current.renderer.resize(width, height);
             updateCamera();
        }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [updateCamera]);

  return (
    <div className="map-surface" style={{ padding: 0, position: "relative" }}>
      {!map ? (
        <div className="h-full flex flex-col items-center justify-center text-muted space-y-4">
          <div className="spinner w-8 h-8 border-t-primary border-4"></div>
          <p className="text-sm tracking-widest uppercase opacity-70">Initializing GPU Map...</p>
        </div>
      ) : (
        <div 
          ref={containerRef} 
          style={{ width: "100%", height: "100%", overflow: "hidden", cursor: isDragging.current ? "grabbing" : "default" }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={handleClick}
        />
      )}
    </div>
  );
});

function stringColorToHex(color: string): number {
  if (color.startsWith("#")) {
    const hex = parseInt(color.replace("#", ""), 16);
    return hex;
  }
  if (color.startsWith("rgb")) {
    // rgb(r, g, b)
    const parts = color.match(/\d+/g);
    if (parts && parts.length >= 3) {
      const r = parseInt(parts[0]);
      const g = parseInt(parts[1]);
      const b = parseInt(parts[2]);
      return (r << 16) + (g << 8) + b;
    }
  }
  // 默认返回白色
  console.warn('[stringColorToHex] 无法解析颜色:', color);
  return 0xffffff;
}
