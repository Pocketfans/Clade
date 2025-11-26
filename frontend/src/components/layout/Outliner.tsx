import { TrendingUp, TrendingDown, Minus, Skull } from "lucide-react";
import { SpeciesSnapshot } from "../../services/api.types";

interface Props {
  speciesList: SpeciesSnapshot[];
  selectedSpeciesId: string | null;
  onSelectSpecies: (id: string) => void;
  onCollapse?: () => void;
}

// 生态角色颜色映射
const roleColors: Record<string, string> = {
  producer: "#4ade80",      // 生产者 - 绿色
  herbivore: "#facc15",     // 食草动物 - 金黄
  carnivore: "#f43f5e",     // 食肉动物 - 玫红
  omnivore: "#fb923c",      // 杂食动物 - 橙色
  decomposer: "#c084fc",    // 分解者 - 紫色
  scavenger: "#94a3b8",     // 食腐动物 - 灰色
  default: "#2dd4bf"        // 默认 - 主题色
};

// 生态角色图标
const roleIcons: Record<string, string> = {
  producer: "🌿",
  herbivore: "🦌",
  carnivore: "🦁",
  omnivore: "🐻",
  decomposer: "🍄",
  scavenger: "🦅",
  default: "🧬"
};

// 获取趋势指示
function getTrendIndicator(deathRate: number, status: string) {
  if (status === 'extinct') {
    return { icon: Skull, color: "#94a3b8", label: "已灭绝" };
  }
  if (deathRate > 0.15) {
    return { icon: TrendingDown, color: "#f43f5e", label: "危急" };
  }
  if (deathRate > 0.08) {
    return { icon: TrendingDown, color: "#fb923c", label: "衰退" };
  }
  if (deathRate < 0.03) {
    return { icon: TrendingUp, color: "#4ade80", label: "繁荣" };
  }
  return { icon: Minus, color: "#94a3b8", label: "稳定" };
}

export function Outliner({ speciesList, selectedSpeciesId, onSelectSpecies, onCollapse }: Props) {
  // Sort by population desc
  const sorted = [...speciesList].sort((a, b) => b.population - a.population);

  // 统计
  const aliveCount = sorted.filter(s => s.status !== 'extinct').length;
  const extinctCount = sorted.length - aliveCount;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="outliner-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '1.1rem' }}>🧬</span>
          <span>物种概览</span>
          <span style={{ 
            background: 'rgba(45, 212, 191, 0.15)', 
            padding: '2px 8px', 
            borderRadius: '12px',
            fontSize: '0.75rem',
            color: '#2dd4bf'
          }}>
            {aliveCount} 存活
          </span>
          {extinctCount > 0 && (
            <span style={{ 
              background: 'rgba(148, 163, 184, 0.15)', 
              padding: '2px 8px', 
              borderRadius: '12px',
              fontSize: '0.75rem',
              color: '#94a3b8'
            }}>
              {extinctCount} 灭绝
            </span>
          )}
        </div>
        {onCollapse && (
          <button 
            onClick={onCollapse}
            className="btn-icon"
            style={{ 
              width: '24px', 
              height: '24px', 
              padding: 0, 
              minHeight: 'unset', 
              fontSize: '14px',
              background: 'rgba(45, 212, 191, 0.1)',
              border: '1px solid rgba(45, 212, 191, 0.2)',
              borderRadius: '6px'
            }}
            title="折叠列表"
          >
            ‹
          </button>
        )}
      </div>
      <div className="outliner-list">
        {sorted.map(s => {
          const roleColor = roleColors[s.ecological_role?.toLowerCase()] || roleColors.default;
          const roleIcon = roleIcons[s.ecological_role?.toLowerCase()] || roleIcons.default;
          const trend = getTrendIndicator(s.death_rate, s.status);
          const TrendIcon = trend.icon;
          const isExtinct = s.status === 'extinct';

          return (
            <div 
              key={s.lineage_code}
              className={`outliner-item ${selectedSpeciesId === s.lineage_code ? "selected" : ""}`}
              onClick={() => onSelectSpecies(s.lineage_code)}
              style={{
                borderLeftColor: selectedSpeciesId === s.lineage_code ? roleColor : 'transparent',
                opacity: isExtinct ? 0.5 : 1
              }}
            >
              {/* 左侧：角色图标 + 名称 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '8px',
                  marginBottom: '2px'
                }}>
                  {/* 角色指示器 */}
                  <div style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '8px',
                    background: `linear-gradient(135deg, ${roleColor}20, ${roleColor}10)`,
                    border: `1px solid ${roleColor}40`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '14px',
                    flexShrink: 0
                  }}>
                    {roleIcon}
                  </div>
                  
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ 
                      fontWeight: 600, 
                      color: isExtinct ? '#666' : '#f0f4e8',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '0.9rem'
                    }}>
                      <span style={{ 
                        overflow: 'hidden', 
                        textOverflow: 'ellipsis', 
                        whiteSpace: 'nowrap' 
                      }}>
                        {s.common_name}
                      </span>
                      {isExtinct && (
                        <span style={{ color: '#94a3b8', fontSize: '0.7rem' }}>†</span>
                      )}
                    </div>
                    <div style={{ 
                      fontSize: "0.7rem", 
                      opacity: 0.6,
                      fontStyle: 'italic',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {s.latin_name}
                    </div>
                  </div>
                </div>
              </div>

              {/* 右侧：数据指标 */}
              <div style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'flex-end',
                gap: '2px'
              }}>
                {/* 人口数量 */}
                <div style={{ 
                  fontWeight: "bold", 
                  fontSize: "0.95rem",
                  fontFamily: 'var(--font-mono)',
                  color: isExtinct ? '#666' : '#f0f4e8'
                }}>
                  {s.population >= 1000000 
                    ? `${(s.population / 1000000).toFixed(1)}M` 
                    : s.population >= 1000 
                      ? `${(s.population / 1000).toFixed(1)}k`
                      : s.population}
                </div>
                
                {/* 趋势指示器 */}
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '4px',
                  fontSize: '0.7rem',
                  color: trend.color,
                  padding: '2px 6px',
                  background: `${trend.color}15`,
                  borderRadius: '4px'
                }}>
                  <TrendIcon size={10} />
                  <span>{trend.label}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


