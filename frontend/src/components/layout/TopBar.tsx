import { Zap, Save, FolderOpen, Settings } from "lucide-react";
import { ActionQueueStatus } from "../../services/api.types";
import { EnergyBar } from "../EnergyBar";

interface Props {
  turnIndex: number;
  speciesCount: number;
  queueStatus: ActionQueueStatus | null;
  saveName: string;
  scenarioInfo?: string;
  onOpenSettings: () => void;
  onSaveGame: () => void;
  onLoadGame: () => void;
  onOpenLedger: () => void;
  onOpenPressure: () => void;
  onOpenEnergyHistory?: () => void;
}

export function TopBar({ 
  turnIndex, 
  speciesCount, 
  queueStatus, 
  saveName,
  scenarioInfo,
  onOpenSettings,
  onSaveGame,
  onLoadGame,
  onOpenLedger,
  onOpenPressure,
  onOpenEnergyHistory
}: Props) {
  const normalizedTurn = Math.max(turnIndex, 0);
  const displayTurn = normalizedTurn + 1;
  // Calculate time: Start 2800 MYA, 0.5 MY per turn
  const yearsAgo = 2800 - (normalizedTurn * 0.5);
  const timeText = yearsAgo >= 100 
    ? `${(yearsAgo / 100).toFixed(1)} 亿年前` 
    : `${(yearsAgo * 100).toFixed(0)} 万年前`;

  return (
    <div className="topbar-container">
      {/* Left: Status */}
      <div className="resource-group">
        <div className="resource-item clickable" onClick={onOpenLedger} title="查看物种统计">
          <span className="resource-label">🧬 物种</span>
          <span className="resource-value">{speciesCount}</span>
        </div>
        <div className="resource-item">
          <span className="resource-label">📋 队列</span>
          <span className="resource-value">{queueStatus?.queued_rounds ?? 0}</span>
        </div>
        <EnergyBar onOpenHistory={onOpenEnergyHistory} />
      </div>

      {/* Center: Time Display & Next Turn Button */}
      <div className="topbar-center">
        <div className="time-display">
          <span className="turn-number">第 {displayTurn} 回合</span>
          <span className="time-separator">·</span>
          <span className="time-era">{timeText}</span>
        </div>
        
        {/* Prominent Next Turn / Pressure Button */}
        <button onClick={onOpenPressure} className="btn-pressure-evolution">
          <span className="btn-pressure-icon">
            <Zap size={18} fill="currentColor" />
          </span>
          <span className="btn-pressure-text">压力策划</span>
          <div className="btn-pressure-shine" />
          <div className="btn-pressure-glow" />
        </button>
      </div>

      {/* Right: System Actions */}
      <div className="topbar-actions">
        <button onClick={onSaveGame} className="btn-icon-evo" title="保存游戏">
          <Save size={18} />
        </button>
        <button onClick={onLoadGame} className="btn-icon-evo" title="读取存档">
          <FolderOpen size={18} />
        </button>
        <button onClick={onOpenSettings} className="btn-icon-evo" title="系统设置">
          <Settings size={18} />
        </button>
      </div>
    </div>
  );
}


