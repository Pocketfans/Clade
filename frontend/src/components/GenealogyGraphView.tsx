import { useEffect, useRef, useState, useCallback } from "react";
import { Application, Container, Graphics, Text, BlurFilter, FederatedPointerEvent } from "pixi.js";
import * as d3 from "d3";
import type { LineageNode } from "../services/api.types";

interface Props {
  nodes: LineageNode[];
  spacingX?: number;
  spacingY?: number;
  onNodeClick?: (node: LineageNode) => void;
}

// Enhanced Colors
const COLORS = {
  ALIVE: 0x22c55e,       // Green
  EXTINCT: 0xef4444,     // Red
  BACKGROUND: 0x4b5563,  // Gray
  PRODUCER: 0x10b981,    // Emerald
  HERBIVORE: 0xfbbf24,   // Amber
  CARNIVORE: 0xf43f5e,   // Rose
  OMNIVORE: 0xf97316,    // Orange
  DEFAULT: 0xffffff,
  SELECTED: 0x3b82f6,    // Blue
  SUBSPECIES: 0x8b5cf6,  // Violet
  HYBRID: 0xd946ef,      // Fuchsia
  TEXT_MAIN: 0xffffff,
  TEXT_SUB: 0x9ca3af,
  LINK_NORMAL: 0x475569, // Slate-600
  LINK_ACTIVE: 0x94a3b8, // Slate-400
  ROOT_GOLD: 0xfbbf24,   // Gold for root
  ROOT_GLOW: 0xf59e0b,   // Amber glow
  COLLAPSE_BTN: 0x64748b,
  COLLAPSE_BTN_HOVER: 0x94a3b8,
};

interface NodeVisual {
    container: Container;
    innerGroup: Container; 
    border: Graphics;
    shadow: Graphics;
    collapseBtn?: Container;
    
    baseX: number;
    baseY: number;
    
    targetX: number;
    targetY: number; 
    
    targetLift: number;
    targetScale: number;
    targetShadowAlpha: number;
    targetShadowScale: number;
    
    hasChildren: boolean;
    lineageCode: string;
}

interface LinkVisual {
    graphics: Graphics;
    sourceCode: string;
    targetCode: string;
    type: 'solid' | 'dashed';
    color: number;
    alpha: number;
    width: number;
}

interface FlowParticle {
  t: number;
  speed: number;
  linkVisual: LinkVisual; 
  graphics: Graphics;
  color: number;
}

// ROOT常量
const ROOT_NAME = "始祖物种";
const ROOT_CODE = "ROOT";

export function GenealogyGraphView({ nodes, spacingX = 200, spacingY = 85, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  
  const appRef = useRef<Application | null>(null);
  const stageRef = useRef<Container | null>(null);
  
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<LineageNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [pixiReady, setPixiReady] = useState(false);
  
  // 折叠状态管理
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set());

  const cameraRef = useRef({ x: 100, y: 300, zoom: 0.8 }); 
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const currentMousePos = useRef({ x: 0, y: 0 });
  
  const particlesRef = useRef<FlowParticle[]>([]);
  const nodeVisualsRef = useRef<Map<string, NodeVisual>>(new Map());
  const linkVisualsRef = useRef<LinkVisual[]>([]);

  // 切换折叠状态
  const toggleCollapse = useCallback((lineageCode: string) => {
    setCollapsedNodes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(lineageCode)) {
        newSet.delete(lineageCode);
      } else {
        newSet.add(lineageCode);
      }
      return newSet;
    });
  }, []);

  // 重置视图
  const resetView = useCallback(() => {
    if (stageRef.current) {
      cameraRef.current = { x: 100, y: 300, zoom: 0.8 };
      stageRef.current.position.set(100, 300);
      stageRef.current.scale.set(0.8);
    }
  }, []);

  // 缩放控制
  const zoomIn = useCallback(() => {
    if (stageRef.current) {
      const newZoom = Math.min(5, cameraRef.current.zoom * 1.2);
      cameraRef.current.zoom = newZoom;
      stageRef.current.scale.set(newZoom);
    }
  }, []);

  const zoomOut = useCallback(() => {
    if (stageRef.current) {
      const newZoom = Math.max(0.1, cameraRef.current.zoom / 1.2);
      cameraRef.current.zoom = newZoom;
      stageRef.current.scale.set(newZoom);
    }
  }, []);

  // 展开全部
  const expandAll = useCallback(() => {
    setCollapsedNodes(new Set());
  }, []);

  // 折叠全部
  const collapseAll = useCallback(() => {
    const nodesWithChildren = nodes.filter(n => 
      nodes.some(c => c.parent_code === n.lineage_code)
    ).map(n => n.lineage_code);
    setCollapsedNodes(new Set(nodesWithChildren));
  }, [nodes]);

  // Init Pixi
  useEffect(() => {
    if (!canvasContainerRef.current) return;
    if (appRef.current) return;

    const initPixi = async () => {
      const container = canvasContainerRef.current;
      if (!container) return;

      const app = new Application();
      
      try {
        await app.init({ 
          background: '#0a0f1a', 
          resizeTo: container,
          antialias: true,
          resolution: window.devicePixelRatio || 1,
          autoDensity: true,
        });

        appRef.current = app;
        stageRef.current = app.stage;
        app.stage.eventMode = 'static';
        
        app.stage.position.set(cameraRef.current.x, cameraRef.current.y);
        app.stage.scale.set(cameraRef.current.zoom);

        if (container.firstChild) container.removeChild(container.firstChild);
        container.appendChild(app.canvas);
        app.canvas.style.display = 'block';
        app.canvas.style.width = '100%';
        app.canvas.style.height = '100%';

        const resizeObserver = new ResizeObserver(() => app.resize());
        resizeObserver.observe(container);

        const canvas = app.canvas;
        
        const onWheel = (e: WheelEvent) => {
            e.preventDefault();
            const stage = app.stage;
            
            const zoomSensitivity = 0.001;
            const delta = -e.deltaY * zoomSensitivity;
            const oldZoom = cameraRef.current.zoom;
            const newZoom = Math.max(0.1, Math.min(5, oldZoom + delta));
            
            const rect = container.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            const worldX = (mouseX - cameraRef.current.x) / oldZoom;
            const worldY = (mouseY - cameraRef.current.y) / oldZoom;
            
            const newCamX = mouseX - worldX * newZoom;
            const newCamY = mouseY - worldY * newZoom;
            
            cameraRef.current = { x: newCamX, y: newCamY, zoom: newZoom };
            stage.position.set(newCamX, newCamY);
            stage.scale.set(newZoom);
        };
        
        const onMouseDown = (e: MouseEvent) => {
            isDragging.current = true;
            lastMousePos.current = { x: e.clientX, y: e.clientY };
            window.addEventListener('mousemove', onMouseMove);
            window.addEventListener('mouseup', onMouseUp);
        };
        
        const onMouseMove = (e: MouseEvent) => {
            const rect = container.getBoundingClientRect();
            currentMousePos.current = { 
                x: e.clientX - rect.left, 
                y: e.clientY - rect.top 
            };

            if (isDragging.current) {
                const dx = e.clientX - lastMousePos.current.x;
                const dy = e.clientY - lastMousePos.current.y;
                
                cameraRef.current.x += dx;
                cameraRef.current.y += dy;
                
                stageRef.current?.position.set(cameraRef.current.x, cameraRef.current.y);
                lastMousePos.current = { x: e.clientX, y: e.clientY };
            }
        };
        
        const onMouseUp = () => {
            isDragging.current = false;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        canvas.addEventListener('wheel', onWheel, { passive: false });
        canvas.addEventListener('mousedown', onMouseDown);
        container.addEventListener('mousemove', (e) => {
             const rect = container.getBoundingClientRect();
             currentMousePos.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        });
        
        app.ticker.add((ticker) => {
            const dt = ticker.deltaTime;
            updateNodeAnimations(dt);
            updateLinks();
            updateParticles(dt);
        });

        setPixiReady(true);
        
        (app as any)._cleanup = () => {
             resizeObserver.disconnect();
             canvas.removeEventListener('wheel', onWheel);
             canvas.removeEventListener('mousedown', onMouseDown);
             window.removeEventListener('mousemove', onMouseMove);
             window.removeEventListener('mouseup', onMouseUp);
        };

      } catch (err) {
        console.error("Pixi init failed", err);
      }
    };

    initPixi();

    return () => {
      if (appRef.current) {
        if ((appRef.current as any)._cleanup) (appRef.current as any)._cleanup();
        appRef.current.destroy({ removeView: true });
        appRef.current = null;
        setPixiReady(false);
      }
    };
  }, []);

  // Animation Logic - 保持不变
  const updateNodeAnimations = (delta: number) => {
      const lerp = 0.15 * delta; 
      const magneticStrength = 0.15;
      const magneticRange = 80;
      const maxDisplacement = 20;
      
      const zoom = cameraRef.current.zoom;
      const camX = cameraRef.current.x;
      const camY = cameraRef.current.y;
      const mouseWorldX = (currentMousePos.current.x - camX) / zoom;
      const mouseWorldY = (currentMousePos.current.y - camY) / zoom;

      nodeVisualsRef.current.forEach((vis) => {
          const dx = mouseWorldX - vis.baseX;
          const dy = mouseWorldY - vis.baseY;
          const distSq = dx*dx + dy*dy;
          
          let magX = 0;
          let magY = 0;
          
          if (distSq < magneticRange * magneticRange) {
              const dist = Math.sqrt(distSq);
              const factor = (1 - dist / magneticRange) * magneticStrength;
              magX = dx * factor;
              magY = dy * factor;
              
              const dispLen = Math.sqrt(magX*magX + magY*magY);
              if (dispLen > maxDisplacement) {
                  const ratio = maxDisplacement / dispLen;
                  magX *= ratio;
                  magY *= ratio;
              }
          }

          const destX = vis.targetX + magX;
          const destY = vis.targetY + magY;

          vis.container.x += (destX - vis.container.x) * lerp;
          vis.container.y += (destY - vis.container.y) * lerp;
          
          vis.innerGroup.y += (vis.targetLift - vis.innerGroup.y) * lerp;
          
          vis.innerGroup.scale.x += (vis.targetScale - vis.innerGroup.scale.x) * lerp;
          vis.innerGroup.scale.y += (vis.targetScale - vis.innerGroup.scale.y) * lerp;
          
          vis.shadow.alpha += (vis.targetShadowAlpha - vis.shadow.alpha) * lerp;
          vis.shadow.scale.x += (vis.targetShadowScale - vis.shadow.scale.x) * lerp;
          vis.shadow.scale.y += (vis.targetShadowScale - vis.shadow.scale.y) * lerp;
      });
  };

  const updateLinks = () => {
      const NODE_W = 140;
      const NODE_OFFSET_X = NODE_W / 2;
      
      linkVisualsRef.current.forEach(link => {
          const sourceVis = nodeVisualsRef.current.get(link.sourceCode);
          const targetVis = nodeVisualsRef.current.get(link.targetCode);
          
          if (!sourceVis || !targetVis) return;
          
          link.graphics.clear();
          
          const p0 = { x: sourceVis.container.x + NODE_OFFSET_X, y: sourceVis.container.y };
          const p3 = { x: targetVis.container.x - NODE_OFFSET_X, y: targetVis.container.y };
          
          const cpOffset = (p3.x - p0.x) * 0.5;
          const p1 = { x: p0.x + cpOffset, y: p0.y };
          const p2 = { x: p3.x - cpOffset, y: p3.y };
          
          if (link.type === 'dashed') {
              drawDashedBezier(link.graphics, p0, p1, p2, p3, link.color, link.alpha, link.width);
          } else {
              link.graphics.moveTo(p0.x, p0.y);
              link.graphics.bezierCurveTo(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
              link.graphics.stroke({ width: link.width, color: link.color, alpha: link.alpha });
          }
      });
  };

  const updateParticles = (delta: number) => {
     const NODE_W = 140;
     const NODE_OFFSET_X = NODE_W / 2;
     
     const particles = particlesRef.current;
     for (let i = particles.length - 1; i >= 0; i--) {
         const p = particles[i];
         p.t += p.speed * delta;
         if (p.t >= 1) p.t = 0;
         
         const sourceVis = nodeVisualsRef.current.get(p.linkVisual.sourceCode);
         const targetVis = nodeVisualsRef.current.get(p.linkVisual.targetCode);
         
         if (sourceVis && targetVis) {
             const p0 = { x: sourceVis.container.x + NODE_OFFSET_X, y: sourceVis.container.y };
             const p3 = { x: targetVis.container.x - NODE_OFFSET_X, y: targetVis.container.y };
             const cpOffset = (p3.x - p0.x) * 0.5;
             const p1 = { x: p0.x + cpOffset, y: p0.y };
             const p2 = { x: p3.x - cpOffset, y: p3.y };
             
             const pos = getPointOnBezier(p.t, p0, p1, p2, p3);
             p.graphics.position.set(pos.x, pos.y);
             p.graphics.alpha = Math.sin(p.t * Math.PI); 
         }
     }
  };

  // Build Graph with Collapse Support
  useEffect(() => {
    if (!pixiReady || !appRef.current || !stageRef.current) return;
    
    const stage = stageRef.current;
    
    stage.removeChildren();
    particlesRef.current = [];
    nodeVisualsRef.current.clear();
    linkVisualsRef.current = [];
    
    if (nodes.length === 0) {
        const text = new Text({ text: "等待物种数据...", style: { fill: 0x64748b, fontSize: 24, fontFamily: 'system-ui, sans-serif' } });
        text.anchor.set(0.5);
        stage.addChild(text);
        return;
    }

    // 绘制背景网格
    const gridLayer = new Container();
    const gridG = new Graphics();
    gridG.alpha = 0.03;
    const gridSize = 50;
    const gridExtent = 5000;
    for (let x = -gridExtent; x <= gridExtent; x += gridSize) {
        gridG.moveTo(x, -gridExtent);
        gridG.lineTo(x, gridExtent);
        gridG.stroke({ width: 1, color: 0xffffff });
    }
    for (let y = -gridExtent; y <= gridExtent; y += gridSize) {
        gridG.moveTo(-gridExtent, y);
        gridG.lineTo(gridExtent, y);
        gridG.stroke({ width: 1, color: 0xffffff });
    }
    gridLayer.addChild(gridG);
    stage.addChild(gridLayer);

    // 过滤出需要显示的节点（考虑折叠状态）
    const visibleNodes = getVisibleNodes(nodes, collapsedNodes);
    
    const root = buildHierarchy(visibleNodes, nodes);
    const treeLayout = d3.tree<LineageNode>()
      .nodeSize([spacingY, spacingX])
      .separation((a, b) => (a.parent === b.parent ? 1 : 1.2));
    
    const treeData = treeLayout(root);
    const descendants = treeData.descendants();
    const links = treeData.links();

    const linksLayer = new Container();
    const nodesLayer = new Container();
    const particleLayer = new Container();
    nodesLayer.sortableChildren = true; 
    
    stage.addChild(linksLayer);
    stage.addChild(particleLayer);
    stage.addChild(nodesLayer);
    
    // 预计算哪些节点有子节点
    const childrenCount = new Map<string, number>();
    nodes.forEach(n => {
      const parentCode = n.parent_code || ROOT_CODE;
      childrenCount.set(parentCode, (childrenCount.get(parentCode) || 0) + 1);
    });

    // 创建节点
    descendants.forEach(node => {
        const isRoot = node.data.lineage_code === ROOT_CODE;
        const hasChildren = (childrenCount.get(node.data.lineage_code) || 0) > 0;
        const isCollapsed = collapsedNodes.has(node.data.lineage_code);
        const hiddenChildCount = isCollapsed ? getHiddenDescendantCount(node.data.lineage_code, nodes, collapsedNodes) : 0;
        
        const nodeContainer = new Container();
        nodeContainer.position.set(node.y, node.x);
        
        nodeContainer.eventMode = 'static';
        nodeContainer.cursor = 'pointer';
        nodeContainer.on('pointerdown', (e: FederatedPointerEvent) => {
            e.stopPropagation();
            if (!isRoot) {
              setSelectedNode(node.data.lineage_code);
              onNodeClick?.(node.data);
            }
        });
        nodeContainer.on('pointerenter', (e: FederatedPointerEvent) => {
            if (!isRoot) {
              setHoveredNode(node.data);
              setTooltipPos({ x: e.global.x, y: e.global.y });
            }
        });
        nodeContainer.on('pointermove', (e: FederatedPointerEvent) => {
             if (hoveredNode === node.data) {
                 setTooltipPos({ x: e.global.x, y: e.global.y });
             }
        });
        nodeContainer.on('pointerleave', () => setHoveredNode(null));

        const isAlive = node.data.state === 'alive';
        const roleColor = isRoot ? COLORS.ROOT_GOLD : getNodeColorHex(node.data);
        
        // Shadow
        const shadow = new Graphics();
        shadow.roundRect(-65, -18, 130, 36, 18); 
        shadow.fill({ color: 0x000000, alpha: 1 });
        shadow.filters = [new BlurFilter({ strength: 15, quality: 3 })]; 
        shadow.alpha = 0; 
        shadow.position.set(0, 15); 
        nodeContainer.addChild(shadow);

        const innerGroup = new Container();
        
        if (isRoot) {
            // 特殊的始祖物种节点样式
            const rootGlow = new Graphics();
            rootGlow.roundRect(-72, -25, 144, 50, 12);
            rootGlow.fill({ color: COLORS.ROOT_GOLD, alpha: 0.15 });
            rootGlow.filters = [new BlurFilter({ strength: 8, quality: 2 })];
            innerGroup.addChild(rootGlow);
            
            const rootBg = new Graphics();
            rootBg.roundRect(-70, -23, 140, 46, 10);
            rootBg.fill({ color: 0x1a1a2e, alpha: 0.95 });
            innerGroup.addChild(rootBg);
            
            const rootBorder = new Graphics();
            rootBorder.roundRect(-70, -23, 140, 46, 10);
            rootBorder.stroke({ width: 2, color: COLORS.ROOT_GOLD, alpha: 0.8 });
            innerGroup.addChild(rootBorder);
            
            // 装饰线条
            const deco1 = new Graphics();
            deco1.moveTo(-50, -15);
            deco1.lineTo(-30, -15);
            deco1.stroke({ width: 1, color: COLORS.ROOT_GOLD, alpha: 0.5 });
            deco1.moveTo(30, -15);
            deco1.lineTo(50, -15);
            deco1.stroke({ width: 1, color: COLORS.ROOT_GOLD, alpha: 0.5 });
            innerGroup.addChild(deco1);
            
            const TEXT_SCALE = 0.28;
            const nameText = new Text({
                text: ROOT_NAME,
                style: {
                    fontFamily: 'system-ui, sans-serif',
                    fontSize: 52,
                    fontWeight: 'bold',
                    fill: COLORS.ROOT_GOLD,
                }
            });
            nameText.scale.set(TEXT_SCALE);
            nameText.anchor.set(0.5, 0.5);
            nameText.position.set(0, 0);
            innerGroup.addChild(nameText);
            
            // 添加小图标
            const icon = new Graphics();
            icon.moveTo(0, -8);
            icon.lineTo(4, -4);
            icon.lineTo(0, 0);
            icon.lineTo(-4, -4);
            icon.closePath();
            icon.fill({ color: COLORS.ROOT_GOLD, alpha: 0.6 });
            icon.position.set(0, 16);
            icon.scale.set(0.8);
            innerGroup.addChild(icon);
            
        } else {
            // 普通节点样式
            const mask = new Graphics();
            mask.roundRect(-70, -22, 140, 44, 10);
            mask.fill(0xffffff);
            
            const bg = new Graphics();
            bg.rect(-70, -22, 140, 44);
            bg.fill({ color: 0x151c2c, alpha: 0.95 }); 
            
            // 左侧角色指示条
            const indicator = new Graphics();
            indicator.rect(-70, -22, 6, 44);
            indicator.fill({ color: roleColor });
            
            // 如果有被折叠的子节点，显示计数徽章
            if (isCollapsed && hiddenChildCount > 0) {
                const badge = new Graphics();
                badge.circle(60, -15, 10);
                badge.fill({ color: COLORS.SELECTED, alpha: 0.9 });
                innerGroup.addChild(badge);
                
                const badgeText = new Text({
                    text: `+${hiddenChildCount}`,
                    style: {
                        fontFamily: 'system-ui, sans-serif',
                        fontSize: 32,
                        fontWeight: 'bold',
                        fill: 0xffffff,
                    }
                });
                badgeText.scale.set(0.25);
                badgeText.anchor.set(0.5, 0.5);
                badgeText.position.set(60, -15);
                innerGroup.addChild(badgeText);
            }
            
            const contentContainer = new Container();
            contentContainer.addChild(bg);
            contentContainer.addChild(indicator);
            contentContainer.mask = mask;
            
            innerGroup.addChild(mask);
            innerGroup.addChild(contentContainer);
            
            const border = new Graphics();
            border.roundRect(-70, -22, 140, 44, 10);
            border.stroke({ 
                width: 1.5, 
                color: isAlive ? roleColor : COLORS.EXTINCT,
                alpha: isAlive ? 0.8 : 0.4 
            });
            innerGroup.addChild(border);
            
            // 状态指示灯
            const statusDot = new Graphics();
            statusDot.circle(55, 0, 4);
            statusDot.fill({ color: isAlive ? COLORS.ALIVE : COLORS.EXTINCT, alpha: isAlive ? 1 : 0.6 });
            if (isAlive) {
                const statusGlow = new Graphics();
                statusGlow.circle(55, 0, 6);
                statusGlow.fill({ color: COLORS.ALIVE, alpha: 0.3 });
                innerGroup.addChild(statusGlow);
            }
            innerGroup.addChild(statusDot);

            const TEXT_SCALE = 0.25;
            const nameText = new Text({
                text: node.data.lineage_code,
                style: {
                    fontFamily: 'JetBrains Mono, Monaco, Consolas, monospace',
                    fontSize: 56,
                    fontWeight: 'bold',
                    fill: isAlive ? COLORS.TEXT_MAIN : 0x64748b,
                }
            });
            nameText.scale.set(TEXT_SCALE);
            nameText.anchor.set(0, 0.5);
            nameText.position.set(-58, -6);
            
            const commonName = node.data.common_name || "未知物种";
            const displayName = commonName.length > 10 ? commonName.substring(0, 9) + '..' : commonName;
            const subText = new Text({
                text: displayName,
                style: {
                    fontFamily: 'system-ui, sans-serif',
                    fontSize: 40,
                    fill: COLORS.TEXT_SUB,
                }
            });
            subText.scale.set(TEXT_SCALE);
            subText.anchor.set(0, 0.5);
            subText.position.set(-58, 10);

            innerGroup.addChild(nameText);
            innerGroup.addChild(subText);
        }
        
        nodeContainer.addChild(innerGroup);
        
        // 折叠/展开按钮 (仅对有子节点的非根节点显示)
        let collapseBtn: Container | undefined;
        if (hasChildren && !isRoot) {
            collapseBtn = new Container();
            collapseBtn.position.set(70 + 15, 0);
            collapseBtn.eventMode = 'static';
            collapseBtn.cursor = 'pointer';
            
            const btnBg = new Graphics();
            btnBg.circle(0, 0, 10);
            btnBg.fill({ color: 0x1e293b, alpha: 0.9 });
            btnBg.stroke({ width: 1, color: COLORS.COLLAPSE_BTN, alpha: 0.6 });
            collapseBtn.addChild(btnBg);
            
            // 图标: + 或 -
            const btnIcon = new Graphics();
            if (isCollapsed) {
                // + 图标
                btnIcon.moveTo(-4, 0);
                btnIcon.lineTo(4, 0);
                btnIcon.moveTo(0, -4);
                btnIcon.lineTo(0, 4);
            } else {
                // - 图标
                btnIcon.moveTo(-4, 0);
                btnIcon.lineTo(4, 0);
            }
            btnIcon.stroke({ width: 1.5, color: COLORS.COLLAPSE_BTN_HOVER });
            collapseBtn.addChild(btnIcon);
            
            collapseBtn.on('pointerdown', (e: FederatedPointerEvent) => {
                e.stopPropagation();
                toggleCollapse(node.data.lineage_code);
            });
            
            collapseBtn.on('pointerenter', () => {
                btnBg.clear();
                btnBg.circle(0, 0, 10);
                btnBg.fill({ color: 0x334155, alpha: 1 });
                btnBg.stroke({ width: 1.5, color: COLORS.SELECTED, alpha: 0.8 });
            });
            
            collapseBtn.on('pointerleave', () => {
                btnBg.clear();
                btnBg.circle(0, 0, 10);
                btnBg.fill({ color: 0x1e293b, alpha: 0.9 });
                btnBg.stroke({ width: 1, color: COLORS.COLLAPSE_BTN, alpha: 0.6 });
            });
            
            nodeContainer.addChild(collapseBtn);
        }
        
        nodesLayer.addChild(nodeContainer);

        nodeVisualsRef.current.set(node.data.lineage_code, {
            container: nodeContainer,
            innerGroup,
            border: innerGroup.children.find(c => c instanceof Graphics) as Graphics || new Graphics(),
            shadow,
            collapseBtn,
            baseX: node.y, 
            baseY: node.x,
            targetX: node.y,
            targetY: node.x,
            targetLift: 0,
            targetScale: 1,
            targetShadowAlpha: 0,
            targetShadowScale: 0.8,
            hasChildren,
            lineageCode: node.data.lineage_code
        });
    });

    // 创建连线
    const createLink = (sourceCode: string, targetCode: string, isSubspecies: boolean, isExtinct: boolean, isHybrid = false) => {
        const linkG = new Graphics();
        const color = isSubspecies ? COLORS.SUBSPECIES : (isHybrid ? COLORS.HYBRID : COLORS.LINK_NORMAL);
        const alpha = isExtinct ? 0.25 : 0.5;
        const width = isSubspecies ? 1.5 : 2.5;
        const type = (isSubspecies || isHybrid) ? 'dashed' : 'solid';
        
        const linkVis: LinkVisual = {
            graphics: linkG,
            sourceCode,
            targetCode,
            type,
            color,
            alpha,
            width
        };
        
        linksLayer.addChild(linkG);
        linkVisualsRef.current.push(linkVis);
        
        // 添加流动粒子
        if (!isExtinct) {
            const pG = new Graphics();
            pG.circle(0, 0, 2.5);
            pG.fill({ color: COLORS.ALIVE });
            particleLayer.addChild(pG);
            particlesRef.current.push({
                t: Math.random(),
                speed: 0.005 + Math.random() * 0.005,
                linkVisual: linkVis,
                graphics: pG,
                color: COLORS.ALIVE
            });
        }
    };

    links.forEach(link => {
        const source = link.source as d3.HierarchyPointNode<LineageNode>;
        const target = link.target as d3.HierarchyPointNode<LineageNode>;
        const isExtinct = target.data.state === 'extinct';
        const isSubspecies = target.data.taxonomic_rank === 'subspecies';
        createLink(source.data.lineage_code, target.data.lineage_code, isSubspecies, isExtinct);
    });
    
    // 处理杂交关系连线
    descendants.forEach(node => {
        if (node.data.hybrid_parent_codes && node.data.hybrid_parent_codes.length >= 2) {
             const p0Code = node.data.hybrid_parent_codes[0];
             const p1Code = node.data.hybrid_parent_codes[1];
             
             if (nodeVisualsRef.current.has(p0Code) && nodeVisualsRef.current.has(p1Code)) {
                 createLink(p0Code, node.data.lineage_code, false, false, true);
                 createLink(p1Code, node.data.lineage_code, false, false, true);
             }
        }
    });

  }, [nodes, spacingX, spacingY, pixiReady, collapsedNodes, toggleCollapse, onNodeClick]);

  // State Updates
  useEffect(() => {
      nodeVisualsRef.current.forEach((vis, code) => {
          const isSelected = code === selectedNode;
          const isHovered = code === hoveredNode?.lineage_code;
          const isRoot = code === ROOT_CODE;
          
          if (isRoot) return; // 根节点不响应选中/悬浮
          
          if (isSelected) {
              vis.targetLift = -8; 
              vis.targetScale = 1.12;
              vis.targetShadowAlpha = 0.6;
              vis.targetShadowScale = 1.1;
              vis.container.zIndex = 100;
          } else if (isHovered) {
              vis.targetLift = -5;
              vis.targetScale = 1.06;
              vis.targetShadowAlpha = 0.4;
              vis.targetShadowScale = 1.0;
              vis.container.zIndex = 50;
          } else {
              vis.targetLift = 0;
              vis.targetScale = 1;
              vis.targetShadowAlpha = 0;
              vis.targetShadowScale = 0.8;
              vis.container.zIndex = 0;
          }
      });
  }, [selectedNode, hoveredNode, nodes]);

  return (
    <div ref={containerRef} className="genealogy-container">
      {/* 背景渐变 */}
      <div className="genealogy-bg" />
      
      {/* Canvas容器 */}
      <div ref={canvasContainerRef} className="genealogy-canvas" />
      
      {/* 控制面板 */}
      <ControlPanel
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onReset={resetView}
        onExpandAll={expandAll}
        onCollapseAll={collapseAll}
      />
      
      {/* 统计信息 */}
      <StatsBar nodes={nodes} collapsedCount={collapsedNodes.size} />
      
      {/* Tooltip */}
      {hoveredNode && <Tooltip node={hoveredNode} pos={tooltipPos} />}
      
      {/* 图例 */}
      <Legend />
      
      <style>{`
        .genealogy-container {
          width: 100%;
          height: 100%;
          position: relative;
          overflow: hidden;
          background: #0a0f1a;
        }
        
        .genealogy-bg {
          position: absolute;
          inset: 0;
          background: radial-gradient(ellipse at 30% 20%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
                      radial-gradient(ellipse at 70% 80%, rgba(139, 92, 246, 0.06) 0%, transparent 50%),
                      linear-gradient(180deg, #0a0f1a 0%, #0f172a 100%);
          pointer-events: none;
        }
        
        .genealogy-canvas {
          width: 100%;
          height: 100%;
          position: absolute;
          top: 0;
          left: 0;
        }
      `}</style>
    </div>
  );
}

// 获取可见节点（考虑折叠）
function getVisibleNodes(nodes: LineageNode[], collapsed: Set<string>): LineageNode[] {
  const hidden = new Set<string>();
  
  // 递归标记被折叠的后代
  const markHidden = (parentCode: string) => {
    nodes.forEach(n => {
      if (n.parent_code === parentCode && !hidden.has(n.lineage_code)) {
        hidden.add(n.lineage_code);
        markHidden(n.lineage_code);
      }
    });
  };
  
  collapsed.forEach(code => markHidden(code));
  
  return nodes.filter(n => !hidden.has(n.lineage_code));
}

// 获取被隐藏的后代数量
function getHiddenDescendantCount(parentCode: string, allNodes: LineageNode[], collapsed: Set<string>): number {
  let count = 0;
  const countChildren = (code: string) => {
    allNodes.forEach(n => {
      if (n.parent_code === code) {
        count++;
        if (!collapsed.has(n.lineage_code)) {
          countChildren(n.lineage_code);
        }
      }
    });
  };
  countChildren(parentCode);
  return count;
}

// 构建层级结构
function buildHierarchy(visibleNodes: LineageNode[], allNodes: LineageNode[]): d3.HierarchyNode<LineageNode> {
  if (visibleNodes.length === 0) return d3.hierarchy({} as LineageNode);
  
  const roots = visibleNodes.filter(n => !n.parent_code || n.parent_code === ROOT_CODE);
  const visibleSet = new Set(visibleNodes.map(n => n.lineage_code));
  const orphanRoots = visibleNodes.filter(n => n.parent_code && !visibleSet.has(n.parent_code));
  const allRoots = [...roots, ...orphanRoots];
  const uniqueRoots = Array.from(new Map(allRoots.map(r => [r.lineage_code, r])).values());
  
  if (uniqueRoots.length === 0 && visibleNodes.length > 0) {
    return d3.hierarchy(visibleNodes[0], n => visibleNodes.filter(c => c.parent_code === n.lineage_code));
  }
  
  // 始终创建虚拟根节点 "始祖物种"
  const virtualRoot: LineageNode = { 
    lineage_code: ROOT_CODE, 
    common_name: ROOT_NAME,
    state: 'alive',
    ecological_role: 'producer',
    taxonomic_rank: 'species',
    tier: 'background',
    descendant_count: uniqueRoots.length
  } as LineageNode;
  
  return d3.hierarchy(virtualRoot, (d) => {
    if (d.lineage_code === ROOT_CODE) return uniqueRoots;
    return visibleNodes.filter(n => n.parent_code === d.lineage_code);
  });
}

function getNodeColorHex(node: LineageNode): number {
  if (node.tier === "background") return COLORS.BACKGROUND;
  switch (node.ecological_role) {
    case "producer": return COLORS.PRODUCER;
    case "herbivore": return COLORS.HERBIVORE;
    case "carnivore": return COLORS.CARNIVORE;
    case "omnivore": return COLORS.OMNIVORE;
    default: return COLORS.DEFAULT;
  }
}

function getPointOnBezier(t: number, p0: {x:number, y:number}, p1: {x:number, y:number}, p2: {x:number, y:number}, p3: {x:number, y:number}) {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const mt3 = mt2 * mt;
  const t2 = t * t;
  const t3 = t2 * t;
  const x = mt3 * p0.x + 3 * mt2 * t * p1.x + 3 * mt * t2 * p2.x + t3 * p3.x;
  const y = mt3 * p0.y + 3 * mt2 * t * p1.y + 3 * mt * t2 * p2.y + t3 * p3.y;
  return { x, y };
}

function drawDashedBezier(g: Graphics, p0: {x:number, y:number}, p1: {x:number, y:number}, p2: {x:number, y:number}, p3: {x:number, y:number}, color: number, alpha: number, width: number, dash = 10, gap = 5) {
   const roughLength = Math.hypot(p3.x - p0.x, p3.y - p0.y) * 1.5;
   const stepCount = Math.max(20, Math.ceil(roughLength / 5));
   let prev = p0;
   let currentDist = 0;
   let drawing = true; 
   g.moveTo(p0.x, p0.y);
   for (let i = 1; i <= stepCount; i++) {
       const t = i / stepCount;
       const curr = getPointOnBezier(t, p0, p1, p2, p3);
       const d = Math.hypot(curr.x - prev.x, curr.y - prev.y);
       currentDist += d;
       if (drawing) {
           if (currentDist > dash) {
               g.lineTo(curr.x, curr.y);
               g.stroke({ width, color, alpha });
               drawing = false;
               currentDist = 0;
               g.moveTo(curr.x, curr.y);
           } else {
               g.lineTo(curr.x, curr.y);
           }
       } else {
           if (currentDist > gap) {
               g.moveTo(curr.x, curr.y);
               drawing = true;
               currentDist = 0;
           }
       }
       prev = curr;
   }
   if (drawing) {
       g.stroke({ width, color, alpha });
   }
}

// 控制面板组件
const ControlPanel = ({ onZoomIn, onZoomOut, onReset, onExpandAll, onCollapseAll }: {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}) => (
  <div className="control-panel">
    <div className="control-group">
      <button onClick={onZoomIn} title="放大">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
        </svg>
      </button>
      <button onClick={onZoomOut} title="缩小">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="M21 21l-4.35-4.35M8 11h6"/>
        </svg>
      </button>
      <button onClick={onReset} title="重置视图">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
        </svg>
      </button>
    </div>
    <div className="control-divider" />
    <div className="control-group">
      <button onClick={onExpandAll} title="展开全部">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 15l-6-6-6 6"/>
          <path d="M18 9l-6-6-6 6"/>
        </svg>
      </button>
      <button onClick={onCollapseAll} title="折叠全部">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6"/>
          <path d="M6 15l6 6 6-6"/>
        </svg>
      </button>
    </div>
    <style>{`
      .control-panel {
        position: absolute;
        top: 16px;
        left: 16px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 8px;
        background: rgba(15, 23, 42, 0.9);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 12px;
        backdrop-filter: blur(8px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
      }
      
      .control-group {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      
      .control-divider {
        height: 1px;
        background: rgba(148, 163, 184, 0.2);
        margin: 4px 0;
      }
      
      .control-panel button {
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(148, 163, 184, 0.1);
        border-radius: 8px;
        color: #94a3b8;
        cursor: pointer;
        transition: all 0.2s ease;
      }
      
      .control-panel button:hover {
        background: rgba(59, 130, 246, 0.2);
        border-color: rgba(59, 130, 246, 0.4);
        color: #e2e8f0;
        transform: scale(1.05);
      }
      
      .control-panel button:active {
        transform: scale(0.95);
      }
    `}</style>
  </div>
);

// 统计信息栏
const StatsBar = ({ nodes, collapsedCount }: { nodes: LineageNode[]; collapsedCount: number }) => {
  const aliveCount = nodes.filter(n => n.state === 'alive').length;
  const extinctCount = nodes.filter(n => n.state === 'extinct').length;
  
  return (
    <div className="stats-bar">
      <div className="stat-item">
        <span className="stat-dot alive" />
        <span className="stat-label">存活</span>
        <span className="stat-value">{aliveCount}</span>
      </div>
      <div className="stat-item">
        <span className="stat-dot extinct" />
        <span className="stat-label">灭绝</span>
        <span className="stat-value">{extinctCount}</span>
      </div>
      <div className="stat-item">
        <span className="stat-dot total" />
        <span className="stat-label">总计</span>
        <span className="stat-value">{nodes.length}</span>
      </div>
      {collapsedCount > 0 && (
        <div className="stat-item collapsed">
          <span className="stat-label">已折叠</span>
          <span className="stat-value">{collapsedCount}</span>
        </div>
      )}
      <style>{`
        .stats-bar {
          position: absolute;
          top: 16px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 20px;
          padding: 10px 20px;
          background: rgba(15, 23, 42, 0.85);
          border: 1px solid rgba(148, 163, 184, 0.12);
          border-radius: 24px;
          backdrop-filter: blur(8px);
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }
        
        .stat-item {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        
        .stat-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        
        .stat-dot.alive {
          background: #22c55e;
          box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
        }
        
        .stat-dot.extinct {
          background: #ef4444;
          box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
        }
        
        .stat-dot.total {
          background: #3b82f6;
          box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
        }
        
        .stat-label {
          color: #94a3b8;
          font-size: 12px;
        }
        
        .stat-value {
          color: #f1f5f9;
          font-size: 14px;
          font-weight: 600;
          font-feature-settings: 'tnum';
        }
        
        .stat-item.collapsed {
          padding-left: 12px;
          border-left: 1px solid rgba(148, 163, 184, 0.2);
        }
      `}</style>
    </div>
  );
};

// Tooltip组件
const Tooltip = ({ node, pos }: { node: LineageNode, pos: {x:number, y:number} }) => (
    <div style={{
      position: "fixed",
      left: `${pos.x + 20}px`,
      top: `${pos.y}px`,
      background: "rgba(10, 15, 26, 0.98)",
      padding: "14px 16px",
      borderRadius: "12px",
      border: "1px solid rgba(59, 130, 246, 0.25)",
      backdropFilter: "blur(12px)",
      zIndex: 1000,
      pointerEvents: "none",
      minWidth: "220px",
      boxShadow: "0 12px 28px -4px rgba(0, 0, 0, 0.6), 0 0 20px rgba(59, 130, 246, 0.1)"
    }}>
      <div style={{ 
        color: "#f8fafc", 
        fontWeight: "700", 
        fontSize: "15px", 
        marginBottom: "4px",
        letterSpacing: "-0.01em"
      }}>
        {node.common_name || "未知物种"}
      </div>
      <div style={{ 
        color: "#64748b", 
        fontSize: "12px", 
        fontFamily: "JetBrains Mono, Monaco, Consolas, monospace", 
        marginBottom: "12px",
        padding: "4px 8px",
        background: "rgba(30, 41, 59, 0.5)",
        borderRadius: "4px",
        display: "inline-block"
      }}>
        {node.lineage_code}
      </div>
      <div style={{ display: "flex", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
        <Badge text={node.state === 'alive' ? '存活' : '灭绝'} color={node.state === 'alive' ? "#22c55e" : "#ef4444"} />
        <Badge text={getRoleName(node.ecological_role)} color={getNodeColorHexStr(node)} outline />
        <Badge text={getRankName(node.taxonomic_rank)} color="#8b5cf6" outline />
      </div>
      <div style={{ 
        display: "grid", 
        gridTemplateColumns: "1fr 1fr", 
        gap: "8px 16px", 
        fontSize: "12px", 
        color: "#94a3b8",
        padding: "10px",
        background: "rgba(30, 41, 59, 0.3)",
        borderRadius: "8px"
      }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>分类等级</span>
            <span style={{ color: "#e2e8f0" }}>{getRankName(node.taxonomic_rank)}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>后代数量</span>
            <span style={{ color: "#e2e8f0" }}>{node.descendant_count || 0}</span>
          </div>
      </div>
    </div>
);

const Badge = ({ text, color, outline }: { text: string, color: string, outline?: boolean }) => (
    <span style={{
        padding: "3px 8px",
        borderRadius: "6px",
        fontSize: "11px",
        fontWeight: "600",
        backgroundColor: outline ? "transparent" : color + "20",
        border: `1px solid ${outline ? color + "60" : "transparent"}`,
        color: color,
        letterSpacing: "0.02em"
    }}>
        {text}
    </span>
);

const Legend = () => (
    <div className="legend-panel">
        <div className="legend-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
          </svg>
          图例
        </div>
        <div className="legend-section">
          <div className="legend-subtitle">状态</div>
          <div className="legend-item">
            <div className="legend-dot" style={{ background: "#22c55e", boxShadow: "0 0 6px rgba(34, 197, 94, 0.5)" }} />
            <span>存活 Alive</span>
          </div>
          <div className="legend-item">
            <div className="legend-dot" style={{ background: "#ef4444", boxShadow: "0 0 6px rgba(239, 68, 68, 0.5)" }} />
            <span>灭绝 Extinct</span>
          </div>
        </div>
        <div className="legend-section">
          <div className="legend-subtitle">生态角色</div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#10b981" }} />
            <span>生产者</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#fbbf24" }} />
            <span>食草动物</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#f43f5e" }} />
            <span>食肉动物</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#f97316" }} />
            <span>杂食动物</span>
          </div>
        </div>
        <div className="legend-section">
          <div className="legend-subtitle">连线类型</div>
          <div className="legend-item">
            <div className="legend-line solid" />
            <span>演化谱系</span>
          </div>
          <div className="legend-item">
            <div className="legend-line dashed" style={{ borderColor: "#d946ef" }} />
            <span>杂交关系</span>
          </div>
          <div className="legend-item">
            <div className="legend-line dashed" style={{ borderColor: "#8b5cf6" }} />
            <span>亚种分支</span>
          </div>
        </div>
        <style>{`
          .legend-panel {
            position: absolute;
            bottom: 16px;
            right: 16px;
            background: rgba(10, 15, 26, 0.92);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 12px;
            padding: 14px 16px;
            font-size: 12px;
            color: #94a3b8;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            min-width: 160px;
          }
          
          .legend-title {
            display: flex;
            align-items: center;
            gap: 6px;
            font-weight: 700;
            color: #f1f5f9;
            font-size: 13px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.1);
          }
          
          .legend-section {
            margin-bottom: 10px;
          }
          
          .legend-section:last-child {
            margin-bottom: 0;
          }
          
          .legend-subtitle {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #64748b;
            margin-bottom: 6px;
          }
          
          .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 3px 0;
          }
          
          .legend-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
          }
          
          .legend-bar {
            width: 4px;
            height: 16px;
            border-radius: 2px;
            flex-shrink: 0;
          }
          
          .legend-line {
            width: 24px;
            height: 0;
            flex-shrink: 0;
          }
          
          .legend-line.solid {
            border-top: 2px solid #475569;
          }
          
          .legend-line.dashed {
            border-top: 2px dashed #8b5cf6;
          }
        `}</style>
    </div>
);

// 辅助函数
function getRoleName(role: string): string {
  const names: Record<string, string> = {
    producer: '生产者',
    herbivore: '食草',
    carnivore: '食肉',
    omnivore: '杂食',
  };
  return names[role] || role;
}

function getRankName(rank: string): string {
  const names: Record<string, string> = {
    species: '物种',
    subspecies: '亚种',
    genus: '属',
  };
  return names[rank] || rank;
}

function getNodeColorHexStr(node: LineageNode): string {
  if (node.tier === "background") return "#4b5563";
  switch (node.ecological_role) {
    case "producer": return "#10b981";
    case "herbivore": return "#fbbf24";
    case "carnivore": return "#f43f5e";
    case "omnivore": return "#f97316";
    default: return "#ffffff";
  }
}
