/**
 * ModalsLayer - 模态窗统一渲染层
 * 
 * 职责：
 * - 集中管理所有模态窗的渲染
 * - 错误提示
 * - 加载状态
 * - 覆盖层（族谱、年鉴、生态位、食物网）
 */

import { lazy, Suspense } from "react";
import type {
  TurnReport,
  LineageTree,
  SpeciesSnapshot,
  UIConfig,
  PressureTemplate,
  PressureDraft,
} from "@/services/api.types";
import type { OverlayView } from "@/providers/types";

// 懒加载模态窗组件
const SettingsDrawer = lazy(() => import("./SettingsDrawer").then(m => ({ default: m.SettingsDrawer })));
const GameSettingsMenu = lazy(() => import("./GameSettingsMenu").then(m => ({ default: m.GameSettingsMenu })));
const PressureModal = lazy(() => import("./PressureModal").then(m => ({ default: m.PressureModal })));
const EnhancedCreateSpeciesModal = lazy(() => import("./EnhancedCreateSpeciesModal").then(m => ({ default: m.EnhancedCreateSpeciesModal })));
const GlobalTrendsPanel = lazy(() => import("./GlobalTrendsPanel").then(m => ({ default: m.GlobalTrendsPanel })));
const SpeciesLedger = lazy(() => import("./SpeciesLedger").then(m => ({ default: m.SpeciesLedger })));
const TurnSummaryModal = lazy(() => import("./TurnSummaryModal").then(m => ({ default: m.TurnSummaryModal })));
const MapHistoryView = lazy(() => import("./MapHistoryView").then(m => ({ default: m.MapHistoryView })));
const LogPanel = lazy(() => import("./LogPanel").then(m => ({ default: m.LogPanel })));
const AIAssistantPanel = lazy(() => import("./AIAssistantPanel").then(m => ({ default: m.AIAssistantPanel })));
const AIEnhancedTimeline = lazy(() => import("./AIEnhancedTimeline").then(m => ({ default: m.AIEnhancedTimeline })));
const AchievementsPanel = lazy(() => import("./AchievementsPanel").then(m => ({ default: m.AchievementsPanel })));
const HybridizationPanel = lazy(() => import("./HybridizationPanel").then(m => ({ default: m.HybridizationPanel })));
const DivinePowersPanel = lazy(() => import("./DivinePowersPanel").then(m => ({ default: m.DivinePowersPanel })));
const GenealogyView = lazy(() => import("./GenealogyView").then(m => ({ default: m.GenealogyView })));
const NicheCompareView = lazy(() => import("./NicheCompareView").then(m => ({ default: m.NicheCompareView })));
const FoodWebGraph = lazy(() => import("./FoodWebGraph").then(m => ({ default: m.FoodWebGraph })));
const FullscreenOverlay = lazy(() => import("./FullscreenOverlay").then(m => ({ default: m.FullscreenOverlay })));
const TurnProgressOverlay = lazy(() => import("./TurnProgressOverlay").then(m => ({ default: m.TurnProgressOverlay })));
const GameHintsPanel = lazy(() => import("./GameHintsPanel").then(m => ({ default: m.GameHintsPanel })));
const AchievementNotification = lazy(() => import("./GameHintsPanel").then(m => ({ default: m.AchievementNotification })));

// 加载占位符
function ModalFallback() {
  return (
    <div style={{
      position: "fixed",
      inset: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "rgba(0,0,0,0.5)",
      zIndex: 1000,
    }}>
      <div className="spinner" style={{ width: 40, height: 40 }} />
    </div>
  );
}

// 模态窗状态类型
interface ModalState {
  settings: boolean;
  gameSettings: boolean;
  pressure: boolean;
  createSpecies: boolean;
  trends: boolean;
  ledger: boolean;
  turnSummary: boolean;
  mapHistory: boolean;
  logPanel: boolean;
  aiAssistant: boolean;
  aiTimeline: boolean;
  achievements: boolean;
  hints: boolean;
  hybridization: boolean;
  divinePowers: boolean;
}

interface ModalsLayerProps {
  // 模态窗状态
  modals: ModalState;
  overlay: OverlayView;
  loading: boolean;
  error: string | null;
  batchProgress: { current: number; total: number; message: string } | null;
  
  // 数据
  reports: TurnReport[];
  speciesList: SpeciesSnapshot[];
  lineageTree: LineageTree | null;
  lineageLoading: boolean;
  lineageError: string | null;
  latestReport: TurnReport | null;
  uiConfig: UIConfig;
  pressureTemplates: PressureTemplate[];
  currentSaveName: string;
  selectedSpeciesId: string | null;
  settingsInitialView: "menu" | "load";
  pendingAchievement: { name: string; icon: string; description: string; rarity: string } | null;
  
  // 回调
  onCloseOverlay: () => void;
  onCloseModal: (modal: keyof ModalState) => void;
  onClearError: () => void;
  onRetryLineage: () => void;
  onSelectSpecies: (id: string) => void;
  onExecuteTurn: (drafts: PressureDraft[]) => void;
  onQueueAdd: (drafts: PressureDraft[], rounds: number) => void;
  onSaveConfig: (config: UIConfig) => Promise<void>;
  onRefreshMap: () => void;
  onRefreshQueue: () => void;
  onRefreshSpecies: () => void;
  onBackToMenu: () => void;
  onLoadGame: (saveName: string) => void;
  onDismissAchievement: () => void;
}

export function ModalsLayer({
  modals,
  overlay,
  loading,
  error,
  batchProgress,
  reports,
  speciesList,
  lineageTree,
  lineageLoading,
  lineageError,
  latestReport,
  uiConfig,
  pressureTemplates,
  currentSaveName,
  selectedSpeciesId,
  settingsInitialView,
  pendingAchievement,
  onCloseOverlay,
  onCloseModal,
  onClearError,
  onRetryLineage,
  onSelectSpecies,
  onExecuteTurn,
  onQueueAdd,
  onSaveConfig,
  onRefreshMap,
  onRefreshQueue,
  onRefreshSpecies,
  onBackToMenu,
  onLoadGame,
  onDismissAchievement,
}: ModalsLayerProps) {
  const previousReport = reports.length > 1 ? reports[reports.length - 2] : null;

  return (
    <Suspense fallback={<ModalFallback />}>
      {/* 错误提示 */}
      {error && (
        <div
          style={{
            position: "fixed",
            top: 80,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#ff4444",
            color: "white",
            padding: "12px 24px",
            borderRadius: "8px",
            zIndex: 9999,
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          }}
        >
          {error}
          <button
            onClick={onClearError}
            style={{ marginLeft: 12, background: "none", border: "none", color: "white", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      )}

      {/* 加载状态（推演中） */}
      {loading && !modals.turnSummary && (
        <TurnProgressOverlay
          message={
            batchProgress
              ? `🎲 自动演化 ${batchProgress.current}/${batchProgress.total} - ${batchProgress.message}`
              : "AI 正在分析生态系统变化..."
          }
          showDetails={!batchProgress}
        />
      )}

      {/* 回合总结 */}
      {modals.turnSummary && latestReport && (
        <TurnSummaryModal
          report={latestReport}
          previousReport={previousReport}
          onClose={() => onCloseModal("turnSummary")}
        />
      )}

      {/* 日志面板 */}
      {modals.logPanel && <LogPanel onClose={() => onCloseModal("logPanel")} />}

      {/* AI 助手 */}
      {modals.aiAssistant && <AIAssistantPanel onClose={() => onCloseModal("aiAssistant")} />}

      {/* AI 增强年鉴 */}
      {modals.aiTimeline && <AIEnhancedTimeline reports={reports} onClose={() => onCloseModal("aiTimeline")} />}

      {/* 成就面板 */}
      {modals.achievements && <AchievementsPanel onClose={() => onCloseModal("achievements")} />}

      {/* 杂交面板 */}
      {modals.hybridization && (
        <HybridizationPanel
          onClose={() => onCloseModal("hybridization")}
          onSuccess={() => {
            onRefreshSpecies();
            onRefreshMap();
          }}
        />
      )}

      {/* 神力进阶 */}
      {modals.divinePowers && <DivinePowersPanel onClose={() => onCloseModal("divinePowers")} />}

      {/* 地图历史 */}
      {modals.mapHistory && <MapHistoryView onClose={() => onCloseModal("mapHistory")} />}

      {/* 成就通知 */}
      {pendingAchievement && (
        <AchievementNotification achievement={pendingAchievement} onClose={onDismissAchievement} />
      )}

      {/* 覆盖层：族谱 */}
      {overlay === "genealogy" && (
        <GenealogyView
          tree={lineageTree}
          loading={lineageLoading}
          error={lineageError}
          onRetry={onRetryLineage}
          onClose={onCloseOverlay}
        />
      )}

      {/* 覆盖层：年鉴 */}
      {overlay === "chronicle" && <AIEnhancedTimeline reports={reports} onClose={onCloseOverlay} />}

      {/* 覆盖层：生态位对比 */}
      {overlay === "niche" && (
        <FullscreenOverlay title="生态位对比" onClose={onCloseOverlay}>
          <NicheCompareView onClose={onCloseOverlay} />
        </FullscreenOverlay>
      )}

      {/* 覆盖层：食物网 */}
      {overlay === "foodweb" && (
        <FoodWebGraph
          speciesList={speciesList}
          onClose={onCloseOverlay}
          onSelectSpecies={(id) => {
            onSelectSpecies(id);
            onCloseOverlay();
          }}
        />
      )}

      {/* 设置抽屉 */}
      {modals.settings && (
        <SettingsDrawer config={uiConfig} onClose={() => onCloseModal("settings")} onSave={onSaveConfig} />
      )}

      {/* 压力模态窗 */}
      {modals.pressure && (
        <PressureModal
          pressures={[]}
          templates={pressureTemplates}
          onChange={() => {}}
          onQueue={onQueueAdd}
          onExecute={onExecuteTurn}
          onBatchExecute={() => {}}
          onClose={() => onCloseModal("pressure")}
        />
      )}

      {/* 创建物种 */}
      {modals.createSpecies && (
        <EnhancedCreateSpeciesModal
          onClose={() => onCloseModal("createSpecies")}
          onSuccess={() => {
            onRefreshMap();
            onRefreshQueue();
          }}
        />
      )}

      {/* 游戏设置菜单 */}
      {modals.gameSettings && (
        <GameSettingsMenu
          currentSaveName={currentSaveName}
          onClose={() => onCloseModal("gameSettings")}
          initialView={settingsInitialView}
          onBackToMenu={onBackToMenu}
          onSaveGame={async () => {}}
          onLoadGame={onLoadGame}
          onOpenAISettings={() => {
            onCloseModal("gameSettings");
          }}
        />
      )}

      {/* 全局趋势 */}
      {modals.trends && <GlobalTrendsPanel reports={reports} onClose={() => onCloseModal("trends")} />}

      {/* 物种图鉴 */}
      {modals.ledger && (
        <SpeciesLedger
          speciesList={speciesList}
          onClose={() => onCloseModal("ledger")}
          selectedSpeciesId={selectedSpeciesId}
          onSelectSpecies={onSelectSpecies}
        />
      )}

      {/* 智能提示 */}
      {modals.hints && (
        <GameHintsPanel
          onSelectSpecies={onSelectSpecies}
          refreshTrigger={0}
          onClose={() => onCloseModal("hints")}
        />
      )}
    </Suspense>
  );
}

