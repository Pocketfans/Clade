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
  Activity
} from "lucide-react";

interface Props {
  tile?: MapTileInfo | null;
  habitats: HabitatEntry[];
  selectedSpecies?: string | null;
  onSelectSpecies: (lineageCode: string) => void;
}

export function TileDetailPanel({ tile, habitats, selectedSpecies, onSelectSpecies }: Props) {
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
          <span style={{display: 'flex', alignItems: 'center'}}><Users size={14} style={{marginRight: 6}}/> 物种占据 ({habitats.length})</span>
        </div>
        
        <div className="habitat-list custom-scrollbar">
          {habitats.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(255,255,255,0.3)' }}>
              <Activity size={32} strokeWidth={1} style={{ marginBottom: '0.5rem' }} />
              <p style={{ margin: 0, fontSize: '0.9rem' }}>该地块暂无物种</p>
            </div>
          ) : (
            // 按人口数量排序，最多的在前面
            [...habitats]
              .sort((a, b) => b.population - a.population)
              .map((entry) => (
                <div
                  key={`${entry.lineage_code}-${entry.tile_id}`}
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
