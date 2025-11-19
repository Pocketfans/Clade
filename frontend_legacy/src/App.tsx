import { useEffect, useMemo, useRef, useState } from "react";

import { ControlPanel } from "./components/ControlPanel";
import { CreateSpeciesModal } from "./components/CreateSpeciesModal";
import { EventLog } from "./components/EventLog";
import { FloatingWindow } from "./components/FloatingWindow";
import { FullscreenOverlay } from "./components/FullscreenOverlay";
import { GameSettingsMenu } from "./components/GameSettingsMenu";
import { GenealogyView } from "./components/GenealogyView";
import { HistoryTimeline } from "./components/HistoryTimeline";
import { MainMenu, type StartPayload } from "./components/MainMenu";
import { NicheCompareView } from "./components/NicheCompareView";
import { MapPanel } from "./components/MapPanel";
import type { ViewMode } from "./components/MapViewSelector";
import { PressureModal } from "./components/PressureModal";
import { PressureSummaryPanel } from "./components/PressureSummaryPanel";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { SpeciesDetailPanel } from "./components/SpeciesDetailPanel";
import { TileDetailPanel } from "./components/TileDetailPanel";
import { TurnReportPanel } from "./components/TurnReportPanel";
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
type SidePanel = "intel" | "pressure";
type OverlayView = "none" | "genealogy" | "chronicle" | "niche";
type StoredSession = {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
};

const SESSION_STORAGE_KEY = "evosandbox:session";

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
  ai_base_url: null,
  ai_api_key: null,
  ai_timeout: 60,
  embedding_provider: null,
  embedding_model: null,
  embedding_base_url: null,
  embedding_api_key: null,
};

export default function App() {
  const restoredSession =
    typeof window !== "undefined" ? readStoredSession() : null;
  const { status, refresh } = useQueue();
  const [scene, setScene] = useState<Scene>(restoredSession?.scene ?? "menu");
  const [sessionInfo, setSessionInfo] = useState<StartPayload | null>(
    restoredSession?.sessionInfo ?? null,
  );
  const [currentSaveName, setCurrentSaveName] = useState<string>(
    restoredSession?.currentSaveName ??
      restoredSession?.sessionInfo?.save_name ??
      "",
  );
  const [sidePanel, setSidePanel] = useState<SidePanel>("intel");
  const [overlay, setOverlay] = useState<OverlayView>("none");
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [mapData, setMapData] = useState<MapOverview | null>(null);
  const [lineageTree, setLineageTree] = useState<LineageTree | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [selectedTileId, setSelectedTileId] = useState<number | null>(null);
  const [selectedSpecies, setSelectedSpecies] = useState<string | null>(null);
  const [speciesDetail, setSpeciesDetail] = useState<SpeciesDetail | null>(null);
  const [uiConfig, setUIConfig] = useState<UIConfig>(defaultConfig);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingPressures, setPendingPressures] = useState<PressureDraft[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [showGameSettings, setShowGameSettings] = useState(false);
  const [showPressureModal, setShowPressureModal] = useState(false);
  const [showCreateSpecies, setShowCreateSpecies] = useState(false);
  const [pressureTemplates, setPressureTemplates] = useState<PressureTemplate[]>([]);
  const [showSpeciesWindow, setShowSpeciesWindow] = useState(false);
  const [tileWindow, setTileWindow] = useState<{
    tileId: number;
    anchor: { x: number; y: number };
  } | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("terrain");
  const mapViewportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetchUIConfig().then(setUIConfig).catch(() => setUIConfig(defaultConfig));
  }, []);

  useEffect(() => {
    fetchPressureTemplates().then(setPressureTemplates).catch(console.error);
  }, []);

  useEffect(() => {
    if (scene !== "game") {
      clearStoredSession();
      return;
    }
    persistSession({
      scene,
      sessionInfo,
      currentSaveName,
    });
  }, [scene, sessionInfo, currentSaveName]);

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

  useEffect(() => {
    if (scene !== "game") return;
    function handleShortcut(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "g") {
        setOverlay("genealogy");
      } else if (key === "h") {
        setOverlay("chronicle");
      } else if (key === "n") {
        setOverlay("niche");
      } else if (key === "p") {
        setShowPressureModal(true);
        setSidePanel("pressure");
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [scene]);

  useEffect(() => {
    if (scene !== "game") return;
    refreshMap();
    // 加载历史记录
    fetchHistory(20)
      .then(setReports)
      .catch(console.error);
  }, [scene]);

  useEffect(() => {
    if (!selectedSpecies) {
      setSpeciesDetail(null);
      return;
    }
    fetchSpeciesDetail(selectedSpecies)
      .then((detail) => {
        setSpeciesDetail(detail);
        setShowSpeciesWindow(true);
      })
      .catch(console.error);
  }, [selectedSpecies]);

  const latestReport = useMemo(
    () => (reports.length > 0 ? reports[reports.length - 1] : null),
    [reports],
  );

  const selectedTile: MapTileInfo | null = useMemo(() => {
    if (!mapData || selectedTileId == null) return null;
    return mapData.tiles.find((tile) => tile.id === selectedTileId) ?? null;
  }, [mapData, selectedTileId]);

  const selectedTileHabitats: HabitatEntry[] = useMemo(() => {
    if (!mapData || selectedTileId == null) return [];
    return mapData.habitats.filter((hab) => hab.tile_id === selectedTileId);
  }, [mapData, selectedTileId]);

  async function refreshMap() {
    try {
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
      console.log(`[前端] 地图加载成功: ${data.tiles.length} 个地块, ${data.habitats.length} 个栖息地, 视图模式: ${viewMode}`);
      if (data.tiles.length > 0 && selectedTileId == null) {
        setSelectedTileId(data.tiles[0].id);
      }
      if (data.tiles.length === 0) {
        console.warn("[前端] 地图没有地块数据");
        setError("地图数据为空，请检查后端是否正确初始化");
      }
    } catch (error: any) {
      console.error("[前端] 地图加载失败:", error);
      setError(`地图加载失败: ${error.message || "未知错误"}`);
    }
  }
  
  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    // 性能优化：如果地图数据已加载且包含预计算的颜色，直接切换
    // 无需重新请求后端
    if (mapData && mapData.tiles.length > 0 && mapData.tiles[0].colors) {
      // 直接使用缓存的颜色数据
      const updatedTiles = mapData.tiles.map(tile => ({
        ...tile,
        color: tile.colors?.[mode] || tile.color
      }));
      setMapData({
        ...mapData,
        tiles: updatedTiles
      });
    } else {
      // 旧版本：需要重新请求后端
      fetchMapOverview(mode)
        .then(setMapData)
        .catch(console.error);
    }
  };

  async function executeTurn(drafts: PressureDraft[]) {
    setLoading(true);
    setError(null);
    console.log(`[前端] 开始推演，压力数: ${drafts.length}`);
    
    try {
      const next = await runTurn(drafts);
      console.log(`[前端] 推演完成，收到 ${next.length} 个报告`);
      
      if (next.length === 0) {
        setError("推演完成但没有生成报告，请检查后端日志");
        return;
      }
      
      setReports((prev) => [...prev, ...next]);
      refresh();
      await refreshMap();
      setPendingPressures([]);
      setShowPressureModal(false);
      
      console.log(`[前端] 推演成功: 回合 ${next[next.length - 1].turn_index}, ${next[next.length - 1].species.length} 个物种`);
    } catch (error: any) {
      console.error("[前端] 推演失败:", error);
      const errorMsg = error.message || "未知错误";
      const detail = error.response?.data?.detail || "";
      setError(`推演失败: ${errorMsg}${detail ? ` - ${detail}` : ""}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleQueueAdd(drafts: PressureDraft[], rounds: number) {
    if (!drafts.length) return;
    await addQueue(drafts, rounds);
    refresh();
    setPendingPressures([]);
    setShowPressureModal(false);
  }

  function handleTileSelect(tile: MapTileInfo, point: { clientX: number; clientY: number }) {
    const anchor = toViewportAnchor(point);
    setSelectedTileId(tile.id);
    setTileWindow({ tileId: tile.id, anchor });
    setSelectedSpecies(null);
    setShowSpeciesWindow(false);
  }

  function toViewportAnchor(point: { clientX: number; clientY: number }) {
    const bounds = mapViewportRef.current?.getBoundingClientRect();
    if (!bounds) return { x: point.clientX, y: point.clientY };
    return { x: point.clientX - bounds.left, y: point.clientY - bounds.top };
  }

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
              // 不再自动关闭设置抽屉
            }}
          />
        )}
      </>
    );
  }

  function renderSidePanel() {
    if (sidePanel === "pressure") {
      return (
        <PressureSummaryPanel
          drafts={pendingPressures}
          status={status}
          onOpenPlanner={() => setShowPressureModal(true)}
        />
      );
    }
    return (
      <>
        <ControlPanel 
          status={status} 
          onOpenPressure={() => setShowPressureModal(true)} 
          onOpenCreateSpecies={() => setShowCreateSpecies(true)}
        />
        <EventLog report={latestReport} />
        {latestReport ? (
          <TurnReportPanel report={latestReport} />
        ) : (
          <div className="glass-card report-card placeholder">尚无推演记录。</div>
        )}
      </>
    );
  }

  const overlayPanel =
    overlay === "genealogy" ? (
      <FullscreenOverlay title="族谱树" onClose={() => setOverlay("none")}>
        <GenealogyView
          tree={lineageTree}
          loading={lineageLoading}
          error={lineageError}
          onRetry={() => {
            setLineageTree(null);
            setLineageError(null);
          }}
        />
      </FullscreenOverlay>
    ) : overlay === "chronicle" ? (
      <FullscreenOverlay title="演化年鉴" onClose={() => setOverlay("none")}>
        <HistoryTimeline reports={reports} variant="overlay" />
      </FullscreenOverlay>
    ) : overlay === "niche" ? (
      <FullscreenOverlay title="生态位对比" onClose={() => setOverlay("none")}>
        <NicheCompareView onClose={() => setOverlay("none")} />
      </FullscreenOverlay>
    ) : null;

  const settingsDrawer =
    showSettings && scene === "game" ? (
      <SettingsDrawer
        config={uiConfig}
        onClose={() => setShowSettings(false)}
        onSave={async (next) => {
          const saved = await updateUIConfig(next);
          setUIConfig(saved);
          // 不再自动关闭设置抽屉
        }}
      />
    ) : null;

  const pressureModal =
    showPressureModal && scene === "game" ? (
      <PressureModal
        pressures={pendingPressures}
        templates={pressureTemplates}
        onChange={setPendingPressures}
        onQueue={handleQueueAdd}
        onExecute={executeTurn}
        onClose={() => setShowPressureModal(false)}
      />
    ) : null;

  const gameSettingsMenu =
    showGameSettings && scene === "game" ? (
      <GameSettingsMenu
        currentSaveName={currentSaveName}
        onClose={() => setShowGameSettings(false)}
        onBackToMenu={() => setScene("menu")}
        onSaveGame={async () => {
          try {
            await saveGame(currentSaveName);
            alert("保存成功！");
          } catch (e: any) {
            setError(`保存失败: ${e.message}`);
          }
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
    ) : null;

  return (
    <div className="game-root">
      {error && (
        <div
          style={{
            position: "fixed",
            top: "80px",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 10000,
            backgroundColor: "#ff4444",
            color: "white",
            padding: "12px 24px",
            borderRadius: "8px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            maxWidth: "600px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
          }}
        >
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{
              background: "rgba(255,255,255,0.2)",
              border: "none",
              color: "white",
              padding: "4px 8px",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            关闭
          </button>
        </div>
      )}
      <header className="command-banner">
        <div className="command-emblem">
          <h1>EvoSandbox</h1>
          <p>环境之手 · 演化沙盒</p>
          <small>
            {sessionInfo
              ? `${sessionInfo.scenario} · ${sessionInfo.mode === "create" ? "新纪元" : "续写"}`
              : "未选择剧本"}
          </small>
        </div>
        <div className="command-stats">
          <div>
            <label>回合</label>
            <span>{latestReport?.turn_index ?? 0}</span>
          </div>
          <div>
            <label>物种</label>
            <span>{latestReport?.species.length ?? 0}</span>
          </div>
          <div>
            <label>队列</label>
            <span>{status?.queued_rounds ?? 0}</span>
          </div>
        </div>
        <div className="command-run">
          <button type="button" onClick={() => setShowPressureModal(true)} disabled={loading}>
            {loading ? "推演中..." : "开始推演"}
          </button>
          <small>{loading ? "正在执行推演，请稍候..." : "设置好压力后再启动推演。"}</small>
        </div>
        <div className="command-actions" style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setShowGameSettings(true)}
            title="游戏设置"
          >
            ⚙️ 设置
          </button>
          <div className="command-save-info" style={{ display: "flex", flexDirection: "column", fontSize: "0.85rem" }}>
            <small style={{ opacity: 0.7 }}>存档: {currentSaveName}</small>
            <small style={{ opacity: 0.6 }}>
              AI: {uiConfig.ai_provider ? `${uiConfig.ai_provider} · ${uiConfig.ai_model ?? "默认"}` : "未配置"}
            </small>
          </div>
        </div>
      </header>
      <div className="world-grid">
        <section className="map-viewport" ref={mapViewportRef}>
          <div className="map-control-bar">
            <div>
              <button type="button" onClick={() => setOverlay("genealogy")}>
                族谱树 (G)
              </button>
              <button type="button" onClick={() => setOverlay("chronicle")}>
                演化年鉴 (H)
              </button>
              <button type="button" onClick={() => setOverlay("niche")}>
                生态位对比 (N)
              </button>
            </div>
            <button type="button" onClick={() => setShowPressureModal(true)}>
              打开压力策划 (P)
            </button>
          </div>
          <MapPanel
            map={mapData}
            onRefresh={refreshMap}
            selectedTile={selectedTile}
            onSelectTile={handleTileSelect}
            viewMode={viewMode}
            onViewModeChange={handleViewModeChange}
          />
          {tileWindow && selectedTile && (
            <FloatingWindow
              title="地块情报"
              anchor={tileWindow.anchor}
              onClose={() => setTileWindow(null)}
            >
              <TileDetailPanel
                tile={selectedTile}
                habitats={selectedTileHabitats}
                selectedSpecies={selectedSpecies}
                onSelectSpecies={(code) => setSelectedSpecies(code)}
              />
            </FloatingWindow>
          )}
          {speciesDetail && showSpeciesWindow && (
            <FloatingWindow
              title="物种档案"
              inline
              onClose={() => {
                setShowSpeciesWindow(false);
                setSelectedSpecies(null);
              }}
            >
              <SpeciesDetailPanel species={speciesDetail} variant="floating" />
            </FloatingWindow>
          )}
        </section>
        <aside className="intel-stack">
          <div className="intel-tabs">
            <button
              className={sidePanel === "intel" ? "tab-button active" : "tab-button"}
              onClick={() => setSidePanel("intel")}
            >
              情报
            </button>
            <button
              className={sidePanel === "pressure" ? "tab-button active" : "tab-button"}
              onClick={() => setSidePanel("pressure")}
            >
              压力
            </button>
          </div>
          {renderSidePanel()}
        </aside>
      </div>
      <HistoryTimeline reports={reports} variant="bar" />
      {settingsDrawer}
      {pressureModal}
      {gameSettingsMenu}
      {overlayPanel}
      {showCreateSpecies && (
        <CreateSpeciesModal 
          onClose={() => setShowCreateSpecies(false)}
          onSuccess={() => {
            // 创造成功后，刷新地图以显示可能的分布（虽然通常需要时间演化，但如果prompt包含位置偏好可能会直接生成）
            refreshMap();
            // 刷新队列状态（不直接相关，但保持同步）
            refresh();
            // 如果正在查看族谱，也刷新
            if (overlay === "genealogy") {
              setLineageTree(null); // trigger reload
            }
          }}
        />
      )}
    </div>
  );
}

function readStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.scene !== "game") return null;
    return {
      scene: "game",
      sessionInfo: parsed.sessionInfo ?? null,
      currentSaveName:
        parsed.currentSaveName ||
        parsed.sessionInfo?.save_name ||
        `存档_${Date.now()}`,
    };
  } catch (error) {
    console.warn("[前端] 恢复会话失败:", error);
    return null;
  }
}

function persistSession(payload: StoredSession) {
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn("[前端] 存储会话失败:", error);
  }
}

function clearStoredSession() {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
