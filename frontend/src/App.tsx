import { useEffect, useMemo, useRef, useState } from "react";
import "./layout.css"; // 引入新布局样式

// 新布局组件
import { GameLayout } from "./components/layout/GameLayout";
import { TopBar } from "./components/layout/TopBar";
import { LensBar } from "./components/layout/LensBar";
import { Outliner } from "./components/layout/Outliner";
import { ContextDrawer } from "./components/layout/ContextDrawer";

// 现有组件 (复用)
import { MainMenu, type StartPayload } from "./components/MainMenu";
import { MapPanel } from "./components/MapPanel";
import { SpeciesDetailPanel } from "./components/SpeciesDetailPanel";
import { TileDetailPanel } from "./components/TileDetailPanel";
import type { ViewMode } from "./components/MapViewSelector";

// 模态窗与覆盖层
import { FullscreenOverlay } from "./components/FullscreenOverlay";
import { GenealogyView } from "./components/GenealogyView";
import { HistoryTimeline } from "./components/HistoryTimeline";
import { NicheCompareView } from "./components/NicheCompareView";
import { PressureModal } from "./components/PressureModal";
import { GameSettingsMenu } from "./components/GameSettingsMenu";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { CreateSpeciesModal } from "./components/CreateSpeciesModal";

// API 与类型
import type {
  ActionQueueStatus,
  LineageTree,
  HabitatEntry,
  MapOverview,
  MapTileInfo,
  PressureDraft,
  PressureTemplate,
  SpeciesDetail,
  TurnReport,
  UIConfig,
} from "./services/api.types";
import {
  addQueue,
  fetchMapOverview,
  fetchLineageTree,
  fetchPressureTemplates,
  fetchQueueStatus,
  fetchSpeciesDetail,
  fetchUIConfig,
  runTurn,
  updateUIConfig,
  fetchHistory,
  saveGame,
} from "./services/api";

type Scene = "menu" | "game";
type OverlayView = "none" | "genealogy" | "chronicle" | "niche";
type DrawerMode = "none" | "tile" | "species";
type StoredSession = {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
};

const SESSION_STORAGE_KEY = "evosandbox:session";

// Custom Hook for Queue
function useQueue() {
  const [status, setStatus] = useState<ActionQueueStatus | null>(null);
  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);
  function refresh() {
    fetchQueueStatus().then(setStatus).catch(console.error);
  }
  return { status, refresh };
}

const defaultConfig: UIConfig = {
  ai_provider: null,
  ai_model: null,
  ai_timeout: 60,
  embedding_provider: null,
};

export default function App() {
  // --- Session State ---
  const restoredSession = typeof window !== "undefined" ? readStoredSession() : null;
  const [scene, setScene] = useState<Scene>(restoredSession?.scene ?? "menu");
  const [sessionInfo, setSessionInfo] = useState<StartPayload | null>(restoredSession?.sessionInfo ?? null);
  const [currentSaveName, setCurrentSaveName] = useState<string>(
    restoredSession?.currentSaveName ?? restoredSession?.sessionInfo?.save_name ?? ""
  );

  // --- Game Data State ---
  const { status, refresh: refreshQueue } = useQueue();
  const [mapData, setMapData] = useState<MapOverview | null>(null);
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [lineageTree, setLineageTree] = useState<LineageTree | null>(null);
  const [pressureTemplates, setPressureTemplates] = useState<PressureTemplate[]>([]);
  const [uiConfig, setUIConfig] = useState<UIConfig>(defaultConfig);

  // --- UI State ---
  const [viewMode, setViewMode] = useState<ViewMode>("terrain");
  const [overlay, setOverlay] = useState<OverlayView>("none");
  const [drawerMode, setDrawerMode] = useState<DrawerMode>("none");
  
  // Selections
  const [selectedTileId, setSelectedTileId] = useState<number | null>(null);
  const [selectedSpeciesId, setSelectedSpeciesId] = useState<string | null>(null);
  const [speciesDetail, setSpeciesDetail] = useState<SpeciesDetail | null>(null);

  // Modals visibility
  const [showSettings, setShowSettings] = useState(false); // System settings (AI)
  const [showGameSettings, setShowGameSettings] = useState(false); // In-game menu
  const [showPressureModal, setShowPressureModal] = useState(false);
  const [showCreateSpecies, setShowCreateSpecies] = useState(false);

  // Working Data
  const [pendingPressures, setPendingPressures] = useState<PressureDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);

  // Refs
  const mapViewportRef = useRef<HTMLDivElement | null>(null);

  // --- Effects ---

  // Initial Config Load
  useEffect(() => {
    fetchUIConfig().then(setUIConfig).catch(() => setUIConfig(defaultConfig));
    fetchPressureTemplates().then(setPressureTemplates).catch(console.error);
  }, []);

  // Session Persistence
  useEffect(() => {
    if (scene !== "game") {
      clearStoredSession();
      return;
    }
    persistSession({ scene, sessionInfo, currentSaveName });
  }, [scene, sessionInfo, currentSaveName]);

  // Game Start Logic
  useEffect(() => {
    if (scene !== "game") return;
    refreshMap();
    fetchHistory(20).then(setReports).catch(console.error);
    
    // Shortcuts
    const handleShortcut = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      const key = event.key.toLowerCase();
      if (key === "g") setOverlay("genealogy");
      else if (key === "h") setOverlay("chronicle");
      else if (key === "n") setOverlay("niche");
      else if (key === "p") setShowPressureModal(true);
      else if (key === "escape") {
        setOverlay("none");
        setDrawerMode("none");
        setShowPressureModal(false);
        setShowGameSettings(false);
        setShowSettings(false);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [scene]);

  // Lazy Load Lineage
  useEffect(() => {
    if (overlay !== "genealogy" || lineageTree || lineageLoading) return;
    setLineageLoading(true);
    fetchLineageTree()
      .then((tree) => {
        setLineageTree(tree);
        setLineageError(null);
      })
      .catch((err) => {
        console.error(err);
        setLineageError("族谱数据加载失败");
      })
      .finally(() => setLineageLoading(false));
  }, [overlay, lineageTree, lineageLoading]);

  // Load Species Detail
  useEffect(() => {
    if (!selectedSpeciesId) {
      setSpeciesDetail(null);
      return;
    }
    fetchSpeciesDetail(selectedSpeciesId)
      .then((detail) => {
        setSpeciesDetail(detail);
        // Auto-open drawer if not already handling a tile
        if (drawerMode !== "tile") setDrawerMode("species");
      })
      .catch(console.error);
  }, [selectedSpeciesId]);

  // --- Memoized Data ---

  const latestReport = useMemo(() => (reports.length > 0 ? reports[reports.length - 1] : null), [reports]);
  
  const speciesList = useMemo(() => latestReport?.species || [], [latestReport]);

  const selectedTile: MapTileInfo | null = useMemo(() => {
    if (!mapData || selectedTileId == null) return null;
    return mapData.tiles.find((tile) => tile.id === selectedTileId) ?? null;
  }, [mapData, selectedTileId]);

  const selectedTileHabitats: HabitatEntry[] = useMemo(() => {
    if (!mapData || selectedTileId == null) return [];
    return mapData.habitats.filter((hab) => hab.tile_id === selectedTileId);
  }, [mapData, selectedTileId]);

  // --- Actions ---

  async function refreshMap() {
    try {
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
      if (data.tiles.length > 0 && selectedTileId == null) {
        setSelectedTileId(data.tiles[0].id);
      }
    } catch (error: any) {
      setError(`地图加载失败: ${error.message || "未知错误"}`);
    }
  }

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    if (mapData && mapData.tiles.length > 0 && mapData.tiles[0].colors) {
      const updatedTiles = mapData.tiles.map(tile => ({
        ...tile,
        color: tile.colors?.[mode] || tile.color
      }));
      setMapData({ ...mapData, tiles: updatedTiles });
    } else {
      fetchMapOverview(mode).then(setMapData).catch(console.error);
    }
  };

  const handleTileSelect = (tile: MapTileInfo) => {
    setSelectedTileId(tile.id);
    setDrawerMode("tile");
  };

  const handleSpeciesSelect = (id: string) => {
    setSelectedSpeciesId(id);
    setDrawerMode("species");
  };

  async function executeTurn(drafts: PressureDraft[]) {
    setLoading(true);
    setError(null);
    try {
      const next = await runTurn(drafts);
      setReports((prev) => [...prev, ...next]);
      refreshQueue();
      await refreshMap();
      setPendingPressures([]);
      setShowPressureModal(false);
    } catch (error: any) {
      setError(`推演失败: ${error.message || "未知错误"}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleQueueAdd(drafts: PressureDraft[], rounds: number) {
    if (!drafts.length) return;
    await addQueue(drafts, rounds);
    refreshQueue();
    setPendingPressures([]);
    setShowPressureModal(false);
  }

  // --- Render: Scene Switching ---

  if (scene === "menu") {
    return (
      <>
        <MainMenu
          onStart={(payload) => {
            setSessionInfo(payload);
            setCurrentSaveName(payload.save_name || `存档_${Date.now()}`);
            setScene("game");
          }}
          onOpenSettings={() => setShowSettings(true)}
          uiConfig={uiConfig}
        />
        {showSettings && (
          <SettingsDrawer
            config={uiConfig}
            onClose={() => setShowSettings(false)}
            onSave={async (next) => {
              const saved = await updateUIConfig(next);
              setUIConfig(saved);
            }}
          />
        )}
      </>
    );
  }

  // --- Render: Game Scene Content ---

  // 1. Right Drawer Content
  const renderDrawerContent = () => {
    if (drawerMode === "tile" && selectedTile) {
      return (
        <ContextDrawer title="地块情报" onClose={() => setDrawerMode("none")}>
          <TileDetailPanel
            tile={selectedTile}
            habitats={selectedTileHabitats}
            selectedSpecies={selectedSpeciesId}
            onSelectSpecies={handleSpeciesSelect}
          />
        </ContextDrawer>
      );
    }
    if (drawerMode === "species" && speciesDetail) {
      return (
        <ContextDrawer title="物种档案" onClose={() => setDrawerMode("none")}>
          <SpeciesDetailPanel 
            species={speciesDetail} 
            variant="panel"
            onUpdate={(updated) => setSpeciesDetail(updated)}
          />
        </ContextDrawer>
      );
    }
    return null;
  };

  // 2. Modal Visibility Logic
  const hasActiveModal = Boolean(
    error || 
    overlay !== "none" || 
    showSettings || 
    showPressureModal || 
    showCreateSpecies || 
    showGameSettings
  );

  // 3. Modals Layer
  const renderModals = () => {
    if (!hasActiveModal) return null;

    return (
      <>
        {/* Errors */}
        {error && (
          <div style={{
            position: "fixed", top: 80, left: "50%", transform: "translateX(-50%)",
            background: "#ff4444", color: "white", padding: "12px 24px",
            borderRadius: "8px", zIndex: 9999, boxShadow: "0 4px 12px rgba(0,0,0,0.3)"
          }}>
            {error}
            <button onClick={() => setError(null)} style={{marginLeft: 12, background:"none", border:"none", color:"white", cursor:"pointer"}}>✕</button>
          </div>
        )}

        {/* Overlays */}
        {overlay === "genealogy" && (
          <FullscreenOverlay title="族谱树" onClose={() => setOverlay("none")}>
            <GenealogyView
              tree={lineageTree}
              loading={lineageLoading}
              error={lineageError}
              onRetry={() => { setLineageTree(null); setLineageError(null); }}
            />
          </FullscreenOverlay>
        )}
        {overlay === "chronicle" && (
          <FullscreenOverlay title="演化年鉴" onClose={() => setOverlay("none")}>
            <HistoryTimeline reports={reports} variant="overlay" />
          </FullscreenOverlay>
        )}
        {overlay === "niche" && (
          <FullscreenOverlay title="生态位对比" onClose={() => setOverlay("none")}>
            <NicheCompareView onClose={() => setOverlay("none")} />
          </FullscreenOverlay>
        )}

        {/* Dialogs */}
        {showSettings && (
          <SettingsDrawer
            config={uiConfig}
            onClose={() => setShowSettings(false)}
            onSave={async (next) => {
              const saved = await updateUIConfig(next);
              setUIConfig(saved);
            }}
          />
        )}
        {showPressureModal && (
          <PressureModal
            pressures={pendingPressures}
            templates={pressureTemplates}
            onChange={setPendingPressures}
            onQueue={handleQueueAdd}
            onExecute={executeTurn}
            onClose={() => setShowPressureModal(false)}
          />
        )}
        {showCreateSpecies && (
          <CreateSpeciesModal 
            onClose={() => setShowCreateSpecies(false)}
            onSuccess={() => {
              refreshMap();
              refreshQueue();
              if (overlay === "genealogy") setLineageTree(null);
            }}
          />
        )}
        {showGameSettings && (
          <GameSettingsMenu
            currentSaveName={currentSaveName}
            onClose={() => setShowGameSettings(false)}
            onBackToMenu={() => setScene("menu")}
            onSaveGame={async () => {
              try { await saveGame(currentSaveName); alert("保存成功！"); }
              catch (e: any) { setError(`保存失败: ${e.message}`); }
            }}
            onLoadGame={(saveName) => {
              setCurrentSaveName(saveName);
              refreshMap();
              fetchHistory(20).then(setReports).catch(console.error);
            }}
            onOpenAISettings={() => {
              setShowGameSettings(false);
              setShowSettings(true);
            }}
          />
        )}
      </>
    );
  };

  return (
    <GameLayout
      mapLayer={
        <MapPanel
          map={mapData}
          onRefresh={refreshMap}
          selectedTile={selectedTile}
          onSelectTile={handleTileSelect}
          viewMode={viewMode}
          onViewModeChange={handleViewModeChange}
        />
      }
      topBar={
        <TopBar
          turnIndex={latestReport?.turn_index ?? 0}
          speciesCount={latestReport?.species.length ?? 0}
          queueStatus={status}
          saveName={currentSaveName}
          scenarioInfo={sessionInfo?.scenario}
          onOpenSettings={() => setShowGameSettings(true)}
          onSaveGame={async () => {
             try { await saveGame(currentSaveName); alert("保存成功！"); }
             catch (e: any) { setError(`保存失败: ${e.message}`); }
          }}
        />
      }
      outliner={
        <Outliner
          speciesList={speciesList}
          selectedSpeciesId={selectedSpeciesId}
          onSelectSpecies={handleSpeciesSelect}
        />
      }
      lensBar={
        <LensBar
          currentMode={viewMode}
          onModeChange={handleViewModeChange}
          onOpenPressure={() => setShowPressureModal(true)}
          onToggleGenealogy={() => setOverlay("genealogy")}
          onToggleHistory={() => setOverlay("chronicle")}
          onToggleNiche={() => setOverlay("niche")}
        />
      }
      drawer={renderDrawerContent()}
      modals={hasActiveModal ? renderModals() : null}
    />
  );
}

// Helper Functions (Storage)
function readStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.scene !== "game") return null;
    return {
      scene: "game",
      sessionInfo: parsed.sessionInfo ?? null,
      currentSaveName: parsed.currentSaveName || parsed.sessionInfo?.save_name || `存档_${Date.now()}`,
    };
  } catch { return null; }
}

function persistSession(payload: StoredSession) {
  try { window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload)); } catch {}
}

function clearStoredSession() {
  try { window.localStorage.removeItem(SESSION_STORAGE_KEY); } catch {}
}
