/**
 * GlobalTrendsPanel - 全球趋势面板（现代化重构版 v2）
 * 
 * 特点：
 * - 现代化玻璃态设计
 * - 丰富的信息展示
 * - 自定义下拉菜单
 * - 流畅的动画效果
 */

import { memo, useState, useCallback, useRef, useEffect, useMemo } from "react";
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
  Sparklines,
  SparklinesLine,
  ComposedChart,
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
  Globe,
  Zap,
  ChevronDown,
  AreaChart as AreaChartIcon,
  Sparkles,
  Droplets,
  Skull,
  GitBranch,
  Clock,
  Target,
  Award,
  Layers,
  Sun,
  Mountain,
  Check,
  ChevronRight,
  AlertTriangle,
  Info,
  Timer,
  Flame,
} from "lucide-react";
import { GamePanel } from "../common/GamePanel";
import { useTrendsData } from "./hooks/useTrendsData";
import type { GlobalTrendsPanelProps, Tab, ChartType, TrendDirection, TimeRange } from "./types";
import { CHART_COLORS, ROLE_COLORS } from "./types";
import "./GlobalTrendsPanel.css";

// ============ 标签页配置 ============
const TABS: { id: Tab; label: string; icon: React.ReactNode; color: string }[] = [
  { id: "environment", label: "环境", icon: <Thermometer size={18} />, color: "#ef4444" },
  { id: "biodiversity", label: "生物多样性", icon: <Leaf size={18} />, color: "#22c55e" },
  { id: "evolution", label: "进化", icon: <Activity size={18} />, color: "#8b5cf6" },
  { id: "health", label: "生态健康", icon: <Heart size={18} />, color: "#ec4899" },
];

// ============ 时间范围选项 ============
const TIME_RANGE_OPTIONS: { value: TimeRange; label: string; icon: React.ReactNode }[] = [
  { value: "all", label: "全部回合", icon: <Globe size={14} /> },
  { value: "10", label: "最近 10 回合", icon: <Clock size={14} /> },
  { value: "20", label: "最近 20 回合", icon: <Timer size={14} /> },
  { value: "50", label: "最近 50 回合", icon: <Layers size={14} /> },
];

// ============ 自定义下拉菜单 ============
const CustomSelect = memo(function CustomSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string; icon?: React.ReactNode }[];
  onChange: (value: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find(o => o.value === value) || options[0];

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={ref} className={`gtp-custom-select ${isOpen ? "open" : ""}`}>
      <button 
        className="gtp-select-trigger"
        onClick={() => setIsOpen(!isOpen)}
      >
        {selected.icon && <span className="gtp-select-icon">{selected.icon}</span>}
        <span className="gtp-select-text">{selected.label}</span>
        <ChevronDown size={14} className={`gtp-select-chevron ${isOpen ? "rotated" : ""}`} />
      </button>
      
      {isOpen && (
        <div className="gtp-select-dropdown">
          {options.map((option) => (
            <button
              key={option.value}
              className={`gtp-select-option ${option.value === value ? "selected" : ""}`}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
            >
              {option.icon && <span className="gtp-option-icon">{option.icon}</span>}
              <span className="gtp-option-text">{option.label}</span>
              {option.value === value && <Check size={14} className="gtp-option-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

// ============ 迷你趋势线 ============
const MiniTrendLine = memo(function MiniTrendLine({ 
  data, 
  color,
  height = 24,
}: { 
  data: number[];
  color: string;
  height?: number;
}) {
  if (!data.length) return null;
  
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const normalized = data.map(v => ((v - min) / range) * 100);
  
  const pathData = normalized.map((v, i) => 
    `${i === 0 ? 'M' : 'L'} ${(i / (normalized.length - 1)) * 100} ${100 - v}`
  ).join(' ');

  return (
    <svg 
      viewBox="0 0 100 100" 
      className="gtp-mini-trend"
      style={{ height }}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path
        d={pathData + ` L 100 100 L 0 100 Z`}
        fill={`url(#grad-${color.replace('#', '')})`}
      />
      <path
        d={pathData}
        fill="none"
        stroke={color}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
});

// ============ 趋势指示器 ============
const TrendIndicator = memo(function TrendIndicator({ 
  direction, 
  value 
}: { 
  direction: TrendDirection; 
  value: number;
}) {
  const config = {
    up: { Icon: TrendingUp, color: "#22c55e", bg: "rgba(34, 197, 94, 0.15)" },
    down: { Icon: TrendingDown, color: "#ef4444", bg: "rgba(239, 68, 68, 0.15)" },
    neutral: { Icon: Minus, color: "#64748b", bg: "rgba(100, 116, 139, 0.15)" },
  }[direction];

  return (
    <div className="gtp-trend-indicator" style={{ background: config.bg }}>
      <config.Icon size={12} style={{ color: config.color }} />
      <span style={{ color: config.color }}>
        {direction === "neutral" ? "0" : (value > 0 ? "+" : "") + value.toFixed(1)}
      </span>
    </div>
  );
});

// ============ 增强型统计卡片 ============
const StatCard = memo(function StatCard({
  icon,
  label,
  value,
  unit,
  delta,
  direction,
  color,
  delay = 0,
  sparklineData,
  subValue,
  subLabel,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  unit?: string;
  delta?: number;
  direction?: TrendDirection;
  color: string;
  delay?: number;
  sparklineData?: number[];
  subValue?: string | number;
  subLabel?: string;
}) {
  return (
    <div 
      className="gtp-stat-card"
      style={{ 
        "--card-color": color,
        "--delay": `${delay}ms`,
      } as React.CSSProperties}
    >
      <div className="gtp-stat-main">
        <div className="gtp-stat-icon-wrap" style={{ background: `${color}20`, color }}>
          {icon}
        </div>
        <div className="gtp-stat-content">
          <div className="gtp-stat-label">{label}</div>
          <div className="gtp-stat-value-row">
            <span className="gtp-stat-value">
              {typeof value === "number" ? value.toLocaleString() : value}
            </span>
            {unit && <span className="gtp-stat-unit">{unit}</span>}
          </div>
          {delta !== undefined && direction && (
            <TrendIndicator direction={direction} value={delta} />
          )}
        </div>
      </div>
      
      {/* 迷你趋势图 */}
      {sparklineData && sparklineData.length > 1 && (
        <div className="gtp-stat-sparkline">
          <MiniTrendLine data={sparklineData} color={color} />
        </div>
      )}
      
      {/* 附加信息 */}
      {subValue !== undefined && (
        <div className="gtp-stat-sub">
          <span className="gtp-stat-sub-label">{subLabel}</span>
          <span className="gtp-stat-sub-value">{subValue}</span>
        </div>
      )}
      
      <div className="gtp-stat-glow" style={{ background: color }} />
    </div>
  );
});

// ============ 信息卡片 ============
const InfoCard = memo(function InfoCard({
  icon,
  title,
  items,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  items: { label: string; value: string | number; color?: string }[];
  color: string;
}) {
  return (
    <div className="gtp-info-card" style={{ "--card-color": color } as React.CSSProperties}>
      <div className="gtp-info-header">
        <span className="gtp-info-icon" style={{ color }}>{icon}</span>
        <span className="gtp-info-title">{title}</span>
      </div>
      <div className="gtp-info-items">
        {items.map((item, i) => (
          <div key={i} className="gtp-info-item">
            <span className="gtp-info-label">{item.label}</span>
            <span className="gtp-info-value" style={{ color: item.color }}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
});

// ============ 事件时间线项 ============
const TimelineItem = memo(function TimelineItem({
  turn,
  type,
  title,
  detail,
  color,
}: {
  turn: number;
  type: string;
  title: string;
  detail?: string;
  color: string;
}) {
  return (
    <div className="gtp-timeline-item">
      <div className="gtp-timeline-dot" style={{ background: color }} />
      <div className="gtp-timeline-content">
        <div className="gtp-timeline-header">
          <span className="gtp-timeline-turn">回合 {turn}</span>
          <span className="gtp-timeline-type" style={{ color }}>{type}</span>
        </div>
        <div className="gtp-timeline-title">{title}</div>
        {detail && <div className="gtp-timeline-detail">{detail}</div>}
      </div>
    </div>
  );
});

// ============ 自定义 Tooltip ============
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  
  return (
    <div className="gtp-tooltip">
      <div className="gtp-tooltip-header">回合 {label}</div>
      <div className="gtp-tooltip-content">
        {payload.map((entry: any, index: number) => (
          <div key={index} className="gtp-tooltip-item">
            <span 
              className="gtp-tooltip-dot" 
              style={{ background: entry.color }}
            />
            <span className="gtp-tooltip-label">{entry.name}</span>
            <span className="gtp-tooltip-value">
              {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

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
    filteredReports,
  } = useTrendsData({ reports });

  // 格式化大数字
  const formatNumber = useCallback((n: number): string => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toLocaleString();
  }, []);

  // 计算额外统计
  const extraStats = useMemo(() => {
    if (!filteredReports.length) return null;
    
    const latest = filteredReports[filteredReports.length - 1];
    const latestSpecies = latest.species || [];
    
    // 总灭绝数
    const extinctCount = latestSpecies.filter(s => s.status === "extinct").length;
    
    // 总分化事件
    const totalBranching = filteredReports.reduce((sum, r) => 
      sum + (r.branching_events?.length || 0), 0
    );
    
    // 最近的重要事件
    const recentEvents: { turn: number; type: string; title: string; detail?: string; color: string }[] = [];
    
    // 收集最近的分化事件
    [...filteredReports].reverse().slice(0, 10).forEach(r => {
      r.branching_events?.forEach(e => {
        if (recentEvents.length < 5) {
          recentEvents.push({
            turn: r.turn_index,
            type: "分化",
            title: `新物种 ${e.child_code} 诞生`,
            detail: `从 ${e.parent_code} 分化`,
            color: "#22c55e"
          });
        }
      });
    });
    
    // 湿度数据
    const humidity = latest.global_humidity ?? 0;
    const prevHumidity = filteredReports.length > 1 
      ? filteredReports[filteredReports.length - 2].global_humidity ?? humidity
      : humidity;
    
    // 环境趋势数据
    const tempTrend = environmentData.map(d => d.temperature);
    const humidityTrend = environmentData.map(d => d.humidity);
    const seaLevelTrend = environmentData.map(d => d.sea_level);
    const speciesTrend = speciesTimeline.map(d => d.alive);
    const populationTrend = speciesTimeline.map(d => d.alive); // 使用物种数代替
    
    // 角色统计
    const roleStats = roleDistribution.reduce((acc, r) => {
      acc[r.name] = r.value;
      return acc;
    }, {} as Record<string, number>);
    
    // 计算平均适应度（如果有的话）
    const avgFitness = latestSpecies.length > 0
      ? latestSpecies.reduce((sum, s) => sum + (s.population || 0), 0) / latestSpecies.length
      : 0;
    
    return {
      extinctCount,
      totalBranching,
      recentEvents,
      humidity,
      humidityDelta: humidity - prevHumidity,
      tempTrend,
      humidityTrend,
      seaLevelTrend,
      speciesTrend,
      populationTrend,
      roleStats,
      avgFitness,
      aliveSpecies: latestSpecies.filter(s => s.status === "alive"),
    };
  }, [filteredReports, environmentData, speciesTimeline, roleDistribution]);

  // 获取当前Tab配置
  const currentTab = TABS.find(t => t.id === activeTab) || TABS[0];

  // 渲染环境图表
  const renderEnvironmentChart = () => {
    return (
      <div className="gtp-env-layout">
        {/* 主图表 */}
        <div className="gtp-main-chart">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={environmentData}>
              <defs>
                <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CHART_COLORS.temperature} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={CHART_COLORS.temperature} stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="humidityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CHART_COLORS.humidity} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={CHART_COLORS.humidity} stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="seaLevelGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CHART_COLORS.seaLevel} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={CHART_COLORS.seaLevel} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="turn" stroke="rgba(255,255,255,0.3)" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ paddingTop: "12px" }} iconType="circle" />
              <Area type="monotone" dataKey="temperature" name="温度 (°C)" stroke={CHART_COLORS.temperature} fill="url(#tempGradient)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="humidity" name="湿度 (%)" stroke={CHART_COLORS.humidity} fill="url(#humidityGradient)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="sea_level" name="海平面 (m)" stroke={CHART_COLORS.seaLevel} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        
        {/* 环境详情侧栏 */}
        <div className="gtp-env-sidebar">
          <InfoCard
            icon={<Thermometer size={16} />}
            title="温度详情"
            color={CHART_COLORS.temperature}
            items={[
              { label: "当前温度", value: `${summaryStats.temp.toFixed(1)}°C` },
              { label: "温度变化", value: `${summaryStats.tempDelta > 0 ? '+' : ''}${summaryStats.tempDelta.toFixed(2)}°C`, color: summaryStats.tempDelta > 0 ? "#ef4444" : "#22c55e" },
              { label: "适宜范围", value: "15-25°C" },
            ]}
          />
          <InfoCard
            icon={<Droplets size={16} />}
            title="湿度详情"
            color={CHART_COLORS.humidity}
            items={[
              { label: "当前湿度", value: `${(extraStats?.humidity || 0).toFixed(1)}%` },
              { label: "湿度变化", value: `${(extraStats?.humidityDelta || 0) > 0 ? '+' : ''}${(extraStats?.humidityDelta || 0).toFixed(2)}%` },
              { label: "最佳范围", value: "40-70%" },
            ]}
          />
          <InfoCard
            icon={<Waves size={16} />}
            title="海平面"
            color={CHART_COLORS.seaLevel}
            items={[
              { label: "当前高度", value: `${summaryStats.seaLevel.toFixed(1)}m` },
              { label: "变化趋势", value: `${summaryStats.seaLevelDelta > 0 ? '+' : ''}${summaryStats.seaLevelDelta.toFixed(2)}m` },
            ]}
          />
        </div>
      </div>
    );
  };

  // 渲染生物多样性图表
  const renderBiodiversityChart = () => {
    return (
      <div className="gtp-bio-layout">
        {/* 左侧主图表区 */}
        <div className="gtp-bio-main">
          {/* 物种变化趋势图 */}
          <div className="gtp-chart-section">
            <div className="gtp-section-header">
              <span className="gtp-section-icon"><Leaf size={16} /></span>
              <span className="gtp-section-title">物种数量变化</span>
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={speciesTimeline}>
                <defs>
                  <linearGradient id="aliveGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.species} stopOpacity={0.4}/>
                    <stop offset="95%" stopColor={CHART_COLORS.species} stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="extinctGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.extinction} stopOpacity={0.4}/>
                    <stop offset="95%" stopColor={CHART_COLORS.extinction} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="turn" stroke="rgba(255,255,255,0.3)" fontSize={10} />
                <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Area type="monotone" dataKey="alive" name="存活" stroke={CHART_COLORS.species} fill="url(#aliveGradient)" strokeWidth={2} />
                <Area type="monotone" dataKey="extinct" name="灭绝" stroke={CHART_COLORS.extinction} fill="url(#extinctGradient)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          
          {/* 角色分布饼图 */}
          {roleDistribution.length > 0 && (
            <div className="gtp-chart-section">
              <div className="gtp-section-header">
                <span className="gtp-section-icon"><Layers size={16} /></span>
                <span className="gtp-section-title">生态角色分布</span>
              </div>
              <div className="gtp-pie-container">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie
                      data={roleDistribution}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={65}
                      paddingAngle={3}
                    >
                      {roleDistribution.map((entry, index) => (
                        <Cell key={index} fill={entry.color} stroke="rgba(0,0,0,0.2)" strokeWidth={1} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => [value, "物种"]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="gtp-pie-legend">
                  {roleDistribution.map((item, i) => (
                    <div key={i} className="gtp-pie-legend-item">
                      <span className="gtp-pie-legend-dot" style={{ background: item.color }} />
                      <span className="gtp-pie-legend-label">{item.name}</span>
                      <span className="gtp-pie-legend-value">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* 右侧统计栏 */}
        <div className="gtp-bio-sidebar">
          <div className="gtp-stats-mini-grid">
            <div className="gtp-mini-stat">
              <div className="gtp-mini-stat-icon" style={{ background: "rgba(34, 197, 94, 0.15)", color: "#22c55e" }}>
                <Leaf size={16} />
              </div>
              <div className="gtp-mini-stat-info">
                <span className="gtp-mini-stat-value">{summaryStats.species}</span>
                <span className="gtp-mini-stat-label">存活物种</span>
              </div>
            </div>
            <div className="gtp-mini-stat">
              <div className="gtp-mini-stat-icon" style={{ background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" }}>
                <Skull size={16} />
              </div>
              <div className="gtp-mini-stat-info">
                <span className="gtp-mini-stat-value">{extraStats?.extinctCount || 0}</span>
                <span className="gtp-mini-stat-label">已灭绝</span>
              </div>
            </div>
            <div className="gtp-mini-stat">
              <div className="gtp-mini-stat-icon" style={{ background: "rgba(139, 92, 246, 0.15)", color: "#8b5cf6" }}>
                <GitBranch size={16} />
              </div>
              <div className="gtp-mini-stat-info">
                <span className="gtp-mini-stat-value">{extraStats?.totalBranching || 0}</span>
                <span className="gtp-mini-stat-label">分化事件</span>
              </div>
            </div>
            <div className="gtp-mini-stat">
              <div className="gtp-mini-stat-icon" style={{ background: "rgba(34, 211, 238, 0.15)", color: "#22d3ee" }}>
                <Users size={16} />
              </div>
              <div className="gtp-mini-stat-info">
                <span className="gtp-mini-stat-value">{formatNumber(summaryStats.population)}</span>
                <span className="gtp-mini-stat-label">总规模(kg)</span>
              </div>
            </div>
          </div>
          
          {/* 顶级物种 */}
          {extraStats?.aliveSpecies && extraStats.aliveSpecies.length > 0 && (
            <div className="gtp-top-species">
              <div className="gtp-section-header small">
                <Award size={14} />
                <span>规模最大物种</span>
              </div>
              <div className="gtp-species-list">
                {[...extraStats.aliveSpecies]
                  .sort((a, b) => (b.population || 0) - (a.population || 0))
                  .slice(0, 5)
                  .map((species, i) => (
                    <div key={i} className="gtp-species-item">
                      <span className="gtp-species-rank">#{i + 1}</span>
                      <span className="gtp-species-code">{species.lineage_code}</span>
                      <span className="gtp-species-pop">{formatNumber(species.population || 0)}</span>
                    </div>
                  ))
                }
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // 渲染进化图表
  const renderEvolutionChart = () => {
    return (
      <div className="gtp-evo-layout">
        {/* 分化事件图表 */}
        <div className="gtp-evo-main">
          <div className="gtp-section-header">
            <span className="gtp-section-icon"><GitBranch size={16} /></span>
            <span className="gtp-section-title">分化事件趋势</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={speciesTimeline}>
              <defs>
                <linearGradient id="branchingGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.8}/>
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.2}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="turn" stroke="rgba(255,255,255,0.3)" fontSize={11} />
              <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="branching" name="分化事件" fill="url(#branchingGradient)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        
        {/* 进化时间线 */}
        <div className="gtp-evo-sidebar">
          <div className="gtp-section-header small">
            <Clock size={14} />
            <span>近期进化事件</span>
          </div>
          <div className="gtp-timeline">
            {extraStats?.recentEvents && extraStats.recentEvents.length > 0 ? (
              extraStats.recentEvents.map((event, i) => (
                <TimelineItem key={i} {...event} />
              ))
            ) : (
              <div className="gtp-timeline-empty">
                <Info size={20} />
                <span>暂无进化事件</span>
              </div>
            )}
          </div>
          
          {/* 进化统计 */}
          <div className="gtp-evo-stats">
            <div className="gtp-evo-stat">
              <span className="gtp-evo-stat-value">{extraStats?.totalBranching || 0}</span>
              <span className="gtp-evo-stat-label">总分化次数</span>
            </div>
            <div className="gtp-evo-stat">
              <span className="gtp-evo-stat-value">
                {filteredReports.length > 0 
                  ? ((extraStats?.totalBranching || 0) / filteredReports.length).toFixed(2)
                  : "0.00"
                }
              </span>
              <span className="gtp-evo-stat-label">每回合分化率</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // 渲染健康指标图表
  const renderHealthChart = () => {
    const latestHealth = healthMetrics.length > 0 ? healthMetrics[healthMetrics.length - 1] : null;
    
    return (
      <div className="gtp-health-layout">
        {/* 主图表 */}
        <div className="gtp-health-main">
          <div className="gtp-section-header">
            <span className="gtp-section-icon"><Heart size={16} /></span>
            <span className="gtp-section-title">生态健康指数</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={healthMetrics}>
              <defs>
                <linearGradient id="biodivGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="stabilityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="turn" stroke="rgba(255,255,255,0.3)" fontSize={10} />
              <YAxis domain={[0, 1]} stroke="rgba(255,255,255,0.3)" fontSize={10} />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Area type="monotone" dataKey="biodiversity_index" name="多样性指数" stroke="#22c55e" fill="url(#biodivGradient)" strokeWidth={2} />
              <Area type="monotone" dataKey="ecosystem_stability" name="稳定性指数" stroke="#3b82f6" fill="url(#stabilityGradient)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        
        {/* 健康仪表盘 */}
        <div className="gtp-health-sidebar">
          <div className="gtp-health-gauges">
            {latestHealth && (
              <>
                <div className="gtp-gauge-card">
                  <div className="gtp-gauge-ring">
                    <svg viewBox="0 0 36 36" className="gtp-gauge-svg">
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3" />
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#22c55e" strokeWidth="3" strokeDasharray={`${latestHealth.biodiversity_index * 100}, 100`} strokeLinecap="round" style={{ filter: "drop-shadow(0 0 6px #22c55e80)" }} />
                    </svg>
                    <div className="gtp-gauge-value" style={{ color: "#22c55e" }}>
                      {(latestHealth.biodiversity_index * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="gtp-gauge-label">生物多样性</div>
                </div>
                <div className="gtp-gauge-card">
                  <div className="gtp-gauge-ring">
                    <svg viewBox="0 0 36 36" className="gtp-gauge-svg">
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3" />
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#3b82f6" strokeWidth="3" strokeDasharray={`${latestHealth.ecosystem_stability * 100}, 100`} strokeLinecap="round" style={{ filter: "drop-shadow(0 0 6px #3b82f680)" }} />
                    </svg>
                    <div className="gtp-gauge-value" style={{ color: "#3b82f6" }}>
                      {(latestHealth.ecosystem_stability * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="gtp-gauge-label">生态稳定性</div>
                </div>
              </>
            )}
          </div>
          
          {/* 健康状态 */}
          <div className="gtp-health-status">
            <div className="gtp-status-header">
              <Target size={14} />
              <span>综合评估</span>
            </div>
            {latestHealth && (() => {
              const overallScore = (latestHealth.biodiversity_index + latestHealth.ecosystem_stability) / 2;
              let status, color, icon;
              if (overallScore >= 0.7) {
                status = "生态系统健康";
                color = "#22c55e";
                icon = <Sparkles size={16} />;
              } else if (overallScore >= 0.4) {
                status = "需要关注";
                color = "#f59e0b";
                icon = <AlertTriangle size={16} />;
              } else {
                status = "生态危机";
                color = "#ef4444";
                icon = <Flame size={16} />;
              }
              return (
                <div className="gtp-status-badge" style={{ background: `${color}20`, borderColor: `${color}40` }}>
                  <span style={{ color }}>{icon}</span>
                  <span style={{ color }}>{status}</span>
                </div>
              );
            })()}
          </div>
        </div>
      </div>
    );
  };

  // 渲染图表
  const renderChart = () => {
    switch (activeTab) {
      case "environment":
        return renderEnvironmentChart();
      case "biodiversity":
        return renderBiodiversityChart();
      case "evolution":
        return renderEvolutionChart();
      case "health":
        return renderHealthChart();
      default:
        return null;
    }
  };

  return (
    <GamePanel
      title={
        <div className="gtp-title">
          <Globe size={22} className="gtp-title-icon" />
          <span>全球趋势分析</span>
          <Sparkles size={14} className="gtp-title-sparkle" />
        </div>
      }
      onClose={onClose}
      width="1100px"
      height="auto"
    >
      <div className="gtp-container">
        {/* 顶部统计卡片 - 6列网格 */}
        <div className="gtp-stats-grid-6">
          <StatCard
            icon={<Thermometer size={18} />}
            label="温度"
            value={summaryStats.temp.toFixed(1)}
            unit="°C"
            delta={summaryStats.tempDelta}
            direction={getTrendDirection(summaryStats.temp, summaryStats.temp - summaryStats.tempDelta)}
            color={CHART_COLORS.temperature}
            delay={0}
            sparklineData={extraStats?.tempTrend}
          />
          <StatCard
            icon={<Droplets size={18} />}
            label="湿度"
            value={(extraStats?.humidity || 0).toFixed(1)}
            unit="%"
            delta={extraStats?.humidityDelta || 0}
            direction={getTrendDirection(extraStats?.humidity || 0, (extraStats?.humidity || 0) - (extraStats?.humidityDelta || 0))}
            color={CHART_COLORS.humidity}
            delay={50}
            sparklineData={extraStats?.humidityTrend}
          />
          <StatCard
            icon={<Waves size={18} />}
            label="海平面"
            value={summaryStats.seaLevel.toFixed(1)}
            unit="m"
            delta={summaryStats.seaLevelDelta}
            direction={getTrendDirection(summaryStats.seaLevel, summaryStats.seaLevel - summaryStats.seaLevelDelta)}
            color={CHART_COLORS.seaLevel}
            delay={100}
            sparklineData={extraStats?.seaLevelTrend}
          />
          <StatCard
            icon={<Leaf size={18} />}
            label="存活物种"
            value={summaryStats.species}
            delta={summaryStats.speciesDelta}
            direction={getTrendDirection(summaryStats.species, summaryStats.species - summaryStats.speciesDelta)}
            color={CHART_COLORS.species}
            delay={150}
            sparklineData={extraStats?.speciesTrend}
            subLabel="灭绝"
            subValue={extraStats?.extinctCount || 0}
          />
          <StatCard
            icon={<Users size={18} />}
            label="总规模"
            value={formatNumber(summaryStats.population)}
            unit="kg"
            delta={summaryStats.populationDelta}
            direction={getTrendDirection(summaryStats.population, summaryStats.population - summaryStats.populationDelta)}
            color={CHART_COLORS.population}
            delay={200}
          />
          <StatCard
            icon={<GitBranch size={18} />}
            label="分化事件"
            value={extraStats?.totalBranching || 0}
            color="#8b5cf6"
            delay={250}
          />
        </div>

        {/* 控制栏 */}
        <div className="gtp-controls">
          {/* 标签页 */}
          <div className="gtp-tabs">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={`gtp-tab ${activeTab === tab.id ? "active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
                style={{ "--tab-color": tab.color } as React.CSSProperties}
              >
                <span className="gtp-tab-icon">{tab.icon}</span>
                <span className="gtp-tab-label">{tab.label}</span>
                {activeTab === tab.id && <div className="gtp-tab-indicator" />}
              </button>
            ))}
          </div>

          {/* 工具栏 */}
          <div className="gtp-toolbar">
            {/* 图表类型切换 */}
            <div className="gtp-chart-types">
              <button
                className={`gtp-chart-type-btn ${chartType === "line" ? "active" : ""}`}
                onClick={() => setChartType("line")}
                title="折线图"
              >
                <LineChartIcon size={16} />
              </button>
              <button
                className={`gtp-chart-type-btn ${chartType === "area" ? "active" : ""}`}
                onClick={() => setChartType("area")}
                title="面积图"
              >
                <AreaChartIcon size={16} />
              </button>
              <button
                className={`gtp-chart-type-btn ${chartType === "bar" ? "active" : ""}`}
                onClick={() => setChartType("bar")}
                title="柱状图"
              >
                <BarChart2 size={16} />
              </button>
            </div>

            {/* 时间范围 - 自定义下拉菜单 */}
            <CustomSelect
              value={timeRange}
              options={TIME_RANGE_OPTIONS}
              onChange={(v) => setTimeRange(v as TimeRange)}
            />

            {/* 导出按钮 */}
            <button className="gtp-export-btn" onClick={exportData} title="导出数据">
              <Download size={16} />
              <span>导出</span>
            </button>
          </div>
        </div>

        {/* 图表区域 */}
        <div className="gtp-chart-area">
          {reports.length === 0 ? (
            <div className="gtp-empty-state">
              <div className="gtp-empty-icon-wrap">
                <Activity size={48} className="gtp-empty-icon" />
                <div className="gtp-empty-pulse" />
                <div className="gtp-empty-pulse delay" />
              </div>
              <h3 className="gtp-empty-title">暂无回合数据</h3>
              <p className="gtp-empty-hint">完成一些回合后，这里将显示详细的趋势分析</p>
            </div>
          ) : (
            <div className="gtp-chart-wrapper">
              {renderChart()}
            </div>
          )}
        </div>

        {/* 底部信息 */}
        <div className="gtp-footer">
          <div className="gtp-footer-stat">
            <Zap size={14} />
            <span>已分析 <strong>{reports.length}</strong> 回合数据</span>
          </div>
          <div className="gtp-footer-stat">
            <Clock size={14} />
            <span>显示范围：{TIME_RANGE_OPTIONS.find(o => o.value === timeRange)?.label}</span>
          </div>
          <div className="gtp-footer-stat">
            <Activity size={14} />
            <span>最后更新：回合 {reports.length > 0 ? reports[reports.length - 1].turn_index : 0}</span>
          </div>
        </div>
      </div>
    </GamePanel>
  );
});

export default GlobalTrendsPanel;
