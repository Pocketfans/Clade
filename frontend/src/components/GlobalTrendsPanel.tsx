import React, { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { 
  Thermometer, 
  Waves, 
  Sprout, 
  Users, 
  TrendingUp, 
  TrendingDown, 
  Minus,
  Activity
} from "lucide-react";
import { TurnReport } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  reports: TurnReport[];
  onClose: () => void;
}

type Tab = "environment" | "biodiversity";
type TrendDirection = "up" | "down" | "neutral";

// --- Types ---
interface SummaryStats {
  temp: number;
  seaLevel: number;
  species: number;
  population: number;
  tempDelta: number;
  seaLevelDelta: number;
  speciesDelta: number;
  populationDelta: number;
  turnSpan: number;
  latestTurn: number;
  baselineTurn: number;
}

interface MetricDefinition {
  key: string;
  label: string;
  value: string;
  deltaText: string;
  trend: TrendDirection;
  accent: string;
  icon: React.ReactNode;
}

interface InsightItem {
  key: string;
  label: string;
  value: string;
  description: string;
}

// --- Constants ---
const PANEL_WIDTH = "min(95vw, 1200px)"; // Slightly wider for better dashboard view

const THEME = {
  bg: "rgba(15, 23, 42, 0.6)",
  cardBg: "rgba(30, 41, 59, 0.5)",
  borderColor: "rgba(148, 163, 184, 0.2)",
  textPrimary: "#e2e8f0",
  textSecondary: "rgba(226, 232, 240, 0.65)",
  accentEnv: "#f97316",
  accentSea: "#3b82f6",
  accentBio: "#a855f7",
  accentPop: "#10b981",
};

// --- Formatters ---
const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const integerFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

// --- Main Component ---
export function GlobalTrendsPanel({ reports, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("environment");

  const chartData = useMemo(() => {
    return reports.map((report) => ({
      turn: report.turn_index + 1,
      speciesCount: report.species.length,
      totalPop: report.species.reduce((sum, s) => sum + s.population, 0),
      temp: report.global_temperature ?? 15,
      seaLevel: report.sea_level ?? 0,
    }));
  }, [reports]);

  const summary = useMemo(() => buildSummary(reports), [reports]);
  const metrics = useMemo(() => buildMetricDefinitions(summary), [summary]);
  const insightItems = useMemo(
    () => buildInsightItems(activeTab, summary, reports),
    [activeTab, summary, reports]
  );
  const hasReports = reports.length > 0;

  return (
    <GamePanel
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Activity size={20} color={THEME.accentSea} />
          <span>全球生态演变 (Global Trends)</span>
        </div>
      }
      onClose={onClose}
      variant="modal"
      width={PANEL_WIDTH}
    >
      <div style={styles.layoutContainer}>
        {/* Top Metrics Row */}
        <div style={styles.metricsRow}>
          {metrics.map((metric) => (
            <MetricCard key={metric.key} metric={metric} />
          ))}
        </div>

        {/* Main Content Area: Split Chart & Sidebar */}
        <div style={styles.mainContent}>
          {/* Left: Chart Section */}
          <div style={styles.chartSection}>
            <div style={styles.chartHeader}>
              <div style={styles.tabContainer}>
                <TabButton
                  active={activeTab === "environment"}
                  onClick={() => setActiveTab("environment")}
                  icon={<Thermometer size={16} />}
                  label="环境气候"
                  color={THEME.accentEnv}
                />
                <TabButton
                  active={activeTab === "biodiversity"}
                  onClick={() => setActiveTab("biodiversity")}
                  icon={<Sprout size={16} />}
                  label="生物群落"
                  color={THEME.accentBio}
                />
              </div>
              <div style={styles.chartLegend}>
                 {activeTab === 'environment' ? '温度 (℃) & 海平面 (m)' : '物种数 & 生物量'}
              </div>
            </div>

            <div style={styles.chartContainer}>
              {hasReports ? (
                <ResponsiveContainer width="100%" height="100%">
                  {activeTab === "environment" ? (
                    <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
                      <XAxis 
                        dataKey="turn" 
                        stroke={THEME.textSecondary} 
                        tick={{ fontSize: 12 }} 
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        yAxisId="left"
                        stroke={THEME.textSecondary}
                        tick={{ fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                        domain={['auto', 'auto']}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        stroke={THEME.textSecondary}
                        tick={{ fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                        domain={['auto', 'auto']}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend wrapperStyle={{ paddingTop: '10px' }} />
                      <Line
                        yAxisId="left"
                        type="monotone"
                        dataKey="temp"
                        name="全球均温"
                        stroke={THEME.accentEnv}
                        strokeWidth={3}
                        dot={false}
                        activeDot={{ r: 6, strokeWidth: 0 }}
                      />
                      <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="seaLevel"
                        name="海平面"
                        stroke={THEME.accentSea}
                        strokeWidth={3}
                        dot={false}
                        activeDot={{ r: 6, strokeWidth: 0 }}
                      />
                    </LineChart>
                  ) : (
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorPop" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={THEME.accentPop} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={THEME.accentPop} stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorSpecies" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={THEME.accentBio} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={THEME.accentBio} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
                      <XAxis 
                        dataKey="turn" 
                        stroke={THEME.textSecondary} 
                        tick={{ fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis 
                        stroke={THEME.textSecondary} 
                        tick={{ fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend wrapperStyle={{ paddingTop: '10px' }} />
                      <Area
                        type="monotone"
                        dataKey="totalPop"
                        name="生物量指数"
                        stroke={THEME.accentPop}
                        fill="url(#colorPop)"
                        strokeWidth={2}
                      />
                      <Area
                        type="monotone"
                        dataKey="speciesCount"
                        name="物种数量"
                        stroke={THEME.accentBio}
                        fill="url(#colorSpecies)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  )}
                </ResponsiveContainer>
              ) : (
                <div style={styles.emptyState}>
                  <Activity size={48} color={THEME.textSecondary} strokeWidth={1} />
                  <p>暂无演化数据，请推进回合</p>
                </div>
              )}
            </div>
          </div>

          {/* Right: Insights Sidebar */}
          <div style={styles.sidebar}>
            <div style={styles.sidebarHeader}>
              <span style={styles.sidebarTitle}>趋势洞察 (Insights)</span>
            </div>
            
            <div style={styles.insightsList}>
              {insightItems.map((insight) => (
                <div key={insight.key} style={styles.insightCard}>
                  <div style={styles.insightLabel}>{insight.label}</div>
                  <div style={styles.insightValue}>{insight.value}</div>
                  <div style={styles.insightDesc}>{insight.description}</div>
                </div>
              ))}
            </div>

            <div style={styles.footer}>
               <div style={styles.footerItem}>
                 <span>数据范围:</span>
                 <span style={{ color: THEME.textPrimary }}>
                   {hasReports ? `T${summary.baselineTurn} - T${summary.latestTurn}` : '--'}
                 </span>
               </div>
               <div style={styles.footerItem}>
                 <span>采样点:</span>
                 <span style={{ color: THEME.textPrimary }}>{reports.length}</span>
               </div>
            </div>
          </div>
        </div>
      </div>
    </GamePanel>
  );
}

// --- Sub Components ---

function MetricCard({ metric }: { metric: MetricDefinition }) {
  const trendColor =
    metric.trend === "up"
      ? "#4ade80"
      : metric.trend === "down"
      ? "#f87171"
      : THEME.textSecondary;

  const TrendIcon = metric.trend === 'up' ? TrendingUp : metric.trend === 'down' ? TrendingDown : Minus;

  return (
    <div style={{...styles.metricCard, borderTop: `3px solid ${metric.accent}`}}>
      <div style={styles.metricHeader}>
        <span style={styles.metricLabel}>{metric.label}</span>
        <div style={{ color: metric.accent, opacity: 0.8 }}>{metric.icon}</div>
      </div>
      <div style={styles.metricContent}>
        <span style={styles.metricValue}>{metric.value}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: trendColor, fontSize: '0.85rem' }}>
           <TrendIcon size={14} />
           <span>{metric.deltaText}</span>
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, label, icon, color }: { active: boolean; onClick: () => void; label: string; icon: React.ReactNode; color: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        ...styles.tabButton,
        backgroundColor: active ? `${color}22` : 'transparent',
        borderColor: active ? color : 'transparent',
        color: active ? color : THEME.textSecondary,
      }}
    >
      {icon}
      {label}
    </button>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={styles.tooltip}>
        <p style={styles.tooltipTitle}>{`Turn ${label}`}</p>
        {payload.map((entry: any, index: number) => (
          <div key={index} style={{ color: entry.color, fontSize: '0.85rem', marginBottom: '4px' }}>
            {entry.name}: {typeof entry.value === 'number' && entry.value % 1 !== 0 ? entry.value.toFixed(2) : entry.value}
          </div>
        ))}
      </div>
    );
  }
  return null;
};

// --- Logic Helpers ---

const summaryFallback: SummaryStats = {
  temp: 0, seaLevel: 0, species: 0, population: 0,
  tempDelta: 0, seaLevelDelta: 0, speciesDelta: 0, populationDelta: 0,
  turnSpan: 0, latestTurn: 0, baselineTurn: 0,
};

function buildSummary(reports: TurnReport[]): SummaryStats {
  if (!reports.length) return summaryFallback;
  const first = reports[0];
  const last = reports[reports.length - 1];
  
  const calcPop = (r: TurnReport) => r.species.reduce((sum, s) => sum + s.population, 0);
  
  const bTemp = first.global_temperature ?? 15;
  const lTemp = last.global_temperature ?? 15;
  const bSea = first.sea_level ?? 0;
  const lSea = last.sea_level ?? 0;
  const bPop = calcPop(first);
  const lPop = calcPop(last);

  return {
    temp: lTemp, seaLevel: lSea, species: last.species.length, population: lPop,
    tempDelta: lTemp - bTemp, seaLevelDelta: lSea - bSea,
    speciesDelta: last.species.length - first.species.length,
    populationDelta: lPop - bPop,
    turnSpan: last.turn_index - first.turn_index,
    latestTurn: last.turn_index + 1,
    baselineTurn: first.turn_index + 1,
  };
}

function buildMetricDefinitions(summary: SummaryStats): MetricDefinition[] {
  return [
    {
      key: "temp", label: "全球均温",
      value: `${summary.temp.toFixed(1)}°C`,
      deltaText: formatDelta(summary.tempDelta, "°C", 1),
      trend: getTrend(summary.tempDelta),
      accent: THEME.accentEnv,
      icon: <Thermometer size={18} />,
    },
    {
      key: "seaLevel", label: "海平面",
      value: `${summary.seaLevel.toFixed(2)} m`,
      deltaText: formatDelta(summary.seaLevelDelta, " m", 2),
      trend: getTrend(summary.seaLevelDelta),
      accent: THEME.accentSea,
      icon: <Waves size={18} />,
    },
    {
      key: "species", label: "物种丰富度",
      value: integerFormatter.format(summary.species),
      deltaText: formatDelta(summary.speciesDelta, "", 0),
      trend: getTrend(summary.speciesDelta),
      accent: THEME.accentBio,
      icon: <Sprout size={18} />,
    },
    {
      key: "population", label: "总生物量",
      value: formatPopulation(summary.population),
      deltaText: formatDelta(summary.populationDelta, "", 1, formatPopulation),
      trend: getTrend(summary.populationDelta),
      accent: THEME.accentPop,
      icon: <Users size={18} />,
    },
  ];
}

function buildInsightItems(tab: Tab, summary: SummaryStats, reports: TurnReport[]): InsightItem[] {
  if (!reports.length) return [{ key: "empty", label: "等待数据", value: "--", description: "暂无演化记录" }];
  
  if (tab === "environment") {
    const rate = summary.turnSpan > 0 ? summary.tempDelta / summary.turnSpan : 0;
    return [
      {
        key: "tempRate", label: "升温速率",
        value: `${formatDelta(rate, "°C", 3)} / Turn`,
        description: "每回合平均温度变化",
      },
      {
        key: "seaTotal", label: "海平面净变",
        value: formatDelta(summary.seaLevelDelta, " m", 2),
        description: "相较于初始记录的累计变化",
      },
      {
        key: "co2", label: "环境压力", // Placeholder calculation
        value: rate > 0.5 ? "Critical" : rate > 0.1 ? "High" : "Stable",
        description: "基于当前变化率的压力评级",
      }
    ];
  } else {
     const avgPop = summary.species > 0 ? summary.population / summary.species : 0;
     return [
       {
         key: "diversity", label: "多样性趋势",
         value: formatDelta(summary.speciesDelta, " 种", 0),
         description: "物种形成与灭绝的净结果",
       },
       {
         key: "biomass", label: "生物量净变",
         value: formatDelta(summary.populationDelta, "", 1, formatPopulation),
         description: "生态系统承载力变化",
       },
       {
         key: "density", label: "平均种群",
         value: formatPopulation(avgPop),
         description: "单物种平均规模",
       }
     ];
  }
}

// --- Utilities ---

function getTrend(delta: number): TrendDirection {
  if (Math.abs(delta) < 0.001) return "neutral";
  return delta > 0 ? "up" : "down";
}

function formatPopulation(val: number) {
  return compactNumberFormatter.format(val);
}

function formatDelta(d: number, unit = "", digits = 1, formatter?: (v: number) => string) {
  if (Math.abs(d) < Math.pow(10, -digits) / 2) return "持平";
  const val = formatter ? formatter(Math.abs(d)) : Math.abs(d).toFixed(digits);
  return `${d > 0 ? "+" : "-"}${val}${unit}`;
}

// --- Styles ---

const styles: Record<string, React.CSSProperties> = {
  layoutContainer: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: '24px',
    gap: '24px',
    color: THEME.textPrimary,
  },
  metricsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '16px',
    flexShrink: 0,
  },
  mainContent: {
    display: 'flex',
    flex: 1,
    gap: '24px',
    minHeight: 0, // Critical for flex child scrolling/resizing
    overflow: 'hidden',
  },
  chartSection: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '16px',
    border: `1px solid ${THEME.borderColor}`,
    padding: '20px',
    minWidth: '0', // Prevent flex overflow
  },
  chartHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
    flexWrap: 'wrap',
    gap: '10px',
  },
  tabContainer: {
    display: 'flex',
    gap: '8px',
    background: 'rgba(0,0,0,0.2)',
    padding: '4px',
    borderRadius: '8px',
  },
  tabButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '6px',
    border: '1px solid transparent',
    cursor: 'pointer',
    fontSize: '0.85rem',
    fontWeight: 500,
    transition: 'all 0.2s',
  },
  chartLegend: {
    fontSize: '0.8rem',
    color: THEME.textSecondary,
  },
  chartContainer: {
    flex: 1,
    minHeight: '200px',
    position: 'relative',
  },
  emptyState: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: THEME.textSecondary,
    gap: '12px',
  },
  sidebar: {
    width: '280px',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '16px',
    border: `1px solid ${THEME.borderColor}`,
    padding: '20px',
  },
  sidebarHeader: {
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: `1px solid ${THEME.borderColor}`,
  },
  sidebarTitle: {
    fontSize: '0.9rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: THEME.textSecondary,
  },
  insightsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    flex: 1,
    overflowY: 'auto',
  },
  insightCard: {
    padding: '12px',
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '8px',
    borderLeft: `3px solid ${THEME.accentSea}`,
  },
  insightLabel: {
    fontSize: '0.8rem',
    color: THEME.textSecondary,
    marginBottom: '4px',
  },
  insightValue: {
    fontSize: '1.1rem',
    fontWeight: 600,
    color: THEME.textPrimary,
  },
  insightDesc: {
    fontSize: '0.75rem',
    color: 'rgba(148, 163, 184, 0.7)',
    marginTop: '4px',
  },
  metricCard: {
    background: THEME.cardBg,
    borderRadius: '12px',
    padding: '16px',
    border: `1px solid ${THEME.borderColor}`,
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
  },
  metricHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: '0.85rem',
    color: THEME.textSecondary,
  },
  metricContent: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '8px',
    flexWrap: 'wrap',
  },
  metricValue: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: THEME.textPrimary,
  },
  tooltip: {
    backgroundColor: "rgba(15, 23, 42, 0.95)",
    border: `1px solid ${THEME.borderColor}`,
    borderRadius: "8px",
    padding: "12px",
    boxShadow: "0 10px 15px rgba(0,0,0,0.5)",
  },
  tooltipTitle: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: THEME.textPrimary,
    marginBottom: '8px',
    borderBottom: `1px solid ${THEME.borderColor}`,
    paddingBottom: '4px',
  },
  footer: {
    marginTop: 'auto',
    paddingTop: '16px',
    borderTop: `1px solid ${THEME.borderColor}`,
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    fontSize: '0.8rem',
    color: THEME.textSecondary,
  }
};
