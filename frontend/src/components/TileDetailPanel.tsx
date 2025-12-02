import { useMemo, useState } from "react";
import type { HabitatEntry, MapTileInfo, SuitabilityBreakdown } from "@/services/api.types";
import { 
  Mountain, 
  Thermometer, 
  Droplets, 
  Wind, 
  Trees, 
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
  Wheat
} from "lucide-react";

interface Props {
  tile?: MapTileInfo | null;
  habitats: HabitatEntry[];
  selectedSpecies?: string | null;
  onSelectSpecies: (lineageCode: string) => void;
}

// 12 维特征名称和图标映射
const DIMENSION_INFO: Record<string, { icon: string; label: string; weight: number; critical?: boolean }> = {
  aquatic: { icon: "🌊", label: "水域性", weight: 0.22, critical: true },  // 最重要
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
    `📊 宜居度: ${(displayedSuitability * 100).toFixed(0)}%`,
    `════════════════════`,
  ];
  
  // 显示语义和特征分数
  if (breakdown.semantic_score > 0 || breakdown.feature_score > 0) {
    lines.push(`🧠 语义: ${(breakdown.semantic_score * 100).toFixed(0)}% × 40%`);
    lines.push(`📐 特征: ${(breakdown.feature_score * 100).toFixed(0)}% × 60%`);
    lines.push(`────────────────────`);
  }
  
  // 收集所有维度分数
  const scores: { key: string; score: number; info: typeof DIMENSION_INFO[string] }[] = [];
  for (const [key, info] of Object.entries(DIMENSION_INFO)) {
    const score = (breakdown as Record<string, number>)[key] ?? 0;
    scores.push({ key, score, info });
  }
  
  // 只显示重要/低分的维度
  // 规则：只显示权重高或分数低的维度
  const criticalDims = scores.filter(s => s.info.critical || s.score < 0.6);
  const sortedDims = criticalDims.sort((a, b) => {
    // 关键维度优先，然后按分数升序
    if (a.info.critical && !b.info.critical) return -1;
    if (!a.info.critical && b.info.critical) return 1;
    return a.score - b.score;
  });
  
  // 最多显示 5 个
  const showDims = sortedDims.slice(0, 5);
  
  if (showDims.length > 0) {
    lines.push(`📊 关键因素:`);
    for (const { score, info } of showDims) {
      const pct = (score * 100).toFixed(0);
      const bar = score < 0.5 ? "⚠️" : score < 0.8 ? "○" : "●";
      lines.push(`  ${info.icon} ${info.label}: ${pct}% ${bar}`);
    }
  }
  
  // 特别警告
  if (breakdown.aquatic < 0.4) {
    lines.push(`────────────────────`);
    lines.push(`⚠️ 水域/陆地严重不匹配！`);
  }
  
  return lines.join('\n');
}

// 地形类型配置 - 与后端 map_coloring.py 35级分类协调
const TERRAIN_CONFIG: Record<string, { icon: typeof Mountain; gradient: string; emoji: string }> = {
  // ===== 通用简称 =====
  "深海": { icon: Waves, gradient: "linear-gradient(135deg, #050a12, #0c1e38)", emoji: "🌊" },
  "浅海": { icon: Waves, gradient: "linear-gradient(135deg, #2d6699, #4a94cc)", emoji: "🐚" },
  "海岸": { icon: Compass, gradient: "linear-gradient(135deg, #4a94cc, #5dade2)", emoji: "🏖️" },
  "平原": { icon: Wheat, gradient: "linear-gradient(135deg, #4e855b, #649f6d)", emoji: "🌾" },
  "丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #72ab76, #94c088)", emoji: "⛰️" },
  "山地": { icon: Mountain, gradient: "linear-gradient(135deg, #bf9a6a, #9f7a50)", emoji: "🏔️" },
  "高山": { icon: Mountain, gradient: "linear-gradient(135deg, #7a6350, #78787a)", emoji: "🗻" },
  "极高山": { icon: Snowflake, gradient: "linear-gradient(135deg, #b5bcc6, #f0f4f8)", emoji: "❄️" },
  
  // ===== 海洋10级 (01-10) =====
  "超深海沟": { icon: Waves, gradient: "linear-gradient(135deg, #050a12, #081425)", emoji: "🌊" },
  "深海沟": { icon: Waves, gradient: "linear-gradient(135deg, #081425, #0c1e38)", emoji: "🌊" },
  "深海平原": { icon: Waves, gradient: "linear-gradient(135deg, #0c1e38, #12294a)", emoji: "🌊" },
  "深海盆地": { icon: Waves, gradient: "linear-gradient(135deg, #12294a, #1a3d66)", emoji: "🌊" },
  "海洋丘陵": { icon: Waves, gradient: "linear-gradient(135deg, #1a3d66, #235080)", emoji: "🌊" },
  "大陆坡深部": { icon: Waves, gradient: "linear-gradient(135deg, #235080, #2d6699)", emoji: "🐚" },
  "大陆坡": { icon: Waves, gradient: "linear-gradient(135deg, #2d6699, #3a7db3)", emoji: "🐚" },
  "大陆架深部": { icon: Waves, gradient: "linear-gradient(135deg, #3a7db3, #4a94cc)", emoji: "🐚" },
  "大陆架": { icon: Waves, gradient: "linear-gradient(135deg, #4a94cc, #5dade2)", emoji: "🏖️" },
  "近岸浅水": { icon: Compass, gradient: "linear-gradient(135deg, #5dade2, #6bc4e8)", emoji: "🏖️" },
  
  // ===== 陆地低海拔8级 (11-18) =====
  "潮间带": { icon: Compass, gradient: "linear-gradient(135deg, #3d6b4a, #457852)", emoji: "🏖️" },
  "沿海低地": { icon: Compass, gradient: "linear-gradient(135deg, #457852, #4e855b)", emoji: "🏖️" },
  "冲积平原": { icon: Wheat, gradient: "linear-gradient(135deg, #4e855b, #589264)", emoji: "🌾" },
  "低海拔平原": { icon: Wheat, gradient: "linear-gradient(135deg, #589264, #649f6d)", emoji: "🌾" },
  "平原区": { icon: Wheat, gradient: "linear-gradient(135deg, #649f6d, #72ab76)", emoji: "🌾" },
  "缓坡丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #72ab76, #82b67f)", emoji: "⛰️" },
  "丘陵区": { icon: Mountain, gradient: "linear-gradient(135deg, #82b67f, #94c088)", emoji: "⛰️" },
  "高丘陵": { icon: Mountain, gradient: "linear-gradient(135deg, #94c088, #a6c48e)", emoji: "⛰️" },
  
  // ===== 陆地中海拔8级 (19-26) =====
  "台地": { icon: Mountain, gradient: "linear-gradient(135deg, #a6c48e, #b5c58e)", emoji: "⛰️" },
  "低高原": { icon: Mountain, gradient: "linear-gradient(135deg, #b5c58e, #c4c38d)", emoji: "⛰️" },
  "高原": { icon: Mountain, gradient: "linear-gradient(135deg, #c4c38d, #ccbb86)", emoji: "⛰️" },
  "亚山麓": { icon: Mountain, gradient: "linear-gradient(135deg, #ccbb86, #c9ab78)", emoji: "🏔️" },
  "山麓带": { icon: Mountain, gradient: "linear-gradient(135deg, #c9ab78, #bf9a6a)", emoji: "🏔️" },
  "低山": { icon: Mountain, gradient: "linear-gradient(135deg, #bf9a6a, #b08a5c)", emoji: "🏔️" },
  "中低山": { icon: Mountain, gradient: "linear-gradient(135deg, #b08a5c, #9f7a50)", emoji: "🏔️" },
  "中山": { icon: Mountain, gradient: "linear-gradient(135deg, #9f7a50, #8d6c47)", emoji: "🏔️" },
  
  // ===== 高海拔雪山9级 (27-35) =====
  "中高山": { icon: Mountain, gradient: "linear-gradient(135deg, #8d6c47, #7a6350)", emoji: "🏔️" },
  "高山区": { icon: Mountain, gradient: "linear-gradient(135deg, #7a6350, #6e6a5e)", emoji: "🗻" },
  "雪线区": { icon: Snowflake, gradient: "linear-gradient(135deg, #6e6a5e, #78787a)", emoji: "❄️" },
  "高寒荒漠": { icon: Snowflake, gradient: "linear-gradient(135deg, #78787a, #8a8e94)", emoji: "❄️" },
  "永久冰雪": { icon: Snowflake, gradient: "linear-gradient(135deg, #8a8e94, #9ea4ac)", emoji: "❄️" },
  "冰川区": { icon: Snowflake, gradient: "linear-gradient(135deg, #9ea4ac, #b5bcc6)", emoji: "❄️" },
  "极高山区": { icon: Snowflake, gradient: "linear-gradient(135deg, #b5bcc6, #d0d8e2)", emoji: "❄️" },
  "山峰": { icon: Snowflake, gradient: "linear-gradient(135deg, #d0d8e2, #f0f4f8)", emoji: "❄️" },
  "极地之巅": { icon: Snowflake, gradient: "linear-gradient(135deg, #f0f4f8, #ffffff)", emoji: "❄️" }
};

// 气候带配置 - 更鲜明的颜色
const CLIMATE_CONFIG: Record<string, { color: string; icon: typeof Sun }> = {
  "热带": { color: "#ff5722", icon: Sun },      // 热橙
  "亚热带": { color: "#ffc107", icon: Sun },    // 金黄
  "温带": { color: "#4caf50", icon: Cloud },    // 翠绿
  "寒带": { color: "#81d4fa", icon: Cloud },    // 冷蓝
  "极地": { color: "#b3e5fc", icon: Snowflake } // 冰蓝
};

// 植被覆盖配置 - 30种细分覆盖物
const COVER_CONFIG: Record<string, { icon: typeof Trees; color: string }> = {
  // 冰雪类 (6种)
  "冰川": { icon: Snowflake, color: "#F5FAFF" },
  "冰原": { icon: Snowflake, color: "#E6F2FF" },
  "冰帽": { icon: Snowflake, color: "#EDF6FF" },
  "海冰": { icon: Snowflake, color: "#C5E0F5" },
  "冰湖": { icon: Snowflake, color: "#A8D4F0" },
  "冻土": { icon: Snowflake, color: "#8A9BAA" },
  "季节冻土": { icon: Snowflake, color: "#9AABB8" },
  
  // 荒漠类 (6种)
  "沙漠": { icon: CircleDot, color: "#E8C872" },
  "沙丘": { icon: CircleDot, color: "#F0D080" },
  "戈壁": { icon: CircleDot, color: "#C4A87A" },
  "盐碱地": { icon: CircleDot, color: "#D8D0C0" },
  "裸岩": { icon: Mountain, color: "#7A7A7A" },
  "裸地": { icon: CircleDot, color: "#A09080" },
  
  // 苔原/草地类 (6种)
  "苔原": { icon: Wheat, color: "#7A9E8A" },
  "高山草甸": { icon: Wheat, color: "#8CB878" },
  "草甸": { icon: Wheat, color: "#90C878" },
  "草原": { icon: Wheat, color: "#A8D068" },
  "稀树草原": { icon: Wheat, color: "#C8D060" },
  "灌木丛": { icon: Shrub, color: "#6A9A58" },
  
  // 森林类 (7种)
  "苔藓林": { icon: TreePine, color: "#4A7858" },
  "针叶林": { icon: TreePine, color: "#3E6850" },
  "混合林": { icon: TreePine, color: "#4A8058" },
  "阔叶林": { icon: TreePine, color: "#3A7048" },
  "森林": { icon: TreePine, color: "#3A7048" },
  "常绿林": { icon: TreePine, color: "#2A6040" },
  "雨林": { icon: TreePine, color: "#1A5030" },
  "云雾林": { icon: TreePine, color: "#3A6858" },
  
  // 湿地类 (5种)
  "沼泽": { icon: Waves, color: "#3D5A45" },
  "湿地": { icon: Waves, color: "#4A6A50" },
  "泥炭地": { icon: Waves, color: "#5A5A48" },
  "红树林": { icon: TreePine, color: "#3A5840" },
  "水域": { icon: Waves, color: "#5DADE2" },
  
  // 兼容旧类型
  "灌木": { icon: Shrub, color: "#6A9A58" },
  "草地": { icon: Wheat, color: "#A8D068" },
  "无": { icon: CircleDot, color: "#78909c" }
};

export function TileDetailPanel({ tile, habitats, selectedSpecies, onSelectSpecies }: Props) {
  const [showAllSpecies, setShowAllSpecies] = useState(false);

  // 确保 habitats 只包含当前地块的物种，并去重
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
    
    // 综合考虑：物种多样性、平均适宜度、资源丰度
    const diversityScore = Math.min(filteredHabitats.length / 5, 1) * 30; // 最多5个物种得满分
    const suitabilityScore = avgSuitability * 40;
    const resourceScore = Math.min(tile.resources / 500, 1) * 30;
    
    return Math.round(diversityScore + suitabilityScore + resourceScore);
  }, [tile, filteredHabitats, avgSuitability]);

  if (!tile) {
    return (
      <div className="tile-detail-panel tile-detail-empty">
        <div className="empty-state-icon">
          <MapPin size={64} strokeWidth={1} />
          <div className="empty-pulse-ring"></div>
        </div>
        <p className="empty-title">选择一个地块</p>
        <p className="empty-hint">点击地图上的任意位置以查看详细信息</p>
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

  // 温度颜色
  const tempColor = tile.temperature > 25 ? "#ef4444" : 
                    tile.temperature > 15 ? "#f97316" : 
                    tile.temperature > 5 ? "#22c55e" : 
                    tile.temperature > -5 ? "#3b82f6" : "#a5b4fc";

  // 显示的物种（默认显示前3个）
  const displayedHabitats = showAllSpecies ? filteredHabitats : filteredHabitats.slice(0, 3);
  const hasMoreSpecies = filteredHabitats.length > 3;

  return (
    <div className="tile-detail-panel tile-detail-enhanced">
      {/* 标题区域 - 带有地形渐变背景 */}
      <div className="tile-hero" style={{ background: terrainConfig.gradient }}>
        <div className="tile-hero-overlay"></div>
        <div className="tile-hero-content">
          <div className="tile-hero-icon">
            <TerrainIcon size={24} strokeWidth={1.5} />
          </div>
          <div className="tile-hero-info">
            <h3 className="tile-hero-title" title={tile.terrain_type}>
              {terrainConfig.emoji} {tile.terrain_type}
            </h3>
            <div className="tile-hero-coords">
              <Compass size={10} />
              <span>({tile.x}, {tile.y})</span>
              <span className="tile-hex-id">#{tile.id}</span>
            </div>
          </div>
          {/* 地块颜色预览 */}
          <div 
            className="tile-color-preview"
            style={{ backgroundColor: tile.color }}
            title="当前视图颜色"
          ></div>
        </div>
      </div>

      {/* 生态健康指数 */}
      <div className="ecology-score-section">
        <div className="ecology-score-ring">
          <svg viewBox="0 0 100 100" className="ecology-score-svg">
            <circle 
              cx="50" cy="50" r="42" 
              fill="none" 
              stroke="rgba(255,255,255,0.1)" 
              strokeWidth="8"
            />
            <circle 
              cx="50" cy="50" r="42" 
              fill="none" 
              stroke={ecologyScore >= 70 ? "#22c55e" : ecologyScore >= 40 ? "#eab308" : "#ef4444"}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${ecologyScore * 2.64} 264`}
              transform="rotate(-90 50 50)"
              className="ecology-score-progress"
            />
          </svg>
          <div className="ecology-score-value">
            <span className="score-number">{ecologyScore}</span>
            <span className="score-label">生态</span>
          </div>
        </div>
        <div className="ecology-metrics">
          <div className="metric-item">
            <Heart size={14} className="metric-icon" style={{ color: "#f472b6" }} />
            <span className="metric-label">物种</span>
            <span className="metric-value">{filteredHabitats.length}</span>
          </div>
          <div className="metric-item">
            <TrendingUp size={14} className="metric-icon" style={{ color: "#60a5fa" }} />
            <span className="metric-label">生物量</span>
            <span className="metric-value">{totalPopulation.toLocaleString()}</span>
          </div>
          <div className="metric-item">
            <Zap size={14} className="metric-icon" style={{ color: "#fbbf24" }} />
            <span className="metric-label">适宜度</span>
            <span className="metric-value">{fmt(avgSuitability * 100, 0)}%</span>
          </div>
        </div>
      </div>

      {/* 环境数据网格 */}
      <div className="env-data-section">
        <div className="section-title">
          <Activity size={14} />
          <span>环境参数</span>
        </div>
        
        <div className="env-grid">
          {/* 海拔 */}
          <div className="env-card">
            <div className="env-card-header">
              <Mountain size={16} className="env-icon" />
              <span className="env-label">海拔</span>
            </div>
            <div className="env-card-body">
              <div className="env-value-large">
                {fmt(tile.elevation, 0)}
                <span className="env-unit">m</span>
              </div>
              <div className="env-bar-container">
                <div 
                  className="env-bar" 
                  style={{ 
                    width: `${Math.min(Math.abs(tile.elevation) / 50, 100)}%`,
                    background: tile.elevation > 0 ? 
                      "linear-gradient(90deg, #65a30d, #a3e635)" : 
                      "linear-gradient(90deg, #0284c7, #38bdf8)"
                  }}
                ></div>
              </div>
            </div>
          </div>

          {/* 温度 */}
          <div className="env-card">
            <div className="env-card-header">
              <Thermometer size={16} className="env-icon" style={{ color: tempColor }} />
              <span className="env-label">温度</span>
            </div>
            <div className="env-card-body">
              <div className="env-value-large" style={{ color: tempColor }}>
                {fmt(tile.temperature)}
                <span className="env-unit">°C</span>
              </div>
              <div className="temp-gauge">
                <div className="temp-scale">
                  <span>-20</span>
                  <span>0</span>
                  <span>20</span>
                  <span>40</span>
                </div>
                <div className="temp-indicator" style={{ 
                  left: `${Math.max(0, Math.min(100, (tile.temperature + 20) / 60 * 100))}%`,
                  backgroundColor: tempColor
                }}></div>
              </div>
            </div>
          </div>

          {/* 湿度 */}
          <div className="env-card">
            <div className="env-card-header">
              <Droplets size={16} className="env-icon" style={{ color: "#38bdf8" }} />
              <span className="env-label">湿度</span>
            </div>
            <div className="env-card-body">
              <div className="env-value-large">
                {fmt(tile.humidity * 100, 0)}
                <span className="env-unit">%</span>
              </div>
              <div className="humidity-bubbles">
                {[...Array(5)].map((_, i) => (
                  <div 
                    key={i}
                    className={`humidity-bubble ${tile.humidity > i * 0.2 ? 'active' : ''}`}
                  ></div>
                ))}
              </div>
            </div>
          </div>

          {/* 资源 */}
          <div className="env-card">
            <div className="env-card-header">
              <Gem size={16} className="env-icon" style={{ color: "#c084fc" }} />
              <span className="env-label">资源</span>
            </div>
            <div className="env-card-body">
              <div className="env-value-large" style={{ color: "#c084fc" }}>
                {fmt(tile.resources, 0)}
              </div>
              <div className="resource-stars">
                {[...Array(5)].map((_, i) => (
                  <span 
                    key={i}
                    className={`resource-star ${tile.resources > i * 200 ? 'active' : ''}`}
                  >◆</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 气候和覆盖 */}
        <div className="env-tags">
          <div className="env-tag" style={{ borderColor: climateConfig.color }}>
            <ClimateIcon size={14} style={{ color: climateConfig.color }} />
            <span>{tile.climate_zone}</span>
          </div>
          <div className="env-tag" style={{ borderColor: coverConfig.color }}>
            <CoverIcon size={14} style={{ color: coverConfig.color }} />
            <span>{tile.cover || "无覆盖"}</span>
          </div>
        </div>
      </div>

      {/* 物种栖息区 */}
      <div className="habitat-section-enhanced">
        <div className="section-title">
          <Users size={14} />
          <span>栖息物种</span>
          <span className="species-count">{filteredHabitats.length}</span>
        </div>
        
        <div className="habitat-list-enhanced custom-scrollbar">
          {filteredHabitats.length === 0 ? (
            <div className="habitat-empty">
              <div className="habitat-empty-icon">
                <Leaf size={36} strokeWidth={1} />
              </div>
              <p className="habitat-empty-title">暂无物种栖息</p>
              <p className="habitat-empty-hint">该地块的环境条件可能不适宜生物生存</p>
            </div>
          ) : (
            <>
              {displayedHabitats.map((entry, index) => (
                <div
                  key={`${tile.id}-${entry.lineage_code}`}
                  className={`species-card ${selectedSpecies === entry.lineage_code ? "selected" : ""}`}
                  onClick={() => onSelectSpecies(entry.lineage_code)}
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className="species-avatar" style={{
                    background: `linear-gradient(135deg, hsl(${(entry.lineage_code.charCodeAt(0) * 20) % 360}, 60%, 40%), hsl(${(entry.lineage_code.charCodeAt(0) * 20 + 30) % 360}, 70%, 50%))`
                  }}>
                    {entry.common_name.charAt(0)}
                  </div>
                  
                  <div className="species-details">
                    <div className="species-name-row">
                      <span className="species-common-name">{entry.common_name}</span>
                      {entry.suitability > 0.8 && <span className="thriving-badge">🌟</span>}
                    </div>
                    <div className="species-meta-row">
                      <span className="species-code-badge">{entry.lineage_code}</span>
                      <span className="species-population">
                        {entry.population.toLocaleString()} kg
                      </span>
                    </div>
                  </div>
                  
                  <div 
                    className={`suitability-meter ${
                      entry.suitability > 0.7 ? 'high' : 
                      entry.suitability > 0.4 ? 'mid' : 'low'
                    }`}
                    title={entry.breakdown ? formatBreakdownTooltip(entry.breakdown, entry.suitability) : `宜居度: ${fmt(entry.suitability, 2)}`}
                  >
                    <div className="suitability-fill" style={{ height: `${entry.suitability * 100}%` }}></div>
                    <span className="suitability-text">{fmt(entry.suitability, 2)}</span>
                    {entry.breakdown?.has_prey === false && (
                      <span className="no-prey-indicator" title="无猎物！">⚠</span>
                    )}
                  </div>
                </div>
              ))}
              
              {hasMoreSpecies && (
                <button 
                  className="show-more-species"
                  onClick={() => setShowAllSpecies(!showAllSpecies)}
                >
                  {showAllSpecies ? (
                    <>
                      <ChevronUp size={14} />
                      收起
                    </>
                  ) : (
                    <>
                      <ChevronDown size={14} />
                      显示全部 ({filteredHabitats.length})
                    </>
                  )}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

