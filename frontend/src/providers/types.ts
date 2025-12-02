/**
 * Provider 共享类型定义
 * 用于 Context 之间的状态共享
 */

import type { StartPayload } from "@/components/MainMenu";
import type {
  MapOverview,
  TurnReport,
  LineageTree,
  SpeciesSnapshot,
  UIConfig,
  PressureTemplate,
  ActionQueueStatus,
} from "@/services/api.types";
import type { ViewMode } from "@/components/MapViewSelector";

// ============ 会话状态 ============
export type Scene = "menu" | "game" | "loading";

export interface SessionState {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
  backendSessionId: string;
}

export interface SessionActions {
  startGame: (payload: StartPayload) => void;
  backToMenu: () => void;
  setScene: (scene: Scene) => void;
  setBackendSessionId: (id: string) => void;
  resetSession: () => void;
}

// ============ 游戏数据状态 ============
export interface GameDataState {
  // 地图与环境
  mapData: MapOverview | null;
  // 回合报告
  reports: TurnReport[];
  currentTurnIndex: number;
  // 物种
  speciesList: SpeciesSnapshot[];
  freshSpeciesList: SpeciesSnapshot[];
  // 族谱
  lineageTree: LineageTree | null;
  lineageLoading: boolean;
  lineageError: string | null;
  // 配置
  uiConfig: UIConfig;
  pressureTemplates: PressureTemplate[];
  // 队列
  queueStatus: ActionQueueStatus | null;
  // 加载状态
  loading: boolean;
  error: string | null;
  // 刷新触发器
  speciesRefreshTrigger: number;
}

export interface GameDataActions {
  // 地图操作
  refreshMap: () => Promise<void>;
  setMapData: (data: MapOverview | null) => void;
  // 报告操作
  addReports: (reports: TurnReport[]) => void;
  setReports: (reports: TurnReport[]) => void;
  setCurrentTurnIndex: (index: number) => void;
  // 物种操作
  refreshSpeciesList: () => Promise<void>;
  setFreshSpeciesList: (list: SpeciesSnapshot[]) => void;
  triggerSpeciesRefresh: () => void;
  // 族谱操作
  loadLineageTree: () => Promise<void>;
  invalidateLineage: () => void;
  setLineageTree: (tree: LineageTree | null) => void;
  // 配置操作
  setUIConfig: (config: UIConfig) => void;
  updateUIConfig: (config: UIConfig) => Promise<void>;
  // 队列操作
  refreshQueue: () => Promise<void>;
  // 错误处理
  setError: (error: string | null) => void;
  setLoading: (loading: boolean) => void;
  clearError: () => void;
}

// ============ UI 状态 ============
export type OverlayView = "none" | "genealogy" | "chronicle" | "niche" | "foodweb";
export type DrawerMode = "none" | "tile";

export interface UIState {
  // 视图模式
  viewMode: ViewMode;
  // 覆盖层
  overlay: OverlayView;
  // 抽屉
  drawerMode: DrawerMode;
  // 选择状态
  selectedTileId: number | null;
  selectedSpeciesId: string | null;
  // 面板显示状态
  showOutliner: boolean;
  // 模态窗显示状态
  modals: {
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
  };
  // 设置初始视图
  settingsInitialView: "menu" | "load";
  // 提示信息
  hintsInfo: { count: number; criticalCount: number; highCount: number };
  // 成就通知
  pendingAchievement: { name: string; icon: string; description: string; rarity: string } | null;
  // 批量执行进度
  batchProgress: { current: number; total: number; message: string } | null;
}

export interface UIActions {
  // 视图模式
  setViewMode: (mode: ViewMode) => void;
  changeViewMode: (mode: ViewMode, options?: { preserveCamera?: boolean }) => void;
  // 覆盖层
  setOverlay: (view: OverlayView) => void;
  // 抽屉
  setDrawerMode: (mode: DrawerMode) => void;
  // 选择
  selectTile: (id: number | null) => void;
  selectSpecies: (id: string | null) => void;
  // 面板
  toggleOutliner: () => void;
  // 模态窗
  openModal: (modal: keyof UIState["modals"]) => void;
  closeModal: (modal: keyof UIState["modals"]) => void;
  toggleModal: (modal: keyof UIState["modals"]) => void;
  closeAllModals: () => void;
  // 设置
  setSettingsInitialView: (view: "menu" | "load") => void;
  // 提示与成就
  setHintsInfo: (info: UIState["hintsInfo"]) => void;
  setPendingAchievement: (achievement: UIState["pendingAchievement"]) => void;
  // 批量进度
  setBatchProgress: (progress: UIState["batchProgress"]) => void;
}

// ============ 合并的完整状态 ============
export interface AppState extends SessionState, GameDataState, UIState {}
export interface AppActions extends SessionActions, GameDataActions, UIActions {}

