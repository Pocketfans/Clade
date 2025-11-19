# 前端性能优化计划：GPU 加速与渲染迁移

## 1. 问题诊断
用户反馈前端页面操作卡顿，目标是达到 60fps 并利用 GPU 加速。
经过代码审查，发现性能瓶颈主要位于 **地图渲染组件 (`MapPanel.tsx`)**。

### 现状分析
- **渲染技术**：使用 DOM (`div` + `button`) 渲染六边形瓦片。
- **数据规模**：默认地图大小 80x40 = 3200 个瓦片。
- **性能瓶颈**：
  - **DOM 节点过多**：3200+ 个绝对定位的 DOM 节点会导致浏览器 Layout 和 Paint 开销巨大。
  - **React Reconciliation**：每次缩放、平移或数据更新，React 需要比对数千个虚拟 DOM 节点，占用大量主线程时间。
  - **GPU 利用率低**：虽然使用了 `translate3d` 开启合成层，但每个瓦片的绘制仍在 CPU 上进行（Paint 阶段）。

## 2. 优化方案：Canvas/WebGL 迁移
将地图渲染层从 DOM 迁移到 HTML5 Canvas (2D Context) 或 WebGL。
考虑到项目并未引入 PixiJS/Three.js 等重型库，且 2D Canvas 足以处理 10k 级物体，我们选择 **原生 Canvas 2D** 方案。这将避免引入新依赖，同时提供原生 GPU 加速（现代浏览器默认开启 Canvas 2D GPU 加速）。

### Canvas 方案优势
- **零 DOM 开销**：整个地图只有一个 `<canvas>` 元素。
- **即时模式渲染**：每帧直接绘制像素，完全绕过 React Diff 和 DOM Layout。
- **高性能**：轻松处理 10,000+ 静态/动态图元，稳定 60fps。
- **易于实现**：基于现有的坐标计算逻辑，只需重写绘制循环。

## 3. 实施步骤
1.  **创建 `CanvasMapPanel`**：
    -   实现与原 `MapPanel` 相同的 Props 接口。
    -   使用 `requestAnimationFrame` 实现平滑的拖拽和缩放。
    -   实现点击检测（将屏幕坐标转换为六边形网格坐标）。
    -   复用现有的颜色和视图模式逻辑。
2.  **替换 `App.tsx` 中的组件**：
    -   将 `MapPanel` 替换为 `CanvasMapPanel`。
3.  **验证效果**：
    -   检查帧率。
    -   检查内存使用。

## 4. 其他潜在优化 (Backlog)
-   **GenealogyGraphView**: 目前使用 D3 + SVG。如果族谱节点超过 1000，也建议迁移到 Canvas (或 D3 + Canvas)。
-   **FoodWebGraph**: 已经使用了 `react-force-graph-2d` (Canvas)，应该性能尚可。需关注数据更新频率。
