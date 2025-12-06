/**
 * SpeciesPanel 工具函数
 */

import { TrendingUp, TrendingDown, Minus, Skull } from "lucide-react";
import type { TrendInfo } from "./types";

/**
 * 根据种群变化计算趋势
 */
export function getTrend(
  currentPop: number,
  previousPop: number | undefined,
  status: string
): TrendInfo {
  if (status === "extinct") {
    return {
      icon: Skull,
      color: "#64748b",
      label: "灭绝",
      bg: "rgba(100, 116, 139, 0.12)",
      emoji: "💀",
    };
  }

  if (previousPop === undefined || previousPop === 0) {
    return {
      icon: Minus,
      color: "#94a3b8",
      label: "稳定",
      bg: "rgba(148, 163, 184, 0.12)",
      emoji: "➖",
    };
  }

  const changeRate = (currentPop - previousPop) / previousPop;

  if (changeRate > 0.5) {
    return {
      icon: TrendingUp,
      color: "#22c55e",
      label: "繁荣",
      bg: "rgba(34, 197, 94, 0.15)",
      emoji: "🚀",
    };
  }
  if (changeRate > 0.1) {
    return {
      icon: TrendingUp,
      color: "#4ade80",
      label: "增长",
      bg: "rgba(74, 222, 128, 0.12)",
      emoji: "📈",
    };
  }
  if (changeRate < -0.5) {
    return {
      icon: TrendingDown,
      color: "#ef4444",
      label: "危急",
      bg: "rgba(239, 68, 68, 0.15)",
      emoji: "🔥",
    };
  }
  if (changeRate < -0.2) {
    return {
      icon: TrendingDown,
      color: "#f97316",
      label: "衰退",
      bg: "rgba(249, 115, 22, 0.12)",
      emoji: "📉",
    };
  }
  if (changeRate < -0.1) {
    return {
      icon: TrendingDown,
      color: "#fbbf24",
      label: "下降",
      bg: "rgba(251, 191, 36, 0.12)",
      emoji: "⚠️",
    };
  }

  return {
    icon: Minus,
    color: "#94a3b8",
    label: "稳定",
    bg: "rgba(148, 163, 184, 0.12)",
    emoji: "➖",
  };
}

/**
 * 格式化种群数字
 */
export function formatPopulation(pop: number): string {
  if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
  if (pop >= 1_000) return `${(pop / 1_000).toFixed(1)}K`;
  return pop.toString();
}

/**
 * 格式化数字
 */
export function formatNumber(num: number, decimals = 1): string {
  return num.toFixed(decimals);
}

/**
 * 计算种群变化百分比
 */
export function calculateChangePercent(current: number, previous: number | undefined): number {
  if (!previous || previous === 0) return 0;
  return ((current - previous) / previous) * 100;
}

/**
 * 格式化变化百分比
 */
export function formatChangePercent(current: number, previous: number | undefined): string {
  const percent = calculateChangePercent(current, previous);
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}%`;
}









