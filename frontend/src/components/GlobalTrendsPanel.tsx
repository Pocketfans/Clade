import React, { useMemo, useState, useCallback, useEffect, useRef } from "react";
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
  Calendar,
  Sparkles,
  Orbit,
  Dna,
  Leaf,
  Wind
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
  glow: string;
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
const PANEL_WIDTH = "min(98vw, 1480px)";

// 深空主题配色 - 灵感来自于星际探索
const THEME = {
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
  accentTemp: "#ff7b4a",        // 温暖的橙红 - 温度
  accentOcean: "#00d4ff",       // 明亮的青色 - 海洋
  accentLife: "#a78bfa",        // 柔和的紫色 - 生命多样性
  accentGrowth: "#10b981",      // 生机绿 - 种群增长
  accentDanger: "#f43f5e",      // 警示红 - 死亡/灭绝
  accentEarth: "#fbbf24",       // 大地金 - 地质
  accentVital: "#06b6d4",       // 生命青 - 健康
  accentEvolve: "#ec4899",      // 演化粉 - 进化
  accentNeutral: "#64748b",     // 中性灰 - 平衡
  
  // 发光效果
  glowTemp: "rgba(255, 123, 74, 0.5)",
  glowOcean: "rgba(0, 212, 255, 0.5)",
  glowLife: "rgba(167, 139, 250, 0.5)",
  glowGrowth: "rgba(16, 185, 129, 0.5)",
  glowDanger: "rgba(244, 63, 94, 0.5)",
  glowEarth: "rgba(251, 191, 36, 0.5)",
  glowVital: "rgba(6, 182, 212, 0.5)",
  glowEvolve: "rgba(236, 72, 153, 0.5)",
  
  // 渐变起点
  gradientStart: "#050810",
  gradientMid: "#0c1220",
  gradientEnd: "#08101c",
};

const PIE_COLORS = ["#10b981", "#00d4ff", "#a78bfa", "#ff7b4a", "#f43f5e", "#fbbf24", "#06b6d4", "#ec4899"];

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

// --- Animated Background Component ---
function AnimatedBackground({ activeTab }: { activeTab: Tab }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resize();
    window.addEventListener('resize', resize);
    
    // 粒子系统
    const particles: Array<{
      x: number; y: number; vx: number; vy: number;
      size: number; alpha: number; color: string;
    }> = [];
    
    const tabColors: Record<Tab, string> = {
      environment: THEME.accentTemp,
      biodiversity: THEME.accentLife,
      evolution: THEME.accentEvolve,
      geology: THEME.accentEarth,
      health: THEME.accentVital,
    };
    
    const baseColor = tabColors[activeTab];
    
    // 初始化粒子
    for (let i = 0; i < 50; i++) {
      particles.push({
        x: Math.random() * canvas.offsetWidth,
        y: Math.random() * canvas.offsetHeight,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        size: Math.random() * 2 + 0.5,
        alpha: Math.random() * 0.5 + 0.1,
        color: baseColor,
      });
    }
    
    let animationId: number;
    const animate = () => {
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);
      
      // 绘制粒子
      particles.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        
        // 边界检查
        if (p.x < 0 || p.x > canvas.offsetWidth) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.offsetHeight) p.vy *= -1;
        
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.color + Math.floor(p.alpha * 255).toString(16).padStart(2, '0');
        ctx.fill();
      });
      
      // 绘制连线
      ctx.strokeStyle = baseColor + '15';
      ctx.lineWidth = 0.5;
      particles.forEach((p1, i) => {
        particles.slice(i + 1).forEach(p2 => {
          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        });
      });
      
      animationId = requestAnimationFrame(animate);
    };
    animate();
    
    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationId);
    };
  }, [activeTab]);
  
  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        opacity: 0.6,
      }}
    />
  );
}

// --- Main Component ---
export function GlobalTrendsPanel({ reports, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("environment");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const [showTimeline, setShowTimeline] = useState(false);
  const [hoveredMetric, setHoveredMetric] = useState<string | null>(null);

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

  // 获取当前tab的主题色
  const tabAccent = useMemo(() => {
    const accents: Record<Tab, { color: string; glow: string }> = {
      environment: { color: THEME.accentTemp, glow: THEME.glowTemp },
      biodiversity: { color: THEME.accentLife, glow: THEME.glowLife },
      evolution: { color: THEME.accentEvolve, glow: THEME.glowEvolve },
      geology: { color: THEME.accentEarth, glow: THEME.glowEarth },
      health: { color: THEME.accentVital, glow: THEME.glowVital },
    };
    return accents[activeTab];
  }, [activeTab]);

  return (
    <GamePanel
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            borderRadius: '12px',
            background: `linear-gradient(145deg, ${tabAccent.color}20, ${tabAccent.color}08)`,
            border: `1px solid ${tabAccent.color}40`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: `0 0 24px ${tabAccent.glow}, inset 0 0 12px ${tabAccent.color}15`,
            position: 'relative',
            overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute',
              inset: 0,
              background: `radial-gradient(circle at 30% 30%, ${tabAccent.color}30, transparent 60%)`,
            }} />
            <Globe size={22} color={tabAccent.color} style={{ position: 'relative', zIndex: 1 }} />
          </div>
          <div>
            <div style={{ 
              fontSize: '1.15rem', 
              fontWeight: 700, 
              letterSpacing: '0.03em',
              background: `linear-gradient(135deg, ${THEME.textBright}, ${THEME.textPrimary})`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              全球生态演变
            </div>
            <div style={{ 
              fontSize: '0.68rem', 
              color: THEME.textMuted, 
              marginTop: '3px',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}>
              Global Ecosystem Evolution
            </div>
          </div>
          <div style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 12px',
            borderRadius: '20px',
            background: `${tabAccent.color}12`,
            border: `1px solid ${tabAccent.color}25`,
          }}>
            <div style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: tabAccent.color,
              boxShadow: `0 0 8px ${tabAccent.glow}`,
              animation: 'pulse 2s ease-in-out infinite',
            }} />
            <span style={{ 
              fontSize: '0.72rem', 
              color: tabAccent.color,
              fontWeight: 600,
            }}>
              T{summary.latestTurn || '--'}
            </span>
          </div>
        </div>
      }
      onClose={onClose}
      variant="modal"
      width={PANEL_WIDTH}
    >
      <div style={styles.layoutContainer}>
        {/* Animated Canvas Background */}
        <AnimatedBackground activeTab={activeTab} />
        
        {/* Static Background Layers */}
        <div style={styles.bgGradient} />
        <div style={styles.bgMesh} />
        <div style={styles.bgVignette} />
        
        {/* Control Bar */}
        <div style={styles.controlBar}>
          <div style={styles.tabContainer}>
            <TabButton
              active={activeTab === "environment"}
              onClick={() => setActiveTab("environment")}
              icon={<Thermometer size={15} />}
              label="环境气候"
              color={THEME.accentTemp}
            />
            <TabButton
              active={activeTab === "biodiversity"}
              onClick={() => setActiveTab("biodiversity")}
              icon={<Dna size={15} />}
              label="生物群落"
              color={THEME.accentLife}
            />
            <TabButton
              active={activeTab === "evolution"}
              onClick={() => setActiveTab("evolution")}
              icon={<GitBranch size={15} />}
              label="进化事件"
              color={THEME.accentEvolve}
            />
            <TabButton
              active={activeTab === "geology"}
              onClick={() => setActiveTab("geology")}
              icon={<Mountain size={15} />}
              label="地质变化"
              color={THEME.accentEarth}
            />
            <TabButton
              active={activeTab === "health"}
              onClick={() => setActiveTab("health")}
              icon={<Activity size={15} />}
              label="生态健康"
              color={THEME.accentVital}
            />
          </div>

          <div style={styles.controlGroup}>
            {/* Time Range Selector */}
            <div style={styles.selectWrapper}>
              <Clock size={14} color={THEME.accentOcean} />
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
                backgroundColor: showTimeline ? `${THEME.accentOcean}20` : 'transparent',
                borderColor: showTimeline ? `${THEME.accentOcean}50` : THEME.borderDefault,
                boxShadow: showTimeline ? `0 0 16px ${THEME.glowOcean}, inset 0 0 8px ${THEME.accentOcean}15` : 'none',
              }}
              title="显示事件时间线"
            >
              <Calendar size={14} color={showTimeline ? THEME.accentOcean : THEME.textSecondary} />
            </button>

            {/* Export Button */}
            <button onClick={handleExport} style={styles.iconButton} title="导出数据">
              <Download size={14} />
            </button>
          </div>
        </div>

        {/* Top Metrics Row */}
        <div style={styles.metricsRow}>
          {metrics.map((metric, idx) => (
            <MetricCard 
              key={metric.key} 
              metric={metric} 
              index={idx}
              isHovered={hoveredMetric === metric.key}
              onHover={setHoveredMetric}
            />
          ))}
        </div>

        {/* Main Content Area */}
        <div style={styles.mainContent}>
          {/* Left: Chart Section */}
          <div style={styles.chartSection}>
            <div style={styles.chartHeader}>
              <div style={styles.chartTitleWrapper}>
                <div style={styles.chartTitleIcon}>
                  {getChartIcon(activeTab)}
                </div>
                <div>
                  <div style={styles.chartTitle}>
                    {getChartTitle(activeTab)}
                  </div>
                  <div style={styles.chartLegend}>
                    {getChartLegend(activeTab)}
                  </div>
                </div>
              </div>
              <div style={styles.chartBadge}>
                <Activity size={12} />
                <span>{chartData.length} 数据点</span>
              </div>
            </div>

            <div style={styles.chartContainer}>
              {hasReports ? (
                <ResponsiveContainer width="100%" height="100%">
                  {renderChart(activeTab, chartType, chartData)}
                </ResponsiveContainer>
              ) : (
                <div style={styles.emptyState}>
                  <div style={styles.emptyIcon}>
                    <Activity size={48} strokeWidth={1} />
                  </div>
                  <p style={{ fontSize: '1rem', fontWeight: 600 }}>等待数据...</p>
                  <p style={{ fontSize: '0.8rem', opacity: 0.6 }}>推进回合以生成演化记录</p>
                </div>
              )}
            </div>
          </div>

          {/* Right: Sidebar */}
          <div style={styles.sidebar} className="global-trends-scroll">
            {/* Insights Section */}
            <div style={styles.sidebarSection}>
              <div style={styles.sidebarHeader}>
                <div style={styles.sidebarTitleWrapper}>
                  <div style={{
                    width: '26px',
                    height: '26px',
                    borderRadius: '8px',
                    background: `linear-gradient(135deg, ${THEME.accentOcean}20, ${THEME.accentOcean}08)`,
                    border: `1px solid ${THEME.accentOcean}30`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <Sparkles size={13} color={THEME.accentOcean} />
                  </div>
                  <span style={styles.sidebarTitle}>趋势洞察</span>
                </div>
                <div style={styles.sidebarBadge}>{insightItems.length}</div>
              </div>
              <div style={styles.insightsList}>
                {insightItems.map((insight, idx) => (
                  <div 
                    key={insight.key}
                    className="insight-card"
                    style={{
                      ...styles.insightCard,
                      animationDelay: `${idx * 60}ms`,
                    }}
                  >
                    <div style={{
                      ...styles.insightAccent,
                      background: `linear-gradient(180deg, ${insight.accent || THEME.accentOcean}, ${insight.accent || THEME.accentOcean}20)`,
                      boxShadow: `0 0 8px ${insight.accent || THEME.accentOcean}40`,
                    }} />
                    <div style={styles.insightLabel}>{insight.label}</div>
                    <div style={{
                      ...styles.insightValue, 
                      background: `linear-gradient(135deg, ${insight.accent || THEME.textBright}, ${insight.accent || THEME.textPrimary}cc)`,
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                    }}>{insight.value}</div>
                    <div style={styles.insightDesc}>{insight.description}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Species Ranking (only for biodiversity tab) */}
            {activeTab === "biodiversity" && speciesRanking.length > 0 && (
              <div style={styles.sidebarSection}>
                <div style={styles.sidebarHeader}>
                  <div style={styles.sidebarTitleWrapper}>
                    <div style={{
                      width: '26px',
                      height: '26px',
                      borderRadius: '8px',
                      background: `linear-gradient(135deg, ${THEME.accentEarth}20, ${THEME.accentEarth}08)`,
                      border: `1px solid ${THEME.accentEarth}30`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <Crown size={13} color={THEME.accentEarth} />
                    </div>
                    <span style={styles.sidebarTitle}>物种排行</span>
                  </div>
                  <div style={styles.sidebarBadge}>TOP 5</div>
                </div>
                <div style={styles.rankingList}>
                  {speciesRanking.slice(0, 5).map((sp, idx) => (
                    <div 
                      key={sp.lineage_code} 
                      className="ranking-item"
                      style={{...styles.rankingItem, animationDelay: `${idx * 80}ms`}}
                    >
                      <div style={{
                        ...styles.rankBadge,
                        background: idx === 0 ? `linear-gradient(135deg, ${THEME.accentEarth}, ${THEME.accentTemp})` :
                                   idx === 1 ? `linear-gradient(135deg, #94a3b8, #64748b)` :
                                   idx === 2 ? `linear-gradient(135deg, #cd7f32, #b87333)` :
                                   `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
                        color: idx < 3 ? '#fff' : THEME.textSecondary,
                        boxShadow: idx === 0 ? `0 0 12px ${THEME.glowEarth}` : 'none',
                        border: idx >= 3 ? `1px solid ${THEME.borderSubtle}` : 'none',
                      }}>{idx + 1}</div>
                      <div style={styles.rankInfo}>
                        <div style={styles.rankName}>{sp.common_name}</div>
                        <div style={styles.rankPop}>{formatPopulation(sp.population)} kg</div>
                      </div>
                      <div style={styles.rankBar}>
                        <div 
                          style={{
                            ...styles.rankBarFill,
                            width: `${(sp.population / speciesRanking[0].population) * 100}%`,
                            background: `linear-gradient(90deg, ${PIE_COLORS[idx % PIE_COLORS.length]}, ${PIE_COLORS[idx % PIE_COLORS.length]}88)`,
                            boxShadow: `0 0 8px ${PIE_COLORS[idx % PIE_COLORS.length]}44`,
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
                  <div style={styles.sidebarTitleWrapper}>
                    <div style={{
                      width: '26px',
                      height: '26px',
                      borderRadius: '8px',
                      background: `linear-gradient(135deg, ${THEME.accentEvolve}20, ${THEME.accentEvolve}08)`,
                      border: `1px solid ${THEME.accentEvolve}30`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <Target size={13} color={THEME.accentEvolve} />
                    </div>
                    <span style={styles.sidebarTitle}>生态角色分布</span>
                  </div>
                </div>
                <div style={{ height: 180, position: 'relative' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <defs>
                        {roleDistribution.map((_, idx) => (
                          <linearGradient key={idx} id={`pieGradient${idx}`} x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0%" stopColor={PIE_COLORS[idx % PIE_COLORS.length]} stopOpacity={1} />
                            <stop offset="100%" stopColor={PIE_COLORS[idx % PIE_COLORS.length]} stopOpacity={0.6} />
                          </linearGradient>
                        ))}
                      </defs>
                      <Pie
                        data={roleDistribution}
                        cx="50%"
                        cy="50%"
                        innerRadius={45}
                        outerRadius={72}
                        paddingAngle={3}
                        dataKey="value"
                        nameKey="name"
                        strokeWidth={0}
                      >
                        {roleDistribution.map((_, idx) => (
                          <Cell 
                            key={idx} 
                            fill={`url(#pieGradient${idx})`}
                            style={{ filter: `drop-shadow(0 0 6px ${PIE_COLORS[idx % PIE_COLORS.length]}44)` }}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<PieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={styles.pieCenter}>
                    <div style={styles.pieCenterValue}>{roleDistribution.length}</div>
                    <div style={styles.pieCenterLabel}>角色</div>
                  </div>
                </div>
                <div style={styles.legendGrid}>
                  {roleDistribution.map((item, idx) => (
                    <div key={item.name} style={styles.legendItem}>
                      <div 
                        style={{
                          ...styles.legendDot,
                          background: `linear-gradient(135deg, ${PIE_COLORS[idx % PIE_COLORS.length]}, ${PIE_COLORS[idx % PIE_COLORS.length]}88)`,
                          boxShadow: `0 0 6px ${PIE_COLORS[idx % PIE_COLORS.length]}44`,
                        }}
                      />
                      <span>{item.name}</span>
                      <span style={{ marginLeft: 'auto', color: THEME.textSecondary, fontSize: '0.65rem' }}>{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Footer Stats */}
            <div style={styles.footer}>
              <div style={styles.footerTitle}>
                <div style={{
                  width: '22px',
                  height: '22px',
                  borderRadius: '6px',
                  background: `linear-gradient(135deg, ${THEME.accentOcean}20, ${THEME.accentOcean}08)`,
                  border: `1px solid ${THEME.accentOcean}30`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Shield size={11} color={THEME.accentOcean} />
                </div>
                <span>数据概览</span>
              </div>
              <div style={styles.footerGrid}>
                <div style={styles.footerItem}>
                  <span style={styles.footerLabel}>数据范围</span>
                  <span style={styles.footerValue}>
                    {hasReports ? `T${summary.baselineTurn} → T${summary.latestTurn}` : '--'}
                  </span>
                </div>
                <div style={styles.footerItem}>
                  <span style={styles.footerLabel}>采样点</span>
                  <span style={styles.footerValue}>{filteredReports.length}</span>
                </div>
              </div>
              {summary.tectonicStage && (
                <div style={styles.footerStage}>
                  <Mountain size={12} color={THEME.accentEarth} />
                  <span>{summary.tectonicStage}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Timeline Section (collapsible) */}
        {showTimeline && timelineEvents.length > 0 && (
          <div style={styles.timelineSection}>
            <div style={styles.timelineHeader}>
              <div style={styles.timelineHeaderLeft}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '10px',
                  background: `linear-gradient(135deg, ${THEME.accentOcean}20, ${THEME.accentOcean}08)`,
                  border: `1px solid ${THEME.accentOcean}30`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: `0 0 12px ${THEME.glowOcean}`,
                }}>
                  <Clock size={16} color={THEME.accentOcean} />
                </div>
                <span style={styles.timelineHeaderTitle}>重大事件时间线</span>
              </div>
              <div style={styles.timelineHeaderRight}>
                <span style={styles.timelineCount}>{timelineEvents.length} 事件</span>
              </div>
            </div>
            <div style={styles.timelineScroll} className="global-trends-scroll">
              <div style={styles.timelineTrack} />
              {timelineEvents.slice(0, 20).map((event, idx) => (
                <div 
                  key={`${event.turn}-${idx}`}
                  className="timeline-item"
                  style={{
                    ...styles.timelineItem,
                    animationDelay: `${idx * 60}ms`,
                  }}
                >
                  <div style={styles.timelineConnector}>
                    <div style={{
                      ...styles.timelineDot,
                      background: `linear-gradient(135deg, ${event.color}, ${event.color}aa)`,
                      boxShadow: `0 0 14px ${event.color}70`,
                      border: `2px solid ${THEME.bgDeep}`,
                    }} />
                  </div>
                  <div style={{ 
                    ...styles.timelineIcon, 
                    background: `linear-gradient(145deg, ${event.color}20, ${event.color}08)`,
                    border: `1px solid ${event.color}40`,
                    color: event.color,
                    boxShadow: `0 0 20px ${event.color}25`,
                  }}>
                    {event.icon}
                  </div>
                  <div style={styles.timelineTurnBadge}>
                    <span>T{event.turn}</span>
                  </div>
                  <div style={styles.timelineContent}>
                    <div style={{
                      ...styles.timelineTitle, 
                      background: `linear-gradient(135deg, ${event.color}, ${event.color}cc)`,
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                    }}>{event.title}</div>
                    <div style={styles.timelineDesc}>{event.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <style>{`
        @keyframes metricSlideIn {
          from {
            opacity: 0;
            transform: translateY(16px) scale(0.96);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes insightSlideIn {
          from {
            opacity: 0;
            transform: translateX(-12px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes rankSlideIn {
          from {
            opacity: 0;
            transform: translateX(12px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes timelineSlideIn {
          from {
            opacity: 0;
            transform: translateY(20px) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes pulse {
          0%, 100% { 
            opacity: 1;
            transform: scale(1);
          }
          50% { 
            opacity: 0.6;
            transform: scale(1.1);
          }
        }
        @keyframes pulseGlow {
          0%, 100% { 
            opacity: 0.5;
            box-shadow: 0 0 20px ${THEME.glowOcean}, inset 0 0 15px ${THEME.accentOcean}10;
          }
          50% { 
            opacity: 0.8;
            box-shadow: 0 0 40px ${THEME.glowOcean}, inset 0 0 25px ${THEME.accentOcean}20;
          }
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        
        /* 滚动条样式 */
        .global-trends-scroll::-webkit-scrollbar {
          width: 6px;
          height: 6px;
        }
        .global-trends-scroll::-webkit-scrollbar-track {
          background: ${THEME.bgDeep};
          border-radius: 3px;
        }
        .global-trends-scroll::-webkit-scrollbar-thumb {
          background: ${THEME.borderDefault};
          border-radius: 3px;
        }
        .global-trends-scroll::-webkit-scrollbar-thumb:hover {
          background: ${THEME.borderActive};
        }
        
        /* 悬停效果 */
        .insight-card:hover {
          background: linear-gradient(135deg, ${THEME.bgCardHover}, ${THEME.bgGlass}) !important;
          border-color: ${THEME.borderDefault} !important;
          transform: translateX(4px);
        }
        .ranking-item:hover {
          background: linear-gradient(135deg, ${THEME.bgCardHover}, ${THEME.bgGlass}) !important;
          border-color: ${THEME.borderDefault} !important;
        }
        .timeline-item:hover {
          border-color: ${THEME.borderActive} !important;
          transform: translateY(-4px);
        }
      `}</style>
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
          <stop offset="5%" stopColor={THEME.accentTemp} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentTemp} stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="seaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentOcean} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentOcean} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderSubtle} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '12px' }} />
      {type === "area" ? (
        <>
          <Area yAxisId="left" type="monotone" dataKey="temp" name="全球均温 (°C)" stroke={THEME.accentTemp} fill="url(#tempGradient)" strokeWidth={2.5} />
          <Area yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentOcean} fill="url(#seaGradient)" strokeWidth={2.5} />
        </>
      ) : type === "bar" ? (
        <>
          <Bar yAxisId="left" dataKey="temp" name="全球均温 (°C)" fill={THEME.accentTemp} radius={[6, 6, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentOcean} strokeWidth={3} dot={false} />
        </>
      ) : (
        <>
          <Line yAxisId="left" type="monotone" dataKey="temp" name="全球均温 (°C)" stroke={THEME.accentTemp} strokeWidth={3} dot={false} activeDot={{ r: 6, fill: THEME.accentTemp, strokeWidth: 2, stroke: THEME.bgDeep }} />
          <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面 (m)" stroke={THEME.accentOcean} strokeWidth={3} dot={false} activeDot={{ r: 6, fill: THEME.accentOcean, strokeWidth: 2, stroke: THEME.bgDeep }} />
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
          <stop offset="5%" stopColor={THEME.accentGrowth} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentGrowth} stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="speciesGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentLife} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentLife} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderSubtle} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '12px' }} />
      {type === "area" ? (
        <>
          <Area yAxisId="left" type="monotone" dataKey="totalPop" name="总生物量" stroke={THEME.accentGrowth} fill="url(#popGradient)" strokeWidth={2.5} />
          <Area yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentLife} fill="url(#speciesGradient)" strokeWidth={2.5} />
        </>
      ) : type === "bar" ? (
        <>
          <Bar yAxisId="left" dataKey="totalPop" name="总生物量" fill={THEME.accentGrowth} radius={[6, 6, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentLife} strokeWidth={3} dot={false} />
        </>
      ) : (
        <>
          <Line yAxisId="left" type="monotone" dataKey="totalPop" name="总生物量" stroke={THEME.accentGrowth} strokeWidth={3} dot={false} activeDot={{ r: 6, fill: THEME.accentGrowth, strokeWidth: 2, stroke: THEME.bgDeep }} />
          <Line yAxisId="right" type="monotone" dataKey="speciesCount" name="物种数量" stroke={THEME.accentLife} strokeWidth={3} dot={false} activeDot={{ r: 6, fill: THEME.accentLife, strokeWidth: 2, stroke: THEME.bgDeep }} />
        </>
      )}
    </ChartComponent>
  );
}

function renderEvolutionChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderSubtle} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '12px' }} />
      <Bar dataKey="branchings" name="物种分化" fill={THEME.accentEvolve} radius={[6, 6, 0, 0]} />
      <Bar dataKey="migrations" name="迁徙事件" fill={THEME.accentOcean} radius={[6, 6, 0, 0]} />
      <Line type="monotone" dataKey="speciesCount" name="物种总数" stroke={THEME.accentLife} strokeWidth={2.5} dot={false} />
    </ComposedChart>
  );
}

function renderGeologyChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <defs>
        <linearGradient id="geoGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentEarth} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentEarth} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderSubtle} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '12px' }} />
      <Bar yAxisId="left" dataKey="mapChanges" name="地形变化" fill={THEME.accentEarth} radius={[6, 6, 0, 0]} />
      <Bar yAxisId="left" dataKey="majorEvents" name="重大事件" fill={THEME.accentDanger} radius={[6, 6, 0, 0]} />
      <Line yAxisId="right" type="monotone" dataKey="seaLevel" name="海平面" stroke={THEME.accentOcean} strokeWidth={2.5} dot={false} />
    </ComposedChart>
  );
}

function renderHealthChart(type: ChartType, props: any) {
  return (
    <ComposedChart {...props}>
      <defs>
        <linearGradient id="deathGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor={THEME.accentDanger} stopOpacity={0.4}/>
          <stop offset="95%" stopColor={THEME.accentDanger} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={THEME.borderSubtle} vertical={false} />
      <XAxis dataKey="turn" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="left" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} />
      <YAxis yAxisId="right" orientation="right" stroke={THEME.textMuted} tick={{ fontSize: 11, fill: THEME.textSecondary }} tickLine={false} axisLine={false} domain={[0, 100]} />
      <Tooltip content={<CustomTooltip />} />
      <Legend wrapperStyle={{ paddingTop: '12px' }} />
      <Area yAxisId="left" type="monotone" dataKey="deaths" name="死亡数" stroke={THEME.accentDanger} fill="url(#deathGradient)" strokeWidth={2.5} />
      <Line yAxisId="right" type="monotone" dataKey="deathRate" name="平均死亡率 (%)" stroke={THEME.accentVital} strokeWidth={3} dot={false} />
      <Line yAxisId="left" type="monotone" dataKey="totalPop" name="总生物量" stroke={THEME.accentGrowth} strokeWidth={2} strokeDasharray="5 5" dot={false} />
    </ComposedChart>
  );
}

function getChartTitle(tab: Tab): string {
  const titles: Record<Tab, string> = {
    environment: "环境变化趋势",
    biodiversity: "生物多样性变化",
    evolution: "进化与迁徙活动",
    geology: "地质构造变化",
    health: "生态系统健康",
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

// --- Helper Functions ---
function getChartIcon(tab: Tab): React.ReactNode {
  const icons: Record<Tab, React.ReactNode> = {
    environment: <Thermometer size={20} color={THEME.accentTemp} />,
    biodiversity: <Dna size={20} color={THEME.accentLife} />,
    evolution: <GitBranch size={20} color={THEME.accentEvolve} />,
    geology: <Mountain size={20} color={THEME.accentEarth} />,
    health: <Activity size={20} color={THEME.accentVital} />,
  };
  return icons[tab];
}

// --- Sub Components ---
function MetricCard({ metric, index, isHovered, onHover }: { 
  metric: MetricDefinition; 
  index: number;
  isHovered: boolean;
  onHover: (key: string | null) => void;
}) {
  const trendColor =
    metric.trend === "up"
      ? THEME.accentGrowth
      : metric.trend === "down"
      ? THEME.accentDanger
      : THEME.textSecondary;

  const TrendIcon = metric.trend === 'up' ? TrendingUp : metric.trend === 'down' ? TrendingDown : Minus;

  return (
    <div 
      style={{
        ...styles.metricCard,
        animation: 'metricSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        animationDelay: `${index * 80}ms`,
        opacity: 0,
        transform: isHovered ? 'translateY(-4px) scale(1.02)' : 'translateY(0) scale(1)',
        boxShadow: isHovered 
          ? `0 12px 40px ${metric.glow || metric.accent + '30'}, 0 0 0 1px ${metric.accent}30, inset 0 1px 0 rgba(255,255,255,0.08)`
          : `0 4px 20px rgba(0,0,0,0.2), 0 0 0 1px ${THEME.borderSubtle}`,
      }}
      onMouseEnter={() => onHover(metric.key)}
      onMouseLeave={() => onHover(null)}
    >
      {/* 顶部发光条 */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '2px',
        background: `linear-gradient(90deg, transparent, ${metric.accent}, transparent)`,
        opacity: isHovered ? 1 : 0.7,
        transition: 'opacity 0.3s',
      }} />
      
      {/* 顶部光晕 */}
      <div style={{
        position: 'absolute',
        top: '-20px',
        left: '50%',
        transform: 'translateX(-50%)',
        width: '80%',
        height: '60px',
        background: `radial-gradient(ellipse at center, ${metric.accent}20, transparent 70%)`,
        pointerEvents: 'none',
        opacity: isHovered ? 1 : 0.5,
        transition: 'opacity 0.3s',
      }} />
      
      {/* 角落装饰 */}
      <div style={{
        position: 'absolute',
        top: '8px',
        right: '8px',
        width: '20px',
        height: '20px',
        borderTop: `1px solid ${metric.accent}40`,
        borderRight: `1px solid ${metric.accent}40`,
        borderRadius: '0 6px 0 0',
        opacity: isHovered ? 1 : 0.4,
        transition: 'opacity 0.3s',
      }} />
      <div style={{
        position: 'absolute',
        bottom: '8px',
        left: '8px',
        width: '20px',
        height: '20px',
        borderBottom: `1px solid ${metric.accent}40`,
        borderLeft: `1px solid ${metric.accent}40`,
        borderRadius: '0 0 0 6px',
        opacity: isHovered ? 1 : 0.4,
        transition: 'opacity 0.3s',
      }} />
      
      <div style={styles.metricHeader}>
        <span style={styles.metricLabel}>{metric.label}</span>
        <div style={{ 
          width: '34px',
          height: '34px',
          borderRadius: '10px',
          background: `linear-gradient(135deg, ${metric.accent}18, ${metric.accent}08)`,
          border: `1px solid ${metric.accent}30`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: metric.accent,
          boxShadow: isHovered ? `0 0 16px ${metric.accent}40` : 'none',
          transition: 'box-shadow 0.3s',
        }}>
          {metric.icon}
        </div>
      </div>
      
      <div style={styles.metricContent}>
        <span style={{
          ...styles.metricValue, 
          background: `linear-gradient(135deg, ${metric.accent}, ${metric.accent}cc)`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          filter: isHovered ? `drop-shadow(0 0 8px ${metric.accent}60)` : 'none',
          transition: 'filter 0.3s',
        }}>
          {metric.value}
        </span>
      </div>
      
      <div style={styles.metricFooter}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '5px', 
          color: trendColor, 
          fontSize: '0.78rem',
          fontWeight: 600,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '20px',
            height: '20px',
            borderRadius: '6px',
            background: `${trendColor}18`,
          }}>
            <TrendIcon size={12} />
          </div>
          <span>{metric.deltaText}</span>
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, label, icon, color }: { active: boolean; onClick: () => void; label: string; icon: React.ReactNode; color: string }) {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        ...styles.tabButton,
        background: active 
          ? `linear-gradient(135deg, ${color}22, ${color}10)` 
          : isHovered 
            ? `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`
            : 'transparent',
        borderColor: active ? `${color}50` : isHovered ? THEME.borderDefault : 'transparent',
        color: active ? color : isHovered ? THEME.textPrimary : THEME.textSecondary,
        boxShadow: active 
          ? `0 0 20px ${color}25, inset 0 1px 0 ${color}20, inset 0 0 12px ${color}08` 
          : 'none',
        transform: active ? 'translateY(-1px)' : isHovered ? 'translateY(-1px)' : 'none',
      }}
    >
      <div style={{ 
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '24px',
        height: '24px',
        borderRadius: '7px',
        background: active ? `${color}20` : 'transparent',
        transition: 'all 0.25s',
      }}>
        <span style={{ 
          filter: active ? `drop-shadow(0 0 6px ${color})` : 'none',
          transition: 'filter 0.25s',
        }}>{icon}</span>
      </div>
      <span style={{ fontWeight: active ? 700 : 500 }}>{label}</span>
      {active && (
        <div style={{
          position: 'absolute',
          bottom: '-1px',
          left: '20%',
          right: '20%',
          height: '2px',
          background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
          borderRadius: '2px',
        }} />
      )}
    </button>
  );
}

function ChartTypeButton({ active, onClick, icon, title }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string }) {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        ...styles.chartTypeBtn,
        background: active 
          ? `linear-gradient(135deg, ${THEME.accentOcean}25, ${THEME.accentOcean}12)` 
          : isHovered
            ? THEME.bgGlass
            : 'transparent',
        borderColor: active ? `${THEME.accentOcean}45` : 'transparent',
        color: active ? THEME.accentOcean : isHovered ? THEME.textPrimary : THEME.textSecondary,
        boxShadow: active ? `0 0 14px ${THEME.glowOcean}, inset 0 0 8px ${THEME.accentOcean}10` : 'none',
        transform: isHovered && !active ? 'scale(1.08)' : 'scale(1)',
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
        <div style={styles.tooltipHeader}>
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '8px',
            background: `linear-gradient(135deg, ${THEME.accentOcean}20, ${THEME.accentOcean}08)`,
            border: `1px solid ${THEME.accentOcean}30`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Clock size={14} color={THEME.accentOcean} />
          </div>
          <div>
            <span style={styles.tooltipTitle}>{`回合 ${label}`}</span>
            <div style={{ fontSize: '0.65rem', color: THEME.textMuted, marginTop: '1px' }}>TURN DATA</div>
          </div>
        </div>
        <div style={styles.tooltipDivider} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {payload.map((entry: any, index: number) => (
            <div key={index} style={styles.tooltipItem}>
              <div style={{
                width: '10px',
                height: '10px',
                borderRadius: '3px',
                background: `linear-gradient(135deg, ${entry.color}, ${entry.color}aa)`,
                boxShadow: `0 0 8px ${entry.color}50`,
              }} />
              <span style={{ color: THEME.textSecondary, flex: 1, fontSize: '0.8rem' }}>{entry.name}</span>
              <span style={{ 
                color: entry.color, 
                fontWeight: 700,
                fontSize: '0.88rem',
                fontFamily: 'JetBrains Mono, monospace',
              }}>
                {typeof entry.value === 'number' && entry.value % 1 !== 0 ? entry.value.toFixed(2) : formatPopulation(entry.value)}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

const PieTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const color = PIE_COLORS[payload[0].payload.index % PIE_COLORS.length] || payload[0].payload.fill;
    return (
      <div style={styles.tooltip}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '14px',
            height: '14px',
            borderRadius: '4px',
            background: `linear-gradient(135deg, ${color}, ${color}aa)`,
            boxShadow: `0 0 10px ${color}50`,
          }} />
          <span style={{ ...styles.tooltipTitle, color }}>{payload[0].name}</span>
        </div>
        <div style={{ 
          fontSize: '1.25rem', 
          fontWeight: 800, 
          marginTop: '8px', 
          color: THEME.textBright,
          fontFamily: 'JetBrains Mono, monospace',
        }}>
          {payload[0].value} 
          <span style={{ 
            fontSize: '0.75rem', 
            fontWeight: 500, 
            color: THEME.textSecondary,
            marginLeft: '6px',
            fontFamily: 'inherit',
          }}>
            个物种
          </span>
        </div>
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
      accent: THEME.accentTemp,
      glow: THEME.glowTemp,
      icon: <Thermometer size={17} />,
    },
    {
      key: "seaLevel", label: "海平面",
      value: `${summary.seaLevel.toFixed(2)} m`,
      deltaText: formatDelta(summary.seaLevelDelta, " m", 2),
      trend: getTrend(summary.seaLevelDelta),
      accent: THEME.accentOcean,
      glow: THEME.glowOcean,
      icon: <Waves size={17} />,
    },
    {
      key: "species", label: "物种丰富度",
      value: integerFormatter.format(summary.species),
      deltaText: formatDelta(summary.speciesDelta, "", 0),
      trend: getTrend(summary.speciesDelta),
      accent: THEME.accentLife,
      glow: THEME.glowLife,
      icon: <Leaf size={17} />,
    },
    {
      key: "population", label: "总生物量",
      value: formatPopulation(summary.population),
      deltaText: formatDelta(summary.populationDelta, "", 1, formatPopulation),
      trend: getTrend(summary.populationDelta),
      accent: THEME.accentGrowth,
      glow: THEME.glowGrowth,
      icon: <Users size={17} />,
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
        accent: THEME.accentEvolve,
        glow: THEME.glowEvolve,
        icon: <GitBranch size={17} />,
      },
      {
        key: "migrations", label: "迁徙活动",
        value: integerFormatter.format(summary.migrationCount),
        deltaText: "累计事件",
        trend: "neutral",
        accent: THEME.accentOcean,
        glow: THEME.glowOcean,
        icon: <Footprints size={17} />,
      },
    ],
    geology: [
      {
        key: "mapChanges", label: "地形变化",
        value: integerFormatter.format(summary.mapChanges),
        deltaText: "累计变化",
        trend: "neutral",
        accent: THEME.accentEarth,
        glow: THEME.glowEarth,
        icon: <Mountain size={17} />,
      },
    ],
    health: [
      {
        key: "deathRate", label: "平均死亡率",
        value: `${(summary.avgDeathRate * 100).toFixed(1)}%`,
        deltaText: summary.avgDeathRate > 0.3 ? "偏高" : summary.avgDeathRate > 0.15 ? "正常" : "健康",
        trend: summary.avgDeathRate > 0.25 ? "down" : "up",
        accent: THEME.accentDanger,
        glow: THEME.glowDanger,
        icon: <Skull size={17} />,
      },
      {
        key: "totalDeaths", label: "累计死亡",
        value: formatPopulation(summary.totalDeaths),
        deltaText: "生命损失",
        trend: "neutral",
        accent: THEME.accentVital,
        glow: THEME.glowVital,
        icon: <Heart size={17} />,
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
          accent: THEME.accentTemp,
        },
        {
          key: "seaTotal", label: "海平面净变",
          value: formatDelta(summary.seaLevelDelta, " m", 2),
          description: "相较于初始记录的累计变化",
          accent: THEME.accentOcean,
        },
        {
          key: "pressure", label: "环境压力",
          value: rate > 0.5 ? "🔴 危急" : rate > 0.1 ? "🟡 高压" : "🟢 稳定",
          description: "基于当前变化率的压力评级",
          accent: rate > 0.5 ? THEME.accentDanger : rate > 0.1 ? THEME.accentEarth : THEME.accentGrowth,
        },
        {
          key: "forecast", label: "趋势预测",
          value: rate > 0 ? "升温中" : rate < 0 ? "降温中" : "平稳",
          description: rate > 0 ? "生态系统面临热压力" : rate < 0 ? "可能进入冰期" : "环境条件稳定",
          accent: THEME.accentTemp,
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
          accent: summary.speciesDelta >= 0 ? THEME.accentGrowth : THEME.accentDanger,
        },
        {
          key: "biomass", label: "生物量净变",
          value: formatDelta(summary.populationDelta, "", 1, formatPopulation),
          description: "生态系统承载力变化",
          accent: THEME.accentLife,
        },
        {
          key: "density", label: "平均生物量",
          value: formatPopulation(avgPop),
          description: "单物种平均生物量 (kg)",
          accent: THEME.accentGrowth,
        },
        {
          key: "health", label: "多样性健康",
          value: diversityHealth,
          description: summary.speciesDelta >= 0 ? "物种多样性正在恢复" : "物种多样性正在下降",
          accent: summary.speciesDelta >= 0 ? THEME.accentGrowth : THEME.accentDanger,
        },
      ];
      
    case "evolution":
      const branchRate = summary.turnSpan > 0 ? summary.branchingCount / summary.turnSpan : 0;
      return [
        {
          key: "speciation", label: "物种形成率",
          value: `${branchRate.toFixed(2)} / 回合`,
          description: "平均每回合产生的新物种",
          accent: THEME.accentEvolve,
        },
        {
          key: "migrations", label: "迁徙活跃度",
          value: integerFormatter.format(summary.migrationCount),
          description: "物种地理扩散事件总数",
          accent: THEME.accentOcean,
        },
        {
          key: "radiationPotential", label: "辐射潜力",
          value: summary.branchingCount > 5 ? "🔥 活跃" : summary.branchingCount > 2 ? "📈 中等" : "💤 低迷",
          description: "物种快速分化的可能性",
          accent: THEME.accentEvolve,
        },
        {
          key: "isolation", label: "隔离程度",
          value: summary.migrationCount > summary.branchingCount ? "低" : "高",
          description: summary.migrationCount > summary.branchingCount ? "频繁基因交流" : "地理隔离促进分化",
          accent: THEME.accentLife,
        },
      ];
      
    case "geology":
      return [
        {
          key: "tectonics", label: "地质阶段",
          value: summary.tectonicStage || "未知",
          description: "当前板块构造状态",
          accent: THEME.accentEarth,
        },
        {
          key: "changes", label: "地形变化",
          value: `${summary.mapChanges} 次`,
          description: "地形改变事件总数",
          accent: THEME.accentEarth,
        },
        {
          key: "seaChange", label: "海平面变化",
          value: formatDelta(summary.seaLevelDelta, " m", 2),
          description: summary.seaLevelDelta > 0 ? "海侵中，陆地面积减少" : summary.seaLevelDelta < 0 ? "海退中，陆地面积增加" : "海平面稳定",
          accent: THEME.accentOcean,
        },
        {
          key: "activity", label: "地质活动度",
          value: summary.mapChanges > 5 ? "🌋 剧烈" : summary.mapChanges > 2 ? "⛰️ 活跃" : "🏔️ 平静",
          description: "基于地形变化频率评估",
          accent: summary.mapChanges > 5 ? THEME.accentDanger : THEME.accentEarth,
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
          accent: healthScore > 70 ? THEME.accentGrowth : healthScore > 40 ? THEME.accentEarth : THEME.accentDanger,
        },
        {
          key: "mortality", label: "平均死亡率",
          value: `${(summary.avgDeathRate * 100).toFixed(1)}%`,
          description: summary.avgDeathRate < 0.15 ? "种群稳定繁衍" : summary.avgDeathRate < 0.3 ? "存在生存压力" : "高死亡率警报",
          accent: THEME.accentDanger,
        },
        {
          key: "sustainability", label: "可持续性",
          value: summary.populationDelta >= 0 && summary.speciesDelta >= 0 ? "🌱 可持续" : "⚠️ 需关注",
          description: "综合生物量和物种变化趋势",
          accent: summary.populationDelta >= 0 ? THEME.accentGrowth : THEME.accentDanger,
        },
        {
          key: "resilience", label: "恢复力",
          value: summary.branchingCount > summary.extinctions ? "强" : "弱",
          description: "物种形成与灭绝的比率",
          accent: summary.branchingCount > summary.extinctions ? THEME.accentGrowth : THEME.accentDanger,
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
        color: THEME.accentEvolve,
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
        color: THEME.accentOcean,
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
        color: THEME.accentEarth,
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
        color: THEME.accentDanger,
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
    padding: '20px 24px 24px',
    gap: '16px',
    color: THEME.textPrimary,
    maxHeight: '85vh',
    overflow: 'hidden',
    position: 'relative',
    background: `linear-gradient(180deg, ${THEME.bgDeep} 0%, ${THEME.bgPrimary} 100%)`,
  },
  bgGradient: {
    position: 'absolute',
    inset: 0,
    background: `
      radial-gradient(ellipse 80% 50% at 20% 10%, ${THEME.accentOcean}08 0%, transparent 50%),
      radial-gradient(ellipse 60% 40% at 85% 90%, ${THEME.accentLife}06 0%, transparent 50%),
      radial-gradient(ellipse 100% 60% at 50% 50%, ${THEME.accentTemp}03 0%, transparent 60%)
    `,
    pointerEvents: 'none',
    zIndex: 0,
  },
  bgMesh: {
    position: 'absolute',
    inset: 0,
    backgroundImage: `
      linear-gradient(${THEME.borderSubtle} 1px, transparent 1px),
      linear-gradient(90deg, ${THEME.borderSubtle} 1px, transparent 1px)
    `,
    backgroundSize: '60px 60px',
    opacity: 0.4,
    pointerEvents: 'none',
    zIndex: 0,
    maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 80%)',
    WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 80%)',
  },
  bgVignette: {
    position: 'absolute',
    inset: 0,
    background: 'radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.4) 100%)',
    pointerEvents: 'none',
    zIndex: 0,
  },
  controlBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '12px',
    flexShrink: 0,
    position: 'relative',
    zIndex: 1,
  },
  tabContainer: {
    display: 'flex',
    gap: '3px',
    background: `linear-gradient(135deg, ${THEME.bgCard}, ${THEME.bgDeep})`,
    padding: '5px',
    borderRadius: '14px',
    flexWrap: 'wrap',
    border: `1px solid ${THEME.borderSubtle}`,
    backdropFilter: 'blur(12px)',
    boxShadow: '0 4px 20px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.03)',
  },
  tabButton: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '9px 14px',
    borderRadius: '10px',
    border: '1px solid transparent',
    cursor: 'pointer',
    fontSize: '0.8rem',
    fontWeight: 500,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    whiteSpace: 'nowrap',
    letterSpacing: '0.02em',
    overflow: 'hidden',
  },
  controlGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  selectWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: `linear-gradient(135deg, ${THEME.bgCard}, ${THEME.bgDeep})`,
    padding: '8px 14px',
    borderRadius: '10px',
    border: `1px solid ${THEME.borderSubtle}`,
    backdropFilter: 'blur(12px)',
    transition: 'all 0.25s',
    boxShadow: '0 2px 10px rgba(0,0,0,0.15)',
  },
  select: {
    background: 'transparent',
    border: 'none',
    color: THEME.textPrimary,
    fontSize: '0.8rem',
    cursor: 'pointer',
    outline: 'none',
    fontWeight: 500,
  },
  chartTypeGroup: {
    display: 'flex',
    gap: '2px',
    background: `linear-gradient(135deg, ${THEME.bgCard}, ${THEME.bgDeep})`,
    padding: '4px',
    borderRadius: '10px',
    border: `1px solid ${THEME.borderSubtle}`,
    boxShadow: '0 2px 10px rgba(0,0,0,0.15)',
  },
  chartTypeBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '32px',
    height: '32px',
    borderRadius: '8px',
    border: '1px solid transparent',
    cursor: 'pointer',
    transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
    background: 'transparent',
  },
  iconButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '38px',
    height: '38px',
    borderRadius: '10px',
    border: `1px solid ${THEME.borderSubtle}`,
    cursor: 'pointer',
    transition: 'all 0.25s',
    background: `linear-gradient(135deg, ${THEME.bgCard}, ${THEME.bgDeep})`,
    color: THEME.textSecondary,
    backdropFilter: 'blur(12px)',
    boxShadow: '0 2px 10px rgba(0,0,0,0.15)',
  },
  metricsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
    gap: '12px',
    flexShrink: 0,
    position: 'relative',
    zIndex: 1,
  },
  mainContent: {
    display: 'flex',
    flex: 1,
    gap: '16px',
    minHeight: 0,
    overflow: 'hidden',
    position: 'relative',
    zIndex: 1,
  },
  chartSection: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    background: `linear-gradient(145deg, ${THEME.bgCard}, ${THEME.bgDeep}90)`,
    borderRadius: '18px',
    border: `1px solid ${THEME.borderSubtle}`,
    padding: '20px',
    minWidth: '0',
    backdropFilter: 'blur(16px)',
    boxShadow: `0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04)`,
    position: 'relative',
    overflow: 'hidden',
  },
  chartHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
    flexWrap: 'wrap',
    gap: '12px',
  },
  chartTitleWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
  },
  chartTitleIcon: {
    width: '44px',
    height: '44px',
    borderRadius: '12px',
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    border: `1px solid ${THEME.borderDefault}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
    position: 'relative',
    overflow: 'hidden',
  },
  chartTitle: {
    fontSize: '1.08rem',
    fontWeight: 700,
    color: THEME.textBright,
    letterSpacing: '0.02em',
  },
  chartLegend: {
    fontSize: '0.72rem',
    color: THEME.textMuted,
    marginTop: '3px',
    letterSpacing: '0.02em',
  },
  chartBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '20px',
    background: `linear-gradient(135deg, ${THEME.accentOcean}15, ${THEME.accentOcean}08)`,
    border: `1px solid ${THEME.accentOcean}30`,
    color: THEME.accentOcean,
    fontSize: '0.72rem',
    fontWeight: 600,
    boxShadow: `0 0 12px ${THEME.glowOcean}`,
  },
  chartContainer: {
    flex: 1,
    minHeight: '220px',
    position: 'relative',
  },
  emptyState: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: THEME.textSecondary,
    gap: '16px',
  },
  emptyIcon: {
    width: '90px',
    height: '90px',
    borderRadius: '50%',
    background: `linear-gradient(135deg, ${THEME.accentOcean}12, ${THEME.accentOcean}05)`,
    border: `1px solid ${THEME.accentOcean}25`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: THEME.accentOcean,
    boxShadow: `0 0 40px ${THEME.glowOcean}, inset 0 0 20px ${THEME.accentOcean}10`,
    animation: 'pulseGlow 3s ease-in-out infinite',
  },
  sidebar: {
    width: '290px',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    overflowY: 'auto',
    paddingRight: '4px',
  },
  sidebarSection: {
    background: `linear-gradient(145deg, ${THEME.bgCard}, ${THEME.bgDeep}90)`,
    borderRadius: '16px',
    border: `1px solid ${THEME.borderSubtle}`,
    padding: '16px',
    backdropFilter: 'blur(16px)',
    boxShadow: `0 4px 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.03)`,
  },
  sidebarHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '14px',
    paddingBottom: '10px',
    borderBottom: `1px solid ${THEME.borderSubtle}`,
  },
  sidebarTitleWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '9px',
  },
  sidebarTitle: {
    fontSize: '0.85rem',
    fontWeight: 700,
    color: THEME.textBright,
    letterSpacing: '0.02em',
  },
  sidebarBadge: {
    fontSize: '0.65rem',
    fontWeight: 700,
    padding: '3px 9px',
    borderRadius: '12px',
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    color: THEME.textSecondary,
    border: `1px solid ${THEME.borderSubtle}`,
  },
  insightsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  insightCard: {
    position: 'relative',
    padding: '12px 14px 12px 18px',
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    borderRadius: '12px',
    border: `1px solid ${THEME.borderSubtle}`,
    overflow: 'hidden',
    animation: 'insightSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
    opacity: 0,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    cursor: 'default',
  },
  insightAccent: {
    position: 'absolute',
    left: 0,
    top: '10%',
    bottom: '10%',
    width: '3px',
    borderRadius: '3px',
  },
  insightLabel: {
    fontSize: '0.68rem',
    color: THEME.textMuted,
    marginBottom: '5px',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    fontWeight: 600,
  },
  insightValue: {
    fontSize: '1.15rem',
    fontWeight: 800,
    letterSpacing: '-0.01em',
  },
  insightDesc: {
    fontSize: '0.7rem',
    color: THEME.textSecondary,
    marginTop: '5px',
    lineHeight: 1.45,
  },
  rankingList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  rankingItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    borderRadius: '12px',
    border: `1px solid ${THEME.borderSubtle}`,
    animation: 'rankSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
    opacity: 0,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  rankBadge: {
    width: '26px',
    height: '26px',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.75rem',
    fontWeight: 800,
    flexShrink: 0,
  },
  rankInfo: {
    flex: 1,
    minWidth: 0,
  },
  rankName: {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: THEME.textPrimary,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  rankPop: {
    fontSize: '0.68rem',
    color: THEME.textMuted,
    marginTop: '2px',
    fontFamily: 'JetBrains Mono, monospace',
  },
  rankBar: {
    width: '55px',
    height: '6px',
    background: `linear-gradient(90deg, ${THEME.bgGlass}, transparent)`,
    borderRadius: '3px',
    overflow: 'hidden',
    border: `1px solid ${THEME.borderSubtle}`,
  },
  rankBarFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
  },
  legendGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '5px',
    marginTop: '12px',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '0.72rem',
    color: THEME.textPrimary,
    padding: '5px 8px',
    borderRadius: '8px',
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    border: `1px solid ${THEME.borderSubtle}`,
    transition: 'all 0.2s',
  },
  legendDot: {
    width: '10px',
    height: '10px',
    borderRadius: '3px',
  },
  pieCenter: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    textAlign: 'center',
    pointerEvents: 'none',
  },
  pieCenterValue: {
    fontSize: '1.5rem',
    fontWeight: 800,
    color: THEME.textBright,
    lineHeight: 1,
    fontFamily: 'JetBrains Mono, monospace',
  },
  pieCenterLabel: {
    fontSize: '0.62rem',
    color: THEME.textMuted,
    marginTop: '3px',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  metricCard: {
    position: 'relative',
    background: `linear-gradient(145deg, ${THEME.bgCard}, ${THEME.bgDeep}95)`,
    borderRadius: '16px',
    padding: '16px 18px',
    border: `1px solid ${THEME.borderSubtle}`,
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    backdropFilter: 'blur(16px)',
    overflow: 'hidden',
    transition: 'all 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
    cursor: 'pointer',
  },
  metricHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  metricLabel: {
    fontSize: '0.72rem',
    color: THEME.textSecondary,
    fontWeight: 600,
    letterSpacing: '0.03em',
    textTransform: 'uppercase',
  },
  metricContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  metricValue: {
    fontSize: '1.65rem',
    fontWeight: 800,
    letterSpacing: '-0.02em',
    fontFamily: 'JetBrains Mono, monospace',
  },
  metricFooter: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    marginTop: '2px',
  },
  tooltip: {
    background: `linear-gradient(145deg, ${THEME.bgDeep}f8, ${THEME.bgPrimary}f5)`,
    border: `1px solid ${THEME.borderActive}`,
    borderRadius: '14px',
    padding: '16px',
    boxShadow: `0 16px 48px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04), 0 0 30px ${THEME.glowOcean}`,
    backdropFilter: 'blur(20px)',
    minWidth: '200px',
  },
  tooltipHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '12px',
  },
  tooltipTitle: {
    fontSize: '0.9rem',
    fontWeight: 700,
    color: THEME.textBright,
  },
  tooltipDivider: {
    height: '1px',
    background: `linear-gradient(90deg, transparent, ${THEME.borderDefault}, transparent)`,
    marginBottom: '12px',
  },
  tooltipItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '4px 0',
  },
  footer: {
    marginTop: 'auto',
    background: `linear-gradient(145deg, ${THEME.bgCard}80, ${THEME.bgDeep}60)`,
    borderRadius: '14px',
    padding: '14px 16px',
    border: `1px solid ${THEME.borderSubtle}`,
    backdropFilter: 'blur(12px)',
  },
  footerTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '0.75rem',
    fontWeight: 700,
    color: THEME.textSecondary,
    marginBottom: '12px',
    paddingBottom: '10px',
    borderBottom: `1px solid ${THEME.borderSubtle}`,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  footerGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px',
  },
  footerItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  footerLabel: {
    fontSize: '0.65rem',
    color: THEME.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  footerValue: {
    fontSize: '0.88rem',
    fontWeight: 700,
    color: THEME.textBright,
    fontFamily: 'JetBrains Mono, monospace',
  },
  footerStage: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginTop: '12px',
    paddingTop: '10px',
    borderTop: `1px solid ${THEME.borderSubtle}`,
    fontSize: '0.78rem',
    color: THEME.accentEarth,
    fontWeight: 600,
  },
  timelineSection: {
    background: `linear-gradient(145deg, ${THEME.bgCard}, ${THEME.bgDeep}90)`,
    borderRadius: '18px',
    border: `1px solid ${THEME.borderSubtle}`,
    padding: '18px 20px',
    flexShrink: 0,
    position: 'relative',
    zIndex: 1,
    backdropFilter: 'blur(16px)',
    boxShadow: `0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.03)`,
  },
  timelineHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '18px',
    paddingBottom: '14px',
    borderBottom: `1px solid ${THEME.borderSubtle}`,
  },
  timelineHeaderLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  timelineHeaderTitle: {
    fontSize: '0.95rem',
    fontWeight: 700,
    color: THEME.textBright,
    letterSpacing: '0.02em',
  },
  timelineHeaderRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  timelineCount: {
    fontSize: '0.72rem',
    fontWeight: 700,
    color: THEME.accentOcean,
    background: `linear-gradient(135deg, ${THEME.accentOcean}18, ${THEME.accentOcean}08)`,
    padding: '5px 14px',
    borderRadius: '20px',
    border: `1px solid ${THEME.accentOcean}30`,
    boxShadow: `0 0 12px ${THEME.glowOcean}`,
  },
  timelineScroll: {
    display: 'flex',
    gap: '10px',
    overflowX: 'auto',
    paddingBottom: '10px',
    position: 'relative',
  },
  timelineTrack: {
    position: 'absolute',
    top: '22px',
    left: '0',
    right: '0',
    height: '2px',
    background: `linear-gradient(90deg, transparent, ${THEME.accentOcean}40, ${THEME.accentOcean}40, transparent)`,
    borderRadius: '1px',
  },
  timelineItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    minWidth: '150px',
    padding: '14px 12px',
    background: `linear-gradient(145deg, ${THEME.bgGlass}, transparent)`,
    borderRadius: '14px',
    border: `1px solid ${THEME.borderSubtle}`,
    animation: 'timelineSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
    opacity: 0,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  timelineConnector: {
    marginBottom: '10px',
  },
  timelineDot: {
    width: '14px',
    height: '14px',
    borderRadius: '50%',
  },
  timelineIcon: {
    width: '40px',
    height: '40px',
    borderRadius: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '10px',
  },
  timelineTurnBadge: {
    fontSize: '0.68rem',
    fontWeight: 800,
    color: THEME.textSecondary,
    background: `linear-gradient(135deg, ${THEME.bgGlass}, transparent)`,
    padding: '3px 10px',
    borderRadius: '10px',
    marginBottom: '8px',
    border: `1px solid ${THEME.borderSubtle}`,
    fontFamily: 'JetBrains Mono, monospace',
  },
  timelineContent: {
    textAlign: 'center',
  },
  timelineTitle: {
    fontSize: '0.78rem',
    fontWeight: 700,
    marginBottom: '5px',
    lineHeight: 1.35,
  },
  timelineDesc: {
    fontSize: '0.68rem',
    color: THEME.textSecondary,
    lineHeight: 1.45,
    maxWidth: '125px',
  },
};
