import { useEffect, useRef, useState, useCallback } from "react";
import { Application, Container, Graphics, Text, BlurFilter, FederatedPointerEvent } from "pixi.js";
import * as d3 from "d3";
import type { LineageNode } from "@/services/api.types";

interface Props {
  nodes: LineageNode[];
  spacingX?: number;
  spacingY?: number;
  onNodeClick?: (node: LineageNode) => void;
}

// Enhanced Colors
const COLORS = {
  ALIVE: 0x22c55e,
  EXTINCT: 0xef4444,
  BACKGROUND: 0x4b5563,
  PRODUCER: 0x10b981,
  HERBIVORE: 0xfbbf24,
  CARNIVORE: 0xf43f5e,
  OMNIVORE: 0xf97316,
  MIXOTROPH: 0x22d3ee,
  DECOMPOSER: 0xa78bfa,
  DEFAULT: 0xffffff,
  SELECTED: 0x3b82f6,
  SUBSPECIES: 0x8b5cf6,
  HYBRID: 0xd946ef,
  TEXT_MAIN: 0xffffff,
  TEXT_SUB: 0x9ca3af,
  LINK_NORMAL: 0x475569,
  LINK_ACTIVE: 0x94a3b8,
  ROOT_GOLD: 0xfbbf24,
  ROOT_GLOW: 0xf59e0b,
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
    isSecondaryHybrid?: boolean;  // 次要亲本连线标记
}

interface FlowParticle {
  t: number;
  speed: number;
  linkVisual: LinkVisual; 
  graphics: Graphics;
  color: number;
}

const ROOT_NAME = "始祖物种";
const ROOT_CODE = "ROOT";

export function GenealogyGraphView({ nodes, spacingX = 160, spacingY = 120, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  
  const appRef = useRef<Application | null>(null);
  const stageRef = useRef<Container | null>(null);
  
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<LineageNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [pixiReady, setPixiReady] = useState(false);
  
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set());
  const [showAllHybridLinks, setShowAllHybridLinks] = useState(false);  // 是否显示所有杂交连线
  const [focusedLineage, setFocusedLineage] = useState<string | null>(null);  // 聚焦的谱系物种代码
  const [compactMode, setCompactMode] = useState(false);  // 概要模式（大量节点时简化显示）

  // CK3风格：垂直布局，初始相机位置调整到顶部中央
  const cameraRef = useRef({ x: 400, y: 80, zoom: 0.7 }); 
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const currentMousePos = useRef({ x: 0, y: 0 });
  
  const particlesRef = useRef<FlowParticle[]>([]);
  const nodeVisualsRef = useRef<Map<string, NodeVisual>>(new Map());
  const linkVisualsRef = useRef<LinkVisual[]>([]);
  
  // 用于追踪当前hover/选中的节点，供updateLinks使用
  const activeNodeRef = useRef<string | null>(null);
  const showAllHybridLinksRef = useRef(false);

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

  const resetView = useCallback(() => {
    if (stageRef.current) {
      // CK3风格：重置到顶部中央位置
      cameraRef.current = { x: 400, y: 80, zoom: 0.7 };
      stageRef.current.position.set(400, 80);
      stageRef.current.scale.set(0.7);
    }
  }, []);

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

  const expandAll = useCallback(() => {
    setCollapsedNodes(new Set());
  }, []);

  const collapseAll = useCallback(() => {
    const nodesWithChildren = nodes.filter(n => 
      nodes.some(c => c.parent_code === n.lineage_code)
    ).map(n => n.lineage_code);
    setCollapsedNodes(new Set(nodesWithChildren));
  }, [nodes]);

  // 适应屏幕功能
  const fitToScreen = useCallback(() => {
    if (!stageRef.current || !canvasContainerRef.current || nodeVisualsRef.current.size === 0) return;
    
    const container = canvasContainerRef.current;
    const { width: containerWidth, height: containerHeight } = container.getBoundingClientRect();
    
    // 计算所有节点的边界
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    nodeVisualsRef.current.forEach(vis => {
      minX = Math.min(minX, vis.baseX - 70);
      maxX = Math.max(maxX, vis.baseX + 70);
      minY = Math.min(minY, vis.baseY - 22);
      maxY = Math.max(maxY, vis.baseY + 22);
    });
    
    const contentWidth = maxX - minX + 100;
    const contentHeight = maxY - minY + 100;
    
    // 计算合适的缩放比例
    const scaleX = containerWidth / contentWidth;
    const scaleY = containerHeight / contentHeight;
    const newZoom = Math.min(scaleX, scaleY, 1.5) * 0.9; // 留一些边距
    
    // 计算中心位置
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const newCamX = containerWidth / 2 - centerX * newZoom;
    const newCamY = containerHeight / 2 - centerY * newZoom;
    
    cameraRef.current = { x: newCamX, y: newCamY, zoom: newZoom };
    stageRef.current.position.set(newCamX, newCamY);
    stageRef.current.scale.set(newZoom);
  }, []);

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
          background: '#080c15', 
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

  // Animation Logic
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

  // CK3风格：使用直线拐角连线（垂直布局）
  const updateLinks = () => {
      const NODE_H = 44;  // 节点高度
      const NODE_OFFSET_Y = NODE_H / 2;
      const activeCode = activeNodeRef.current;
      const showAll = showAllHybridLinksRef.current;
      
      linkVisualsRef.current.forEach(link => {
          const sourceVis = nodeVisualsRef.current.get(link.sourceCode);
          const targetVis = nodeVisualsRef.current.get(link.targetCode);
          
          if (!sourceVis || !targetVis) return;
          
          link.graphics.clear();
          
          // 次要杂交连线的可见性逻辑
          if (link.isSecondaryHybrid) {
              const isRelatedToActive = activeCode && (
                  link.targetCode === activeCode || 
                  link.sourceCode === activeCode
              );
              
              if (!showAll && !isRelatedToActive) {
                  return;
              }
          }
          
          // CK3风格：垂直布局，从上到下
          // 起点在父节点底部中央，终点在子节点顶部中央
          const startX = sourceVis.container.x;
          const startY = sourceVis.container.y + NODE_OFFSET_Y;
          const endX = targetVis.container.x;
          const endY = targetVis.container.y - NODE_OFFSET_Y;
          
          // 中间拐点的Y坐标（在两者之间）
          const midY = startY + (endY - startY) * 0.5;
          
          const isHighlighted = link.isSecondaryHybrid && activeCode && (
              link.targetCode === activeCode || link.sourceCode === activeCode
          );
          const alpha = isHighlighted ? 0.6 : link.alpha;
          const width = isHighlighted ? 2.0 : link.width;
          
          if (link.type === 'dashed') {
              // 虚线直线拐角
              drawDashedOrthoLine(link.graphics, startX, startY, endX, endY, midY, link.color, alpha, width);
          } else {
              // 实线直线拐角（CK3风格）
              link.graphics.moveTo(startX, startY);
              link.graphics.lineTo(startX, midY);  // 垂直向下
              link.graphics.lineTo(endX, midY);    // 水平移动
              link.graphics.lineTo(endX, endY);    // 垂直到子节点
              link.graphics.stroke({ width, color: link.color, alpha });
          }
      });
  };

  // CK3风格：粒子沿直线拐角路径移动
  const updateParticles = (delta: number) => {
     const NODE_H = 44;
     const NODE_OFFSET_Y = NODE_H / 2;
     
     const particles = particlesRef.current;
     for (let i = particles.length - 1; i >= 0; i--) {
         const p = particles[i];
         p.t += p.speed * delta;
         if (p.t >= 1) p.t = 0;
         
         const sourceVis = nodeVisualsRef.current.get(p.linkVisual.sourceCode);
         const targetVis = nodeVisualsRef.current.get(p.linkVisual.targetCode);
         
         if (sourceVis && targetVis) {
             const startX = sourceVis.container.x;
             const startY = sourceVis.container.y + NODE_OFFSET_Y;
             const endX = targetVis.container.x;
             const endY = targetVis.container.y - NODE_OFFSET_Y;
             const midY = startY + (endY - startY) * 0.5;
             
             // 沿直线拐角路径插值
             const pos = getPointOnOrthoPath(p.t, startX, startY, endX, endY, midY);
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

    // 自动启用概要模式（当节点数超过阈值时）
    const autoCompactThreshold = 100;
    const useCompact = compactMode || nodes.length > autoCompactThreshold;

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

    // 先应用谱系聚焦过滤，再应用折叠过滤
    let filteredNodes = nodes;
    if (focusedLineage) {
      filteredNodes = getFocusedLineageNodes(nodes, focusedLineage);
    }
    const visibleNodes = getVisibleNodes(filteredNodes, collapsedNodes);
    
    const root = buildHierarchy(visibleNodes, filteredNodes);
    // CK3风格：垂直布局（从上到下）
    // nodeSize: [水平间距, 垂直间距]
    const treeLayout = d3.tree<LineageNode>()
      .nodeSize([spacingX, spacingY])
      .separation((a, b) => (a.parent === b.parent ? 1 : 1.3));
    
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
    
    const childrenCount = new Map<string, number>();
    nodes.forEach(n => {
      const parentCode = n.parent_code || ROOT_CODE;
      childrenCount.set(parentCode, (childrenCount.get(parentCode) || 0) + 1);
    });

    descendants.forEach(node => {
        const isRoot = node.data.lineage_code === ROOT_CODE;
        const hasChildren = (childrenCount.get(node.data.lineage_code) || 0) > 0;
        const isCollapsed = collapsedNodes.has(node.data.lineage_code);
        const hiddenChildCount = isCollapsed ? getHiddenDescendantCount(node.data.lineage_code, nodes, collapsedNodes) : 0;
        
        const nodeContainer = new Container();
        // CK3风格：垂直布局 (x是水平位置, y是深度/垂直位置)
        nodeContainer.position.set(node.x, node.y);
        
        nodeContainer.eventMode = 'static';
        nodeContainer.cursor = 'pointer';
        
        // 双击计时器
        let clickTimer: ReturnType<typeof setTimeout> | null = null;
        let clickCount = 0;
        
        nodeContainer.on('pointerdown', (e: FederatedPointerEvent) => {
            e.stopPropagation();
            if (!isRoot) {
              clickCount++;
              
              if (clickCount === 1) {
                // 单击：选中节点
                clickTimer = setTimeout(() => {
                  clickCount = 0;
                  setSelectedNode(node.data.lineage_code);
                  onNodeClick?.(node.data);
                }, 250);
              } else if (clickCount === 2) {
                // 双击：聚焦该谱系
                if (clickTimer) clearTimeout(clickTimer);
                clickCount = 0;
                setFocusedLineage(node.data.lineage_code);
                setSelectedNode(node.data.lineage_code);
              }
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
            
        } else if (useCompact) {
            // === 概要模式：简化节点（仅圆形+代码） ===
            const compactRadius = 18;
            
            // 节点背景圆
            const nodeBg = new Graphics();
            nodeBg.circle(0, 0, compactRadius);
            nodeBg.fill({ color: roleColor, alpha: isAlive ? 0.9 : 0.4 });
            innerGroup.addChild(nodeBg);
            
            // 状态边框
            const nodeBorder = new Graphics();
            nodeBorder.circle(0, 0, compactRadius);
            nodeBorder.stroke({ 
                width: 2, 
                color: isAlive ? COLORS.ALIVE : COLORS.EXTINCT,
                alpha: isAlive ? 1 : 0.6 
            });
            innerGroup.addChild(nodeBorder);
            
            // 折叠指示器
            if (isCollapsed && hiddenChildCount > 0) {
                const badge = new Graphics();
                badge.circle(14, -14, 8);
                badge.fill({ color: COLORS.SELECTED, alpha: 0.9 });
                innerGroup.addChild(badge);
                
                const badgeText = new Text({
                    text: `${hiddenChildCount}`,
                    style: { fontFamily: 'system-ui, sans-serif', fontSize: 28, fontWeight: 'bold', fill: 0xffffff }
                });
                badgeText.scale.set(0.25);
                badgeText.anchor.set(0.5, 0.5);
                badgeText.position.set(14, -14);
                innerGroup.addChild(badgeText);
            }
            
            // 物种代码（缩小显示）
            const codeText = new Text({
                text: node.data.lineage_code,
                style: {
                    fontFamily: 'JetBrains Mono, Monaco, Consolas, monospace',
                    fontSize: 36,
                    fontWeight: 'bold',
                    fill: 0xffffff,
                }
            });
            codeText.scale.set(0.28);
            codeText.anchor.set(0.5, 0.5);
            codeText.position.set(0, compactRadius + 12);
            innerGroup.addChild(codeText);
            
        } else {
            // === 完整模式：详细节点 ===
            const mask = new Graphics();
            mask.roundRect(-70, -22, 140, 44, 10);
            mask.fill(0xffffff);
            
            const bg = new Graphics();
            bg.rect(-70, -22, 140, 44);
            bg.fill({ color: 0x151c2c, alpha: 0.95 }); 
            
            const indicator = new Graphics();
            indicator.rect(-70, -22, 6, 44);
            indicator.fill({ color: roleColor });
            
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
            
            // 【v2】杂交物种标记🧬
            const isHybrid = node.data.taxonomic_rank === 'hybrid' || 
                            (node.data.hybrid_parent_codes && node.data.hybrid_parent_codes.length >= 2);
            if (isHybrid) {
                // 杂交标记背景
                const hybridBadgeBg = new Graphics();
                hybridBadgeBg.circle(-55, 0, 8);
                hybridBadgeBg.fill({ color: COLORS.HYBRID, alpha: 0.3 });
                innerGroup.addChild(hybridBadgeBg);
                
                // 杂交图标
                const hybridIcon = new Text({
                    text: '🧬',
                    style: {
                        fontFamily: 'system-ui, sans-serif',
                        fontSize: 36,
                    }
                });
                hybridIcon.scale.set(0.28);
                hybridIcon.anchor.set(0.5, 0.5);
                hybridIcon.position.set(-55, 0);
                innerGroup.addChild(hybridIcon);
            }

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
        
        let collapseBtn: Container | undefined;
        if (hasChildren && !isRoot) {
            collapseBtn = new Container();
            // CK3风格：折叠按钮放在节点底部
            collapseBtn.position.set(0, 22 + 12);
            collapseBtn.eventMode = 'static';
            collapseBtn.cursor = 'pointer';
            
            const btnBg = new Graphics();
            btnBg.circle(0, 0, 10);
            btnBg.fill({ color: 0x1e293b, alpha: 0.9 });
            btnBg.stroke({ width: 1, color: COLORS.COLLAPSE_BTN, alpha: 0.6 });
            collapseBtn.addChild(btnBg);
            
            const btnIcon = new Graphics();
            if (isCollapsed) {
                btnIcon.moveTo(-4, 0);
                btnIcon.lineTo(4, 0);
                btnIcon.moveTo(0, -4);
                btnIcon.lineTo(0, 4);
            } else {
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
            // CK3风格：垂直布局坐标
            baseX: node.x, 
            baseY: node.y,
            targetX: node.x,
            targetY: node.y,
            targetLift: 0,
            targetScale: 1,
            targetShadowAlpha: 0,
            targetShadowScale: 0.8,
            hasChildren,
            lineageCode: node.data.lineage_code
        });
    });

    const createLink = (
        sourceCode: string, 
        targetCode: string, 
        isSubspecies: boolean, 
        isExtinct: boolean, 
        isHybrid = false,
        isSecondaryHybrid = false  // 次要亲本连线
    ) => {
        const linkG = new Graphics();
        const color = isSubspecies ? COLORS.SUBSPECIES : (isHybrid ? COLORS.HYBRID : COLORS.LINK_NORMAL);
        // 次要杂交连线默认透明度更低
        const alpha = isSecondaryHybrid ? 0.15 : (isExtinct ? 0.25 : 0.5);
        const width = isSubspecies ? 1.5 : (isSecondaryHybrid ? 1.5 : 2.5);
        const type = (isSubspecies || isHybrid) ? 'dashed' : 'solid';
        
        const linkVis: LinkVisual = {
            graphics: linkG,
            sourceCode,
            targetCode,
            type,
            color,
            alpha,
            width,
            isSecondaryHybrid
        };
        
        linksLayer.addChild(linkG);
        linkVisualsRef.current.push(linkVis);
        
        // 次要杂交连线不添加粒子
        if (!isExtinct && !isSecondaryHybrid) {
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
    
    // 【v2】杂交物种：只绘制次要亲本连线（主亲本连线已通过普通谱系绘制）
    // hybrid_parent_codes[0] = 主亲本（已作为parent_code）
    // hybrid_parent_codes[1] = 次要亲本（需要额外绘制虚线）
    descendants.forEach(node => {
        if (node.data.hybrid_parent_codes && node.data.hybrid_parent_codes.length >= 2) {
            // 次要亲本编码
            const secondaryParentCode = node.data.hybrid_parent_codes[1];
            
            if (nodeVisualsRef.current.has(secondaryParentCode)) {
                // 绘制次要亲本连线（标记为isSecondaryHybrid）
                createLink(
                    secondaryParentCode, 
                    node.data.lineage_code, 
                    false, 
                    false, 
                    true,   // isHybrid
                    true    // isSecondaryHybrid
                );
            }
        }
    });

  }, [nodes, spacingX, spacingY, pixiReady, collapsedNodes, toggleCollapse, onNodeClick, focusedLineage, compactMode]);

  // State Updates
  useEffect(() => {
      // 更新activeNodeRef供updateLinks使用
      activeNodeRef.current = hoveredNode?.lineage_code || selectedNode || null;
      
      nodeVisualsRef.current.forEach((vis, code) => {
          const isSelected = code === selectedNode;
          const isHovered = code === hoveredNode?.lineage_code;
          const isRoot = code === ROOT_CODE;
          
          if (isRoot) return;
          
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
  
  // 同步showAllHybridLinks到ref
  useEffect(() => {
      showAllHybridLinksRef.current = showAllHybridLinks;
  }, [showAllHybridLinks]);

  // 键盘快捷键支持
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 忽略在输入框中的按键
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      
      switch (e.key) {
        case '+':
        case '=':
          zoomIn();
          break;
        case '-':
          zoomOut();
          break;
        case 'Home':
        case 'h':
          resetView();
          break;
        case 'f':
        case 'F':
          fitToScreen();
          break;
        case 'e':
        case 'E':
          expandAll();
          break;
        case 'c':
        case 'C':
          collapseAll();
          break;
        case 'Escape':
          // 如果有聚焦，先退出聚焦；否则取消选择
          if (focusedLineage) {
            setFocusedLineage(null);
          } else {
            setSelectedNode(null);
            setHoveredNode(null);
          }
          break;
        case 'Backspace':
          // Backspace 也可以退出聚焦
          if (focusedLineage) {
            setFocusedLineage(null);
          }
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [zoomIn, zoomOut, resetView, fitToScreen, expandAll, collapseAll, focusedLineage]);

  return (
    <div ref={containerRef} className="graph-container">
      {/* 渐变背景 */}
      <div className="graph-bg" />
      
      {/* Canvas容器 */}
      <div ref={canvasContainerRef} className="graph-canvas" />
      
      {/* CK3风格控制面板 */}
      <ControlPanel
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onReset={resetView}
        onExpandAll={expandAll}
        onCollapseAll={collapseAll}
        showHybridLinks={showAllHybridLinks}
        onToggleHybridLinks={() => setShowAllHybridLinks(!showAllHybridLinks)}
        onFitToScreen={fitToScreen}
        focusedLineage={focusedLineage}
        focusedName={nodes.find(n => n.lineage_code === focusedLineage)?.common_name}
        onClearFocus={() => setFocusedLineage(null)}
        compactMode={compactMode}
        onToggleCompact={() => setCompactMode(!compactMode)}
        nodeCount={nodes.length}
      />
      
      {/* 统计信息 */}
      <StatsBar 
        nodes={focusedLineage ? getFocusedLineageNodes(nodes, focusedLineage) : nodes} 
        collapsedCount={collapsedNodes.size}
        totalNodes={nodes.length}
        isFocused={!!focusedLineage}
      />
      
      {/* Tooltip */}
      {hoveredNode && <Tooltip node={hoveredNode} pos={tooltipPos} isFocused={focusedLineage === hoveredNode.lineage_code} />}
      
      {/* 图例 */}
      <Legend />
      
      <style>{graphStyles}</style>
    </div>
  );
}

// 获取可见节点
function getVisibleNodes(nodes: LineageNode[], collapsed: Set<string>): LineageNode[] {
  const hidden = new Set<string>();
  
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

// 获取聚焦谱系的节点（祖先 + 自己 + 所有后代）
function getFocusedLineageNodes(nodes: LineageNode[], focusCode: string): LineageNode[] {
  const result = new Set<string>();
  const nodeMap = new Map(nodes.map(n => [n.lineage_code, n]));
  
  // 添加焦点物种
  result.add(focusCode);
  
  // 向上追溯所有祖先
  let current = nodeMap.get(focusCode);
  while (current && current.parent_code) {
    result.add(current.parent_code);
    current = nodeMap.get(current.parent_code);
  }
  
  // 向下收集所有后代
  const collectDescendants = (code: string) => {
    nodes.forEach(n => {
      if (n.parent_code === code && !result.has(n.lineage_code)) {
        result.add(n.lineage_code);
        collectDescendants(n.lineage_code);
      }
    });
  };
  collectDescendants(focusCode);
  
  return nodes.filter(n => result.has(n.lineage_code));
}

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
  // 只使用营养级来判断颜色
  const trophic = node.trophic_level ?? 1.0;
  
  if (trophic < 1.5) {
    return COLORS.PRODUCER;      // T < 1.5: 生产者（绿色）
  } else if (trophic < 2.0) {
    return COLORS.MIXOTROPH;     // 1.5 ≤ T < 2.0: 混合营养（青色）
  } else if (trophic < 2.8) {
    return COLORS.HERBIVORE;     // 2.0 ≤ T < 2.8: 草食者（黄色）
  } else if (trophic < 3.5) {
    return COLORS.OMNIVORE;      // 2.8 ≤ T < 3.5: 杂食者（橙色）
  } else {
    return COLORS.CARNIVORE;     // T ≥ 3.5: 肉食者（红色）
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

// CK3风格：沿直线拐角路径插值
function getPointOnOrthoPath(t: number, startX: number, startY: number, endX: number, endY: number, midY: number) {
  // 路径分三段：
  // 1. startX, startY -> startX, midY (垂直向下)
  // 2. startX, midY -> endX, midY (水平移动)
  // 3. endX, midY -> endX, endY (垂直向下)
  
  const seg1Len = Math.abs(midY - startY);
  const seg2Len = Math.abs(endX - startX);
  const seg3Len = Math.abs(endY - midY);
  const totalLen = seg1Len + seg2Len + seg3Len;
  
  if (totalLen === 0) return { x: startX, y: startY };
  
  const pos = t * totalLen;
  
  if (pos <= seg1Len) {
    // 第一段
    const ratio = pos / seg1Len;
    return { x: startX, y: startY + (midY - startY) * ratio };
  } else if (pos <= seg1Len + seg2Len) {
    // 第二段
    const ratio = (pos - seg1Len) / seg2Len;
    return { x: startX + (endX - startX) * ratio, y: midY };
  } else {
    // 第三段
    const ratio = (pos - seg1Len - seg2Len) / seg3Len;
    return { x: endX, y: midY + (endY - midY) * ratio };
  }
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

// CK3风格：绘制虚线直线拐角
function drawDashedOrthoLine(g: Graphics, startX: number, startY: number, endX: number, endY: number, midY: number, color: number, alpha: number, width: number, dash = 8, gap = 4) {
  // 计算总长度用于步进
  const seg1Len = Math.abs(midY - startY);
  const seg2Len = Math.abs(endX - startX);
  const seg3Len = Math.abs(endY - midY);
  const totalLen = seg1Len + seg2Len + seg3Len;
  
  if (totalLen === 0) return;
  
  const stepSize = 3;
  const stepCount = Math.max(10, Math.ceil(totalLen / stepSize));
  
  let currentDist = 0;
  let drawing = true;
  let prevPoint = getPointOnOrthoPath(0, startX, startY, endX, endY, midY);
  g.moveTo(prevPoint.x, prevPoint.y);
  
  for (let i = 1; i <= stepCount; i++) {
    const t = i / stepCount;
    const curr = getPointOnOrthoPath(t, startX, startY, endX, endY, midY);
    const d = Math.hypot(curr.x - prevPoint.x, curr.y - prevPoint.y);
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
    prevPoint = curr;
  }
  
  if (drawing) {
    g.stroke({ width, color, alpha });
  }
}

// CK3风格控制面板组件
const ControlPanel = ({ 
  onZoomIn, 
  onZoomOut, 
  onReset, 
  onExpandAll, 
  onCollapseAll,
  showHybridLinks,
  onToggleHybridLinks,
  onFitToScreen,
  focusedLineage,
  focusedName,
  onClearFocus,
  compactMode,
  onToggleCompact,
  nodeCount
}: {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  showHybridLinks: boolean;
  onToggleHybridLinks: () => void;
  onFitToScreen?: () => void;
  focusedLineage?: string | null;
  focusedName?: string;
  onClearFocus?: () => void;
  compactMode?: boolean;
  onToggleCompact?: () => void;
  nodeCount?: number;
}) => (
  <div className="control-panel">
    {/* 聚焦模式指示器 */}
    {focusedLineage && (
      <>
        <div className="focus-indicator">
          <div className="focus-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            </svg>
            <span>聚焦谱系</span>
          </div>
          <div className="focus-info">
            <span className="focus-code">{focusedLineage}</span>
            {focusedName && <span className="focus-name">{focusedName}</span>}
          </div>
          <button className="focus-clear" onClick={onClearFocus} title="退出聚焦 (Esc)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
            <span>显示全部</span>
          </button>
        </div>
        <div className="control-divider" />
      </>
    )}
    
    <div className="control-section">
      <span className="section-label">视图</span>
      <div className="control-buttons">
        <button onClick={onZoomIn} title="放大 (+)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
          </svg>
        </button>
        <button onClick={onZoomOut} title="缩小 (-)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35M8 11h6"/>
          </svg>
        </button>
        <button onClick={onReset} title="重置视图 (Home)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
          </svg>
        </button>
        {onFitToScreen && (
          <button onClick={onFitToScreen} title="适应屏幕 (F)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 3H5a2 2 0 0 0-2 2v3"/>
              <path d="M21 8V5a2 2 0 0 0-2-2h-3"/>
              <path d="M3 16v3a2 2 0 0 0 2 2h3"/>
              <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
            </svg>
          </button>
        )}
      </div>
    </div>
    <div className="control-divider" />
    <div className="control-section">
      <span className="section-label">族谱</span>
      <div className="control-buttons">
        <button onClick={onExpandAll} title="展开全部 (E)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M7 13l5 5 5-5"/>
            <path d="M7 6l5 5 5-5"/>
          </svg>
        </button>
        <button onClick={onCollapseAll} title="折叠全部 (C)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17 11l-5-5-5 5"/>
            <path d="M17 18l-5-5-5 5"/>
          </svg>
        </button>
      </div>
    </div>
    <div className="control-divider" />
    <div className="control-section">
      <span className="section-label">显示</span>
      <div className="control-buttons">
        <button 
          onClick={onToggleHybridLinks} 
          title={showHybridLinks ? "隐藏杂交关系" : "显示所有杂交关系"}
          className={showHybridLinks ? "active" : ""}
        >
          <span style={{ fontSize: '14px' }}>🧬</span>
        </button>
        {onToggleCompact && (
          <button 
            onClick={onToggleCompact} 
            title={compactMode ? "详细模式" : "概要模式（简化显示）"}
            className={compactMode ? "active compact" : ""}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <circle cx="4" cy="12" r="2"/>
              <circle cx="20" cy="12" r="2"/>
              <circle cx="12" cy="4" r="2"/>
              <circle cx="12" cy="20" r="2"/>
            </svg>
          </button>
        )}
      </div>
    </div>
    {/* 节点数量提示（大量节点时显示） */}
    {nodeCount && nodeCount > 50 && (
      <>
        <div className="control-divider" />
        <div className="node-count-hint">
          <span className="count-label">节点数</span>
          <span className="count-value">{nodeCount}</span>
          {nodeCount > 100 && !compactMode && (
            <span className="count-warning">建议开启概要模式</span>
          )}
        </div>
      </>
    )}
  </div>
);

// 统计信息栏
const StatsBar = ({ nodes, collapsedCount, totalNodes, isFocused }: { 
  nodes: LineageNode[]; 
  collapsedCount: number;
  totalNodes?: number;
  isFocused?: boolean;
}) => {
  const aliveCount = nodes.filter(n => n.state === 'alive').length;
  const extinctCount = nodes.filter(n => n.state === 'extinct').length;
  
  return (
    <div className="stats-bar">
      <div className={`stats-container ${isFocused ? 'focused' : ''}`}>
        {isFocused && (
          <>
            <div className="stat-item focus-mode">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
              </svg>
              <span className="stat-label">聚焦模式</span>
            </div>
            <div className="stat-divider" />
          </>
        )}
        <div className="stat-item alive">
          <div className="stat-dot" />
          <span className="stat-label">存活</span>
          <span className="stat-value">{aliveCount}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item extinct">
          <div className="stat-dot" />
          <span className="stat-label">灭绝</span>
          <span className="stat-value">{extinctCount}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item total">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7"/>
            <rect x="14" y="3" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/>
          </svg>
          <span className="stat-label">{isFocused ? '谱系' : '总计'}</span>
          <span className="stat-value">
            {nodes.length}
            {isFocused && totalNodes && <span className="stat-total">/{totalNodes}</span>}
          </span>
        </div>
        {collapsedCount > 0 && (
          <>
            <div className="stat-divider" />
            <div className="stat-item collapsed">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6"/>
              </svg>
              <span className="stat-label">已折叠</span>
              <span className="stat-value">{collapsedCount}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// Tooltip组件
const Tooltip = ({ node, pos, isFocused }: { node: LineageNode, pos: {x:number, y:number}, isFocused?: boolean }) => {
    const isHybrid = node.taxonomic_rank === 'hybrid' || 
                    (node.hybrid_parent_codes && node.hybrid_parent_codes.length >= 2);
    
    return (
      <div className="tooltip" style={{ left: `${pos.x + 20}px`, top: `${pos.y}px` }}>
        <div className="tooltip-header">
          <span className="tooltip-name">
            {isHybrid && <span style={{ marginRight: '4px' }}>🧬</span>}
            {node.common_name || "未知物种"}
          </span>
          <span className={`tooltip-status ${node.state}`}>
            {node.state === 'alive' ? '存活' : '灭绝'}
          </span>
        </div>
        <div className="tooltip-code">{node.lineage_code}</div>
        <div className="tooltip-tags">
          <span className="tooltip-tag" style={{ 
            background: `${getNodeColorStr(node)}20`,
            borderColor: `${getNodeColorStr(node)}50`,
            color: getNodeColorStr(node)
          }}>
            T{(node.trophic_level ?? 1.0).toFixed(1)} {getTrophicName(node.trophic_level ?? 1.0)}
          </span>
          <span className="tooltip-tag rank">{getRankName(node.taxonomic_rank)}</span>
        </div>
        {/* 杂交亲本信息 */}
        {isHybrid && node.hybrid_parent_codes && node.hybrid_parent_codes.length >= 2 && (
          <div className="tooltip-hybrid">
            <span className="hybrid-label">亲本:</span>
            <span className="hybrid-parents">
              {node.hybrid_parent_codes[0]} × {node.hybrid_parent_codes[1]}
            </span>
          </div>
        )}
        <div className="tooltip-stats">
          <div className="tooltip-stat">
            <span className="stat-key">后代</span>
            <span className="stat-val">{node.descendant_count || 0}</span>
          </div>
          <div className="tooltip-stat">
            <span className="stat-key">诞生</span>
            <span className="stat-val">T{node.birth_turn + 1}</span>
          </div>
        </div>
        {/* 双击提示 */}
        <div className="tooltip-hint">
          {isFocused 
            ? <span>当前聚焦物种</span>
            : <span>双击聚焦此谱系</span>
          }
        </div>
      </div>
    );
};

// CK3风格图例组件
const Legend = () => (
    <div className="legend">
        <div className="legend-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
          </svg>
          <span>图例</span>
        </div>
        
        <div className="legend-group">
          <div className="legend-title">状态</div>
          <div className="legend-item">
            <div className="legend-dot alive" />
            <span>存活</span>
          </div>
          <div className="legend-item">
            <div className="legend-dot extinct" />
            <span>灭绝</span>
          </div>
        </div>
        
        <div className="legend-group">
          <div className="legend-title">营养级</div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#10b981" }} />
            <span>T1 生产者</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#22d3ee" }} />
            <span>T1.5 混养</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#fbbf24" }} />
            <span>T2 草食</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#f97316" }} />
            <span>T3 杂食</span>
          </div>
          <div className="legend-item">
            <div className="legend-bar" style={{ background: "#f43f5e" }} />
            <span>T4+ 肉食</span>
          </div>
        </div>
        
        <div className="legend-group">
          <div className="legend-title">连线</div>
          <div className="legend-item">
            <div className="legend-line-ortho solid" />
            <span>谱系</span>
          </div>
          <div className="legend-item">
            <div className="legend-line-ortho dashed" />
            <span>杂交/亚种</span>
          </div>
        </div>
        
        <div className="legend-group shortcuts">
          <div className="legend-title">快捷键</div>
          <div className="shortcut-item"><kbd>双击</kbd> 聚焦谱系</div>
          <div className="shortcut-item"><kbd>Esc</kbd> 退出聚焦</div>
          <div className="shortcut-item"><kbd>+/-</kbd> 缩放</div>
          <div className="shortcut-item"><kbd>F</kbd> 适应屏幕</div>
          <div className="shortcut-item"><kbd>E/C</kbd> 展开/折叠</div>
        </div>
    </div>
);

// 辅助函数
function getTrophicName(trophic: number): string {
  if (trophic < 1.5) return '生产者';
  if (trophic < 2.0) return '混养';
  if (trophic < 2.8) return '草食';
  if (trophic < 3.5) return '杂食';
  return '肉食';
}

function getRoleName(role: string): string {
  const names: Record<string, string> = {
    producer: '生产者',
    herbivore: '食草',
    carnivore: '食肉',
    omnivore: '杂食',
    mixotroph: '混养',
    decomposer: '分解',
  };
  return names[role] || role;
}

function getRankName(rank: string): string {
  const names: Record<string, string> = {
    species: '物种',
    subspecies: '亚种',
    genus: '属',
    hybrid: '杂交种',
  };
  return names[rank] || rank;
}

function getNodeColorStr(node: LineageNode): string {
  // 只使用营养级来判断颜色
  const trophic = node.trophic_level ?? 1.0;
  
  if (trophic < 1.5) {
    return "#10b981";  // T < 1.5: 生产者（绿色）
  } else if (trophic < 2.0) {
    return "#22d3ee";  // 1.5 ≤ T < 2.0: 混合营养（青色）
  } else if (trophic < 2.8) {
    return "#fbbf24";  // 2.0 ≤ T < 2.8: 草食者（黄色）
  } else if (trophic < 3.5) {
    return "#f97316";  // 2.8 ≤ T < 3.5: 杂食者（橙色）
  } else {
    return "#f43f5e";  // T ≥ 3.5: 肉食者（红色）
  }
}

// 样式
const graphStyles = `
  .graph-container {
    width: 100%;
    height: 100%;
    position: relative;
    overflow: hidden;
    background: #080c15;
  }
  
  .graph-bg {
    position: absolute;
    inset: 0;
    background: 
      radial-gradient(ellipse at 20% 30%, rgba(34, 197, 94, 0.06) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 70%, rgba(59, 130, 246, 0.06) 0%, transparent 50%),
      radial-gradient(ellipse at 50% 50%, rgba(139, 92, 246, 0.04) 0%, transparent 60%),
      linear-gradient(180deg, #080c15 0%, #0f172a 100%);
    pointer-events: none;
  }
  
  .graph-canvas {
    width: 100%;
    height: 100%;
    position: absolute;
    top: 0;
    left: 0;
  }

  /* 控制面板 */
  .control-panel {
    position: absolute;
    top: 20px;
    left: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 14px;
    background: linear-gradient(145deg, rgba(15, 23, 42, 0.95) 0%, rgba(10, 15, 26, 0.95) 100%);
    border: 1px solid rgba(59, 130, 246, 0.15);
    border-radius: 16px;
    backdrop-filter: blur(12px);
    box-shadow: 
      0 8px 32px rgba(0, 0, 0, 0.4),
      0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  }
  
  /* 聚焦指示器 */
  .focus-indicator {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px 12px;
    background: linear-gradient(135deg, rgba(251, 191, 36, 0.15) 0%, rgba(245, 158, 11, 0.1) 100%);
    border: 1px solid rgba(251, 191, 36, 0.3);
    border-radius: 10px;
  }
  
  .focus-header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.7rem;
    font-weight: 600;
    color: #fbbf24;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .focus-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  
  .focus-code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.95rem;
    font-weight: 700;
    color: #fef3c7;
  }
  
  .focus-name {
    font-size: 0.8rem;
    color: rgba(254, 243, 199, 0.7);
  }
  
  .focus-clear {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 12px;
    margin-top: 4px;
    background: rgba(251, 191, 36, 0.15);
    border: 1px solid rgba(251, 191, 36, 0.3);
    border-radius: 8px;
    color: #fbbf24;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .focus-clear:hover {
    background: rgba(251, 191, 36, 0.25);
    border-color: rgba(251, 191, 36, 0.5);
    transform: translateY(-1px);
  }
  
  /* 概要模式按钮 */
  .control-panel button.compact {
    background: rgba(34, 197, 94, 0.2);
    border-color: rgba(34, 197, 94, 0.4);
    color: #22c55e;
  }
  
  /* 节点数量提示 */
  .node-count-hint {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    background: rgba(30, 41, 59, 0.5);
    border-radius: 8px;
  }
  
  .count-label {
    font-size: 0.65rem;
    color: rgba(148, 163, 184, 0.6);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .count-value {
    font-size: 1rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: #f1f5f9;
  }
  
  .count-warning {
    font-size: 0.65rem;
    color: #fbbf24;
    margin-top: 2px;
  }
  
  .control-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  .section-label {
    font-size: 0.65rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.6);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding-left: 4px;
  }
  
  .control-buttons {
    display: flex;
    gap: 6px;
  }
  
  .control-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.2), transparent);
    margin: 2px 0;
  }
  
  .control-panel button {
    width: 38px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    color: #94a3b8;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .control-panel button:hover {
    background: rgba(59, 130, 246, 0.15);
    border-color: rgba(59, 130, 246, 0.3);
    color: #e2e8f0;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  }
  
  .control-panel button:active {
    transform: translateY(0);
  }
  
  .control-panel button.active {
    background: rgba(217, 70, 239, 0.2);
    border-color: rgba(217, 70, 239, 0.4);
    color: #d946ef;
    box-shadow: 0 0 12px rgba(217, 70, 239, 0.3);
  }

  /* 统计栏 */
  .stats-bar {
    position: absolute;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
  }
  
  .stats-container {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 24px;
    background: linear-gradient(145deg, rgba(15, 23, 42, 0.92) 0%, rgba(10, 15, 26, 0.92) 100%);
    border: 1px solid rgba(59, 130, 246, 0.12);
    border-radius: 20px;
    backdrop-filter: blur(12px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }
  
  .stat-item {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .stat-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  
  .stat-item.alive .stat-dot {
    background: #22c55e;
    box-shadow: 0 0 12px rgba(34, 197, 94, 0.5);
  }
  
  .stat-item.extinct .stat-dot {
    background: #ef4444;
    box-shadow: 0 0 12px rgba(239, 68, 68, 0.5);
  }
  
  .stat-item.total {
    color: #60a5fa;
  }
  
  .stat-item.collapsed {
    color: #a78bfa;
  }
  
  .stat-label {
    color: rgba(148, 163, 184, 0.7);
    font-size: 0.8rem;
  }
  
  .stat-value {
    color: #f1f5f9;
    font-size: 1rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
  }
  
  .stat-divider {
    width: 1px;
    height: 20px;
    background: rgba(148, 163, 184, 0.15);
  }
  
  .stats-container.focused {
    border-color: rgba(251, 191, 36, 0.3);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), 0 0 20px rgba(251, 191, 36, 0.1);
  }
  
  .stat-item.focus-mode {
    color: #fbbf24;
  }
  
  .stat-total {
    font-size: 0.75rem;
    font-weight: 400;
    color: rgba(148, 163, 184, 0.5);
  }

  /* Tooltip */
  .tooltip {
    position: fixed;
    background: linear-gradient(145deg, rgba(10, 15, 26, 0.98) 0%, rgba(15, 23, 42, 0.98) 100%);
    padding: 16px 18px;
    border-radius: 14px;
    border: 1px solid rgba(59, 130, 246, 0.2);
    backdrop-filter: blur(16px);
    z-index: 1000;
    pointer-events: none;
    min-width: 200px;
    box-shadow: 
      0 20px 40px -8px rgba(0, 0, 0, 0.6),
      0 0 0 1px rgba(255, 255, 255, 0.05) inset,
      0 0 30px rgba(59, 130, 246, 0.08);
  }
  
  .tooltip-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }
  
  .tooltip-name {
    font-size: 1rem;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.01em;
  }
  
  .tooltip-status {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
  }
  
  .tooltip-status.alive {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
  }
  
  .tooltip-status.extinct {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }
  
  .tooltip-code {
    font-size: 0.8rem;
    font-family: 'JetBrains Mono', monospace;
    color: #64748b;
    padding: 5px 10px;
    background: rgba(30, 41, 59, 0.5);
    border-radius: 6px;
    display: inline-block;
    margin-bottom: 12px;
  }
  
  .tooltip-tags {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
  }
  
  .tooltip-tag {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid;
  }
  
  .tooltip-tag.rank {
    background: rgba(139, 92, 246, 0.15);
    border-color: rgba(139, 92, 246, 0.3);
    color: #a78bfa;
  }
  
  .tooltip-hybrid {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding: 8px 10px;
    background: rgba(217, 70, 239, 0.1);
    border: 1px solid rgba(217, 70, 239, 0.2);
    border-radius: 6px;
  }
  
  .hybrid-label {
    font-size: 0.7rem;
    color: rgba(217, 70, 239, 0.8);
    font-weight: 600;
  }
  
  .hybrid-parents {
    font-size: 0.8rem;
    font-family: 'JetBrains Mono', monospace;
    color: #d946ef;
    font-weight: 600;
  }
  
  .tooltip-stats {
    display: flex;
    gap: 16px;
    padding: 10px 12px;
    background: rgba(30, 41, 59, 0.4);
    border-radius: 8px;
  }
  
  .tooltip-stat {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .stat-key {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.7);
  }
  
  .stat-val {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e2e8f0;
  }
  
  .tooltip-hint {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px dashed rgba(148, 163, 184, 0.2);
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.5);
    text-align: center;
    font-style: italic;
  }

  /* 图例 */
  .legend {
    position: absolute;
    bottom: 20px;
    right: 20px;
    background: linear-gradient(145deg, rgba(10, 15, 26, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%);
    border: 1px solid rgba(59, 130, 246, 0.12);
    border-radius: 14px;
    padding: 16px 18px;
    font-size: 0.8rem;
    color: #94a3b8;
    backdrop-filter: blur(12px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    min-width: 150px;
  }
  
  .legend-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    color: #f1f5f9;
    font-size: 0.85rem;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(59, 130, 246, 0.15);
  }
  
  .legend-group {
    margin-bottom: 12px;
  }
  
  .legend-group:last-child {
    margin-bottom: 0;
  }
  
  .legend-title {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: rgba(148, 163, 184, 0.5);
    margin-bottom: 8px;
    font-weight: 600;
  }
  
  .legend-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 0;
    font-size: 0.75rem;
  }
  
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  .legend-dot.alive {
    background: #22c55e;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
  }
  
  .legend-dot.extinct {
    background: #ef4444;
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
  }
  
  .legend-bar {
    width: 5px;
    height: 18px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  
  .legend-line {
    width: 28px;
    height: 0;
    flex-shrink: 0;
  }
  
  .legend-line.solid {
    border-top: 2.5px solid #475569;
  }
  
  .legend-line.dashed {
    border-top: 2px dashed #8b5cf6;
  }
  
  .legend-line.dashed.purple {
    border-color: #d946ef;
  }
  
  .legend-line.dashed.violet {
    border-color: #8b5cf6;
  }
  
  /* CK3风格直线拐角图例 */
  .legend-line-ortho {
    width: 20px;
    height: 14px;
    position: relative;
    flex-shrink: 0;
  }
  
  .legend-line-ortho::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 2px;
    height: 8px;
    background: #475569;
  }
  
  .legend-line-ortho::after {
    content: '';
    position: absolute;
    left: 0;
    top: 7px;
    width: 20px;
    height: 2px;
    background: #475569;
  }
  
  .legend-line-ortho.solid::before,
  .legend-line-ortho.solid::after {
    background: #475569;
  }
  
  .legend-line-ortho.dashed::before {
    background: repeating-linear-gradient(
      to bottom,
      #a78bfa 0px,
      #a78bfa 3px,
      transparent 3px,
      transparent 5px
    );
  }
  
  .legend-line-ortho.dashed::after {
    background: repeating-linear-gradient(
      to right,
      #a78bfa 0px,
      #a78bfa 3px,
      transparent 3px,
      transparent 5px
    );
  }
  
  /* 快捷键样式 */
  .legend-group.shortcuts {
    border-top: 1px solid rgba(59, 130, 246, 0.1);
    padding-top: 8px;
    margin-top: 4px;
  }
  
  .shortcut-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.7rem;
    padding: 2px 0;
    color: rgba(148, 163, 184, 0.7);
  }
  
  .shortcut-item kbd {
    padding: 2px 5px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(100, 116, 139, 0.3);
    border-radius: 3px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: #94a3b8;
    min-width: 20px;
    text-align: center;
  }
`;
