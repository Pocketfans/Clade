/**
 * GlobalTrendsPanel - 全球趋势面板（重构版）
 * 
 * 使用模块化的 hooks 和组件
 */

import { memo } from "react";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Thermometer,
  Waves,
  Users,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  Download,
  BarChart2,
  LineChart as LineChartIcon,
  Leaf,
  Heart,
} from "lucide-react";
import { GamePanel } from "../common/GamePanel";
import { useTrendsData } from "./hooks/useTrendsData";
import type { GlobalTrendsPanelProps, Tab, ChartType, TrendDirection } from "./types";
import { CHART_COLORS, ROLE_COLORS } from "./types";

// ============ 标签页配置 ============
const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "environment", label: "环境", icon: <Thermometer size={16} /> },
  { id: "biodiversity", label: "生物多样性", icon: <Leaf size={16} /> },
  { id: "evolution", label: "进化", icon: <Activity size={16} /> },
  { id: "health", label: "生态健康", icon: <Heart size={16} /> },
];

// ============ 趋势图标 ============
const TrendIcon = memo(function TrendIcon({ direction, value }: { direction: TrendDirection; value: number }) {
  const Icon = direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;
  const color = direction === "up" ? "#22c55e" : direction === "down" ? "#ef4444" : "#64748b";
  
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, color }}>
      <Icon size={14} />
      <span>{direction === "neutral" ? "0" : (value > 0 ? "+" : "") + value.toFixed(1)}</span>
    </span>
  );
});

// ============ 统计卡片 ============
const StatCard = memo(function StatCard({
  icon,
  label,
  value,
  unit,
  delta,
  direction,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  unit?: string;
  delta?: number;
  direction?: TrendDirection;
  color: string;
}) {
  return (
    <div className="stat-card" style={{ borderColor: color }}>
      <div className="stat-icon" style={{ color }}>{icon}</div>
      <div className="stat-content">
        <div className="stat-label">{label}</div>
        <div className="stat-value">
          {typeof value === "number" ? value.toLocaleString() : value}
          {unit && <span className="stat-unit">{unit}</span>}
        </div>
        {delta !== undefined && direction && (
          <TrendIcon direction={direction} value={delta} />
        )}
      </div>
    </div>
  );
});

// ============ 主组件 ============
export const GlobalTrendsPanel = memo(function GlobalTrendsPanel({
  reports,
  onClose,
}: GlobalTrendsPanelProps) {
  const {
    activeTab,
    setActiveTab,
    chartType,
    setChartType,
    timeRange,
    setTimeRange,
    summaryStats,
    environmentData,
    speciesTimeline,
    populationData,
    roleDistribution,
    healthMetrics,
    getTrendDirection,
    exportData,
  } = useTrendsData({ reports });

  // 格式化大数字
  const formatNumber = (n: number): string => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toLocaleString();
  };

  // 渲染图表
  const renderChart = () => {
    const ChartComponent = chartType === "area" ? AreaChart : chartType === "bar" ? BarChart : LineChart;
    const DataComponent = chartType === "area" ? Area : chartType === "bar" ? Bar : Line;

    switch (activeTab) {
      case "environment":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <ChartComponent data={environmentData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="turn" stroke="#888" fontSize={12} />
              <YAxis stroke="#888" fontSize={12} />
              <Tooltip
                contentStyle={{ background: "rgba(0,0,0,0.8)", border: "none", borderRadius: 8 }}
              />
              <Legend />
              <DataComponent
                type="monotone"
                dataKey="temperature"
                name="温度 (°C)"
                stroke={CHART_COLORS.temperature}
                fill={CHART_COLORS.temperature}
                fillOpacity={0.3}
              />
              <DataComponent
                type="monotone"
                dataKey="humidity"
                name="湿度 (%)"
                stroke={CHART_COLORS.humidity}
                fill={CHART_COLORS.humidity}
                fillOpacity={0.3}
              />
              <DataComponent
                type="monotone"
                dataKey="sea_level"
                name="海平面 (m)"
                stroke={CHART_COLORS.seaLevel}
                fill={CHART_COLORS.seaLevel}
                fillOpacity={0.3}
              />
            </ChartComponent>
          </ResponsiveContainer>
        );

      case "biodiversity":
        return (
          <div className="biodiversity-charts">
            <ResponsiveContainer width="100%" height={200}>
              <ChartComponent data={speciesTimeline}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="turn" stroke="#888" fontSize={12} />
                <YAxis stroke="#888" fontSize={12} />
                <Tooltip
                  contentStyle={{ background: "rgba(0,0,0,0.8)", border: "none", borderRadius: 8 }}
                />
                <Legend />
                <DataComponent
                  type="monotone"
                  dataKey="alive"
                  name="存活物种"
                  stroke={CHART_COLORS.species}
                  fill={CHART_COLORS.species}
                  fillOpacity={0.3}
                />
                <DataComponent
                  type="monotone"
                  dataKey="extinct"
                  name="灭绝物种"
                  stroke={CHART_COLORS.extinction}
                  fill={CHART_COLORS.extinction}
                  fillOpacity={0.3}
                />
              </ChartComponent>
            </ResponsiveContainer>
            
            {roleDistribution.length > 0 && (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={roleDistribution}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {roleDistribution.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        );

      case "evolution":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <ChartComponent data={speciesTimeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="turn" stroke="#888" fontSize={12} />
              <YAxis stroke="#888" fontSize={12} />
              <Tooltip
                contentStyle={{ background: "rgba(0,0,0,0.8)", border: "none", borderRadius: 8 }}
              />
              <Legend />
              <DataComponent
                type="monotone"
                dataKey="branching"
                name="分化事件"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.3}
              />
            </ChartComponent>
          </ResponsiveContainer>
        );

      case "health":
        return (
          <ResponsiveContainer width="100%" height={300}>
            <ChartComponent data={healthMetrics}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="turn" stroke="#888" fontSize={12} />
              <YAxis stroke="#888" fontSize={12} domain={[0, 1]} />
              <Tooltip
                contentStyle={{ background: "rgba(0,0,0,0.8)", border: "none", borderRadius: 8 }}
              />
              <Legend />
              <DataComponent
                type="monotone"
                dataKey="biodiversity_index"
                name="生物多样性指数"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.3}
              />
              <DataComponent
                type="monotone"
                dataKey="ecosystem_stability"
                name="生态稳定性"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.3}
              />
            </ChartComponent>
          </ResponsiveContainer>
        );

      default:
        return null;
    }
  };

  return (
    <GamePanel
      title="📊 全球趋势"
      onClose={onClose}
      className="global-trends-panel"
    >
      <div className="trends-layout">
        {/* 统计摘要 */}
        <div className="stats-row">
          <StatCard
            icon={<Thermometer size={20} />}
            label="温度"
            value={summaryStats.temp.toFixed(1)}
            unit="°C"
            delta={summaryStats.tempDelta}
            direction={getTrendDirection(summaryStats.temp, summaryStats.temp - summaryStats.tempDelta)}
            color={CHART_COLORS.temperature}
          />
          <StatCard
            icon={<Waves size={20} />}
            label="海平面"
            value={summaryStats.seaLevel.toFixed(1)}
            unit="m"
            delta={summaryStats.seaLevelDelta}
            direction={getTrendDirection(summaryStats.seaLevel, summaryStats.seaLevel - summaryStats.seaLevelDelta)}
            color={CHART_COLORS.seaLevel}
          />
          <StatCard
            icon={<Leaf size={20} />}
            label="物种数"
            value={summaryStats.species}
            delta={summaryStats.speciesDelta}
            direction={getTrendDirection(summaryStats.species, summaryStats.species - summaryStats.speciesDelta)}
            color={CHART_COLORS.species}
          />
          <StatCard
            icon={<Users size={20} />}
            label="总人口"
            value={formatNumber(summaryStats.population)}
            delta={summaryStats.populationDelta}
            direction={getTrendDirection(summaryStats.population, summaryStats.population - summaryStats.populationDelta)}
            color={CHART_COLORS.population}
          />
        </div>

        {/* 控制栏 */}
        <div className="controls-bar">
          {/* 标签页 */}
          <div className="tabs">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* 控制 */}
          <div className="controls">
            {/* 图表类型 */}
            <div className="control-group">
              <button
                className={`icon-btn ${chartType === "line" ? "active" : ""}`}
                onClick={() => setChartType("line")}
                title="折线图"
              >
                <LineChartIcon size={16} />
              </button>
              <button
                className={`icon-btn ${chartType === "area" ? "active" : ""}`}
                onClick={() => setChartType("area")}
                title="面积图"
              >
                <Activity size={16} />
              </button>
              <button
                className={`icon-btn ${chartType === "bar" ? "active" : ""}`}
                onClick={() => setChartType("bar")}
                title="柱状图"
              >
                <BarChart2 size={16} />
              </button>
            </div>

            {/* 时间范围 */}
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as typeof timeRange)}
              className="range-select"
            >
              <option value="all">全部</option>
              <option value="10">最近10回合</option>
              <option value="20">最近20回合</option>
              <option value="50">最近50回合</option>
            </select>

            {/* 导出 */}
            <button className="icon-btn" onClick={exportData} title="导出数据">
              <Download size={16} />
            </button>
          </div>
        </div>

        {/* 图表区域 */}
        <div className="chart-area">
          {reports.length === 0 ? (
            <div className="empty-state">
              <Activity size={48} />
              <p>暂无回合数据</p>
              <p className="hint">完成一些回合后才能查看趋势</p>
            </div>
          ) : (
            renderChart()
          )}
        </div>
      </div>
    </GamePanel>
  );
});

export default GlobalTrendsPanel;



