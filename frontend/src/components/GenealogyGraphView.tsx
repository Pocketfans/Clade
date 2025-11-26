import { useEffect, useRef, useState } from "react";
import { Application, Container, Graphics, Text, Ticker, BlurFilter } from "pixi.js";
import * as d3 from "d3";
import type { LineageNode } from "../services/api.types";

interface Props {
  nodes: LineageNode[];
  spacingX?: number;
  spacingY?: number;
  onNodeClick?: (node: LineageNode) => void;
}

// Colors in Hex
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
};

interface NodeVisual {
    container: Container;
    innerGroup: Container; 
    border: Graphics;
    shadow: Graphics;
    
    baseX: number;
    baseY: number;
    
    targetX: number; // For magnetic translation
    targetY: number; 
    
    targetLift: number; // For Z-axis lift (innerGroup y offset)
    targetScale: number; // Zoom
    targetShadowAlpha: number;
    targetShadowScale: number;
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
  // No static path anymore
  linkVisual: LinkVisual; 
  graphics: Graphics;
  color: number;
}

export function GenealogyGraphView({ nodes, spacingX = 200, spacingY = 80, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  
  const appRef = useRef<Application | null>(null);
  const stageRef = useRef<Container | null>(null);
  
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<LineageNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [pixiReady, setPixiReady] = useState(false);

  const cameraRef = useRef({ x: 100, y: 300, zoom: 0.8 }); 
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 }); // Used for dragging
  const currentMousePos = useRef({ x: 0, y: 0 }); // Used for magnetic effect
  
  const particlesRef = useRef<FlowParticle[]>([]);
  const nodeVisualsRef = useRef<Map<string, NodeVisual>>(new Map());
  const linkVisualsRef = useRef<LinkVisual[]>([]);

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
          background: '#0f172a', 
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
            // Update links AFTER nodes moved
            updateLinks();
            // Update particles AFTER links moved
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
      // Reduced Magnetic Params
      const magneticStrength = 0.15; // Reduced from 0.3
      const magneticRange = 80;      // Reduced from 200
      const maxDisplacement = 20;    // Clamp max movement
      
      // Transform mouse pos to world space
      const zoom = cameraRef.current.zoom;
      const camX = cameraRef.current.x;
      const camY = cameraRef.current.y;
      const mouseWorldX = (currentMousePos.current.x - camX) / zoom;
      const mouseWorldY = (currentMousePos.current.y - camY) / zoom;

      nodeVisualsRef.current.forEach((vis) => {
          // --- Magnetic Effect Calculation ---
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
              
              // Clamp displacement
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
      const NODE_W = 120;
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
     const NODE_W = 120;
     const NODE_OFFSET_X = NODE_W / 2;
     
     const particles = particlesRef.current;
     for (let i = particles.length - 1; i >= 0; i--) {
         const p = particles[i];
         p.t += p.speed * delta;
         if (p.t >= 1) p.t = 0;
         
         // Dynamic path calculation based on current node positions
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

  // Build Graph
  useEffect(() => {
    if (!pixiReady || !appRef.current || !stageRef.current) return;
    
    const stage = stageRef.current;
    
    stage.removeChildren();
    particlesRef.current = [];
    nodeVisualsRef.current.clear();
    linkVisualsRef.current = [];
    
    if (nodes.length === 0) {
        const text = new Text({ text: "Waiting for Species Data...", style: { fill: 0x64748b, fontSize: 24 } });
        text.anchor.set(0.5);
        stage.addChild(text);
        return;
    }

    const root = buildHierarchy(nodes);
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
    
    // 1. Create Nodes FIRST (so we can reference them)
    descendants.forEach(node => {
        const nodeContainer = new Container();
        nodeContainer.position.set(node.y, node.x);
        
        nodeContainer.eventMode = 'static';
        nodeContainer.cursor = 'pointer';
        nodeContainer.on('pointerdown', (e) => {
            e.stopPropagation();
            setSelectedNode(node.data.lineage_code);
            onNodeClick?.(node.data);
        });
        nodeContainer.on('pointerenter', (e) => {
            setHoveredNode(node.data);
            setTooltipPos({ x: e.global.x, y: e.global.y });
        });
        nodeContainer.on('pointermove', (e) => {
             if (hoveredNode === node.data) {
                 setTooltipPos({ x: e.global.x, y: e.global.y });
             }
        });
        nodeContainer.on('pointerleave', () => setHoveredNode(null));

        const isAlive = node.data.state === 'alive';
        const roleColor = getNodeColorHex(node.data);
        
        const shadow = new Graphics();
        shadow.roundRect(-55, -15, 110, 30, 15); 
        shadow.fill({ color: 0x000000, alpha: 1 });
        shadow.filters = [new BlurFilter({ strength: 15, quality: 3 })]; 
        shadow.alpha = 0; 
        shadow.position.set(0, 15); 
        nodeContainer.addChild(shadow);

        const innerGroup = new Container();
        const mask = new Graphics();
        mask.roundRect(-60, -20, 120, 40, 8);
        mask.fill(0xffffff);
        
        const bg = new Graphics();
        bg.rect(-60, -20, 120, 40);
        bg.fill({ color: 0x1e293b, alpha: 0.9 }); 
        
        const indicator = new Graphics();
        indicator.rect(-60, -20, 6, 40);
        indicator.fill({ color: roleColor });
        
        const contentContainer = new Container();
        contentContainer.addChild(bg);
        contentContainer.addChild(indicator);
        contentContainer.mask = mask;
        
        innerGroup.addChild(mask);
        innerGroup.addChild(contentContainer);
        
        const border = new Graphics();
        border.roundRect(-60, -20, 120, 40, 8);
        border.stroke({ 
            width: 1, 
            color: isAlive ? roleColor : COLORS.EXTINCT,
            alpha: isAlive ? 1 : 0.5 
        });
        innerGroup.addChild(border);

        const TEXT_SCALE = 0.25;
        const nameText = new Text({
            text: node.data.lineage_code,
            style: {
                fontFamily: 'Inter, Arial, sans-serif',
                fontSize: 56,
                fontWeight: 'bold',
                fill: isAlive ? COLORS.TEXT_MAIN : 0x64748b,
            }
        });
        nameText.scale.set(TEXT_SCALE);
        nameText.anchor.set(0, 0.5);
        nameText.position.set(-48, -5);
        
        const commonName = node.data.common_name || "Unknown";
        const subText = new Text({
            text: commonName.length > 12 ? commonName.substring(0, 11) + '..' : commonName,
            style: {
                fontFamily: 'Inter, Arial, sans-serif',
                fontSize: 44,
                fill: COLORS.TEXT_SUB,
            }
        });
        subText.scale.set(TEXT_SCALE);
        subText.anchor.set(0, 0.5);
        subText.position.set(-48, 10);

        innerGroup.addChild(nameText);
        innerGroup.addChild(subText);
        
        nodeContainer.addChild(innerGroup);
        nodesLayer.addChild(nodeContainer);

        nodeVisualsRef.current.set(node.data.lineage_code, {
            container: nodeContainer,
            innerGroup,
            border,
            shadow,
            baseX: node.y, 
            baseY: node.x,
            targetX: node.y,
            targetY: node.x,
            targetLift: 0,
            targetScale: 1,
            targetShadowAlpha: 0,
            targetShadowScale: 0.8
        });
    });

    // 2. Create Links
    const createLink = (sourceCode: string, targetCode: string, isSubspecies: boolean, isExtinct: boolean, isHybrid = false) => {
        const linkG = new Graphics();
        const color = isSubspecies ? COLORS.SUBSPECIES : (isHybrid ? COLORS.HYBRID : COLORS.LINK_NORMAL);
        const alpha = isExtinct ? 0.3 : 0.6;
        const width = isSubspecies ? 1 : 2;
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
        
        // Add Particle
        if (!isExtinct) {
            const pG = new Graphics();
            pG.circle(0, 0, 2);
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
    
    descendants.forEach(node => {
        if (node.data.hybrid_parent_codes && node.data.hybrid_parent_codes.length >= 2) {
             const p0Code = node.data.hybrid_parent_codes[0];
             const p1Code = node.data.hybrid_parent_codes[1];
             
             // Check if parents exist in current tree
             if (nodeVisualsRef.current.has(p0Code) && nodeVisualsRef.current.has(p1Code)) {
                 createLink(p0Code, node.data.lineage_code, false, false, true);
                 createLink(p1Code, node.data.lineage_code, false, false, true);
             }
        }
    });

  }, [nodes, spacingX, spacingY, pixiReady]);

  // State Updates ... (Same as before)
  useEffect(() => {
      nodeVisualsRef.current.forEach((vis, code) => {
          const isSelected = code === selectedNode;
          const isHovered = code === hoveredNode?.lineage_code;
          
          if (isSelected) {
              vis.targetLift = -8; 
              vis.targetScale = 1.15;
              vis.targetShadowAlpha = 0.6;
              vis.targetShadowScale = 1.1;
              vis.container.zIndex = 100;
              
              vis.border.clear();
              vis.border.roundRect(-60, -20, 120, 40, 8);
              vis.border.stroke({ width: 2, color: COLORS.SELECTED, alpha: 1 });
          } else if (isHovered) {
              vis.targetLift = -5;
              vis.targetScale = 1.08;
              vis.targetShadowAlpha = 0.4;
              vis.targetShadowScale = 1.0;
              vis.container.zIndex = 50;
              
              const node = nodes.find(n => n.lineage_code === code);
              if (node) {
                  const roleColor = getNodeColorHex(node);
                  const isAlive = node.state === 'alive';
                  vis.border.clear();
                  vis.border.roundRect(-60, -20, 120, 40, 8);
                  vis.border.stroke({ width: 1.5, color: isAlive ? roleColor : COLORS.EXTINCT, alpha: 1 });
              }
          } else {
              vis.targetLift = 0;
              vis.targetScale = 1;
              vis.targetShadowAlpha = 0;
              vis.targetShadowScale = 0.8;
              vis.container.zIndex = 0;
              
              const node = nodes.find(n => n.lineage_code === code);
              if (node) {
                  const roleColor = getNodeColorHex(node);
                  const isAlive = node.state === 'alive';
                  vis.border.clear();
                  vis.border.roundRect(-60, -20, 120, 40, 8);
                  vis.border.stroke({ 
                    width: 1, 
                    color: isAlive ? roleColor : COLORS.EXTINCT,
                    alpha: isAlive ? 1 : 0.5 
                  });
              }
          }
      });
  }, [selectedNode, hoveredNode, nodes]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden", background: "#0f172a" }}>
      <div ref={canvasContainerRef} style={{ width: "100%", height: "100%", position: "absolute", top: 0, left: 0 }} />
      {hoveredNode && <Tooltip node={hoveredNode} pos={tooltipPos} />}
      <Legend />
    </div>
  );
}

// ... Helpers (same) ...
function buildHierarchy(nodes: LineageNode[]): d3.HierarchyNode<LineageNode> {
  if (nodes.length === 0) return d3.hierarchy({} as LineageNode);
  const roots = nodes.filter(n => !n.parent_code || n.parent_code === "ROOT");
  const nodeMap = new Set(nodes.map(n => n.lineage_code));
  const orphanRoots = nodes.filter(n => n.parent_code && !nodeMap.has(n.parent_code));
  const allRoots = [...roots, ...orphanRoots];
  const uniqueRoots = Array.from(new Set(allRoots));
  if (uniqueRoots.length === 0 && nodes.length > 0) return d3.hierarchy(nodes[0], n => nodes.filter(c => c.parent_code === n.lineage_code));
  if (uniqueRoots.length > 1) {
    const virtualRoot = { lineage_code: "ROOT", children: uniqueRoots } as any;
    return d3.hierarchy(virtualRoot, (d) => {
      if (d.lineage_code === "ROOT") return uniqueRoots;
      return nodes.filter(n => n.parent_code === d.lineage_code);
    });
  }
  return d3.hierarchy(uniqueRoots[0], (d) => nodes.filter(n => n.parent_code === d.lineage_code));
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

const Tooltip = ({ node, pos }: { node: LineageNode, pos: {x:number, y:number} }) => (
    <div style={{
      position: "fixed",
      left: `${pos.x + 20}px`,
      top: `${pos.y}px`,
      background: "rgba(15, 23, 42, 0.95)",
      padding: "12px",
      borderRadius: "8px",
      border: "1px solid rgba(59, 130, 246, 0.3)",
      backdropFilter: "blur(4px)",
      zIndex: 50,
      pointerEvents: "none",
      minWidth: "200px",
      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)"
    }}>
      <div style={{ color: "#f8fafc", fontWeight: "bold", fontSize: "14px", marginBottom: "4px" }}>
        {node.common_name}
      </div>
      <div style={{ color: "#94a3b8", fontSize: "12px", fontFamily: "monospace", marginBottom: "8px" }}>
        {node.lineage_code}
      </div>
      <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
        <Badge text={node.state} color={node.state === 'alive' ? "#22c55e" : "#ef4444"} />
        <Badge text={node.ecological_role} color="#cbd5e1" outline />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "11px", color: "#cbd5e1" }}>
          <div>Rank: {node.taxonomic_rank}</div>
          <div>Descendants: {node.descendant_count}</div>
      </div>
    </div>
);

const Badge = ({ text, color, outline }: { text: string, color: string, outline?: boolean }) => (
    <span style={{
        padding: "2px 6px",
        borderRadius: "4px",
        fontSize: "10px",
        textTransform: "uppercase",
        fontWeight: "bold",
        backgroundColor: outline ? "transparent" : color + "33",
        border: `1px solid ${outline ? color : "transparent"}`,
        color: outline ? color : color
    }}>
        {text}
    </span>
);

const Legend = () => (
    <div style={{
        position: "absolute",
        bottom: "20px",
        right: "20px",
        background: "rgba(15, 23, 42, 0.9)",
        border: "1px solid rgba(148, 163, 184, 0.2)",
        borderRadius: "8px",
        padding: "12px",
        fontSize: "12px",
        color: "#cbd5e1",
        display: "flex",
        flexDirection: "column",
        gap: "8px"
    }}>
        <div style={{ fontWeight: "bold", color: "#f1f5f9" }}>Legend</div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: 12, height: 12, background: "#22c55e", borderRadius: 2 }}></div>
            <span>Alive / 存活</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: 12, height: 12, background: "#ef4444", borderRadius: 2 }}></div>
            <span>Extinct / 灭绝</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: 20, height: 2, background: "#475569" }}></div>
            <span>Lineage / 演化</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: 20, height: 0, borderTop: "2px dashed #d946ef" }}></div>
            <span>Hybrid / 杂交</span>
        </div>
    </div>
);
