/**
 * GlobalTrendsPanel 主题常量
 * 深空主题配色 - 灵感来自于星际探索
 */

export const THEME = {
  // 背景层次
  bgDeep: "rgba(4, 6, 14, 0.98)",
  bgPrimary: "rgba(8, 12, 24, 0.95)",
  bgCard: "rgba(14, 20, 38, 0.75)",
  bgCardHover: "rgba(20, 28, 52, 0.85)",
  bgGlass: "rgba(255, 255, 255, 0.03)",

  // 边框
  borderSubtle: "rgba(80, 100, 140, 0.12)",
  borderDefault: "rgba(100, 130, 180, 0.18)",
  borderActive: "rgba(120, 180, 255, 0.35)",
  borderGlow: "rgba(100, 200, 255, 0.5)",

  // 文字层次
  textBright: "#f8fafc",
  textPrimary: "#e2e8f0",
  textSecondary: "rgba(180, 195, 220, 0.75)",
  textMuted: "rgba(130, 150, 180, 0.55)",
  textDim: "rgba(100, 120, 150, 0.4)",

  // 强调色 - 生态系统主题
  accentTemp: "#ff7b4a", // 温暖的橙红 - 温度
  accentOcean: "#00d4ff", // 明亮的青色 - 海洋
  accentLife: "#a78bfa", // 柔和的紫色 - 生命多样性
  accentGrowth: "#10b981", // 生机绿 - 种群增长
  accentWarning: "#fbbf24", // 警告黄 - 灭绝事件
  accentDanger: "#ef4444", // 危险红 - 死亡
  accentEvolution: "#8b5cf6", // 演化紫 - 分化事件
  accentGeology: "#d97706", // 地质橙 - 地壳活动
  accentMigration: "#06b6d4", // 迁移青 - 迁徙
  accentHealth: "#22c55e", // 健康绿 - 生态健康

  // 渐变
  gradientPrimary: "linear-gradient(135deg, rgba(100, 180, 255, 0.1), rgba(120, 100, 200, 0.05))",
  gradientCard: "linear-gradient(145deg, rgba(20, 30, 60, 0.4), rgba(10, 15, 35, 0.2))",
  gradientHeader: "linear-gradient(180deg, rgba(15, 25, 50, 0.9), rgba(8, 12, 24, 0.95))",

  // 阴影
  shadowSoft: "0 4px 20px rgba(0, 0, 0, 0.15)",
  shadowMedium: "0 8px 32px rgba(0, 0, 0, 0.25)",
  shadowGlow: "0 0 20px rgba(100, 180, 255, 0.15)",
  shadowCard: "0 2px 12px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.02)",
} as const;

// 图表颜色
export const CHART_COLORS = {
  temperature: "#ff7b4a",
  seaLevel: "#00d4ff",
  species: "#a78bfa",
  population: "#10b981",
  extinction: "#ef4444",
  branching: "#8b5cf6",
  migration: "#06b6d4",
  deathRate: "#f59e0b",
  growth: "#22c55e",
} as const;

// 趋势颜色
export const TREND_COLORS = {
  up: { color: "#22c55e", glow: "rgba(34, 197, 94, 0.3)" },
  down: { color: "#ef4444", glow: "rgba(239, 68, 68, 0.3)" },
  neutral: { color: "#64748b", glow: "rgba(100, 116, 139, 0.2)" },
} as const;

// Tab 图标和配色
export const TAB_CONFIG = {
  environment: {
    icon: "🌡️",
    label: "气候环境",
    accent: THEME.accentTemp,
  },
  biodiversity: {
    icon: "🧬",
    label: "生物多样性",
    accent: THEME.accentLife,
  },
  evolution: {
    icon: "🌳",
    label: "演化动态",
    accent: THEME.accentEvolution,
  },
  geology: {
    icon: "🏔️",
    label: "地质变迁",
    accent: THEME.accentGeology,
  },
  health: {
    icon: "💚",
    label: "生态健康",
    accent: THEME.accentHealth,
  },
} as const;

// 面板尺寸
export const PANEL_WIDTH = "min(98vw, 1480px)";









