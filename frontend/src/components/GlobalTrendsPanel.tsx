import React, { useMemo, useState, useCallback } from "react";
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
  BarChart,
  Bar,
  ComposedChart,
  PieChart,
  Pie,
  Cell,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import { 
  Thermometer, 
  Waves, 
  Sprout, 
  Users, 
  TrendingUp, 
  TrendingDown, 
  Minus,
  Activity,
  Skull,
  GitBranch,
  Map,
  Heart,
  Download,
  BarChart2,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
  Clock,
  AlertTriangle,
  Zap,
  Globe,
  Footprints,
  Crown,
  Target,
  Shield,
  Mountain,
  Calendar
} from "lucide-react";
import { TurnReport, SpeciesSnapshot, BranchingEvent, MigrationEvent, MapChange } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  reports: TurnReport[];
  onClose: () => void;
}

type Tab = "environment" | "biodiversity" | "evolution" | "geology" | "health";
type ChartType = "line" | "area" | "bar";
type TimeRange = "all" | "10" | "20" | "50";
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
  extinctions: number;
  branchingCount: number;
  migrationCount: number;
  avgDeathRate: number;
  totalDeaths: number;
  mapChanges: number;
  tectonicStage: string;
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
  accent?: string;
}

interface TimelineEvent {
  turn: number;
  type: "branching" | "extinction" | "migration" | "geological" | "pressure";
  title: string;
  description: string;
  icon: React.ReactNode;
  color: string;
}

// --- Constants ---
const PANEL_WIDTH = "min(98vw, 1400px)";

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
  accentDeath: "#ef4444",
  accentGeo: "#eab308",
  accentHealth: "#06b6d4",
  accentEvolution: "#ec4899",
};

const PIE_COLORS = ["#10b981", "#3b82f6", "#a855f7", "#f97316", "#ef4444", "#eab308", "#06b6d4", "#ec4899"];

// --- Formatters ---
const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const integerFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

// --- Main Component ---
export function GlobalTrendsPanel({ reports, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("environment");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const [showTimeline, setShowTimeline] = useState(false);

  // Filter reports based on time range
  const filteredReports = useMemo(() => {
    if (timeRange === "all" || reports.length === 0) return reports;
    const count = parseInt(timeRange);
    return reports.slice(-count);
  }, [reports, timeRange]);

  const chartData = useMemo(() => {
    return filteredReports.map((report) => {
      const totalPop = report.species.reduce((sum, s) => sum + s.population, 0);
      const totalDeaths = report.species.reduce((sum, s) => sum + s.deaths, 0);
      const avgDeathRate = report.species.length > 0 
        ? report.species.reduce((sum, s) => sum + s.death_rate, 0) / report.species.length 
        : 0;
      
      return {
        turn: report.turn_index + 1,
        speciesCount: report.species.length,
        totalPop,
        temp: report.global_temperature ?? 15,
        seaLevel: report.sea_level ?? 0,
        deaths: totalDeaths,
        deathRate: avgDeathRate * 100,
        branchings: report.branching_events?.length ?? 0,
        migrations: report.migration_events?.length ?? 0,
        mapChanges: report.map_changes?.length ?? 0,
        majorEvents: report.major_events?.length ?? 0,
      };
    });
  }, [filteredReports]);

  const summary = useMemo(() => buildSummary(filteredReports), [filteredReports]);
  const metrics = useMemo(() => buildMetricDefinitions(summary, activeTab), [summary, activeTab]);
  const insightItems = useMemo(
    () => buildInsightItems(activeTab, summary, filteredReports),
    [activeTab, summary, filteredReports]
  );
  const timelineEvents = useMemo(() => buildTimelineEvents(filteredReports), [filteredReports]);
  const speciesRanking = useMemo(() => buildSpeciesRanking(filteredReports), [filteredReports]);
  const roleDistribution = useMemo(() => buildRoleDistribution(filteredReports), [filteredReports]);
  
  const hasReports = filteredReports.length > 0;

  const handleExport = useCallback(() => {
    const exportData = {
      summary,
      chartData,
      timelineEvents,
      generatedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `global_trends_T${summary.latestTurn}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [summary, chartData, timelineEvents]);

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
        {/* Control Bar */}
        <div style={styles.controlBar}>
          <div style={styles.tabContainer}>
            <TabButton
              active={activeTab === "environment"}
              onClick={() => setActiveTab("environment")}
              icon={<Thermometer size={14} />}
              label="环境气候"
              color={THEME.accentEnv}
            />
            <TabButton
              active={activeTab === "biodiversity"}
              onClick={() => setActiveTab("biodiversity")}
              icon={<Sprout size={14} />}
              label="生物群落"
              color={THEME.accentBio}
            />
            <TabButton
              active={activeTab === "evolution"}
              onClick={() => setActiveTab("evolution")}
              icon={<GitBranch size={14} />}
              label="进化事件"
              color={THEME.accentEvolution}
            />
            <TabButton
              active={activeTab === "geology"}
              onClick={() => setActiveTab("geology")}
              icon={<Mountain size={14} />}
              label="地质变化"
              color={THEME.accentGeo}
            />
            <TabButton
              active={activeTab === "health"}
              onClick={() => setActiveTab("health")}
              icon={<Heart size={14} />}
              label="生态健康"
              color={THEME.accentHealth}
            />
          </div>

          <div style={styles.controlGroup}>
            {/* Time Range Selector */}
            <div style={styles.selectWrapper}>
              <Clock size={14} color={THEME.textSecondary} />
              <select 
                value={timeRange} 
                onChange={(e) => setTimeRange(e.target.value as TimeRange)}
                style={styles.select}
              >
                <option value="all">全部回合</option>
                <option value="10">最近 10 回合</option>
                <option value="20">最近 20 回合</option>
                <option value="50">最近 50 回合</option>
              </select>
            </div>

            {/* Chart Type Selector */}
            <div style={styles.chartTypeGroup}>
              <ChartTypeButton 
                active={chartType === "line"} 
                onClick={() => setChartType("line")}
                icon={<LineChartIcon size={14} />}
                title="折线图"
              />
              <ChartTypeButton 
                active={chartType === "area"} 
                onClick={() => setChartType("area")}
                icon={<BarChart2 size={14} />}
                title="面积图"
              />
              <ChartTypeButton 
                active={chartType === "bar"} 
                onClick={() => setChartType("bar")}
                icon={<PieChartIcon size={14} />}
                title="柱状图"
              />
            </div>

            {/* Timeline Toggle */}
            <button
              onClick={() => setShowTimeline(!showTimeline)}
              style={{
                ...styles.iconButton,
                backgroundColor: showTimeline ? `${THEME.accentSea}33` : 'transparent',
                borderColor: showTimeline ? THEME.accentSea : 'transparent',
              }}
              title="显示事件时间线"
            >
              <Calendar size={14} />
            </button>

            {/* Export Button */}
            <button onClick={handleExport} style={styles.iconButton} title="导出数据">
              <Download size={14} />
            </button>
          </div>
        </div>

        {/* Top Metrics Row */}
        <div style={styles.metricsRow}>
          {metrics.map((metric) => (
            <MetricCard key={metric.key} metric={metric} />
          ))}
        </div>

        {/* Main Content Area */}
        <div style={styles.mainContent}>
          {/* Left: Chart Section */}
          <div style={styles.chartSection}>
            <div style={styles.chartHeader}>
              <div style={styles.chartTitle}>
                {getChartTitle(activeTab)}
              </div>
              <div style={styles.chartLegend}>
                {getChartLegend(activeTab)}
              </div>
            </div>

            <div style={styles.chartContainer}>
              {hasReports ? (
                <ResponsiveContainer width="100%" height="100%">
                  {renderChart(activeTab, chartType, chartData)}
                </ResponsiveContainer>
              ) : (
                <div style={styles.emptyState}>
                  <Activity size={48} color={THEME.textSecondary} strokeWidth={1} />
                  <p>暂无演化数据，请推进回合</p>
                </div>
              )}
            </div>
          </div>

          {/* Right: Sidebar */}
          <div style={styles.sidebar}>
            {/* Insights Section */}
            <div style={styles.sidebarSection}>
              <div style={styles.sidebarHeader}>
                <span style={styles.sidebarTitle}>📊 趋势洞察</span>
              </div>
              <div style={styles.insightsList}>
                {insightItems.map((insight) => (
                  <div 
                    key={insight.key} 
                    style={{
                      ...styles.insightCard,
                      borderLeftColor: insight.accent || THEME.accentSea,
                    }}
                  >
                    <div style={styles.insightLabel}>{insight.label}</div>
                    <div style={styles.insightValue}>{insight.value}</div>
                    <div style={styles.insightDesc}>{insight.description}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Species Ranking (only for biodiversity tab) */}
            {activeTab === "biodiversity" && speciesRanking.length > 0 && (
              <div style={styles.sidebarSection}>
                <div style={styles.sidebarHeader}>
                  <span style={styles.sidebarTitle}>🏆 物种排行</span>
                </div>
                <div style={styles.rankingList}>
                  {speciesRanking.slice(0, 5).map((sp, idx) => (
                    <div key={sp.lineage_code} style={styles.rankingItem}>
                      <div style={styles.rankBadge}>{idx + 1}</div>
                      <div style={styles.rankInfo}>
                        <div style={styles.rankName}>{sp.common_name}</div>
                        <div style={styles.rankPop}>{formatPopulation(sp.population)}</div>
                      </div>
                      <div style={styles.rankBar}>
                        <div 
                          style={{
                            ...styles.rankBarFill,
                            width: `${(sp.population / speciesRanking[0].population) * 100}%`,
                            backgroundColor: PIE_COLORS[idx % PIE_COLORS.length],
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Role Distribution Chart (for health tab) */}
            {activeTab === "health" && roleDistribution.length > 0 && (
              <div style={styles.sidebarSection}>
                <div style={styles.sidebarHeader}>
                  <span style={styles.sidebarTitle}>🧬 生态角色分布</span>
                </div>
                <div style={{ height: 180 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={roleDistribution}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={70}
                        paddingAngle={2}
                        dataKey="value"
                        nameKey="name"
                      >
                        {roleDistribution.map((_, idx) => (
                          <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<PieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div style={styles.legendGrid}>
                  {roleDistribution.map((item, idx) => (
                    <div key={item.name} style={styles.legendItem}>
                      <div 
                        style={{
                          ...styles.legendDot,
                          backgroundColor: PIE_COLORS[idx % PIE_COLORS.length],
                        }}
                      />
                      <span>{item.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Footer Stats */}
            <div style={styles.footer}>
              <div style={styles.footerItem}>
                <span>数据范围:</span>
                <span style={{ color: THEME.textPrimary }}>
                  {hasReports ? `T${summary.baselineTurn} - T${summary.latestTurn}` : '--'}
                </span>
              </div>
              <div style={styles.footerItem}>
                <span>采样点:</span>
                <span style={{ color: THEME.textPrimary }}>{filteredReports.length}</span>
              </div>
              {summary.tectonicStage && (
                <div style={styles.footerItem}>
                  <span>地质阶段:</span>
                  <span style={{ color: THEME.accentGeo }}>{summary.tectonicStage}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Timeline Section (collapsible) */}
        {showTimeline && timelineEvents.length > 0 && (
          <div style={styles.timelineSection}>
            <div style={styles.timelineHeader}>
              <span style={styles.sidebarTitle}>📅 重大事件时间线</span>
              <span style={styles.timelineCount}>{timelineEvents.length} 事件</span>
            </div>
            <div style={styles.timelineScroll}>
              {timelineEvents.slice(0, 20).map((event, idx) => (
                <div key={`${event.turn}-${idx}`} style={styles.timelineItem}>
                  <div style={{ ...styles.timelineIcon, backgroundColor: `${event.color}22`, color: event.color }}>
                    {event.icon}
                  </div>
                  <div style={styles.timelineTurn}>T{event.turn}</div>
                  <div style={styles.timelineContent}>
                    <div style={styles.timelineTitle}>{event.title}</div>
                    <div style={styles.timelineDesc}>{event.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </GamePanel>
  );
}

// --- Chart Rendering ---
function renderChart(tab: Tab, type: ChartType, data: any[]) {
  const commonProps = {
    data,
    margin: { top: 10, right: 30, left: 0, bottom: 0 },
  };

  switch (tab) {
    case "environment":
      return renderEnvironmentChart(type, commonProps);
    case "biodiversity":
      return renderBiodiversityChart(type, commonProps);
    case "evolution":
      return renderEvolutionChart(type, commonProps);
    case "geology":
      return renderGeologyChart(type, commonProps);
    case "health":
      return renderHealthChart(type, commonProps);
    default:
      return renderEnvironmentChart(type, commonProps);
  }
}

function renderEnvironmentChart(type: ChartType, props: any) {
  const chartComponents = {
    line: LineChart,
    area: AreaChart,
    bar: ComposedChart,
  };
  const ChartComponent = chartComponents[type];

  return (
    <ChartComponent {...props}>
      <defs>
        <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentEnv} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentEnv} stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="seaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentSea} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentSea} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '10px' }} />
      {type === "area" ? (
        <>
          <Area yAxisId="left" type="monotone" dataKey="temp" name="全球均温 (°C)" stroke={THEME.accentEnv} fill="url(#tempGradient)" strokeWidth={2} />
          <Area yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentSea} fill="url(#seaGradient)" strokeWidth={2} />
        </>
      ) : type === "bar" ? (
        <>
          <Bar yAxisId="left" dataKey="temp" name="全球均温 (°C)" fill={THEME.accentEnv} radius={[4, 4, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentSea} strokeWidth={3} dot={false} />
        </>
      ) : (
        <>
          <Line yAxisId="left" type="monotone" dataKey="temp" name="全球均温 (°C)" stroke={THEME.accentEnv} strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
          <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentSea} strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
        </>
      )}
    </ChartComponent>
  );
}

function renderBiodiversityChart(type: ChartType, props: any) {
  const chartComponents = {
    line: LineChart,
    area: AreaChart,
    bar: ComposedChart,
  };
  const ChartComponent = chartComponents[type];

  return (
    <ChartComponent {...props}>
      <defs>
        <linearGradient id="popGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentPop} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentPop} stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="speciesGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentBio} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentBio} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '10px' }} />
      {type === "area" ? (
        <>
          <Area yAxisId="left" type="monotone" dataKey="totalPop" name="总生物量" stroke={THEME.accentPop} fill="url(#popGradient)" strokeWidth={2} />
          <Area yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentBio} fill="url(#speciesGradient)" strokeWidth={2} />
        </>
      ) : type === "bar" ? (
        <>
          <Bar yAxisId="left" dataKey="totalPop" name="总生物量" fill={THEME.accentPop} radius={[4, 4, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentBio} strokeWidth={3} dot={false} />
        </>
      ) : (
        <>
          <Line yAxisId="left" type="monotone" dataKey="totalPop" name="总生物量" stroke={THEME.accentPop} strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
          <Line yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentBio} strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
        </>
      )}
    </ChartComponent>
  );
}

function renderEvolutionChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '10px' }} />
      <Bar dataKey="branchings" name="物种分化" fill={THEME.accentEvolution} radius={[4, 4, 0, 0]} />
      <Bar dataKey="migrations" name="迁徙事件" fill={THEME.accentSea} radius={[4, 4, 0, 0]} />
      <Line type="monotone" dataKey="speciesCount" name="物种总数" stroke={THEME.accentBio} strokeWidth={2} dot={false} />
    </ComposedChart>
  );
}

function renderGeologyChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <defs>
        <linearGradient id="geoGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentGeo} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentGeo} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '10px' }} />
      <Bar yAxisId="left" dataKey="mapChanges" name="地形变化" fill={THEME.accentGeo} radius={[4, 4, 0, 0]} />
      <Bar yAxisId="left" dataKey="majorEvents" name="重大事件" fill={THEME.accentDeath} radius={[4, 4, 0, 0]} />
      <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面" stroke={THEME.accentSea} strokeWidth={2} dot={false} />
    </ComposedChart>
  );
}

function renderHealthChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <defs>
        <linearGradient id="deathGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentDeath} stopOpacity={0.3}/>
          <stop offset="95%" stopColor={THEME.accentDeath} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderColor} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textSecondary} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} domain={[0, 100]} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '10px' }} />
      <Area yAxisId="left" type="monotone" dataKey="deaths" name="死亡数" stroke={THEME.accentDeath} fill="url(#deathGradient)" strokeWidth={2} />
      <Line yAxisId="right" type="monotone" dataKey="deathRate" name="平均死亡率 (%)" stroke={THEME.accentHealth} strokeWidth={3} dot={false} />
      <Line yAxisId="left" type="monotone" dataKey="totalPop" name="总种群" stroke={THEME.accentPop} strokeWidth={2} strokeDasharray="5 5" dot={false} />
    </ComposedChart>
  );
}

function getChartTitle(tab: Tab): string {
  const titles: Record<Tab, string> = {
    environment: "🌡️ 环境变化趋势",
    biodiversity: "🌿 生物多样性变化",
    evolution: "🧬 进化与迁徙活动",
    geology: "⛰️ 地质构造变化",
    health: "❤️ 生态系统健康",
  };
  return titles[tab];
}

function getChartLegend(tab: Tab): string {
  const legends: Record<Tab, string> = {
    environment: "温度 (°C) & 海平面 (m)",
    biodiversity: "物种数 & 生物量",
    evolution: "分化/迁徙事件数",
    geology: "地形变化 & 海平面",
    health: "死亡数 & 死亡率",
  };
  return legends[tab];
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

function ChartTypeButton({ active, onClick, icon, title }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        ...styles.chartTypeBtn,
        backgroundColor: active ? `${THEME.accentSea}33` : 'transparent',
        borderColor: active ? THEME.accentSea : 'transparent',
        color: active ? THEME.accentSea : THEME.textSecondary,
      }}
      title={title}
    >
      {icon}
    </button>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={styles.tooltip}>
        <p style={styles.tooltipTitle}>{`回合 ${label}`}</p>
        {payload.map((entry: any, index: number) => (
          <div key={index} style={{ color: entry.color, fontSize: '0.85rem', marginBottom: '4px' }}>
            {entry.name}: {typeof entry.value === 'number' && entry.value % 1 !== 0 ? entry.value.toFixed(2) : formatPopulation(entry.value)}
          </div>
        ))}
      </div>
    );
  }
  return null;
};

const PieTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={styles.tooltip}>
        <p style={{ ...styles.tooltipTitle, color: payload[0].payload.fill }}>{payload[0].name}</p>
        <p style={{ fontSize: '0.9rem' }}>{payload[0].value} 个物种</p>
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
  extinctions: 0, branchingCount: 0, migrationCount: 0,
  avgDeathRate: 0, totalDeaths: 0, mapChanges: 0, tectonicStage: "",
};

function buildSummary(reports: TurnReport[]): SummaryStats {
  if (!reports.length) return summaryFallback;
  const first = reports[0];
  const last = reports[reports.length - 1];
  
  const calcPop = (r: TurnReport) => r.species.reduce((sum, s) => sum + s.population, 0);
  const calcDeaths = (r: TurnReport) => r.species.reduce((sum, s) => sum + s.deaths, 0);
  
  const bTemp = first.global_temperature ?? 15;
  const lTemp = last.global_temperature ?? 15;
  const bSea = first.sea_level ?? 0;
  const lSea = last.sea_level ?? 0;
  const bPop = calcPop(first);
  const lPop = calcPop(last);

  // Aggregate counts across all reports
  let totalBranchings = 0;
  let totalMigrations = 0;
  let totalMapChanges = 0;
  let totalDeathsAll = 0;
  let totalDeathRateSum = 0;
  let speciesCountForAvg = 0;

  for (const r of reports) {
    totalBranchings += r.branching_events?.length ?? 0;
    totalMigrations += r.migration_events?.length ?? 0;
    totalMapChanges += r.map_changes?.length ?? 0;
    totalDeathsAll += calcDeaths(r);
    for (const s of r.species) {
      totalDeathRateSum += s.death_rate;
      speciesCountForAvg++;
    }
  }

  const extinctions = first.species.length - last.species.length + totalBranchings;

  return {
    temp: lTemp, seaLevel: lSea, species: last.species.length, population: lPop,
    tempDelta: lTemp - bTemp, seaLevelDelta: lSea - bSea,
    speciesDelta: last.species.length - first.species.length,
    populationDelta: lPop - bPop,
    turnSpan: last.turn_index - first.turn_index,
    latestTurn: last.turn_index + 1,
    baselineTurn: first.turn_index + 1,
    extinctions: Math.max(0, extinctions),
    branchingCount: totalBranchings,
    migrationCount: totalMigrations,
    avgDeathRate: speciesCountForAvg > 0 ? totalDeathRateSum / speciesCountForAvg : 0,
    totalDeaths: totalDeathsAll,
    mapChanges: totalMapChanges,
    tectonicStage: last.tectonic_stage || "",
  };
}

function buildMetricDefinitions(summary: SummaryStats, tab: Tab): MetricDefinition[] {
  const baseMetrics: MetricDefinition[] = [
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

  // Add tab-specific metrics
  const extraMetrics: Record<Tab, MetricDefinition[]> = {
    environment: [],
    biodiversity: [],
    evolution: [
      {
        key: "branchings", label: "物种分化",
        value: integerFormatter.format(summary.branchingCount),
        deltaText: "累计事件",
        trend: "neutral",
        accent: THEME.accentEvolution,
        icon: <GitBranch size={18} />,
      },
      {
        key: "migrations", label: "迁徙活动",
        value: integerFormatter.format(summary.migrationCount),
        deltaText: "累计事件",
        trend: "neutral",
        accent: THEME.accentSea,
        icon: <Footprints size={18} />,
      },
    ],
    geology: [
      {
        key: "mapChanges", label: "地形变化",
        value: integerFormatter.format(summary.mapChanges),
        deltaText: "累计变化",
        trend: "neutral",
        accent: THEME.accentGeo,
        icon: <Mountain size={18} />,
      },
    ],
    health: [
      {
        key: "deathRate", label: "平均死亡率",
        value: `${(summary.avgDeathRate * 100).toFixed(1)}%`,
        deltaText: summary.avgDeathRate > 0.3 ? "偏高" : summary.avgDeathRate > 0.15 ? "正常" : "健康",
        trend: summary.avgDeathRate > 0.25 ? "down" : "up",
        accent: THEME.accentDeath,
        icon: <Skull size={18} />,
      },
      {
        key: "totalDeaths", label: "累计死亡",
        value: formatPopulation(summary.totalDeaths),
        deltaText: "生命损失",
        trend: "neutral",
        accent: THEME.accentHealth,
        icon: <Heart size={18} />,
      },
    ],
  };

  return [...baseMetrics, ...(extraMetrics[tab] || [])];
}

function buildInsightItems(tab: Tab, summary: SummaryStats, reports: TurnReport[]): InsightItem[] {
  if (!reports.length) return [{ key: "empty", label: "等待数据", value: "--", description: "暂无演化记录" }];
  
  const rate = summary.turnSpan > 0 ? summary.tempDelta / summary.turnSpan : 0;
  
  switch (tab) {
    case "environment":
      return [
        {
          key: "tempRate", label: "升温速率",
          value: `${formatDelta(rate, "°C", 3)} / 回合`,
          description: "每回合平均温度变化",
          accent: THEME.accentEnv,
        },
        {
          key: "seaTotal", label: "海平面净变",
          value: formatDelta(summary.seaLevelDelta, " m", 2),
          description: "相较于初始记录的累计变化",
          accent: THEME.accentSea,
        },
        {
          key: "pressure", label: "环境压力",
          value: rate > 0.5 ? "🔴 危急" : rate > 0.1 ? "🟡 高压" : "🟢 稳定",
          description: "基于当前变化率的压力评级",
          accent: rate > 0.5 ? THEME.accentDeath : rate > 0.1 ? THEME.accentGeo : THEME.accentPop,
        },
        {
          key: "forecast", label: "趋势预测",
          value: rate > 0 ? "升温中" : rate < 0 ? "降温中" : "平稳",
          description: rate > 0 ? "生态系统面临热压力" : rate < 0 ? "可能进入冰期" : "环境条件稳定",
          accent: THEME.accentEnv,
        },
      ];
      
    case "biodiversity":
      const avgPop = summary.species > 0 ? summary.population / summary.species : 0;
      const diversityHealth = summary.speciesDelta >= 0 ? "增长" : "衰退";
      return [
        {
          key: "diversity", label: "多样性趋势",
          value: formatDelta(summary.speciesDelta, " 种", 0),
          description: "物种形成与灭绝的净结果",
          accent: summary.speciesDelta >= 0 ? THEME.accentPop : THEME.accentDeath,
        },
        {
          key: "biomass", label: "生物量净变",
          value: formatDelta(summary.populationDelta, "", 1, formatPopulation),
          description: "生态系统承载力变化",
          accent: THEME.accentBio,
        },
        {
          key: "density", label: "平均种群规模",
          value: formatPopulation(avgPop),
          description: "单物种平均种群大小",
          accent: THEME.accentPop,
        },
        {
          key: "health", label: "多样性健康",
          value: diversityHealth,
          description: summary.speciesDelta >= 0 ? "物种多样性正在恢复" : "物种多样性正在下降",
          accent: summary.speciesDelta >= 0 ? THEME.accentPop : THEME.accentDeath,
        },
      ];
      
    case "evolution":
      const branchRate = summary.turnSpan > 0 ? summary.branchingCount / summary.turnSpan : 0;
      return [
        {
          key: "speciation", label: "物种形成率",
          value: `${branchRate.toFixed(2)} / 回合`,
          description: "平均每回合产生的新物种",
          accent: THEME.accentEvolution,
        },
        {
          key: "migrations", label: "迁徙活跃度",
          value: integerFormatter.format(summary.migrationCount),
          description: "物种地理扩散事件总数",
          accent: THEME.accentSea,
        },
        {
          key: "radiationPotential", label: "辐射潜力",
          value: summary.branchingCount > 5 ? "🔥 活跃" : summary.branchingCount > 2 ? "📈 中等" : "💤 低迷",
          description: "物种快速分化的可能性",
          accent: THEME.accentEvolution,
        },
        {
          key: "isolation", label: "隔离程度",
          value: summary.migrationCount > summary.branchingCount ? "低" : "高",
          description: summary.migrationCount > summary.branchingCount ? "频繁基因交流" : "地理隔离促进分化",
          accent: THEME.accentBio,
        },
      ];
      
    case "geology":
      return [
        {
          key: "tectonics", label: "地质阶段",
          value: summary.tectonicStage || "未知",
          description: "当前板块构造状态",
          accent: THEME.accentGeo,
        },
        {
          key: "changes", label: "地形变化",
          value: `${summary.mapChanges} 次`,
          description: "地形改变事件总数",
          accent: THEME.accentGeo,
        },
        {
          key: "seaChange", label: "海平面变化",
          value: formatDelta(summary.seaLevelDelta, " m", 2),
          description: summary.seaLevelDelta > 0 ? "海侵中，陆地面积减少" : summary.seaLevelDelta < 0 ? "海退中，陆地面积增加" : "海平面稳定",
          accent: THEME.accentSea,
        },
        {
          key: "activity", label: "地质活动度",
          value: summary.mapChanges > 5 ? "🌋 剧烈" : summary.mapChanges > 2 ? "⛰️ 活跃" : "🏔️ 平静",
          description: "基于地形变化频率评估",
          accent: summary.mapChanges > 5 ? THEME.accentDeath : THEME.accentGeo,
        },
      ];
      
    case "health":
      const healthScore = Math.max(0, Math.min(100, 
        100 - (summary.avgDeathRate * 100) - (summary.extinctions * 5) + (summary.speciesDelta * 2)
      ));
      return [
        {
          key: "score", label: "生态健康指数",
          value: `${healthScore.toFixed(0)} / 100`,
          description: healthScore > 70 ? "生态系统运行良好" : healthScore > 40 ? "存在压力但可恢复" : "生态系统处于危机",
          accent: healthScore > 70 ? THEME.accentPop : healthScore > 40 ? THEME.accentGeo : THEME.accentDeath,
        },
        {
          key: "mortality", label: "平均死亡率",
          value: `${(summary.avgDeathRate * 100).toFixed(1)}%`,
          description: summary.avgDeathRate < 0.15 ? "种群稳定繁衍" : summary.avgDeathRate < 0.3 ? "存在生存压力" : "高死亡率警报",
          accent: THEME.accentDeath,
        },
        {
          key: "sustainability", label: "可持续性",
          value: summary.populationDelta >= 0 && summary.speciesDelta >= 0 ? "🌱 可持续" : "⚠️ 需关注",
          description: "综合种群和物种变化趋势",
          accent: summary.populationDelta >= 0 ? THEME.accentPop : THEME.accentDeath,
        },
        {
          key: "resilience", label: "恢复力",
          value: summary.branchingCount > summary.extinctions ? "强" : "弱",
          description: "物种形成与灭绝的比率",
          accent: summary.branchingCount > summary.extinctions ? THEME.accentPop : THEME.accentDeath,
        },
      ];
      
    default:
      return [];
  }
}

function buildTimelineEvents(reports: TurnReport[]): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  
  for (const report of reports) {
    const turn = report.turn_index + 1;
    
    // Branching events
    for (const branch of report.branching_events || []) {
      events.push({
        turn,
        type: "branching",
        title: `新物种: ${branch.new_lineage}`,
        description: branch.description || `从 ${branch.parent_lineage} 分化`,
        icon: <GitBranch size={14} />,
        color: THEME.accentEvolution,
      });
    }
    
    // Migration events
    for (const migration of report.migration_events || []) {
      events.push({
        turn,
        type: "migration",
        title: `迁徙: ${migration.lineage_code}`,
        description: `${migration.origin} → ${migration.destination}`,
        icon: <Footprints size={14} />,
        color: THEME.accentSea,
      });
    }
    
    // Map changes
    for (const change of report.map_changes || []) {
      events.push({
        turn,
        type: "geological",
        title: `地质事件: ${change.stage}`,
        description: change.description,
        icon: <Mountain size={14} />,
        color: THEME.accentGeo,
      });
    }
    
    // Major pressure events
    for (const event of report.major_events || []) {
      events.push({
        turn,
        type: "pressure",
        title: `压力事件: ${event.severity}`,
        description: event.description,
        icon: <AlertTriangle size={14} />,
        color: THEME.accentDeath,
      });
    }
  }
  
  // Sort by turn descending (most recent first)
  return events.sort((a, b) => b.turn - a.turn);
}

function buildSpeciesRanking(reports: TurnReport[]): SpeciesSnapshot[] {
  if (reports.length === 0) return [];
  const latest = reports[reports.length - 1];
  return [...latest.species]
    .filter(s => !s.is_background)
    .sort((a, b) => b.population - a.population);
}

function buildRoleDistribution(reports: TurnReport[]): { name: string; value: number }[] {
  if (reports.length === 0) return [];
  const latest = reports[reports.length - 1];
  
  const roleCount: Record<string, number> = {};
  for (const sp of latest.species) {
    const role = sp.ecological_role || "未知";
    roleCount[role] = (roleCount[role] || 0) + 1;
  }
  
  return Object.entries(roleCount)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
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
    padding: '20px',
    gap: '16px',
    color: THEME.textPrimary,
    maxHeight: '85vh',
    overflow: 'hidden',
  },
  controlBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '12px',
    flexShrink: 0,
  },
  tabContainer: {
    display: 'flex',
    gap: '6px',
    background: 'rgba(0,0,0,0.2)',
    padding: '4px',
    borderRadius: '10px',
    flexWrap: 'wrap',
  },
  tabButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    padding: '6px 10px',
    borderRadius: '6px',
    border: '1px solid transparent',
    cursor: 'pointer',
    fontSize: '0.8rem',
    fontWeight: 500,
    transition: 'all 0.2s',
    whiteSpace: 'nowrap',
  },
  controlGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  selectWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    background: 'rgba(0,0,0,0.2)',
    padding: '4px 8px',
    borderRadius: '6px',
    border: `1px solid ${THEME.borderColor}`,
  },
  select: {
    background: 'transparent',
    border: 'none',
    color: THEME.textPrimary,
    fontSize: '0.8rem',
    cursor: 'pointer',
    outline: 'none',
  },
  chartTypeGroup: {
    display: 'flex',
    gap: '2px',
    background: 'rgba(0,0,0,0.2)',
    padding: '2px',
    borderRadius: '6px',
  },
  chartTypeBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '28px',
    height: '28px',
    borderRadius: '4px',
    border: '1px solid transparent',
    cursor: 'pointer',
    transition: 'all 0.2s',
    background: 'transparent',
  },
  iconButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '32px',
    height: '32px',
    borderRadius: '6px',
    border: `1px solid ${THEME.borderColor}`,
    cursor: 'pointer',
    transition: 'all 0.2s',
    background: 'rgba(0,0,0,0.2)',
    color: THEME.textSecondary,
  },
  metricsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: '12px',
    flexShrink: 0,
  },
  mainContent: {
    display: 'flex',
    flex: 1,
    gap: '16px',
    minHeight: 0,
    overflow: 'hidden',
  },
  chartSection: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '12px',
    border: `1px solid ${THEME.borderColor}`,
    padding: '16px',
    minWidth: '0',
  },
  chartHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
    flexWrap: 'wrap',
    gap: '8px',
  },
  chartTitle: {
    fontSize: '1rem',
    fontWeight: 600,
    color: THEME.textPrimary,
  },
  chartLegend: {
    fontSize: '0.75rem',
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
    gap: '12px',
    overflowY: 'auto',
  },
  sidebarSection: {
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '12px',
    border: `1px solid ${THEME.borderColor}`,
    padding: '14px',
  },
  sidebarHeader: {
    marginBottom: '12px',
    paddingBottom: '8px',
    borderBottom: `1px solid ${THEME.borderColor}`,
  },
  sidebarTitle: {
    fontSize: '0.85rem',
    fontWeight: 600,
    color: THEME.textSecondary,
  },
  insightsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  insightCard: {
    padding: '10px',
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '8px',
    borderLeft: `3px solid ${THEME.accentSea}`,
  },
  insightLabel: {
    fontSize: '0.75rem',
    color: THEME.textSecondary,
    marginBottom: '2px',
  },
  insightValue: {
    fontSize: '1rem',
    fontWeight: 600,
    color: THEME.textPrimary,
  },
  insightDesc: {
    fontSize: '0.7rem',
    color: 'rgba(148, 163, 184, 0.7)',
    marginTop: '2px',
  },
  rankingList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  rankingItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px',
    background: 'rgba(255,255,255,0.02)',
    borderRadius: '6px',
  },
  rankBadge: {
    width: '20px',
    height: '20px',
    borderRadius: '50%',
    background: 'rgba(255,255,255,0.1)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.7rem',
    fontWeight: 700,
    flexShrink: 0,
  },
  rankInfo: {
    flex: 1,
    minWidth: 0,
  },
  rankName: {
    fontSize: '0.8rem',
    color: THEME.textPrimary,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  rankPop: {
    fontSize: '0.7rem',
    color: THEME.textSecondary,
  },
  rankBar: {
    width: '50px',
    height: '4px',
    background: 'rgba(255,255,255,0.1)',
    borderRadius: '2px',
    overflow: 'hidden',
  },
  rankBarFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.3s',
  },
  legendGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '6px',
    marginTop: '8px',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.7rem',
    color: THEME.textSecondary,
  },
  legendDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
  },
  metricCard: {
    background: THEME.cardBg,
    borderRadius: '10px',
    padding: '12px',
    border: `1px solid ${THEME.borderColor}`,
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  },
  metricHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: '0.75rem',
    color: THEME.textSecondary,
  },
  metricContent: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '6px',
    flexWrap: 'wrap',
  },
  metricValue: {
    fontSize: '1.3rem',
    fontWeight: 700,
    color: THEME.textPrimary,
  },
  tooltip: {
    backgroundColor: "rgba(15, 23, 42, 0.95)",
    border: `1px solid ${THEME.borderColor}`,
    borderRadius: "8px",
    padding: "10px",
    boxShadow: "0 8px 16px rgba(0,0,0,0.4)",
  },
  tooltipTitle: {
    fontSize: '0.85rem',
    fontWeight: 600,
    color: THEME.textPrimary,
    marginBottom: '6px',
    borderBottom: `1px solid ${THEME.borderColor}`,
    paddingBottom: '4px',
  },
  footer: {
    marginTop: 'auto',
    paddingTop: '12px',
    borderTop: `1px solid ${THEME.borderColor}`,
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    fontSize: '0.75rem',
    color: THEME.textSecondary,
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '12px',
    padding: '12px',
    border: `1px solid ${THEME.borderColor}`,
  },
  footerItem: {
    display: 'flex',
    justifyContent: 'space-between',
  },
  timelineSection: {
    background: 'rgba(15, 23, 42, 0.3)',
    borderRadius: '12px',
    border: `1px solid ${THEME.borderColor}`,
    padding: '14px',
    flexShrink: 0,
  },
  timelineHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
    paddingBottom: '8px',
    borderBottom: `1px solid ${THEME.borderColor}`,
  },
  timelineCount: {
    fontSize: '0.75rem',
    color: THEME.textSecondary,
    background: 'rgba(255,255,255,0.1)',
    padding: '2px 8px',
    borderRadius: '10px',
  },
  timelineScroll: {
    display: 'flex',
    gap: '10px',
    overflowX: 'auto',
    paddingBottom: '8px',
  },
  timelineItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    minWidth: '140px',
    padding: '10px',
    background: 'rgba(255,255,255,0.02)',
    borderRadius: '8px',
    border: `1px solid ${THEME.borderColor}`,
  },
  timelineIcon: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '6px',
  },
  timelineTurn: {
    fontSize: '0.7rem',
    color: THEME.textSecondary,
    marginBottom: '4px',
  },
  timelineContent: {
    textAlign: 'center',
  },
  timelineTitle: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: THEME.textPrimary,
    marginBottom: '2px',
  },
  timelineDesc: {
    fontSize: '0.65rem',
    color: THEME.textSecondary,
    lineHeight: 1.3,
  },
};
