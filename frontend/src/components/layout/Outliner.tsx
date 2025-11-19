import { SpeciesSnapshot } from "../../services/api.types";

interface Props {
  speciesList: SpeciesSnapshot[];
  selectedSpeciesId: string | null;
  onSelectSpecies: (id: string) => void;
}

export function Outliner({ speciesList, selectedSpeciesId, onSelectSpecies }: Props) {
  // Sort by population desc
  const sorted = [...speciesList].sort((a, b) => b.population - a.population);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="outliner-header">
        物种概览 ({sorted.length})
      </div>
      <div className="outliner-list">
        {sorted.map(s => (
          <div 
            key={s.lineage_code}
            className={`outliner-item ${selectedSpeciesId === s.lineage_code ? "selected" : ""}`}
            onClick={() => onSelectSpecies(s.lineage_code)}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: s.status === 'extinct' ? '#666' : '#fff' }}>
                {s.common_name}
                {s.status === 'extinct' && <span style={{marginLeft: '4px', fontSize: '0.7rem', color: '#ff4444'}}>†</span>}
              </div>
              <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>{s.latin_name}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontWeight: "bold", fontSize: "0.9rem" }}>
                {s.population >= 1000000 
                  ? `${(s.population / 1000000).toFixed(1)}M` 
                  : `${(s.population / 1000).toFixed(1)}k`}
              </div>
              <div style={{ fontSize: "0.7rem", color: s.death_rate > 0.1 ? "#ff5555" : "#aaa" }}>
                {s.tier || "-"}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


