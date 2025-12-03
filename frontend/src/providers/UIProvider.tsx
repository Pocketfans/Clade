/**
 * UIProvider - UI 状态管理
 * 
 * 职责：
 * - 视图模式 (viewMode)
 * - 覆盖层状态 (overlay)
 * - 抽屉状态 (drawerMode)
 * - 选择状态 (selectedTileId, selectedSpeciesId)
 * - 模态窗状态 (settings, pressure, createSpecies 等)
 * - 提示与成就通知
 * - 批量进度
 */

import {
  createContext,
  useContext,
  useCallback,
  useState,
  type ReactNode,
} from "react";
import type { ViewMode } from "../components/MapViewSelector";
import type { OverlayView, DrawerMode, UIState, UIActions } from "./types";

// ============ 初始状态 ============
const initialModals: UIState["modals"] = {
  settings: false,
  gameSettings: false,
  pressure: false,
  createSpecies: false,
  trends: false,
  ledger: false,
  turnSummary: false,
  mapHistory: false,
  logPanel: false,
  aiAssistant: false,
  aiTimeline: false,
  achievements: false,
  hints: false,
  hybridization: false,
  divinePowers: false,
};

// ============ Context ============
interface UIContextValue extends UIState, UIActions {
  hasActiveModal: boolean;
}

const UIContext = createContext<UIContextValue | null>(null);

// ============ Provider ============
interface UIProviderProps {
  children: ReactNode;
}

export function UIProvider({ children }: UIProviderProps) {
  // ============ 状态 ============
  const [viewMode, setViewModeRaw] = useState<ViewMode>("terrain");
  const [overlay, setOverlay] = useState<OverlayView>("none");
  const [drawerMode, setDrawerMode] = useState<DrawerMode>("none");
  const [selectedTileId, setSelectedTileId] = useState<number | null>(null);
  const [selectedSpeciesId, setSelectedSpeciesId] = useState<string | null>(null);
  const [showOutliner, setShowOutliner] = useState(true);
  const [modals, setModals] = useState<UIState["modals"]>(initialModals);
  const [settingsInitialView, setSettingsInitialView] = useState<"menu" | "load">("menu");
  const [hintsInfo, setHintsInfo] = useState<UIState["hintsInfo"]>({
    count: 0,
    criticalCount: 0,
    highCount: 0,
  });
  const [pendingAchievement, setPendingAchievement] = useState<UIState["pendingAchievement"]>(null);
  const [batchProgress, setBatchProgress] = useState<UIState["batchProgress"]>(null);

  // ============ 派生状态 ============
  const hasActiveModal =
    Object.values(modals).some(Boolean) ||
    overlay !== "none" ||
    batchProgress !== null;

  // ============ Actions ============
  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeRaw(mode);
  }, []);

  const changeViewMode = useCallback(
    (mode: ViewMode, _options?: { preserveCamera?: boolean }) => {
      // preserveCamera 逻辑需要在调用方处理（访问 mapPanelRef）
      setViewModeRaw(mode);
    },
    []
  );

  const selectTile = useCallback((id: number | null) => {
    setSelectedTileId(id);
    if (id !== null) {
      setDrawerMode("tile");
    }
  }, []);

  const selectSpecies = useCallback((id: string | null) => {
    setSelectedSpeciesId(id);
  }, []);

  const toggleOutliner = useCallback(() => {
    setShowOutliner((prev) => !prev);
  }, []);

  const openModal = useCallback((modal: keyof UIState["modals"]) => {
    setModals((prev) => ({ ...prev, [modal]: true }));
  }, []);

  const closeModal = useCallback((modal: keyof UIState["modals"]) => {
    setModals((prev) => ({ ...prev, [modal]: false }));
  }, []);

  const toggleModal = useCallback((modal: keyof UIState["modals"]) => {
    setModals((prev) => ({ ...prev, [modal]: !prev[modal] }));
  }, []);

  const closeAllModals = useCallback(() => {
    setModals(initialModals);
    setOverlay("none");
    setDrawerMode("none");
  }, []);

  // ============ Context Value ============
  const value: UIContextValue = {
    // State
    viewMode,
    overlay,
    drawerMode,
    selectedTileId,
    selectedSpeciesId,
    showOutliner,
    modals,
    settingsInitialView,
    hintsInfo,
    pendingAchievement,
    batchProgress,
    // Derived
    hasActiveModal,
    // Actions
    setViewMode,
    changeViewMode,
    setOverlay,
    setDrawerMode,
    selectTile,
    selectSpecies,
    toggleOutliner,
    openModal,
    closeModal,
    toggleModal,
    closeAllModals,
    setSettingsInitialView,
    setHintsInfo,
    setPendingAchievement,
    setBatchProgress,
  };

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

// ============ Hook ============
export function useUI(): UIContextValue {
  const context = useContext(UIContext);
  if (!context) {
    throw new Error("useUI must be used within UIProvider");
  }
  return context;
}

// 导出 Context 供高级用法
export { UIContext };




