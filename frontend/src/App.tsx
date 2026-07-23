/**
 * App.tsx - 重构版应用入口
 * 
 * 职责：
 * - Provider 组装 (Session → UI → Game)
 * - 场景路由 (menu / loading / game)
 * - 快捷键处理
 * 
 * 架构：
 * App
 * ├── SessionProvider (会话状态)
 * │   └── UIProvider (UI状态)
 * │       └── GameProvider (游戏数据)
 * │           └── AppContent (场景切换)
 */

import { useCallback, useEffect, useRef, lazy, Suspense, useMemo } from "react";
import "./layout.css";

// Providers
import { SessionProvider, useSession } from "./providers/SessionProvider";
import { GameProvider, useGame } from "./providers/GameProvider";
import { UIProvider, useUI } from "./providers/UIProvider";

// Layout 组件
import { GameLayout } from "./components/layout/GameLayout";
import { TopBar } from "./components/layout/TopBar";
import { LensBar } from "./components/layout/LensBar";
import { ContextDrawer } from "./components/layout/ContextDrawer";

// 场景组件
import { MainMenu, type StartPayload } from "./components/MainMenu";

// 面板组件
import { CanvasMapPanel, type CanvasMapPanelHandle, type CameraState } from "./components/CanvasMapPanel";
import { SpeciesPanel } from "./components/SpeciesPanel";
import { TileDetailPanel } from "./components/TileDetailPanel";
import { MapLegend } from "./components/MapLegend";
import { MapModeToast } from "./components/MapModeToast";
import { AmbientEffects } from "./components/AmbientEffects";
import { SettingsDrawer } from "./components/SettingsDrawer";

// 懒加载模态窗组件
const ModalsLayer = lazy(() => import("./components/ModalsLayer").then(m => ({ default: m.ModalsLayer })));

// API（使用模块化 API）
import {
  http,
  runTurn,
  saveGame,
  fetchHistory,
  fetchGameState,
  addQueue,
} from "@/services/api";
import { dispatchEnergyChanged } from "@/components/EnergyBar";
import type { PressureDraft, TurnReport } from "@/services/api.types";

// ============ 加载场景 ============
function LoadingScene() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(ellipse at center, rgba(8, 15, 12, 0.97), rgba(3, 7, 5, 0.99))",
        color: "#f0f4e8",
        gap: "1rem",
      }}
    >
      <div className="spinner" style={{ width: 40, height: 40 }} />
      <p style={{ fontSize: "1.1rem", opacity: 0.8 }}>正在验证游戏状态...</p>
    </div>
  );
}

// ============ 菜单场景 ============
function MenuScene() {
  const { startGame } = useSession();
  const { uiConfig, updateUIConfig } = useGame();
  const { modals, openModal, closeModal } = useUI();

  return (
    <>
      <MainMenu
        onStart={startGame}
        onOpenSettings={() => openModal("settings")}
        uiConfig={uiConfig}
      />
      {modals.settings && (
        <SettingsDrawer
          config={uiConfig}
          onClose={() => closeModal("settings")}
          onSave={updateUIConfig}
        />
      )}
    </>
  );
}

// ============ 游戏场景 ============
function GameScene() {
  const { sessionInfo, currentSaveName, setBackendSessionId } = useSession();
  const {
    mapData,
    reports,
    speciesList,
    lineageTree,
    lineageLoading,
    lineageError,
    uiConfig,
    pressureTemplates,
    queueStatus,
    latestReport,
    previousPopulations,
    speciesRefreshTrigger,
    currentTurnIndex,
    refreshMap,
    refreshSpeciesList,
    refreshQueue,
    addReports,
    setCurrentTurnIndex,
    setReports,
    loadLineageTree,
    invalidateLineage,
    updateUIConfig,
    setLoading,
    setError,
    loading,
    error,
  } = useGame();
  const {
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
    hasActiveModal,
    setViewMode,
    setOverlay,
    setDrawerMode,
    selectTile,
    selectSpecies,
    toggleOutliner,
    openModal,
    closeModal,
    setSettingsInitialView,
    setHintsInfo,
    setPendingAchievement,
    setBatchProgress,
    closeAllModals,
  } = useUI();

  // Refs
  const mapPanelRef = useRef<CanvasMapPanelHandle | null>(null);

  // 派生数据
  const extinctSpeciesSet = useMemo(() => {
    const set = new Set<string>();
    for (const s of speciesList) {
      if (s.status === "extinct") set.add(s.lineage_code);
    }
    return set;
  }, [speciesList]);

  const liveHabitats = useMemo(() => {
    if (!mapData?.habitats) return [];
    return mapData.habitats.filter(
      (h) => h.population > 0 && !extinctSpeciesSet.has(h.lineage_code)
    );
  }, [mapData?.habitats, extinctSpeciesSet]);

  const mapForDisplay = useMemo(() => {
    if (!mapData) return null;
    return { ...mapData, habitats: liveHabitats };
  }, [mapData, liveHabitats]);

  const selectedTile = mapData?.tiles.find((t) => t.id === selectedTileId) ?? null;
  const selectedTileHabitats = liveHabitats.filter((h) => h.tile_id === selectedTileId);

  // 相机控制
  const captureCamera = useCallback((): CameraState | null => {
    return mapPanelRef.current?.getCameraState() ?? null;
  }, []);

  const restoreCamera = useCallback((snapshot: CameraState | null) => {
    if (!snapshot || !mapPanelRef.current) return;
    requestAnimationFrame(() => mapPanelRef.current?.setCameraState(snapshot));
  }, []);

  // 视图模式切换（保持相机位置）
  const handleViewModeChange = useCallback(
    (mode: typeof viewMode) => {
      if (mode === viewMode) return;
      const snapshot = captureCamera();
      setViewMode(mode);
      restoreCamera(snapshot);
    },
    [viewMode, captureCamera, setViewMode, restoreCamera]
  );

  // 选择处理
  const handleTileSelect = useCallback(
    (tile: { id: number }) => {
      selectTile(tile.id);
    },
    [selectTile]
  );

  const handleSpeciesSelect = useCallback(
    (id: string) => {
      selectSpecies(id);
    },
    [selectSpecies]
  );

  // 执行回合
  const executeTurn = useCallback(
    async (drafts: PressureDraft[], rounds = 1) => {
      setLoading(true);
      setError(null);
      try {
        const next = await runTurn(drafts, rounds);
        addReports(next);
        if (next.length > 0) {
          const latest = next[next.length - 1];
          setCurrentTurnIndex(latest.turn_index + 1);
          openModal("turnSummary");
          dispatchEnergyChanged();
        }
        await Promise.all([refreshMap(), refreshSpeciesList(), refreshQueue()].map((p) => p.catch(console.warn)));
        invalidateLineage();
        closeModal("pressure");
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "未知错误";
        setError(`推演失败: ${message}`);
      } finally {
        setLoading(false);
      }
    },
    [addReports, setCurrentTurnIndex, openModal, refreshMap, refreshSpeciesList, refreshQueue, invalidateLineage, closeModal, setLoading, setError]
  );

  // 队列添加
  const handleQueueAdd = useCallback(
    async (drafts: PressureDraft[], rounds: number) => {
      if (!drafts.length) return;
      await addQueue(drafts, rounds);
      refreshQueue();
      closeModal("pressure");
    },
    [refreshQueue, closeModal]
  );

  // 批量执行回合（自动演化）
  const handleBatchExecute = useCallback(
    async (rounds: number, pressures: PressureDraft[], _randomEnergy: number) => {
      if (rounds <= 0) return;
      
      setLoading(true);
      setError(null);
      closeModal("pressure");
      
      try {
        const allReports: TurnReport[] = [];
        
        for (let i = 0; i < rounds; i++) {
          setBatchProgress({ current: i + 1, total: rounds, message: `正在演化第 ${i + 1}/${rounds} 回合...` });
          
          // 如果没有指定压力，使用空数组（自然演化）
          // 【优化】批量执行时不生成详细报告，提高性能
          const next = await runTurn(pressures.length > 0 ? pressures : [], 1, false);
          allReports.push(...next);
          
          if (next.length > 0) {
            const latest = next[next.length - 1];
            setCurrentTurnIndex(latest.turn_index + 1);
          }
        }
        
        // 批量完成后添加所有报告
        if (allReports.length > 0) {
          addReports(allReports);
          openModal("turnSummary");
          dispatchEnergyChanged();
        }
        
        await Promise.all([refreshMap(), refreshSpeciesList(), refreshQueue()].map((p) => p.catch(console.warn)));
        invalidateLineage();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "未知错误";
        setError(`批量演化失败: ${message}`);
      } finally {
        setLoading(false);
        setBatchProgress(null);
      }
    },
    [addReports, setCurrentTurnIndex, openModal, refreshMap, refreshSpeciesList, refreshQueue, invalidateLineage, closeModal, setLoading, setError, setBatchProgress]
  );

  // 快捷键
  useEffect(() => {
    const handleShortcut = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const key = e.key.toLowerCase();
      if (key === "g") setOverlay("genealogy");
      else if (key === "h") setOverlay("chronicle");
      else if (key === "n") setOverlay("niche");
      else if (key === "f") setOverlay("foodweb");
      else if (key === "p") openModal("pressure");
      else if (key === "escape") closeAllModals();
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [setOverlay, openModal, closeAllModals]);

  // 打开族谱视图时自动加载数据
  useEffect(() => {
    if (overlay === "genealogy" && !lineageTree && !lineageLoading) {
      loadLineageTree();
    }
  }, [overlay, lineageTree, lineageLoading, loadLineageTree]);

  // 初始化加载
  useEffect(() => {
    fetchGameState()
      .then((state) => {
        setCurrentTurnIndex(state.turn_index);
        if (state.backend_session_id) {
          setBackendSessionId(state.backend_session_id);
        }
      })
      .catch(console.error);
    fetchHistory(20)
      .then((data) => setReports(data))
      .catch(console.error);
    
    // 游戏加载时自动打开游戏指南
    openModal("gameGuide");
  }, [setCurrentTurnIndex, setBackendSessionId, setReports, openModal]);

  // 提示信息轮询
  useEffect(() => {
    const fetchHintsInfo = async () => {
      try {
        const data = await http.get<{ hints?: { priority: string }[] }>("/api/hints");
        const hints = data.hints || [];
        setHintsInfo({
          count: hints.length,
          criticalCount: hints.filter((h: { priority: string }) => h.priority === "critical").length,
          highCount: hints.filter((h: { priority: string }) => h.priority === "high").length,
        });
      } catch {
        // ignore
      }
    };
    fetchHintsInfo();
    const interval = setInterval(fetchHintsInfo, 30000);
    return () => clearInterval(interval);
  }, [setHintsInfo, speciesRefreshTrigger]);

  // 处理加载游戏（打开设置菜单的加载视图）
  const handleLoadGame = useCallback(() => {
    setSettingsInitialView("load");
    openModal("gameSettings");
  }, [setSettingsInitialView, openModal]);

  // 加载存档后刷新所有数据
  const handleLoadGameFromSettings = useCallback(async (saveName: string) => {
    console.log("[App] 加载存档完成，刷新数据:", saveName);
    try {
      // 刷新游戏状态
      const state = await fetchGameState();
      setCurrentTurnIndex(state.turn_index);
      if (state.backend_session_id) {
        setBackendSessionId(state.backend_session_id);
      }
      // 刷新历史报告
      const history = await fetchHistory(20);
      setReports(history);
      // 刷新地图和物种
      await refreshMap();
      await refreshSpeciesList();
      // 失效族谱缓存
      invalidateLineage();
    } catch (err) {
      console.error("[App] 刷新数据失败:", err);
    }
  }, [setCurrentTurnIndex, setBackendSessionId, setReports, refreshMap, refreshSpeciesList, invalidateLineage]);

  // 保存游戏
  const handleSaveGame = useCallback(async () => {
    try {
      await saveGame(currentSaveName);
      alert("保存成功！");
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "未知错误";
      setError(`保存失败: ${message}`);
    }
  }, [currentSaveName, setError]);

  // 返回主菜单
  const { backToMenu } = useSession();

  return (
    <>
      <AmbientEffects showScanlines={false} showCorners showParticles showGlow particleCount={8} />
      <GameLayout
        mapLayer={
          <>
            <CanvasMapPanel
              ref={mapPanelRef}
              map={mapForDisplay}
              onRefresh={refreshMap}
              selectedTile={selectedTile}
              onSelectTile={handleTileSelect}
              viewMode={viewMode}
              onViewModeChange={handleViewModeChange}
              highlightSpeciesId={selectedSpeciesId}
            />
            <MapLegend
              viewMode={viewMode}
              seaLevel={latestReport?.sea_level ?? 0}
              temperature={latestReport?.global_temperature ?? 15}
              hasSelectedSpecies={!!selectedSpeciesId}
            />
            <MapModeToast viewMode={viewMode} hasSelectedSpecies={!!selectedSpeciesId} />
          </>
        }
        topBar={
          <TopBar
            turnIndex={currentTurnIndex}
            speciesCount={speciesList.filter(s => s.status === "alive").length}
            queueStatus={queueStatus}
            saveName={currentSaveName}
            scenarioInfo={sessionInfo?.scenario}
            onOpenSettings={() => openModal("gameSettings")}
            onSaveGame={handleSaveGame}
            onLoadGame={handleLoadGame}
            onOpenLedger={() => openModal("ledger")}
            onOpenPressure={() => openModal("pressure")}
            onOpenDivinePowers={() => openModal("divinePowers")}
          />
        }
        outlinerCollapsed={!showOutliner}
        outliner={
          showOutliner ? (
            <SpeciesPanel
              speciesList={speciesList}
              selectedSpeciesId={selectedSpeciesId}
              onSelectSpecies={(id) => handleSpeciesSelect(id || "")}
              onCollapse={toggleOutliner}
              refreshTrigger={speciesRefreshTrigger}
              previousPopulations={previousPopulations}
            />
          ) : (
            <div style={{ padding: "8px", display: "flex", justifyContent: "center", background: "rgba(0,0,0,0.2)" }}>
              <button className="btn-icon" onClick={toggleOutliner} title="展开物种列表" style={{ width: 32, height: 32 }}>
                👥
              </button>
            </div>
          )
        }
        lensBar={
          <LensBar
            currentMode={viewMode}
            onModeChange={handleViewModeChange}
            onToggleGenealogy={() => setOverlay("genealogy")}
            onToggleHistory={() => setOverlay("chronicle")}
            onToggleNiche={() => setOverlay("niche")}
            onToggleFoodWeb={() => setOverlay("foodweb")}
            onOpenTrends={() => openModal("trends")}
            onOpenMapHistory={() => openModal("mapHistory")}
            onOpenLogs={() => openModal("logPanel")}
            onCreateSpecies={() => openModal("createSpecies")}
            onOpenHybridization={() => openModal("hybridization")}
            onOpenAIAssistant={() => openModal("aiAssistant")}
            onOpenAchievements={() => openModal("achievements")}
            onToggleHints={() => (modals.hints ? closeModal("hints") : openModal("hints"))}
            onOpenGuide={() => openModal("gameGuide")}
            onOpenGeneLibrary={() => openModal("geneLibrary")}
            showHints={modals.hints}
            hintsInfo={hintsInfo}
          />
        }
        drawer={
          drawerMode === "tile" && selectedTile ? (
            <ContextDrawer title="地块情报" onClose={() => setDrawerMode("none")} noPadding>
              <TileDetailPanel
                tile={selectedTile}
                habitats={selectedTileHabitats}
                selectedSpecies={selectedSpeciesId}
                onSelectSpecies={handleSpeciesSelect}
              />
            </ContextDrawer>
          ) : null
        }
        modals={
          hasActiveModal ? (
            <Suspense fallback={<div className="spinner" style={{ position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }} />}>
              <ModalsLayer
                modals={modals}
                overlay={overlay}
                loading={loading}
                error={error}
                batchProgress={batchProgress}
                reports={reports}
                speciesList={speciesList}
                lineageTree={lineageTree}
                lineageLoading={lineageLoading}
                lineageError={lineageError}
                latestReport={latestReport}
                uiConfig={uiConfig}
                pressureTemplates={pressureTemplates}
                currentSaveName={currentSaveName}
                selectedSpeciesId={selectedSpeciesId}
                settingsInitialView={settingsInitialView}
                pendingAchievement={pendingAchievement}
                onCloseOverlay={() => setOverlay("none")}
                onOpenModal={openModal}
                onCloseModal={closeModal}
                onClearError={() => setError(null)}
                onRetryLineage={invalidateLineage}
                onSelectSpecies={handleSpeciesSelect}
                onExecuteTurn={executeTurn}
                onBatchExecute={handleBatchExecute}
                onQueueAdd={handleQueueAdd}
                onSaveConfig={updateUIConfig}
                onRefreshMap={refreshMap}
                onRefreshQueue={refreshQueue}
                onRefreshSpecies={refreshSpeciesList}
                onBackToMenu={backToMenu}
                onLoadGame={handleLoadGameFromSettings}
                onDismissAchievement={() => setPendingAchievement(null)}
              />
            </Suspense>
          ) : null
        }
      />
    </>
  );
}

// ============ 应用内容 ============
function AppContent() {
  const { scene } = useSession();

  if (scene === "loading") return <LoadingScene />;
  if (scene === "menu") return <MenuScene />;
  return <GameScene />;
}

// ============ Provider 包装器 ============
function GameProviderWrapper({ children }: { children: React.ReactNode }) {
  const { viewMode, setViewMode } = useUI();
  return (
    <GameProvider viewMode={viewMode} onViewModeChange={setViewMode}>
      {children}
    </GameProvider>
  );
}

// ============ 应用入口 ============
export default function App() {
  return (
    <SessionProvider>
      <UIProvider>
        <GameProviderWrapper>
          <AppContent />
        </GameProviderWrapper>
      </UIProvider>
    </SessionProvider>
  );
}
