import { useMemo } from "react";
import type { HabitatEntry, MapTileInfo } from "../services/api.types";
import { 
  Mountain, 
  Thermometer, 
  Droplets, 
  Wind, 
  Trees, 
  Pickaxe, 
  MapPin,
  Users,
  Activity,
  Leaf,
  TrendingUp
} from "lucide-react";

interface Props {
  tile?: MapTileInfo | null;
  habitats: HabitatEntry[];
  selectedSpecies?: string | null;
  onSelectSpecies: (lineageCode: string) => void;
}

export function TileDetailPanel({ tile, habitats, selectedSpecies, onSelectSpecies }: Props) {
  // 确保 habitats 只包含当前地块的物种，并去重
  const filteredHabitats = useMemo(() => {
    if (!tile) return [];
    
    // 按 tile_id 过滤，并使用 Map 去重（以 lineage_code 为 key）
    const habitatMap = new Map<string, HabitatEntry>();
    for (const hab of habitats) {
      if (hab.tile_id === tile.id) {
        // 如果已存在，取人口更大的那个
        const existing = habitatMap.get(hab.lineage_code);
        if (!existing || hab.population > existing.population) {
          habitatMap.set(hab.lineage_code, hab);
        }
      }
    }
    
    // 转为数组并按人口排序
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

  if (!tile) {
    return (
      <div className="tile-detail-panel" style={{ justifyContent: 'center', alignItems: 'center', opacity: 0.5 }}>
        <MapPin size={48} strokeWidth={1} />
        <p className="mt-md">点击任意格子以查看地块信息</p>
      </div>
    );
  }

  // Helper to format numbers
  const fmt = (n: number, d: number = 1) => n.toFixed(d);

  return (
    <div className="tile-detail-panel">
      <div className="tile-header">
        <div className="tile-coords">
           X: {tile.x} / Y: {tile.y} · HEX {tile.id}
        </div>
        <h3 className="tile-title">{tile.terrain_type}</h3>
      </div>

      <div className="tile-stats-grid">
        <div className="stat-card">
          <div className="stat-label">
            <Mountain size={14} /> 海拔
          </div>
          <div className="stat-value">
            {fmt(tile.elevation, 0)}<span className="stat-unit">m</span>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">
            <Thermometer size={14} /> 温度
          </div>
          <div className="stat-value">
            {fmt(tile.temperature)}<span className="stat-unit">°C</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            <Droplets size={14} /> 湿度
          </div>
          <div className="stat-value">
            {fmt(tile.humidity * 100, 0)}<span className="stat-unit">%</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            <Trees size={14} /> 覆盖
          </div>
          <div className="stat-value" style={{ fontSize: '0.9rem' }}>
            {tile.cover || "无"}
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-label">
            <Pickaxe size={14} /> 资源
          </div>
          <div className="stat-value">
            {fmt(tile.resources, 0)}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            <Wind size={14} /> 气候
          </div>
          <div className="stat-value" style={{ fontSize: '0.9rem' }}>
            {tile.climate_zone}
          </div>
        </div>
      </div>

      <div className="habitat-section">
        <div className="habitat-header">
          <span style={{display: 'flex', alignItems: 'center'}}>
            <Users size={14} style={{marginRight: 6}}/> 
            物种占据 ({filteredHabitats.length})
          </span>
          {filteredHabitats.length > 0 && (
            <div style={{ display: 'flex', gap: '12px', fontSize: '0.75rem', color: 'rgba(226, 236, 255, 0.5)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <TrendingUp size={12} />
                {totalPopulation.toLocaleString()}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Leaf size={12} />
                {fmt(avgSuitability, 2)}
              </span>
            </div>
          )}
        </div>
        
        <div className="habitat-list custom-scrollbar" style={{ maxHeight: '300px', overflowY: 'auto' }}>
          {filteredHabitats.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(255,255,255,0.3)' }}>
              <Activity size={32} strokeWidth={1} style={{ marginBottom: '0.5rem' }} />
              <p style={{ margin: 0, fontSize: '0.9rem' }}>该地块暂无物种栖息</p>
              <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', opacity: 0.6 }}>
                可能是环境条件不适宜
              </p>
            </div>
          ) : (
            filteredHabitats.map((entry) => (
              <div
                key={`${tile.id}-${entry.lineage_code}`}
                className={`species-row ${selectedSpecies === entry.lineage_code ? "selected" : ""}`}
                onClick={() => onSelectSpecies(entry.lineage_code)}
                title={`${entry.common_name} (${entry.latin_name}) - ${entry.lineage_code}`}
              >
                <div className="species-info">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1, minWidth: 0 }}>
                    <span className="species-name" style={{ 
                      fontWeight: 600, 
                      fontSize: '0.95rem',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {entry.common_name}
                    </span>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.85rem', opacity: 0.7 }}>
                      <span className="species-code">{entry.lineage_code}</span>
                      <span className="species-pop">{entry.population.toLocaleString()} 个体</span>
                    </div>
                  </div>
                </div>
                
                <div className={`suitability-badge ${
                  entry.suitability > 0.7 ? 'suitability-high animate-pulse-slow' : 
                  entry.suitability > 0.4 ? 'suitability-mid' : 'suitability-low'
                }`}>
                  {fmt(entry.suitability, 2)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
