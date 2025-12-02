/**
 * GenealogyGraphView 常量定义
 */

// ============ 颜色 ============
export const COLORS = {
  // 状态色
  ALIVE: 0x22c55e,
  EXTINCT: 0xef4444,
  
  // 背景
  BACKGROUND: 0x4b5563,
  
  // 生态角色色
  PRODUCER: 0x10b981,
  HERBIVORE: 0xfbbf24,
  CARNIVORE: 0xf43f5e,
  OMNIVORE: 0xf97316,
  MIXOTROPH: 0x22d3ee,
  DECOMPOSER: 0xa78bfa,
  DEFAULT: 0xffffff,
  
  // 交互色
  SELECTED: 0x3b82f6,
  SUBSPECIES: 0x8b5cf6,
  HYBRID: 0xd946ef,
  
  // 文字
  TEXT_MAIN: 0xffffff,
  TEXT_SUB: 0x9ca3af,
  
  // 连线
  LINK_NORMAL: 0x475569,
  LINK_ACTIVE: 0x94a3b8,
  
  // 根节点
  ROOT_GOLD: 0xfbbf24,
  ROOT_GLOW: 0xf59e0b,
  
  // 折叠按钮
  COLLAPSE_BTN: 0x64748b,
  COLLAPSE_BTN_HOVER: 0x94a3b8,
} as const;

// ============ 特殊节点 ============
export const ROOT_NAME = "始祖物种";
export const ROOT_CODE = "ROOT";

// ============ 默认参数 ============
export const DEFAULT_SPACING_X = 160;
export const DEFAULT_SPACING_Y = 120;

// ============ 相机默认值 ============
export const DEFAULT_CAMERA = {
  x: 400,
  y: 80,
  zoom: 0.7,
} as const;

// ============ 缩放限制 ============
export const ZOOM_MIN = 0.1;
export const ZOOM_MAX = 5;
export const ZOOM_STEP = 1.2;

// ============ 节点尺寸 ============
export const NODE_SIZE = {
  width: 140,
  height: 60,
  borderRadius: 8,
  padding: 8,
} as const;

// ============ 动画参数 ============
export const ANIMATION = {
  liftDuration: 0.15,
  scaleDuration: 0.2,
  flowSpeed: 0.02,
} as const;

// ============ 营养级颜色映射 ============
export function getTrophicColor(trophicLevel: number): number {
  if (trophicLevel <= 1) return COLORS.PRODUCER;
  if (trophicLevel <= 2) return COLORS.HERBIVORE;
  if (trophicLevel <= 3) return COLORS.OMNIVORE;
  if (trophicLevel <= 4) return COLORS.CARNIVORE;
  return COLORS.CARNIVORE;
}

// ============ 生态角色颜色映射 ============
export function getRoleColor(role: string): number {
  switch (role) {
    case "producer":
      return COLORS.PRODUCER;
    case "herbivore":
      return COLORS.HERBIVORE;
    case "carnivore":
      return COLORS.CARNIVORE;
    case "omnivore":
      return COLORS.OMNIVORE;
    case "mixotroph":
      return COLORS.MIXOTROPH;
    case "decomposer":
      return COLORS.DECOMPOSER;
    default:
      return COLORS.DEFAULT;
  }
}

// ============ 状态颜色映射 ============
export function getStateColor(state: string): number {
  return state === "alive" ? COLORS.ALIVE : COLORS.EXTINCT;
}



