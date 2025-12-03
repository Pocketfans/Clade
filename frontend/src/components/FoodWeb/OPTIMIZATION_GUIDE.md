# 食物网前端性能优化指南

本文档提供食物网可视化组件的性能优化建议。

## 1. 虚拟化与按需展开

### 1.1 初始渲染策略

```typescript
// 推荐：初始只渲染当前物种的局部网络
interface FoodWebViewProps {
  centerSpecies?: string;  // 中心物种
  initialHops: number;     // 初始展开层数 (默认 1-2)
  maxNodes: number;        // 最大节点数 (默认 50)
}

// 调用 API 时使用 k-hop 参数
const fetchNeighborhood = async (code: string, kHop: number) => {
  const response = await fetch(
    `/api/ecosystem/food-web/${code}?k_hop=${kHop}&max_nodes=50`
  );
  return response.json();
};
```

### 1.2 按需展开更多层级

```typescript
// 点击节点时展开下一层
const handleNodeClick = async (nodeId: string) => {
  // 检查是否已加载
  if (loadedNodes.has(nodeId)) return;
  
  // 单独请求该节点的邻居
  const neighbors = await fetchNeighborhood(nodeId, 1);
  
  // 增量添加到图中
  setNodes(prev => [...prev, ...neighbors.nodes.filter(n => !prev.find(p => p.id === n.id))]);
  setLinks(prev => [...prev, ...neighbors.links]);
  
  loadedNodes.add(nodeId);
};
```

## 2. 链路抽样与聚合

### 2.1 高连接度节点聚合

```typescript
// 对于连接数 > 10 的节点，显示汇总连线
const aggregateHighDegreeNodes = (nodes: Node[], links: Link[]) => {
  const THRESHOLD = 10;
  
  return nodes.map(node => {
    const connections = links.filter(l => l.source === node.id || l.target === node.id);
    
    if (connections.length > THRESHOLD) {
      return {
        ...node,
        isAggregated: true,
        aggregatedCount: connections.length,
        // 只显示前 5 条主要连接
        visibleLinks: connections.slice(0, 5),
      };
    }
    return node;
  });
};
```

### 2.2 延迟加载详细链接

```typescript
// 放大或点击时展开具体猎物列表
const handleNodeExpand = async (nodeId: string) => {
  const fullLinks = await fetch(
    `/api/ecosystem/food-web/${nodeId}?include_preferences=true`
  );
  // 替换聚合链接为完整链接
  updateNodeLinks(nodeId, fullLinks);
};
```

## 3. 分段/流式加载

### 3.1 分块请求

```typescript
// 大型食物网分批加载
const loadFoodWebInChunks = async (chunkSize = 100) => {
  let offset = 0;
  let hasMore = true;
  
  while (hasMore) {
    const chunk = await fetch(
      `/api/ecosystem/food-web?max_nodes=${chunkSize}&offset=${offset}`
    );
    const data = await chunk.json();
    
    // 渐进式添加到画布
    appendToGraph(data.nodes, data.links);
    
    offset += chunkSize;
    hasMore = data.has_more_nodes;
    
    // 让出主线程
    await new Promise(resolve => requestAnimationFrame(resolve));
  }
};
```

### 3.2 优先加载可见区域

```typescript
// 基于视口优先加载
const loadVisibleFirst = async (viewport: Viewport) => {
  // 1. 先加载视口内的节点
  const visibleNodes = await fetch(
    `/api/ecosystem/food-web?trophic_levels=2,3&max_nodes=30`
  );
  
  // 2. 后台加载其余节点
  setTimeout(() => loadRemainingNodes(), 500);
};
```

## 4. WebWorker 力导向计算

### 4.1 创建 Worker

```typescript
// foodWebWorker.ts
self.onmessage = (e: MessageEvent) => {
  const { nodes, links, iterations } = e.data;
  
  // 在 Worker 中执行力导向布局计算
  const positions = computeForceLayout(nodes, links, iterations);
  
  self.postMessage({ type: 'layout', positions });
};

const computeForceLayout = (nodes, links, iterations) => {
  // d3-force 或自定义实现
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id))
    .force('charge', d3.forceManyBody().strength(-100))
    .force('center', d3.forceCenter(0, 0));
  
  for (let i = 0; i < iterations; i++) {
    simulation.tick();
  }
  
  return nodes.map(n => ({ id: n.id, x: n.x, y: n.y }));
};
```

### 4.2 主线程使用

```typescript
// FoodWebCanvas.tsx
const worker = new Worker('./foodWebWorker.ts');

worker.onmessage = (e) => {
  if (e.data.type === 'layout') {
    // 只在主线程更新位置和绑定
    updateNodePositions(e.data.positions);
  }
};

// 发送数据给 Worker 计算
worker.postMessage({ nodes, links, iterations: 300 });
```

## 5. 请求去抖与缓存

### 5.1 前端缓存

```typescript
// useQueryCache.ts
const queryCache = new Map<string, { data: any; timestamp: number }>();
const CACHE_TTL = 30000; // 30秒

const fetchWithCache = async (url: string) => {
  const cached = queryCache.get(url);
  
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }
  
  const response = await fetch(url);
  const data = await response.json();
  
  // 检查后端是否命中缓存
  if (data.cache_hit) {
    // 后端已缓存，前端缓存时间可以更长
  }
  
  queryCache.set(url, { data, timestamp: Date.now() });
  return data;
};
```

### 5.2 搜索/过滤去抖

```typescript
// useDebouncedSearch.ts
import { useDebouncedCallback } from 'use-debounce';

const FoodWebSearch = () => {
  const [searchTerm, setSearchTerm] = useState('');
  
  const debouncedSearch = useDebouncedCallback(
    (term: string) => {
      if (term.length < 2) return;
      fetchFoodWeb({ search: term });
    },
    300 // 300ms 去抖
  );
  
  return (
    <input
      value={searchTerm}
      onChange={(e) => {
        setSearchTerm(e.target.value);
        debouncedSearch(e.target.value);
      }}
    />
  );
};
```

## 6. API 使用建议

### 6.1 简版响应

```typescript
// 仪表盘使用简版 API
const fetchDashboardSummary = () => {
  return fetch('/api/ecosystem/food-web/summary');
};

// 详细分析使用 simple 模式
const fetchAnalysis = () => {
  return fetch('/api/ecosystem/food-web/analysis?detail_level=simple');
};
```

### 6.2 字段过滤

```typescript
// 只请求必要字段
const fetchMinimalNodes = () => {
  return fetch('/api/ecosystem/food-web?detail_level=simple&include_preferences=false');
};
```

## 7. 渲染优化

### 7.1 Canvas vs SVG

```typescript
// 节点数 > 100 时使用 Canvas
const useCanvas = nodes.length > 100;

if (useCanvas) {
  // 使用 @visx/visx 或 react-konva
  return <CanvasFoodWeb nodes={nodes} links={links} />;
} else {
  // 节点少时 SVG 更灵活
  return <SVGFoodWeb nodes={nodes} links={links} />;
}
```

### 7.2 节点分层渲染

```typescript
// 按营养级分层，减少重叠
const renderByTrophicLevel = (nodes: Node[]) => {
  const levels = groupBy(nodes, 'trophic_level');
  
  return Object.entries(levels).map(([level, levelNodes]) => (
    <g key={level} className={`trophic-level-${level}`}>
      {levelNodes.map(node => <NodeComponent key={node.id} node={node} />)}
    </g>
  ));
};
```

## 8. 性能监控

```typescript
// 使用 Performance API 监控
const measureRender = () => {
  const start = performance.now();
  
  // 渲染逻辑...
  
  const duration = performance.now() - start;
  if (duration > 100) {
    console.warn(`食物网渲染耗时 ${duration.toFixed(1)}ms，考虑优化`);
  }
};
```

## API 快速参考

| 端点 | 用途 | 关键参数 |
|------|------|----------|
| `GET /ecosystem/food-web` | 全局食物网 | `max_nodes`, `offset`, `trophic_levels`, `detail_level` |
| `GET /ecosystem/food-web/{code}` | 物种邻域 | `k_hop`, `max_nodes` |
| `GET /ecosystem/food-web/summary` | 仪表盘摘要 | 无（轻量级） |
| `GET /ecosystem/food-web/analysis` | 健康分析 | `detail_level` |




