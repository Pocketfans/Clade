/**
 * SpeciesPanel 常量定义
 */

import type { RoleConfig } from "./types";

// ============ 生态角色配置 ============
export const ROLE_CONFIGS: Record<string, RoleConfig> = {
  producer: {
    color: "#22c55e",
    gradient: "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
    bgGradient: "linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(22, 163, 74, 0.08) 100%)",
    icon: "🌿",
    label: "生产者",
    description: "光合作用的基石",
  },
  herbivore: {
    color: "#eab308",
    gradient: "linear-gradient(135deg, #eab308 0%, #ca8a04 100%)",
    bgGradient: "linear-gradient(135deg, rgba(234, 179, 8, 0.15) 0%, rgba(202, 138, 4, 0.08) 100%)",
    icon: "🦌",
    label: "食草动物",
    description: "植被的消费者",
  },
  carnivore: {
    color: "#ef4444",
    gradient: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
    bgGradient: "linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(220, 38, 38, 0.08) 100%)",
    icon: "🦁",
    label: "食肉动物",
    description: "顶级掠食者",
  },
  omnivore: {
    color: "#f97316",
    gradient: "linear-gradient(135deg, #f97316 0%, #ea580c 100%)",
    bgGradient: "linear-gradient(135deg, rgba(249, 115, 22, 0.15) 0%, rgba(234, 88, 12, 0.08) 100%)",
    icon: "🐻",
    label: "杂食动物",
    description: "适应性强的觅食者",
  },
  decomposer: {
    color: "#a855f7",
    gradient: "linear-gradient(135deg, #a855f7 0%, #9333ea 100%)",
    bgGradient: "linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(147, 51, 234, 0.08) 100%)",
    icon: "🍄",
    label: "分解者",
    description: "生态循环的清道夫",
  },
  scavenger: {
    color: "#64748b",
    gradient: "linear-gradient(135deg, #64748b 0%, #475569 100%)",
    bgGradient: "linear-gradient(135deg, rgba(100, 116, 139, 0.15) 0%, rgba(71, 85, 105, 0.08) 100%)",
    icon: "🦅",
    label: "食腐动物",
    description: "资源的回收者",
  },
  mixotroph: {
    color: "#22d3ee",
    gradient: "linear-gradient(135deg, #22d3ee 0%, #06b6d4 100%)",
    bgGradient: "linear-gradient(135deg, rgba(34, 211, 238, 0.15) 0%, rgba(6, 182, 212, 0.08) 100%)",
    icon: "🔬",
    label: "混合营养",
    description: "既能自养又能捕食",
  },
  unknown: {
    color: "#3b82f6",
    gradient: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    bgGradient: "linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(37, 99, 235, 0.08) 100%)",
    icon: "🧬",
    label: "未知",
    description: "神秘的生命形式",
  },
};

// ============ 获取角色配置 ============
export function getRoleConfig(role: string): RoleConfig {
  return ROLE_CONFIGS[role] || ROLE_CONFIGS.unknown;
}

// ============ 状态配色 ============
export const STATUS_COLORS = {
  alive: {
    color: "#22c55e",
    bg: "rgba(34, 197, 94, 0.1)",
    border: "rgba(34, 197, 94, 0.3)",
    label: "存活",
    icon: "✓",
  },
  extinct: {
    color: "#ef4444",
    bg: "rgba(239, 68, 68, 0.1)",
    border: "rgba(239, 68, 68, 0.3)",
    label: "灭绝",
    icon: "💀",
  },
} as const;

// ============ 趋势配色 ============
export const TREND_COLORS = {
  up: { color: "#22c55e", icon: "↑" },
  down: { color: "#ef4444", icon: "↓" },
  stable: { color: "#64748b", icon: "→" },
} as const;

// ============ 详情标签页配置 ============
export const DETAIL_TABS = [
  { id: "overview" as const, label: "概览", icon: "📊" },
  { id: "stats" as const, label: "属性", icon: "📈" },
  { id: "ai" as const, label: "AI", icon: "🤖" },
  { id: "history" as const, label: "历史", icon: "📜" },
];
