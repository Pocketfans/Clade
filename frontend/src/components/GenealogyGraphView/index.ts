/**
 * GenealogyGraphView 模块导出
 * 
 * 重构后的结构：
 * - types.ts: 类型定义
 * - constants.ts: 颜色和配置常量
 * - hooks/: 相机、折叠等 hooks
 * - utils/: 布局计算工具
 */

// 主组件 - 暂时从原文件导入
export { GenealogyGraphView } from "../GenealogyGraphView.tsx";

// 类型
export type {
  GenealogyGraphViewProps,
  NodeVisual,
  LinkVisual,
  FlowParticle,
  CameraState,
  LayoutNode,
  TooltipData,
} from "./types";

// 常量
export {
  COLORS,
  ROOT_NAME,
  ROOT_CODE,
  DEFAULT_SPACING_X,
  DEFAULT_SPACING_Y,
  DEFAULT_CAMERA,
  ZOOM_MIN,
  ZOOM_MAX,
  ZOOM_STEP,
  NODE_SIZE,
  ANIMATION,
  getTrophicColor,
  getRoleColor,
  getStateColor,
} from "./constants";

// Hooks
export { useCamera } from "./hooks/useCamera";
export { useCollapse } from "./hooks/useCollapse";

// 布局工具
export {
  buildHierarchy,
  calculateTreeLayout,
  getNodePositions,
  getLinks,
  getLayoutBounds,
  type LinkData,
} from "./utils/layout";




