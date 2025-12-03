import { useMemo, useState, useEffect } from "react";
import type { HabitatEntry, MapTileInfo, SuitabilityBreakdown } from "@/services/api.types";
import { 
  Mountain, 
  Thermometer, 
  Droplets, 
  Gem, 
  MapPin,
  Users,
  Activity,
  Leaf,
  TrendingUp,
  Compass,
  Waves,
  Sun,
  Snowflake,
  Cloud,
  ChevronDown,
  ChevronUp,
  Zap,
  Heart,
  CircleDot,
  TreePine,
  Shrub,
  Wheat,
  Eye,
  Sparkles,
  BarChart3
} from "lucide-react";

interface Props {
  tile?: MapTileInfo | null;
  habitats: HabitatEntry[];
  selectedSpecies?: string | null;
  onSelectSpecies: (lineageCode: string) => void;
}

// 12 维特征名称和图标映射
const DIMENSION_INFO: Record<string, { icon: string; label: string; weight: number; critical?: boolean }> = {
  aquatic: { icon: "🌊", label: "水域性", weight: 0.22, critical: true },
  thermal: { icon: "🌡️", label: "温度", weight: 0.10, critical: true },
  salinity: { icon: "🧂", label: "盐度", weight: 0.10 },
  moisture: { icon: "💧", label: "湿度", weight: 0.08 },
  altitude: { icon: "⛰️", label: "海拔", weight: 0.08 },
  resources: { icon: "💎", label: "资源", weight: 0.08 },
  depth: { icon: "🔽", label: "深度", weight: 0.08 },
  light: { icon: "☀️", label: "光照", weight: 0.06 },
  vegetation: { icon: "🌿", label: "植被", weight: 0.06 },
  river: { icon: "🏞️", label: "河流", weight: 0.06 },
  volcanic: { icon: "🌋", label: "地热", weight: 0.04 },
  stability: { icon: "🏔️", label: "稳定性", weight: 0.04 },
};

// 格式化宜居度分解为 tooltip 文本 (新版 12 维系统)
function formatBreakdownTooltip(breakdown: SuitabilityBreakdown, displayedSuitability: number): string {
  const lines: string[] = [
    `📊 综合宜居度: ${(displayedSuitability * 100).toFixed(0)}%`,
    `════════════════════`,
  ];
  
  // 1. 物理限制警告 (硬约束检测)
  if (displayedSuitability < 0.01) {
    lines.push(`❌ 环境致死: 不可生存`);
    if (breakdown.aquatic !== undefined && breakdown.aquatic < 0.1) {
      lines.push(`   • 物理介质不符 (如: 陆生入海)`);
    }
    if (breakdown.thermal !== undefined && breakdown.thermal < 0.1) {
      lines.push(`   • 温度超出耐受极限`);
    }
    lines.push(`────────────────────`);
  }

  // 2. 食物/能量来源 (消费者专用)
  if (typeof breakdown.has_prey === 'boolean') {
    if (breakdown.has_prey) {
      const preyScore = (breakdown.prey_abundance || 0) * 100;
      let preyLevel = "稀少";
      if (preyScore > 80) preyLevel = "极其丰富";
      else if (preyScore > 50) preyLevel = "丰富";
      else if (preyScore > 20) preyLevel = "一般";
      
      lines.push(`🥩 猎物状况: ${preyLevel} (${preyScore.toFixed(0)}%)`);
    } else {
      lines.push(`🍖 严重饥饿: 无猎物来源!`);
      lines.push(`⚠️ 死亡率极高 (缺乏能量)`);
    }
    lines.push(`────────────────────`);
  }
  
  // 3. 生态位与特征
  if (breakdown.semantic_score > 0) {
    lines.push(`🧠 生态位匹配: ${(breakdown.semantic_score * 100).toFixed(0)}%`);
    lines.push(`(基于演化历史与相近物种判定)`);
    lines.push(`────────────────────`);
  }
  
  // 4. 关键环境因素
  const scores: { key: string; score: number; info: typeof DIMENSION_INFO[string] }[] = [];
  for (const [key, info] of Object.entries(DIMENSION_INFO)) {
    const score = (breakdown as unknown as Record<string, number>)[key] ?? 0;
    scores.push({ key, score, info });
  }
  
  const shortBoards = scores.filter(s => s.score < 0.4);
  let showDims = [];
  
  if (shortBoards.length > 0 && displayedSuitability < 0.5) {
    lines.push(`📉 限制因素 (短板):`);
    showDims = shortBoards.sort((a, b) => a.score - b.score).slice(0, 4);
  } else {
    lines.push(`✅ 关键环境指标:`);
    const criticalDims = scores.filter(s => s.info.critical || s.score > 0.7);
    showDims = criticalDims.sort((a, b) => b.score - a.score).slice(0, 5);
  }
  
  if (showDims.length > 0) {
    for (const { score, info } of showDims) {
      const pct = (score * 100).toFixed(0);
      const status = score < 0.3 ? "❌" : score < 0.6 ? "⚠️" : "✅";
      lines.push(`  ${status} ${info.icon} ${info.label}: ${pct}%`);
    }
  }
  
  return lines.join('\n');
}

// 地形类型配置
const TERRAIN_CONFIG: Record<string, { icon: typeof Mountain; gradient: string; emoji: string; glowColor: string }> = {
  "深海": { icon: Waves, gradient: "linear-gradient(135deg, #050a12, #0c1e38)", emoji: "🌊", glowColor: "rgba(13, 99, 172, 0.5)" },
  "浅海": { icon: Waves, gradient: "linear-gradient(135deg, #2d6699, #4a94cc)", emoji: "🐚", glowColor: "rgba(93, 173, 226, 0.5)" },
  "海岸": { icon: Compass, gradient: "linear-gradient(135deg, #4a94cc, #5dade2)", emoji: "🏖️", glowColor: "rgba(93, 173, 226, 0.5)" },
  "平原": { icon: Wheat, gradient: "linear-gradient(135deg, #4e855b, #649f6d)", emoji: "🌾", glowColor: "rgba(100, 159, 109, 0.5)" },
  "丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #72ab76, #94c088)", emoji: "⛰️", glowColor: "rgba(114, 171, 118, 0.5)" },
  "山地": { icon: Mountain, gradient: "linear-gradient(135deg, #bf9a6a, #9f7a50)", emoji: "🏔️", glowColor: "rgba(191, 154, 106, 0.5)" },
  "高山": { icon: Mountain, gradient: "linear-gradient(135deg, #7a6350, #78787a)", emoji: "🗻", glowColor: "rgba(122, 99, 80, 0.5)" },
  "极高山": { icon: Snowflake, gradient: "linear-gradient(135deg, #b5bcc6, #f0f4f8)", emoji: "❄️", glowColor: "rgba(181, 188, 198, 0.5)" },
  
  // 海洋10级
  "超深海沟": { icon: Waves, gradient: "linear-gradient(135deg, #050a12, #081425)", emoji: "🌊", glowColor: "rgba(5, 10, 18, 0.8)" },
  "深海沟": { icon: Waves, gradient: "linear-gradient(135deg, #081425, #0c1e38)", emoji: "🌊", glowColor: "rgba(8, 20, 37, 0.8)" },
  "深海平原": { icon: Waves, gradient: "linear-gradient(135deg, #0c1e38, #12294a)", emoji: "🌊", glowColor: "rgba(12, 30, 56, 0.6)" },
  "深海盆地": { icon: Waves, gradient: "linear-gradient(135deg, #12294a, #1a3d66)", emoji: "🌊", glowColor: "rgba(18, 41, 74, 0.6)" },
  "海洋丘陵": { icon: Waves, gradient: "linear-gradient(135deg, #1a3d66, #235080)", emoji: "🌊", glowColor: "rgba(26, 61, 102, 0.6)" },
  "大陆坡深部": { icon: Waves, gradient: "linear-gradient(135deg, #235080, #2d6699)", emoji: "🐚", glowColor: "rgba(35, 80, 128, 0.6)" },
  "大陆坡": { icon: Waves, gradient: "linear-gradient(135deg, #2d6699, #3a7db3)", emoji: "🐚", glowColor: "rgba(45, 102, 153, 0.5)" },
  "大陆架深部": { icon: Waves, gradient: "linear-gradient(135deg, #3a7db3, #4a94cc)", emoji: "🐚", glowColor: "rgba(58, 125, 179, 0.5)" },
  "大陆架": { icon: Waves, gradient: "linear-gradient(135deg, #4a94cc, #5dade2)", emoji: "🏖️", glowColor: "rgba(74, 148, 204, 0.5)" },
  "近岸浅水": { icon: Compass, gradient: "linear-gradient(135deg, #5dade2, #6bc4e8)", emoji: "🏖️", glowColor: "rgba(93, 173, 226, 0.5)" },
  
  // 陆地低海拔
  "潮间带": { icon: Compass, gradient: "linear-gradient(135deg, #3d6b4a, #457852)", emoji: "🏖️", glowColor: "rgba(61, 107, 74, 0.5)" },
  "沿海低地": { icon: Compass, gradient: "linear-gradient(135deg, #457852, #4e855b)", emoji: "🏖️", glowColor: "rgba(69, 120, 82, 0.5)" },
  "冲积平原": { icon: Wheat, gradient: "linear-gradient(135deg, #4e855b, #589264)", emoji: "🌾", glowColor: "rgba(78, 133, 91, 0.5)" },
  "低海拔平原": { icon: Wheat, gradient: "linear-gradient(135deg, #589264, #649f6d)", emoji: "🌾", glowColor: "rgba(88, 146, 100, 0.5)" },
  "平原区": { icon: Wheat, gradient: "linear-gradient(135deg, #649f6d, #72ab76)", emoji: "🌾", glowColor: "rgba(100, 159, 109, 0.5)" },
  "缓坡丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #72ab76, #82b67f)", emoji: "⛰️", glowColor: "rgba(114, 171, 118, 0.5)" },
  "丘陵区": { icon: Mountain, gradient: "linear-gradient(135deg, #82b67f, #94c088)", emoji: "⛰️", glowColor: "rgba(130, 182, 127, 0.5)" },
  "高丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #94c088, #a6c48e)", emoji: "⛰️", glowColor: "rgba(148, 192, 136, 0.5)" },
  
  // 陆地中海拔
  "台地": { icon: Mountain, gradient: "linear-gradient(135deg, #a6c48e, #b5c58e)", emoji: "⛰️", glowColor: "rgba(166, 196, 142, 0.5)" },
  "低高原": { icon: Mountain, gradient: "linear-gradient(135deg, #b5c58e, #c4c38d)", emoji: "⛰️", glowColor: "rgba(181, 197, 142, 0.5)" },
  "高原": { icon: Mountain, gradient: "linear-gradient(135deg, #c4c38d, #ccbb86)", emoji: "⛰️", glowColor: "rgba(196, 195, 141, 0.5)" },
  "亚山麓": { icon: Mountain, gradient: "linear-gradient(135deg, #ccbb86, #c9ab78)", emoji: "🏔️", glowColor: "rgba(204, 187, 134, 0.5)" },
  "山麓带": { icon: Mountain, gradient: "linear-gradient(135deg, #c9ab78, #bf9a6a)", emoji: "🏔️", glowColor: "rgba(201, 171, 120, 0.5)" },
  "低山": { icon: Mountain, gradient: "linear-gradient(135deg, #bf9a6a, #b08a5c)", emoji: "🏔️", glowColor: "rgba(191, 154, 106, 0.5)" },
  "中低山": { icon: Mountain, gradient: "linear-gradient(135deg, #b08a5c, #9f7a50)", emoji: "🏔️", glowColor: "rgba(176, 138, 92, 0.5)" },
  "中山": { icon: Mountain, gradient: "linear-gradient(135deg, #9f7a50, #8d6c47)", emoji: "🏔️", glowColor: "rgba(159, 122, 80, 0.5)" },
  
  // 高海拔雪山
  "中高山": { icon: Mountain, gradient: "linear-gradient(135deg, #8d6c47, #7a6350)", emoji: "🏔️", glowColor: "rgba(141, 108, 71, 0.5)" },
  "高山区": { icon: Mountain, gradient: "linear-gradient(135deg, #7a6350, #6e6a5e)", emoji: "🗻", glowColor: "rgba(122, 99, 80, 0.5)" },
  "雪线区": { icon: Snowflake, gradient: "linear-gradient(135deg, #6e6a5e, #78787a)", emoji: "❄️", glowColor: "rgba(110, 106, 94, 0.5)" },
  "高寒荒漠": { icon: Snowflake, gradient: "linear-gradient(135deg, #78787a, #8a8e94)", emoji: "❄️", glowColor: "rgba(120, 120, 122, 0.5)" },
  "永久冰雪": { icon: Snowflake, gradient: "linear-gradient(135deg, #8a8e94, #9ea4ac)", emoji: "❄️", glowColor: "rgba(138, 142, 148, 0.5)" },
  "冰川区": { icon: Snowflake, gradient: "linear-gradient(135deg, #9ea4ac, #b5bcc6)", emoji: "❄️", glowColor: "rgba(158, 164, 172, 0.5)" },
  "极高山区": { icon: Snowflake, gradient: "linear-gradient(135deg, #b5bcc6, #d0d8e2)", emoji: "❄️", glowColor: "rgba(181, 188, 198, 0.5)" },
  "山峰": { icon: Snowflake, gradient: "linear-gradient(135deg, #d0d8e2, #f0f4f8)", emoji: "❄️", glowColor: "rgba(208, 216, 226, 0.5)" },
  "极地之巅": { icon: Snowflake, gradient: "linear-gradient(135deg, #f0f4f8, #ffffff)", emoji: "❄️", glowColor: "rgba(240, 244, 248, 0.5)" }
};

// 气候带配置
const CLIMATE_CONFIG: Record<string, { color: string; icon: typeof Sun; bgGradient: string }> = {
  "热带": { color: "#ff5722", icon: Sun, bgGradient: "linear-gradient(135deg, rgba(255, 87, 34, 0.15), rgba(255, 152, 0, 0.1))" },
  "亚热带": { color: "#ffc107", icon: Sun, bgGradient: "linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(255, 235, 59, 0.1))" },
  "温带": { color: "#4caf50", icon: Cloud, bgGradient: "linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(139, 195, 74, 0.1))" },
  "寒带": { color: "#81d4fa", icon: Cloud, bgGradient: "linear-gradient(135deg, rgba(129, 212, 250, 0.15), rgba(79, 195, 247, 0.1))" },
  "极地": { color: "#b3e5fc", icon: Snowflake, bgGradient: "linear-gradient(135deg, rgba(179, 229, 252, 0.15), rgba(225, 245, 254, 0.1))" }
};

// 植被覆盖配置
const COVER_CONFIG: Record<string, { icon: typeof TreePine; color: string }> = {
  "冰川": { icon: Snowflake, color: "#F5FAFF" },
  "冰原": { icon: Snowflake, color: "#E6F2FF" },
  "冰帽": { icon: Snowflake, color: "#EDF6FF" },
  "海冰": { icon: Snowflake, color: "#C5E0F5" },
  "冰湖": { icon: Snowflake, color: "#A8D4F0" },
  "冻土": { icon: Snowflake, color: "#8A9BAA" },
  "季节冻土": { icon: Snowflake, color: "#9AABB8" },
  "沙漠": { icon: CircleDot, color: "#E8C872" },
  "沙丘": { icon: CircleDot, color: "#F0D080" },
  "戈壁": { icon: CircleDot, color: "#C4A87A" },
  "盐碱地": { icon: CircleDot, color: "#D8D0C0" },
  "裸岩": { icon: Mountain, color: "#7A7A7A" },
  "裸地": { icon: CircleDot, color: "#A09080" },
  "苔原": { icon: Wheat, color: "#7A9E8A" },
  "高山草甸": { icon: Wheat, color: "#8CB878" },
  "草甸": { icon: Wheat, color: "#90C878" },
  "草原": { icon: Wheat, color: "#A8D068" },
  "稀树草原": { icon: Wheat, color: "#C8D060" },
  "灌木丛": { icon: Shrub, color: "#6A9A58" },
  "苔藓林": { icon: TreePine, color: "#4A7858" },
  "针叶林": { icon: TreePine, color: "#3E6850" },
  "混合林": { icon: TreePine, color: "#4A8058" },
  "阔叶林": { icon: TreePine, color: "#3A7048" },
  "森林": { icon: TreePine, color: "#3A7048" },
  "常绿林": { icon: TreePine, color: "#2A6040" },
  "雨林": { icon: TreePine, color: "#1A5030" },
  "云雾林": { icon: TreePine, color: "#3A6858" },
  "沼泽": { icon: Waves, color: "#3D5A45" },
  "湿地": { icon: Waves, color: "#4A6A50" },
  "泥炭地": { icon: Waves, color: "#5A5A48" },
  "红树林": { icon: TreePine, color: "#3A5840" },
  "水域": { icon: Waves, color: "#5DADE2" },
  "灌木": { icon: Shrub, color: "#6A9A58" },
  "草地": { icon: Wheat, color: "#A8D068" },
  "无": { icon: CircleDot, color: "#78909c" }
};

export function TileDetailPanel({ tile, habitats, selectedSpecies, onSelectSpecies }: Props) {
  const [showAllSpecies, setShowAllSpecies] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [activeTab, setActiveTab] = useState<'env' | 'species'>('env');

  // 当 tile 变化时触发动画
  useEffect(() => {
    if (tile) {
      setIsAnimating(true);
      const timer = setTimeout(() => setIsAnimating(false), 600);
      return () => clearTimeout(timer);
    }
  }, [tile?.id]);

  // 过滤和排序栖息物种
  const filteredHabitats = useMemo(() => {
    if (!tile) return [];
    
    const habitatMap = new Map<string, HabitatEntry>();
    for (const hab of habitats) {
      if (hab.tile_id === tile.id) {
        const existing = habitatMap.get(hab.lineage_code);
        if (!existing || hab.population > existing.population) {
          habitatMap.set(hab.lineage_code, hab);
        }
      }
    }
    
    return Array.from(habitatMap.values()).sort((a, b) => b.population - a.population);
  }, [tile, habitats]);

  // 计算总生物量
  const totalPopulation = useMemo(() => {
    return filteredHabitats.reduce((sum, hab) => sum + hab.population, 0);
  }, [filteredHabitats]);

  // 计算平均适宜度
  const avgSuitability = useMemo(() => {
    if (filteredHabitats.length === 0) return 0;
    const sum = filteredHabitats.reduce((s, hab) => s + hab.suitability, 0);
    return sum / filteredHabitats.length;
  }, [filteredHabitats]);

  // 计算生态健康指数
  const ecologyScore = useMemo(() => {
    if (!tile) return 0;
    const diversityScore = Math.min(filteredHabitats.length / 5, 1) * 30;
    const suitabilityScore = avgSuitability * 40;
    const resourceScore = Math.min(tile.resources / 500, 1) * 30;
    return Math.round(diversityScore + suitabilityScore + resourceScore);
  }, [tile, filteredHabitats, avgSuitability]);

  // 空状态
  if (!tile) {
    return (
      <div className="tdp">
        <div className="tdp-empty">
          <div className="tdp-empty-icon">
            <MapPin size={48} strokeWidth={1} />
            <div className="tdp-empty-pulse"></div>
            <div className="tdp-empty-pulse delay"></div>
          </div>
          <h3 className="tdp-empty-title">选择地块</h3>
          <p className="tdp-empty-hint">点击地图上的任意位置查看详细信息</p>
        </div>
      </div>
    );
  }

  const fmt = (n: number, d: number = 1) => n.toFixed(d);
  const terrainConfig = TERRAIN_CONFIG[tile.terrain_type] || TERRAIN_CONFIG["平原"];
  const climateConfig = CLIMATE_CONFIG[tile.climate_zone] || CLIMATE_CONFIG["温带"];
  const coverConfig = COVER_CONFIG[tile.cover] || COVER_CONFIG["无"];
  const TerrainIcon = terrainConfig.icon;
  const ClimateIcon = climateConfig.icon;
  const CoverIcon = coverConfig.icon;

  // 温度对应颜色
  const tempColor = tile.temperature > 25 ? "#ef4444" : 
                    tile.temperature > 15 ? "#f97316" : 
                    tile.temperature > 5 ? "#22c55e" : 
                    tile.temperature > -5 ? "#3b82f6" : "#a5b4fc";

  const displayedHabitats = showAllSpecies ? filteredHabitats : filteredHabitats.slice(0, 4);
  const hasMoreSpecies = filteredHabitats.length > 4;

  // 生态评分颜色
  const getScoreColor = (score: number) => {
    if (score >= 70) return { main: "#22c55e", glow: "rgba(34, 197, 94, 0.4)" };
    if (score >= 40) return { main: "#eab308", glow: "rgba(234, 179, 8, 0.4)" };
    return { main: "#ef4444", glow: "rgba(239, 68, 68, 0.4)" };
  };

  const scoreColor = getScoreColor(ecologyScore);

  return (
    <div className={`tdp ${isAnimating ? 'tdp-animating' : ''}`}>
      {/* Hero 区域 - 地形展示 */}
      <div className="tdp-hero" style={{ background: terrainConfig.gradient }}>
        <div className="tdp-hero-glow" style={{ background: `radial-gradient(ellipse at 30% 30%, ${terrainConfig.glowColor}, transparent 70%)` }}></div>
        <div className="tdp-hero-pattern"></div>
        <div className="tdp-hero-content">
          <div className="tdp-terrain-badge">
            <TerrainIcon size={20} strokeWidth={1.5} />
          </div>
          <div className="tdp-terrain-info">
            <h2 className="tdp-terrain-name">
              <span className="tdp-terrain-emoji">{terrainConfig.emoji}</span>
              {tile.terrain_type}
            </h2>
            <div className="tdp-coords">
              <Compass size={11} />
              <span>坐标 ({tile.x}, {tile.y})</span>
              <span className="tdp-tile-id">#{tile.id}</span>
            </div>
          </div>
          <div 
            className="tdp-color-swatch"
            style={{ backgroundColor: tile.color }}
            title="地块渲染颜色"
          >
            <Eye size={10} />
          </div>
        </div>
      </div>

      {/* 生态评分仪表盘 */}
      <div className="tdp-score-dashboard">
        <div className="tdp-score-gauge">
          <svg viewBox="0 0 120 120" className="tdp-gauge-svg">
            {/* 背景轨道 */}
            <circle 
              cx="60" cy="60" r="50"
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="10"
            />
            {/* 进度弧线 */}
            <circle 
              cx="60" cy="60" r="50"
              fill="none"
              stroke={scoreColor.main}
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={`${ecologyScore * 3.14} 314`}
              transform="rotate(-90 60 60)"
              className="tdp-gauge-progress"
              style={{ filter: `drop-shadow(0 0 8px ${scoreColor.glow})` }}
            />
            {/* 装饰刻度 */}
            {[0, 25, 50, 75, 100].map((tick, i) => (
              <line
                key={i}
                x1="60"
                y1="8"
                x2="60"
                y2="14"
                stroke="rgba(255,255,255,0.3)"
                strokeWidth="2"
                transform={`rotate(${tick * 3.6 - 90} 60 60)`}
              />
            ))}
          </svg>
          <div className="tdp-score-center">
            <span className="tdp-score-value" style={{ color: scoreColor.main }}>{ecologyScore}</span>
            <span className="tdp-score-label">生态指数</span>
          </div>
        </div>
        
        <div className="tdp-quick-stats">
          <div className="tdp-stat-chip">
            <Heart size={14} style={{ color: "#f472b6" }} />
            <span className="tdp-stat-number">{filteredHabitats.length}</span>
            <span className="tdp-stat-text">物种</span>
          </div>
          <div className="tdp-stat-chip">
            <BarChart3 size={14} style={{ color: "#60a5fa" }} />
            <span className="tdp-stat-number">{totalPopulation >= 1000 ? `${(totalPopulation/1000).toFixed(1)}k` : totalPopulation}</span>
            <span className="tdp-stat-text">生物量</span>
          </div>
          <div className="tdp-stat-chip">
            <Sparkles size={14} style={{ color: "#fbbf24" }} />
            <span className="tdp-stat-number">{fmt(avgSuitability * 100, 0)}%</span>
            <span className="tdp-stat-text">适宜度</span>
          </div>
        </div>
      </div>

      {/* 标签页切换 */}
      <div className="tdp-tabs">
        <button 
          className={`tdp-tab ${activeTab === 'env' ? 'active' : ''}`}
          onClick={() => setActiveTab('env')}
        >
          <Activity size={14} />
          <span>环境</span>
        </button>
        <button 
          className={`tdp-tab ${activeTab === 'species' ? 'active' : ''}`}
          onClick={() => setActiveTab('species')}
        >
          <Users size={14} />
          <span>物种</span>
          {filteredHabitats.length > 0 && (
            <span className="tdp-tab-badge">{filteredHabitats.length}</span>
          )}
        </button>
      </div>

      {/* 环境参数面板 */}
      {activeTab === 'env' && (
        <div className="tdp-env-panel">
          {/* 主要环境参数 */}
          <div className="tdp-env-grid">
            {/* 海拔卡片 */}
            <div className="tdp-env-card tdp-env-elevation">
              <div className="tdp-env-icon-wrap" style={{ background: "linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(132, 204, 22, 0.1))" }}>
                <Mountain size={18} style={{ color: "#84cc16" }} />
              </div>
              <div className="tdp-env-data">
                <span className="tdp-env-label">海拔</span>
                <div className="tdp-env-value-row">
                  <span className="tdp-env-value">{fmt(tile.elevation, 0)}</span>
                  <span className="tdp-env-unit">m</span>
                </div>
                <div className="tdp-env-bar">
                  <div 
                    className="tdp-env-bar-fill"
                    style={{ 
                      width: `${Math.min(Math.abs(tile.elevation) / 50, 100)}%`,
                      background: tile.elevation >= 0 ? 
                        "linear-gradient(90deg, #84cc16, #22c55e)" : 
                        "linear-gradient(90deg, #0ea5e9, #3b82f6)"
                    }}
                  ></div>
                </div>
              </div>
            </div>

            {/* 温度卡片 */}
            <div className="tdp-env-card tdp-env-temp">
              <div className="tdp-env-icon-wrap" style={{ background: `linear-gradient(135deg, ${tempColor}30, ${tempColor}15)` }}>
                <Thermometer size={18} style={{ color: tempColor }} />
              </div>
              <div className="tdp-env-data">
                <span className="tdp-env-label">温度</span>
                <div className="tdp-env-value-row">
                  <span className="tdp-env-value" style={{ color: tempColor }}>{fmt(tile.temperature)}</span>
                  <span className="tdp-env-unit">°C</span>
                </div>
                <div className="tdp-temp-scale">
                  <div className="tdp-temp-gradient"></div>
                  <div 
                    className="tdp-temp-marker"
                    style={{ left: `${Math.max(0, Math.min(100, (tile.temperature + 20) / 60 * 100))}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* 湿度卡片 */}
            <div className="tdp-env-card tdp-env-humidity">
              <div className="tdp-env-icon-wrap" style={{ background: "linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(14, 165, 233, 0.1))" }}>
                <Droplets size={18} style={{ color: "#38bdf8" }} />
              </div>
              <div className="tdp-env-data">
                <span className="tdp-env-label">湿度</span>
                <div className="tdp-env-value-row">
                  <span className="tdp-env-value">{fmt(tile.humidity * 100, 0)}</span>
                  <span className="tdp-env-unit">%</span>
                </div>
                <div className="tdp-humidity-drops">
                  {[...Array(5)].map((_, i) => (
                    <div 
                      key={i}
                      className={`tdp-humidity-drop ${tile.humidity > i * 0.2 ? 'active' : ''}`}
                      style={{ animationDelay: `${i * 0.1}s` }}
                    ></div>
                  ))}
                </div>
              </div>
            </div>

            {/* 资源卡片 */}
            <div className="tdp-env-card tdp-env-resources">
              <div className="tdp-env-icon-wrap" style={{ background: "linear-gradient(135deg, rgba(192, 132, 252, 0.2), rgba(167, 139, 250, 0.1))" }}>
                <Gem size={18} style={{ color: "#c084fc" }} />
              </div>
              <div className="tdp-env-data">
                <span className="tdp-env-label">资源</span>
                <div className="tdp-env-value-row">
                  <span className="tdp-env-value" style={{ color: "#c084fc" }}>{fmt(tile.resources, 0)}</span>
                </div>
                <div className="tdp-resource-gems">
                  {[...Array(5)].map((_, i) => (
                    <span 
                      key={i}
                      className={`tdp-resource-gem ${tile.resources > i * 200 ? 'active' : ''}`}
                    >◆</span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 气候和植被标签 */}
          <div className="tdp-env-tags">
            <div className="tdp-env-tag" style={{ background: climateConfig.bgGradient, borderColor: `${climateConfig.color}40` }}>
              <ClimateIcon size={14} style={{ color: climateConfig.color }} />
              <span style={{ color: climateConfig.color }}>{tile.climate_zone}</span>
            </div>
            <div className="tdp-env-tag" style={{ background: `linear-gradient(135deg, ${coverConfig.color}20, ${coverConfig.color}10)`, borderColor: `${coverConfig.color}40` }}>
              <CoverIcon size={14} style={{ color: coverConfig.color }} />
              <span style={{ color: coverConfig.color }}>{tile.cover || "无覆盖"}</span>
            </div>
          </div>
        </div>
      )}

      {/* 物种列表面板 */}
      {activeTab === 'species' && (
        <div className="tdp-species-panel">
          {filteredHabitats.length === 0 ? (
            <div className="tdp-species-empty">
              <div className="tdp-species-empty-icon">
                <Leaf size={32} strokeWidth={1} />
              </div>
              <h4>暂无物种栖息</h4>
              <p>该地块环境可能不适宜生物生存</p>
            </div>
          ) : (
            <div className="tdp-species-list custom-scrollbar">
              {displayedHabitats.map((entry, index) => {
                const isSelected = selectedSpecies === entry.lineage_code;
                // 基于物种代码生成一致的颜色
                const hue = (entry.lineage_code.charCodeAt(0) * 37) % 360;
                const borderColor = isSelected ? "#3b82f6" : `hsl(${hue}, 50%, 50%)`;
                
                return (
                  <div
                    key={`${tile.id}-${entry.lineage_code}`}
                    className={`tdp-species-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => onSelectSpecies(entry.lineage_code)}
                    style={{ 
                      animationDelay: `${index * 0.05}s`,
                      borderLeftColor: borderColor
                    }}
                  >
                    <div 
                      className="tdp-species-avatar"
                      style={{
                        background: `linear-gradient(135deg, hsl(${(entry.lineage_code.charCodeAt(0) * 20) % 360}, 55%, 35%), hsl(${(entry.lineage_code.charCodeAt(0) * 20 + 40) % 360}, 65%, 45%))`
                      }}
                    >
                      <span>{entry.common_name.charAt(0)}</span>
                    </div>
                    
                    <div className="tdp-species-info">
                      <div className="tdp-species-name">
                        {entry.common_name}
                        {entry.suitability > 0.8 && <span className="tdp-thrive-badge">✨</span>}
                      </div>
                      <div className="tdp-species-meta">
                        <span className="tdp-species-code">{entry.lineage_code}</span>
                        <span className="tdp-species-pop">
                          <TrendingUp size={10} />
                          {entry.population.toLocaleString()} kg
                        </span>
                      </div>
                    </div>
                    
                    <div 
                      className={`tdp-suitability ${
                        entry.suitability > 0.7 ? 'high' : 
                        entry.suitability > 0.4 ? 'mid' : 'low'
                      }`}
                      title={entry.breakdown ? formatBreakdownTooltip(entry.breakdown, entry.suitability) : `宜居度: ${fmt(entry.suitability, 2)}`}
                    >
                      <svg viewBox="0 0 36 36" className="tdp-suitability-ring">
                        <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3" />
                        <circle 
                          cx="18" cy="18" r="15" 
                          fill="none" 
                          strokeWidth="3"
                          strokeLinecap="round"
                          strokeDasharray={`${entry.suitability * 94.2} 94.2`}
                          transform="rotate(-90 18 18)"
                          className="tdp-suitability-progress"
                        />
                      </svg>
                      <span className="tdp-suitability-value">{fmt(entry.suitability * 100, 0)}</span>
                      {entry.breakdown?.has_prey === false && (
                        <span className="tdp-no-prey" title="无猎物来源">⚠</span>
                      )}
                    </div>
                  </div>
                );
              })}
              
              {hasMoreSpecies && (
                <button 
                  className="tdp-show-more"
                  onClick={() => setShowAllSpecies(!showAllSpecies)}
                >
                  {showAllSpecies ? (
                    <>
                      <ChevronUp size={14} />
                      <span>收起列表</span>
                    </>
                  ) : (
                    <>
                      <ChevronDown size={14} />
                      <span>显示全部 ({filteredHabitats.length})</span>
                    </>
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
