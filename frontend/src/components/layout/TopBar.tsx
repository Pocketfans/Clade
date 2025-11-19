import { ActionQueueStatus } from "../../services/api.types";

interface Props {
  turnIndex: number;
  speciesCount: number;
  queueStatus: ActionQueueStatus | null;
  saveName: string;
  scenarioInfo?: string;
  onOpenSettings: () => void;
  onSaveGame: () => void;
}

export function TopBar({ 
  turnIndex, 
  speciesCount, 
  queueStatus, 
  saveName,
  scenarioInfo,
  onOpenSettings,
  onSaveGame
}: Props) {
  return (
    <div style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      {/* Left: Time and Status */}
      <div className="resource-group">
        <div className="resource-item">
          <span className="resource-label">回合 (Turn)</span>
          <span className="resource-value">{turnIndex}</span>
        </div>
        <div className="resource-item">
          <span className="resource-label">物种 (Species)</span>
          <span className="resource-value">{speciesCount}</span>
        </div>
        <div className="resource-item">
          <span className="resource-label">待办队列 (Queue)</span>
          <span className="resource-value">{queueStatus?.queued_rounds ?? 0}</span>
        </div>
      </div>

      {/* Center: Game Info (Scenario) */}
      <div style={{ textAlign: "center", opacity: 0.8 }}>
        <div style={{ fontSize: "1rem", fontWeight: 600, letterSpacing: "1px" }}>
          {scenarioInfo || "EVO SANDBOX"}
        </div>
        <div style={{ fontSize: "0.75rem", color: "#aaa" }}>{saveName}</div>
      </div>

      {/* Right: System Actions */}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button onClick={onSaveGame} className="btn-icon" title="保存游戏">💾</button>
        <button onClick={onOpenSettings} className="btn-icon" title="系统设置">⚙️</button>
      </div>
    </div>
  );
}


