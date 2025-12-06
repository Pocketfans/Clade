/**
 * StatCard - 统计卡片组件
 */

import { memo, type ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { TrendDirection } from "../types";
import { THEME, TREND_COLORS } from "../theme";

interface StatCardProps {
  label: string;
  value: string;
  deltaText: string;
  trend: TrendDirection;
  accent: string;
  glow: string;
  icon: ReactNode;
}

export const StatCard = memo(function StatCard({
  label,
  value,
  deltaText,
  trend,
  accent,
  glow,
  icon,
}: StatCardProps) {
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendColor = TREND_COLORS[trend];

  return (
    <div
      style={{
        background: THEME.bgCard,
        borderRadius: "16px",
        padding: "20px",
        border: `1px solid ${THEME.borderSubtle}`,
        position: "relative",
        overflow: "hidden",
        transition: "all 0.3s ease",
      }}
    >
      {/* 背景光晕 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: "100px",
          height: "100px",
          background: `radial-gradient(circle at top right, ${glow}, transparent)`,
          opacity: 0.4,
          pointerEvents: "none",
        }}
      />

      {/* 图标 */}
      <div
        style={{
          width: "42px",
          height: "42px",
          borderRadius: "12px",
          background: `linear-gradient(135deg, ${accent}20, ${accent}10)`,
          border: `1px solid ${accent}30`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "16px",
          color: accent,
        }}
      >
        {icon}
      </div>

      {/* 标签 */}
      <div
        style={{
          fontSize: "13px",
          color: THEME.textSecondary,
          marginBottom: "6px",
          fontWeight: 500,
        }}
      >
        {label}
      </div>

      {/* 值 */}
      <div
        style={{
          fontSize: "28px",
          fontWeight: 700,
          color: THEME.textBright,
          marginBottom: "8px",
          fontFamily: "var(--font-mono, monospace)",
          letterSpacing: "-0.5px",
        }}
      >
        {value}
      </div>

      {/* 趋势 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "13px",
          color: trendColor.color,
          fontWeight: 500,
        }}
      >
        <TrendIcon size={14} />
        <span>{deltaText}</span>
      </div>
    </div>
  );
});

// 紧凑版卡片（用于较小空间）
export const CompactStatCard = memo(function CompactStatCard({
  label,
  value,
  trend,
  accent,
}: {
  label: string;
  value: string;
  trend: TrendDirection;
  accent: string;
}) {
  const trendColor = TREND_COLORS[trend];

  return (
    <div
      style={{
        background: THEME.bgCard,
        borderRadius: "10px",
        padding: "12px 16px",
        border: `1px solid ${THEME.borderSubtle}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
      }}
    >
      <span style={{ fontSize: "12px", color: THEME.textSecondary }}>{label}</span>
      <span
        style={{
          fontSize: "16px",
          fontWeight: 600,
          color: accent,
          fontFamily: "var(--font-mono, monospace)",
        }}
      >
        {value}
      </span>
    </div>
  );
});









