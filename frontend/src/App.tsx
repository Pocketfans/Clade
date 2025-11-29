import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./layout.css"; // 引入新布局样式

// 新布局组件
import { GameLayout } from "./components/layout/GameLayout";
import { TopBar } from "./components/layout/TopBar";
import { LensBar } from "./components/layout/LensBar";
import { ContextDrawer } from "./components/layout/ContextDrawer";

// 现有组件 (复用)
import { MainMenu, type StartPayload } from "./components/MainMenu";
import { CanvasMapPanel, type CanvasMapPanelHandle, type CameraState } from "./components/CanvasMapPanel";
import { SpeciesPanel } from "./components/SpeciesPanel";
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
import { EnhancedCreateSpeciesModal } from "./components/EnhancedCreateSpeciesModal";
import { GlobalTrendsPanel } from "./components/GlobalTrendsPanel";
import { SpeciesLedger } from "./components/SpeciesLedger";
import { FoodWebGraph } from "./components/FoodWebGraph";
import { TurnProgressOverlay } from "./components/TurnProgressOverlay";
import { TurnSummaryModal } from "./components/TurnSummaryModal";
import { MapHistoryView } from "./components/MapHistoryView";
import { LogPanel } from "./components/LogPanel";
import { MapLegend } from "./components/MapLegend";
import { MapModeToast } from "./components/MapModeToast";

// AI 增强组件
import { AIAssistantPanel } from "./components/AIAssistantPanel";
import { AIEnhancedTimeline } from "./components/AIEnhancedTimeline";

// 成就与提示系统
import { AchievementsPanel } from "./components/AchievementsPanel";
import { GameHintsPanel, AchievementNotification } from "./components/GameHintsPanel";

// 杂交与能量
import { HybridizationPanel } from "./components/HybridizationPanel";
import { DivinePowersPanel } from "./components/DivinePowersPanel";
import { dispatchEnergyChanged } from "./components/EnergyBar";

// 界面增强效果
import { AmbientEffects } from "./components/AmbientEffects";

// API 与类型
import type {
  ActionQueueStatus,
  LineageTree,
  HabitatEntry,
  MapOverview,
  MapTileInfo,
  PressureDraft,
  PressureTemplate,
  SpeciesSnapshot,
  TurnReport,
  UIConfig,
} from "./services/api.types";
import {
  addQueue,
  fetchMapOverview,
  fetchLineageTree,
  fetchPressureTemplates,
  fetchQueueStatus,
  fetchSpeciesList,
  fetchUIConfig,
  runTurn,
  updateUIConfig,
  fetchHistory,
  saveGame,
  fetchGameState,
} from "./services/api";

type Scene = "menu" | "game" | "loading";
type OverlayView = "none" | "genealogy" | "chronicle" | "niche" | "foodweb";
type DrawerMode = "none" | "tile";  // 物种详情已整合到 SpeciesPanel
type StoredSession = {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
  backendSessionId?: string;  // 后端会话ID，用于检测后端重启
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
  async function refresh() {
    try {
      const data = await fetchQueueStatus();
      setStatus(data);
    } catch (error) {
      console.error("刷新队列状态失败:", error);
    }
  }
  return { status, refresh };
}

const defaultConfig: UIConfig = {
  providers: {},
  capability_routes: {},
  ai_provider: null,
  ai_model: null,
  ai_timeout: 60,
  embedding_provider: null,
};

export default function App() {
  // --- Session State ---
  // 尝试恢复会话，但需要验证后端状态
  const storedSession = typeof window !== "undefined" ? readStoredSession() : null;
  const [scene, setScene] = useState<Scene>(storedSession ? "loading" : "menu");
  const [sessionInfo, setSessionInfo] = useState<StartPayload | null>(storedSession?.sessionInfo ?? null);
  const [currentSaveName, setCurrentSaveName] = useState<string>(
    storedSession?.currentSaveName ?? storedSession?.sessionInfo?.save_name ?? ""
  );
  const [backendSessionId, setBackendSessionId] = useState<string>(
    storedSession?.backendSessionId ?? ""
  );
  
  // 验证后端状态，决定是恢复会话还是回到主菜单
  // 关键逻辑：通过比对后端会话ID来检测后端是否重启
  // - 后端重启：会话ID不匹配 → 回到主菜单
  // - 页面刷新：会话ID匹配 → 保持当前状态
  useEffect(() => {
    if (scene !== "loading") return;
    
    // 验证后端是否有有效的游戏状态
    fetchGameState()
      .then((state) => {
        // 检查后端会话ID是否匹配（关键！）
        const storedBackendSessionId = storedSession?.backendSessionId;
        const currentBackendSessionId = state?.backend_session_id;
        
        if (!currentBackendSessionId) {
          // 后端没有返回会话ID（可能是旧版本后端），回到主菜单
          console.log("[会话恢复] 后端未返回会话ID，回到主菜单");
          clearStoredSession();
          setScene("menu");
          return;
        }
        
        if (storedBackendSessionId && storedBackendSessionId !== currentBackendSessionId) {
          // 后端会话ID不匹配，说明后端重启了，回到主菜单
          console.log("[会话恢复] 后端已重启（会话ID不匹配），回到主菜单");
          console.log(`  - 存储的会话ID: ${storedBackendSessionId?.slice(0, 8)}...`);
          console.log(`  - 当前的会话ID: ${currentBackendSessionId?.slice(0, 8)}...`);
          clearStoredSession();
          setScene("menu");
          return;
        }
        
        // 后端会话ID匹配（或首次进入游戏），且有有效状态，恢复到游戏界面
        if (state && state.turn_index >= 0) {
          console.log("[会话恢复] 后端状态有效，恢复游戏");
          // 更新后端会话ID状态
          setBackendSessionId(currentBackendSessionId);
          setScene("game");
        } else {
          // 后端状态无效，回到主菜单
          console.log("[会话恢复] 后端状态无效，回到主菜单");
          clearStoredSession();
          setScene("menu");
        }
      })
      .catch((err) => {
        // 后端连接失败，回到主菜单
        console.log("[会话恢复] 后端连接失败，回到主菜单:", err);
        clearStoredSession();
        setScene("menu");
      });
  }, [scene]);

  // --- Game Data State ---
  const { status, refresh: refreshQueue } = useQueue();
  const [mapData, setMapData] = useState<MapOverview | null>(null);
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [lineageTree, setLineageTree] = useState<LineageTree | null>(null);
  const [pressureTemplates, setPressureTemplates] = useState<PressureTemplate[]>([]);
  const [uiConfig, setUIConfig] = useState<UIConfig>(defaultConfig);
  const [freshSpeciesList, setFreshSpeciesList] = useState<SpeciesSnapshot[]>([]); // 实时物种列表
  const [currentTurnIndex, setCurrentTurnIndex] = useState<number>(0); // 当前回合数（从后端同步）

  // --- UI State ---
  const [viewMode, setViewMode] = useState<ViewMode>("terrain");
  const [overlay, setOverlay] = useState<OverlayView>("none");
  const [drawerMode, setDrawerMode] = useState<DrawerMode>("none");
  
  // Selections
  const [selectedTileId, setSelectedTileId] = useState<number | null>(null);
  const [selectedSpeciesId, setSelectedSpeciesId] = useState<string | null>(null);

  // Modals visibility
  const [showSettings, setShowSettings] = useState(false); // System settings (AI)
  const [showGameSettings, setShowGameSettings] = useState(false); // In-game menu
  const [showPressureModal, setShowPressureModal] = useState(false);
  const [showCreateSpecies, setShowCreateSpecies] = useState(false);
  const [showTrends, setShowTrends] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const [showOutliner, setShowOutliner] = useState(true);
  const [settingsInitialView, setSettingsInitialView] = useState<"menu" | "load">("menu");
  const [showTurnSummary, setShowTurnSummary] = useState(false); // 新增：回合总结
  const [showMapHistory, setShowMapHistory] = useState(false); // 新增：地图历史
  const [showLogPanel, setShowLogPanel] = useState(false); // 新增：日志面板
  const [showAIAssistant, setShowAIAssistant] = useState(false); // AI 助手面板
  const [showAITimeline, setShowAITimeline] = useState(false); // AI 增强年鉴
  const [showAchievements, setShowAchievements] = useState(false); // 成就面板
  const [showHints, setShowHints] = useState(false); // 智能提示面板（点击打开）
  const [showHybridization, setShowHybridization] = useState(false); // 杂交面板
  const [showDivinePowers, setShowDivinePowers] = useState(false); // 神力进阶面板
  const [hintsInfo, setHintsInfo] = useState<{count: number; criticalCount: number; highCount: number}>({ count: 0, criticalCount: 0, highCount: 0 });
  const [pendingAchievement, setPendingAchievement] = useState<{name: string; icon: string; description: string; rarity: string} | null>(null);

  // Working Data
  const [pendingPressures, setPendingPressures] = useState<PressureDraft[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [speciesRefreshTrigger, setSpeciesRefreshTrigger] = useState(0); // 物种数据刷新触发器

  // Refs
  const mapPanelRef = useRef<CanvasMapPanelHandle | null>(null);

  // --- Effects ---

  // Initial Config Load
  useEffect(() => {
    fetchUIConfig()
      .then((config) => {
        console.log("[App] 配置加载成功，providers 数量:", Object.keys(config.providers || {}).length);
        setUIConfig(config);
      })
      .catch((err) => {
        console.error("[App] 配置加载失败，使用默认配置:", err);
        setUIConfig(defaultConfig);
      });
    fetchPressureTemplates().then(setPressureTemplates).catch(console.error);
  }, []);

  // Session Persistence
  useEffect(() => {
    if (scene === "game") {
      // 游戏中时保存会话（包含后端会话ID，用于检测后端重启）
      persistSession({ scene, sessionInfo, currentSaveName, backendSessionId });
    } else if (scene === "menu") {
      // 回到主菜单时清除会话
      clearStoredSession();
    }
    // loading 状态不做任何操作
  }, [scene, sessionInfo, currentSaveName, backendSessionId]);

  // 定期获取提示信息（用于底部栏徽章显示）
  useEffect(() => {
    if (scene !== "game") return;
    
    const fetchHintsInfo = async () => {
      try {
        const response = await fetch("/api/hints");
        const data = await response.json();
        const hints = data.hints || [];
        setHintsInfo({
          count: hints.length,
          criticalCount: hints.filter((h: {priority: string}) => h.priority === 'critical').length,
          highCount: hints.filter((h: {priority: string}) => h.priority === 'high').length,
        });
      } catch (error) {
        console.error("获取提示信息失败:", error);
      }
    };
    
    fetchHintsInfo();
    const interval = setInterval(fetchHintsInfo, 30000);
    return () => clearInterval(interval);
  }, [scene, speciesRefreshTrigger]);

  // Game Start Logic
  useEffect(() => {
    if (scene !== "game") return;
    refreshMap();
    
    // 获取游戏状态（包含正确的回合数和后端会话ID）
    fetchGameState()
      .then((state) => {
        setCurrentTurnIndex(state.turn_index);
        // 更新后端会话ID（用于检测后端重启）
        if (state.backend_session_id) {
          setBackendSessionId(state.backend_session_id);
        }
        console.log(`[前端] 游戏状态已同步: 回合=${state.turn_index}, 物种=${state.species_count}`);
      })
      .catch(console.error);
    
    fetchHistory(20)
      .then((data) => setReports(normalizeReports(data)))
      .catch(console.error);
    
    // Shortcuts
    const handleShortcut = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      const key = event.key.toLowerCase();
      if (key === "g") setOverlay("genealogy");
      else if (key === "h") setOverlay("chronicle");
      else if (key === "n") setOverlay("niche");
      else if (key === "f") setOverlay("foodweb");
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

  const handleLoadGame = () => {
    setSettingsInitialView("load");
    setShowGameSettings(true);
  };

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

  // 物种详情加载现在由 SpeciesPanel 组件内部处理

  // --- Memoized Data ---

  const latestReport = useMemo(() => (reports.length > 0 ? reports[reports.length - 1] : null), [reports]);
  
  // 前一回合的报告（用于计算趋势）
  const previousReport = useMemo(() => (reports.length > 1 ? reports[reports.length - 2] : null), [reports]);
  
  // 前一回合的种群数量映射（用于趋势判断）
  const previousPopulations = useMemo(() => {
    const map = new Map<string, number>();
    if (previousReport?.species) {
      for (const s of previousReport.species) {
        map.set(s.lineage_code, s.population);
      }
    }
    return map;
  }, [previousReport]);
  
  // 物种列表：合并报告数据和实时数据，确保信息完整
  const speciesList = useMemo(() => {
    const reportSpecies = latestReport?.species || [];
    const reportMap = new Map(reportSpecies.map(s => [s.lineage_code, s]));
    
    // 如果有实时列表，合并数据
    if (freshSpeciesList.length > 0) {
      const merged: SpeciesSnapshot[] = [];
      const seen = new Set<string>();
      
      // 先添加报告中的物种（数据更完整）
      for (const s of reportSpecies) {
        merged.push(s);
        seen.add(s.lineage_code);
      }
      
      // 添加报告中没有的新物种（如新分化物种）
      for (const s of freshSpeciesList) {
        if (!seen.has(s.lineage_code)) {
          merged.push(s);
        }
      }
      
      return merged;
    }
    
    return reportSpecies;
  }, [freshSpeciesList, latestReport]);
  
  // 刷新物种列表的函数
  const refreshSpeciesList = useCallback(async () => {
    try {
      const list = await fetchSpeciesList();
      // 转换为 SpeciesSnapshot 格式（简要数据）
      const snapshots: SpeciesSnapshot[] = list.map(item => ({
        lineage_code: item.lineage_code,
        latin_name: item.latin_name,
        common_name: item.common_name,
        population: item.population,
        population_share: 0,
        deaths: 0,
        death_rate: 0,
        ecological_role: item.ecological_role,
        status: item.status,
        notes: [],
      }));
      setFreshSpeciesList(snapshots);
    } catch (error) {
      console.error("刷新物种列表失败:", error);
    }
  }, []);

  const selectedTile: MapTileInfo | null = useMemo(() => {
    if (!mapData || selectedTileId == null) return null;
    return mapData.tiles.find((tile) => tile.id === selectedTileId) ?? null;
  }, [mapData, selectedTileId]);

  const selectedTileHabitats: HabitatEntry[] = useMemo(() => {
    if (!mapData || selectedTileId == null) return [];
    return mapData.habitats.filter((hab) => hab.tile_id === selectedTileId);
  }, [mapData, selectedTileId]);

  // --- Actions ---

  const captureCamera = useCallback((): CameraState | null => {
    return mapPanelRef.current?.getCameraState() ?? null;
  }, []);

  const restoreCamera = useCallback((snapshot: CameraState | null) => {
    if (!snapshot || !mapPanelRef.current) return;
    const apply = () => mapPanelRef.current?.setCameraState(snapshot);
    if (typeof window !== "undefined" && typeof requestAnimationFrame === "function") {
      requestAnimationFrame(apply);
    } else {
      apply();
    }
  }, []);

  async function refreshMap() {
    try {
      // 【修复】所有视图模式都获取完整的栖息地数据（不传speciesCode参数）
      // 只有适宜度模式需要特殊的适宜度计算，但这不影响栖息地数据获取
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
      if (data.tiles.length > 0 && selectedTileId == null) {
        setSelectedTileId(data.tiles[0].id);
      }
    } catch (error: any) {
      setError(`地图加载失败: ${error.message || "未知错误"}`);
    }
  }

  const changeViewMode = useCallback((mode: ViewMode, options?: { preserveCamera?: boolean }) => {
    if (mode === viewMode) return;

    const preserveCamera = options?.preserveCamera ?? true;
    const snapshot = preserveCamera ? captureCamera() : null;
    setViewMode(mode);

    const hasPrecomputedColors = Boolean(mapData && mapData.tiles.length > 0 && mapData.tiles[0].colors);

    if (hasPrecomputedColors) {
      setMapData((prev) => {
        if (!prev || !prev.tiles.length || !prev.tiles[0].colors) return prev;
        const updatedTiles = prev.tiles.map((tile) => ({
          ...tile,
          color: tile.colors?.[mode] || tile.color,
        }));
        return { ...prev, tiles: updatedTiles };
      });
      restoreCamera(snapshot);
    } else {
      fetchMapOverview(mode)
        .then((data) => setMapData(data))
        .catch(console.error)
        .finally(() => restoreCamera(snapshot));
    }
  }, [mapData, viewMode, captureCamera, restoreCamera]);

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    changeViewMode(mode, { preserveCamera: true });
  }, [changeViewMode]);

  const handleTileSelect = (tile: MapTileInfo) => {
    setSelectedTileId(tile.id);
    setDrawerMode("tile");
  };

  const handleSpeciesSelect = (id: string) => {
    setSelectedSpeciesId(id);
    // 物种详情现已集成到左侧 SpeciesPanel
    // 不再自动切换视图模式，避免地图跳动
    // 用户可以通过底部工具栏手动切换到"适宜度"视图查看该物种的分布
  };

  async function executeTurn(drafts: PressureDraft[]) {
    setLoading(true);
    setError(null);
    
    try {
      // 显示推演开始提示
      console.log("🌍 [演化] 开始推演，压力数:", drafts.length);
      console.log("📊 [演化] 正在解析环境压力...");
      
      console.log("⏳ [演化] 等待后端响应...");
      const startTime = Date.now();
      const next = await runTurn(drafts);
      const elapsed = Date.now() - startTime;
      
      console.log(`✅ [演化] 推演完成，收到报告数: ${next.length}，耗时: ${elapsed}ms`);
      console.log("📈 [演化] 更新物种数据和地图状态...");
      
      setReports((prev) => normalizeReports([...prev, ...next]));
      
      // 【关键】先更新回合状态和显示回合总结，再进行后台刷新
      // 这样即使刷新卡住，用户也能看到回合总结
      if (next.length > 0) {
        const latestReport = next[next.length - 1];
        console.log("🎉 [演化] 回合", latestReport.turn_index, "完成");
        setCurrentTurnIndex(latestReport.turn_index + 1); // 更新回合数（下一回合）
        setShowTurnSummary(true); // 显示回合总结模态窗
        
        // 检查成就解锁
        checkPendingAchievements();
        
        // 刷新能量状态
        dispatchEnergyChanged();
      }
      
      // 并行刷新，加快速度，并捕获错误避免阻塞
      // 【优化】添加超时保护，避免无限等待
      console.log("🔄 [演化] 刷新地图和物种列表...");
      const refreshStart = Date.now();
      const withTimeout = <T,>(promise: Promise<T>, ms: number, name: string): Promise<T | null> =>
        Promise.race([
          promise,
          new Promise<null>((_, reject) => setTimeout(() => reject(new Error(`${name} 超时`)), ms))
        ]).catch(e => { console.warn(`⚠️ ${name}:`, e.message); return null; });
      
      await Promise.all([
        withTimeout(refreshMap(), 30000, "刷新地图"),
        withTimeout(refreshSpeciesList(), 15000, "刷新物种列表"),
        withTimeout(refreshQueue(), 5000, "刷新队列"),
      ]);
      console.log(`✅ [演化] 刷新完成，耗时: ${Date.now() - refreshStart}ms`);
      
      setSpeciesRefreshTrigger(prev => prev + 1); // 触发物种详情刷新
      setPendingPressures([]);
      setShowPressureModal(false);
      
      // 清除族谱缓存，下次打开时会重新获取最新数据
      setLineageTree(null);
    } catch (error: any) {
      console.error("❌ [演化] 推演失败:", error);
      setError(`推演失败: ${error.message || "未知错误"}`);
    } finally {
      console.log("🏁 [演化] 关闭加载状态");
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

  async function handleBatchQueue(items: { drafts: PressureDraft[], rounds: number }[]) {
    if (!items.length) return;
    setLoading(true);
    try {
      for (const item of items) {
        await addQueue(item.drafts, item.rounds);
      }
      refreshQueue();
      setPendingPressures([]);
      setShowPressureModal(false);
    } catch (error: any) {
      setError(`队列添加失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  // 检查成就解锁 (必须在早期返回之前定义)
  const checkPendingAchievements = useCallback(async () => {
    try {
      const response = await fetch("/api/achievements/pending");
      const data = await response.json();
      if (data.events && data.events.length > 0) {
        // 显示第一个未通知的成就
        const event = data.events[0];
        setPendingAchievement(event.achievement);
      }
    } catch (e) {
      console.error("检查成就失败:", e);
    }
  }, []);

  // 记录探索行为（用于成就）(必须在早期返回之前定义)
  const recordExploration = useCallback(async (feature: string) => {
    try {
      await fetch(`/api/achievements/exploration/${feature}`, { method: "POST" });
      checkPendingAchievements();
    } catch (e) {
      console.error("记录探索失败:", e);
    }
  }, [checkPendingAchievements]);

  // --- Render: Scene Switching ---

  // 加载中界面（验证后端状态）
  if (scene === "loading") {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'radial-gradient(ellipse at center, rgba(8, 15, 12, 0.97), rgba(3, 7, 5, 0.99))',
        color: '#f0f4e8',
        gap: '1rem'
      }}>
        <div className="spinner" style={{ width: 40, height: 40 }}></div>
        <p style={{ fontSize: '1.1rem', opacity: 0.8 }}>正在验证游戏状态...</p>
      </div>
    );
  }

  if (scene === "menu") {
    return (
      <>
        <MainMenu
          onStart={(payload) => {
            // 【关键修复】创建新存档时重置所有游戏状态
            setReports([]);
            setLineageTree(null);
            setLineageError(null);
            setCurrentTurnIndex(0);
            setFreshSpeciesList([]);
            setMapData(null);
            setSelectedTileId(null);
            setSelectedSpeciesId(null);
            setDrawerMode("none");
            setOverlay("none");
            setError(null);
            
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

  // 1. Right Drawer Content (仅用于地块详情)
  const renderDrawerContent = () => {
    if (drawerMode === "tile" && selectedTile) {
      return (
        <ContextDrawer title="地块情报" onClose={() => setDrawerMode("none")} noPadding={true}>
          <TileDetailPanel
            tile={selectedTile}
            habitats={selectedTileHabitats}
            selectedSpecies={selectedSpeciesId}
            onSelectSpecies={handleSpeciesSelect}
          />
        </ContextDrawer>
      );
    }
    // 物种详情现在集成在 SpeciesPanel 中，不再需要单独的 drawer
    return null;
  };

  // 2. Modal Visibility Logic
  const hasActiveModal = Boolean(
    error || 
    loading ||  // 添加 loading 状态
    overlay !== "none" || 
    showSettings || 
    showPressureModal || 
    showCreateSpecies || 
    showGameSettings ||
    showTrends ||
    showLedger ||
    showTurnSummary || // 新增
    showMapHistory || // 新增
    showLogPanel ||
    showAIAssistant || // AI 助手
    showAITimeline || // AI 增强年鉴
    showAchievements || // 成就面板
    showHybridization || // 杂交面板
    showDivinePowers // 神力进阶面板
  );

  // 3. Modals Layer
  const renderModals = () => {
    if (!hasActiveModal) return null;

    return (
      <>
        {/* 日志面板 */}
        {showLogPanel && <LogPanel onClose={() => setShowLogPanel(false)} />}
        
        {/* AI 助手面板 */}
        {showAIAssistant && (
          <AIAssistantPanel onClose={() => setShowAIAssistant(false)} />
        )}
        
        {/* AI 增强年鉴 */}
        {showAITimeline && (
          <AIEnhancedTimeline 
            reports={reports} 
            onClose={() => setShowAITimeline(false)} 
          />
        )}

        {/* 成就面板 */}
        {showAchievements && (
          <AchievementsPanel onClose={() => setShowAchievements(false)} />
        )}

        {/* 杂交面板 */}
        {showHybridization && (
          <HybridizationPanel 
            onClose={() => setShowHybridization(false)} 
            onSuccess={() => {
              // 刷新物种列表和地图
              refreshSpeciesList();
              refreshMap();
              // 触发能量刷新
              dispatchEnergyChanged();
            }}
          />
        )}

        {/* 神力进阶面板 */}
        {showDivinePowers && (
          <div style={{
            position: 'fixed',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 1000,
          }}>
            <DivinePowersPanel onClose={() => setShowDivinePowers(false)} />
          </div>
        )}

        {/* 成就解锁通知 */}
        {pendingAchievement && (
          <AchievementNotification 
            achievement={pendingAchievement}
            onClose={() => setPendingAchievement(null)}
          />
        )}

        {/* 推演进度提示 - 如果已显示回合总结则不显示进度覆盖层 */}
        {loading && !showTurnSummary && <TurnProgressOverlay message="AI 正在分析生态系统变化..." showDetails={true} />}
        
        {/* 回合总结模态窗 */}
        {showTurnSummary && latestReport && (
          <TurnSummaryModal
            report={latestReport}
            previousReport={reports.length > 1 ? reports[reports.length - 2] : null}
            onClose={() => setShowTurnSummary(false)}
          />
        )}
        
        {/* 地图历史查看 */}
        {showMapHistory && (
          <MapHistoryView onClose={() => setShowMapHistory(false)} />
        )}
        
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
            <GenealogyView
              tree={lineageTree}
              loading={lineageLoading}
              error={lineageError}
              onRetry={() => { setLineageTree(null); setLineageError(null); }}
              onClose={() => setOverlay("none")}
            />
        )}
        {overlay === "chronicle" && (
          <AIEnhancedTimeline 
            reports={reports} 
            onClose={() => setOverlay("none")} 
          />
        )}
        {overlay === "niche" && (
          <FullscreenOverlay title="生态位对比" onClose={() => setOverlay("none")}>
            <NicheCompareView onClose={() => setOverlay("none")} />
          </FullscreenOverlay>
        )}
        {overlay === "foodweb" && (
          <FoodWebGraph
            speciesList={speciesList}
            onClose={() => setOverlay("none")}
            onSelectSpecies={(id) => {
              handleSpeciesSelect(id);
              setOverlay("none");
            }}
          />
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
          <EnhancedCreateSpeciesModal 
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
            onClose={() => {
              setShowGameSettings(false);
              setSettingsInitialView("menu");
            }}
            initialView={settingsInitialView}
            onBackToMenu={() => setScene("menu")}
            onSaveGame={async () => {
              try { await saveGame(currentSaveName); alert("保存成功！"); }
              catch (e: any) { setError(`保存失败: ${e.message}`); }
            }}
            onLoadGame={(saveName) => {
              // 【关键修复】加载存档时重置所有游戏状态
              setReports([]);
              setLineageTree(null);
              setLineageError(null);
              setFreshSpeciesList([]);
              
              setCurrentSaveName(saveName);
              refreshMap();
              // 加载存档后同步游戏状态
              fetchGameState()
                .then((state) => {
                  setCurrentTurnIndex(state.turn_index);
                  console.log(`[前端] 存档加载完成: 回合=${state.turn_index}`);
                })
                .catch(console.error);
              fetchHistory(20)
                .then((data) => setReports(normalizeReports(data)))
                .catch(console.error);
            }}
            onOpenAISettings={() => {
              setShowGameSettings(false);
              setShowSettings(true);
            }}
          />
        )}
        {showTrends && (
          <GlobalTrendsPanel
            reports={reports}
            onClose={() => setShowTrends(false)}
          />
        )}
        {showLedger && (
          <SpeciesLedger
            speciesList={speciesList}
            onClose={() => setShowLedger(false)}
            onSelectSpecies={(id) => {
              handleSpeciesSelect(id);
              // Optional: close ledger on select, or keep it open? 
              // Vic3 usually keeps ledger open, but here we have a drawer.
              // Let's keep it open for now, or maybe close it if it covers the drawer.
              // Given it's a modal, let's close it to show the drawer.
              setShowLedger(false);
            }}
          />
        )}
      </>
    );
  };

  return (
    <>
    {/* 全局氛围效果 */}
    <AmbientEffects 
      showScanlines={false} 
      showCorners={true} 
      showParticles={true}
      showGlow={true}
      particleCount={8}
    />
    <GameLayout
      mapLayer={
        <>
          <CanvasMapPanel
            ref={mapPanelRef}
            map={mapData}
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
          <MapModeToast
            viewMode={viewMode}
            hasSelectedSpecies={!!selectedSpeciesId}
          />
        </>
      }
      topBar={
        <TopBar
          turnIndex={currentTurnIndex || latestReport?.turn_index || 0}
          speciesCount={latestReport?.species.length ?? 0}
          queueStatus={status}
          saveName={currentSaveName}
          scenarioInfo={sessionInfo?.scenario}
          onOpenSettings={() => setShowGameSettings(true)}
          onSaveGame={async () => {
             try { await saveGame(currentSaveName); alert("保存成功！"); }
             catch (e: any) { setError(`保存失败: ${e.message}`); }
          }}
          onLoadGame={handleLoadGame}
          onOpenLedger={() => setShowLedger(true)}
          onOpenPressure={() => setShowPressureModal(true)}
          onOpenDivinePowers={() => setShowDivinePowers(true)}
        />
      }
      outlinerCollapsed={!showOutliner}
      outliner={
        showOutliner ? (
          <SpeciesPanel
            speciesList={speciesList}
            selectedSpeciesId={selectedSpeciesId}
            onSelectSpecies={(id) => {
              handleSpeciesSelect(id || "");
              if (!id) setDrawerMode("none");
            }}
            onCollapse={() => setShowOutliner(false)}
            refreshTrigger={speciesRefreshTrigger}
            previousPopulations={previousPopulations}
          />
        ) : (
          <div style={{ padding: '8px', display: 'flex', justifyContent: 'center', background: 'rgba(0,0,0,0.2)' }}>
             <button 
                className="btn-icon" 
                onClick={() => setShowOutliner(true)}
                title="展开物种列表"
                style={{ width: '32px', height: '32px' }}
             >
                👥
             </button>
          </div>
        )
      }
      lensBar={
        <LensBar
          currentMode={viewMode}
          onModeChange={handleViewModeChange}
          onToggleGenealogy={() => { setOverlay("genealogy"); recordExploration("genealogy"); }}
          onToggleHistory={() => setOverlay("chronicle")}
          onToggleNiche={() => { setOverlay("niche"); recordExploration("niche"); }}
          onToggleFoodWeb={() => { setOverlay("foodweb"); recordExploration("foodweb"); }}
          onOpenTrends={() => setShowTrends(true)}
          onOpenMapHistory={() => setShowMapHistory(true)}
          onOpenLogs={() => setShowLogPanel(true)}
          onCreateSpecies={() => setShowCreateSpecies(true)}
          onOpenHybridization={() => setShowHybridization(true)}
          onOpenAIAssistant={() => setShowAIAssistant(true)}
          onOpenAchievements={() => setShowAchievements(true)}
          onToggleHints={() => setShowHints(!showHints)}
          showHints={showHints}
          hintsInfo={hintsInfo}
        />
      }
      drawer={renderDrawerContent()}
      modals={hasActiveModal ? renderModals() : null}
    />
    
    {/* 智能提示面板（居中模态弹窗） */}
    {showHints && scene === "game" && (
      <GameHintsPanel 
        onSelectSpecies={handleSpeciesSelect}
        refreshTrigger={speciesRefreshTrigger}
        onClose={() => setShowHints(false)}
      />
    )}
    </>
  );
}

function normalizeReports(entries: TurnReport[]): TurnReport[] {
  const byTurn = new Map<number, TurnReport>();
  entries.forEach((report) => {
    byTurn.set(report.turn_index, report);
  });
  return Array.from(byTurn.values()).sort((a, b) => a.turn_index - b.turn_index);
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
      currentSaveName: parsed.currentSaveName || parsed.sessionInfo?.save_name || "",
      backendSessionId: parsed.backendSessionId,  // 保留后端会话ID
    };
  } catch { return null; }
}

function persistSession(payload: StoredSession) {
  try { window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload)); } catch {}
}

function clearStoredSession() {
  try { window.localStorage.removeItem(SESSION_STORAGE_KEY); } catch {}
}
