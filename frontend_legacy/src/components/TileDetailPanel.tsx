import type { HabitatEntry, MapTileInfo } from "../services/api.types";

interface Props {
  tile?: MapTileInfo | null;
  habitats: HabitatEntry[];
  selectedSpecies?: string | null;
  onSelectSpecies: (lineageCode: string) => void;
}

export function TileDetailPanel({ tile, habitats, selectedSpecies, onSelectSpecies }: Props) {
  if (!tile) {
    return <p className="placeholder">点击任意格子以查看地块信息。</p>;
  }

  return (
    <div className="tile-detail">
      <h3>
        地块 ({tile.x}, {tile.y}) · {tile.terrain_type}
      </h3>
      <div className="tile-stats">
        <span>地形：{tile.terrain_type}</span>
        <span>海拔：{tile.elevation.toFixed(0)}m</span>
        <span>覆盖：{tile.cover}</span>
        <span>气候：{tile.climate_zone}</span>
        <span>温度：{tile.temperature.toFixed(1)}°C</span>
        <span>湿度：{(tile.humidity * 100).toFixed(0)}%</span>
        <span>资源：{tile.resources.toFixed(0)}</span>
      </div>
      <div className="habitat-table">
        <h4>物种占据</h4>
        {habitats.length === 0 ? (
          <p>暂无物种记录。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>谱系</th>
                <th>种群</th>
                <th>适宜度</th>
              </tr>
            </thead>
            <tbody>
              {habitats.map((entry) => (
                <tr
                  key={`${entry.lineage_code}-${entry.tile_id}`}
                  className={selectedSpecies === entry.lineage_code ? "selected-row" : ""}
                >
                  <td>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onSelectSpecies(entry.lineage_code)}
                    >
                      {entry.lineage_code}
                    </button>
                  </td>
                  <td>{entry.population}</td>
                  <td>{entry.suitability.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
