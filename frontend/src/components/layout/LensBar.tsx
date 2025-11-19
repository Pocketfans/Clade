import { ViewMode } from "../MapViewSelector";

interface Props {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  onOpenPressure: () => void;
  onToggleGenealogy: () => void;
  onToggleHistory: () => void;
  onToggleNiche: () => void;
}

export function LensBar({ 
  currentMode, 
  onModeChange, 
  onOpenPressure,
  onToggleGenealogy,
  onToggleHistory,
  onToggleNiche
}: Props) {
  const lenses: Array<{ id: ViewMode; label: string; icon: string }> = [
    { id: "terrain", label: "实景", icon: "🌍" },
    { id: "terrain_type", label: "地形", icon: "🏔️" },
    { id: "elevation", label: "海拔", icon: "📏" },
    { id: "climate", label: "气候", icon: "🌡️" },
    { id: "biodiversity", label: "生态", icon: "🌿" },
  ];

  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {/* Map Lenses Group */}
      <div style={{ display: "flex", gap: "0.75rem" }}>
        {lenses.map(lens => (
          <button
            key={lens.id}
            className={`lens-button ${currentMode === lens.id ? "active" : ""}`}
            onClick={() => onModeChange(lens.id)}
            title={`切换至${lens.label}视图`}
          >
            <span>{lens.icon}</span>
            <span>{lens.label}</span>
          </button>
        ))}
      </div>

      {/* Functional Lenses Group */}
      <div className="lens-group-functional">
        <button className="lens-button functional" onClick={onOpenPressure}>
          <span style={{ color: "#ffa726" }}>⚡</span>
          <span style={{ color: "#ffcc80" }}>环境压力</span>
        </button>
        <button className="lens-button functional" onClick={onToggleGenealogy}>
          <span style={{ color: "#ab47bc" }}>🧬</span>
          <span style={{ color: "#e1bee7" }}>族谱</span>
        </button>
        <button className="lens-button functional" onClick={onToggleNiche}>
          <span style={{ color: "#29b6f6" }}>📊</span>
          <span style={{ color: "#b3e5fc" }}>生态位</span>
        </button>
        <button className="lens-button functional" onClick={onToggleHistory}>
          <span style={{ color: "#bdbdbd" }}>📜</span>
          <span style={{ color: "#eeeeee" }}>年鉴</span>
        </button>
      </div>
    </div>
  );
}
