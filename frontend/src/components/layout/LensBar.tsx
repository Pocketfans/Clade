import { ViewMode } from "../MapViewSelector";

interface Props {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  onOpenPressure: () => void;
  onToggleGenealogy: () => void;
  onToggleHistory: () => void;
  onToggleNiche: () => void;
  onToggleFoodWeb: () => void;
}

export function LensBar({ 
  currentMode, 
  onModeChange, 
  onOpenPressure,
  onToggleGenealogy,
  onToggleHistory,
  onToggleNiche,
  onToggleFoodWeb
}: Props) {
  const lenses: Array<{ id: ViewMode; label: string; icon: string }> = [
    { id: "terrain", label: "实景", icon: "🌍" },
    { id: "terrain_type", label: "地形", icon: "🏔️" },
    { id: "elevation", label: "海拔", icon: "📏" },
    { id: "climate", label: "气候", icon: "🌡️" },
    { id: "biodiversity", label: "生态", icon: "🌿" },
    { id: "suitability", label: "适宜", icon: "🎯" },
  ];

  const tools = [
    { id: "pressure", label: "环境压力", icon: "⚡", action: onOpenPressure, color: "#ffa726" },
    { id: "genealogy", label: "族谱", icon: "🧬", action: onToggleGenealogy, color: "#ab47bc" },
    { id: "niche", label: "生态位", icon: "📊", action: onToggleNiche, color: "#29b6f6" },
    { id: "foodweb", label: "食物网", icon: "🕸️", action: onToggleFoodWeb, color: "#ef5350" },
    { id: "history", label: "年鉴", icon: "📜", action: onToggleHistory, color: "#bdbdbd" },
  ];

  return (
    <div style={{
      position: "fixed",
      bottom: "24px",
      left: "50%",
      transform: "translateX(-50%)",
      display: "flex",
      gap: "16px",
      zIndex: 1000,
      alignItems: "flex-end"
    }}>
      {/* Map Lenses Group */}
      <div style={{
        background: "rgba(15, 20, 35, 0.85)",
        backdropFilter: "blur(12px)",
        padding: "6px",
        borderRadius: "999px",
        border: "1px solid rgba(255,255,255,0.1)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
        display: "flex",
        gap: "4px"
      }}>
        {lenses.map(lens => {
          const isActive = currentMode === lens.id;
          return (
            <button
              key={lens.id}
              onClick={() => onModeChange(lens.id)}
              title={`切换至${lens.label}视图`}
              style={{
                background: isActive ? "rgba(59, 130, 246, 0.9)" : "transparent",
                border: "none",
                borderRadius: "999px",
                padding: "8px 16px",
                color: isActive ? "#fff" : "rgba(255,255,255,0.7)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "0.9rem",
                fontWeight: 500,
                transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: isActive ? "0 4px 12px rgba(59, 130, 246, 0.4)" : "none",
              }}
              onMouseEnter={e => {
                if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.1)";
              }}
              onMouseLeave={e => {
                if (!isActive) e.currentTarget.style.background = "transparent";
              }}
            >
              <span style={{ fontSize: "1.1rem" }}>{lens.icon}</span>
              <span>{lens.label}</span>
            </button>
          );
        })}
      </div>

      {/* Functional Tools Group */}
      <div style={{
        background: "rgba(15, 20, 35, 0.85)",
        backdropFilter: "blur(12px)",
        padding: "6px",
        borderRadius: "16px",
        border: "1px solid rgba(255,255,255,0.1)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
        display: "flex",
        gap: "4px"
      }}>
        {tools.map(tool => (
          <button
            key={tool.id}
            onClick={tool.action}
            title={tool.label}
            style={{
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: "12px",
              width: "44px",
              height: "44px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              transition: "all 0.2s",
              position: "relative",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = "rgba(255,255,255,0.1)";
              e.currentTarget.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            <span style={{ fontSize: "1.4rem", filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.3))" }}>
              {tool.icon}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
