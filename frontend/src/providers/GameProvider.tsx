/**
 * GameProvider - 游戏数据管理
 * 
 * 职责：
 * - 地图数据 (mapData)
 * - 回合报告 (reports, currentTurnIndex)
 * - 物种列表 (speciesList, freshSpeciesList)
 * - 族谱数据 (lineageTree)
 * - UI配置 (uiConfig, pressureTemplates)
 * - 队列状态 (queueStatus)
 * - 全局加载/错误状态
 */

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import type {
  MapOverview,
  TurnReport,
  LineageTree,
  SpeciesSnapshot,
  UIConfig,
  PressureTemplate,
  ActionQueueStatus,
} from "@/services/api.types";
import type { GameDataState, GameDataActions } from "./types";
import type { ViewMode } from "@/components/MapViewSelector";

// 使用模块化 API
import {
  fetchMapOverview,
  fetchLineageTree,
  invalidateLineageCache,
  fetchUIConfig,
  updateUIConfig as apiUpdateUIConfig,
  fetchPressureTemplates,
  fetchQueueStatus,
  fetchSpeciesList,
} from "@/services/api";

import { useSession } from "./SessionProvider";

// ============ 默认配置 ============
const defaultConfig: UIConfig = {
  providers: {},
  capability_routes: {},
  ai_provider: null,
  ai_model: null,
  ai_timeout: 60,
  embedding_provider: null,
};

// ============ 报告去重工具 ============
function normalizeReports(entries: TurnReport[]): TurnReport[] {
  const byTurn = new Map<number, TurnReport>();
  entries.forEach((report) => {
    byTurn.set(report.turn_index, report);
  });
  return Array.from(byTurn.values()).sort((a, b) => a.turn_index - b.turn_index);
}

// ============ Context ============
interface GameContextValue extends GameDataState, GameDataActions {
  // 派生数据
  latestReport: TurnReport | null;
  previousReport: TurnReport | null;
  previousPopulations: Map<string, number>;
}

const GameContext = createContext<GameContextValue | null>(null);

// ============ Provider ============
interface GameProviderProps {
  children: ReactNode;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

export function GameProvider({ children, viewMode, onViewModeChange }: GameProviderProps) {
  const { scene, currentSaveName } = useSession();
  
  // 追踪上一个存档名称，用于检测存档变化
  const lastSaveNameRef = useRef<string | null>(null);

  // ============ 状态 ============
  const [mapData, setMapData] = useState<MapOverview | null>(null);
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [currentTurnIndex, setCurrentTurnIndex] = useState<number>(0);
  const [freshSpeciesList, setFreshSpeciesList] = useState<SpeciesSnapshot[]>([]);
  const [lineageTree, setLineageTree] = useState<LineageTree | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [uiConfig, setUIConfig] = useState<UIConfig>(defaultConfig);
  const [pressureTemplates, setPressureTemplates] = useState<PressureTemplate[]>([]);
  const [queueStatus, setQueueStatus] = useState<ActionQueueStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speciesRefreshTrigger, setSpeciesRefreshTrigger] = useState(0);

  // ============ 派生数据 ============
  const latestReport = useMemo(
    () => (reports.length > 0 ? reports[reports.length - 1] : null),
    [reports]
  );

  const previousReport = useMemo(
    () => (reports.length > 1 ? reports[reports.length - 2] : null),
    [reports]
  );

  const previousPopulations = useMemo(() => {
    const map = new Map<string, number>();
    if (previousReport?.species) {
      for (const s of previousReport.species) {
        map.set(s.lineage_code, s.population);
      }
    }
    return map;
  }, [previousReport]);

  // 合并物种列表（报告 + 实时）
  // 【修复】用 freshSpeciesList 中的数据覆盖 reportSpecies 中的同名物种
  const speciesList = useMemo(() => {
    const reportSpecies = latestReport?.species || [];
    if (freshSpeciesList.length === 0) return reportSpecies;

    // 使用 Map 确保唯一性，freshSpeciesList 优先（更新的数据）
    const speciesMap = new Map<string, SpeciesSnapshot>();
    
    // 先添加报告中的数据
    for (const s of reportSpecies) {
      speciesMap.set(s.lineage_code, s);
    }
    
    // 用实时数据覆盖（freshSpeciesList 是最新的）
    for (const s of freshSpeciesList) {
      speciesMap.set(s.lineage_code, s);
    }

    return Array.from(speciesMap.values());
  }, [freshSpeciesList, latestReport]);

  // ============ Actions ============
  const refreshMap = useCallback(async () => {
    try {
      const data = await fetchMapOverview(viewMode);
      setMapData(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "未知错误";
      setError(`地图加载失败: ${message}`);
    }
  }, [viewMode]);

  const refreshSpeciesList = useCallback(async () => {
    try {
      const list = await fetchSpeciesList();
      const snapshots: SpeciesSnapshot[] = list.map((item) => ({
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
    } catch (err) {
      console.error("刷新物种列表失败:", err);
    }
  }, []);

  const triggerSpeciesRefresh = useCallback(() => {
    setSpeciesRefreshTrigger((prev) => prev + 1);
  }, []);

  const addReports = useCallback((newReports: TurnReport[]) => {
    setReports((prev) => normalizeReports([...prev, ...newReports]));
  }, []);

  const loadLineageTree = useCallback(async () => {
    if (lineageTree || lineageLoading) return;
    setLineageLoading(true);
    try {
      const tree = await fetchLineageTree();
      setLineageTree(tree);
      setLineageError(null);
    } catch (err) {
      console.error(err);
      setLineageError("族谱数据加载失败");
    } finally {
      setLineageLoading(false);
    }
  }, [lineageTree, lineageLoading]);

  const invalidateLineage = useCallback(() => {
    setLineageTree(null);
    invalidateLineageCache();
  }, []);

  const updateUIConfigAction = useCallback(async (config: UIConfig) => {
    const saved = await apiUpdateUIConfig(config);
    setUIConfig(saved);
  }, []);

  const refreshQueue = useCallback(async () => {
    try {
      const status = await fetchQueueStatus();
      setQueueStatus(status);
    } catch (err) {
      // 推演期间超时是正常的，静默处理避免刷屏
      // 只在非超时错误时打印
      if (err instanceof Error && !err.message.includes("超时")) {
        console.warn("刷新队列状态失败:", err);
      }
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // ============ 初始化 Effects ============

  // 【关键修复】监听存档变化，重置游戏数据
  // 这解决了创建新存档后旧数据残留的问题
  useEffect(() => {
    // 当回到主菜单时，重置追踪的存档名称
    // 这样下次进入任何存档时都会触发数据刷新
    if (scene === "menu") {
      lastSaveNameRef.current = null;
      return;
    }
    
    if (scene !== "game") return;
    
    const lastSaveName = lastSaveNameRef.current;
    
    // 检测是否是新存档（存档名称变化或首次进入）
    if (lastSaveName !== currentSaveName) {
      if (lastSaveName !== null) {
        console.log(`[Game] 检测到存档变化: "${lastSaveName}" -> "${currentSaveName}"，重置游戏数据`);
      } else {
        console.log(`[Game] 首次进入存档: "${currentSaveName}"，初始化游戏数据`);
      }
      
      // 重置所有游戏数据
      setReports([]);
      setFreshSpeciesList([]);
      setCurrentTurnIndex(0);
      setLineageTree(null);
      setLineageError(null);
      setMapData(null);
      setError(null);
      
      // 重新获取数据
      refreshMap();
      refreshSpeciesList();
      refreshQueue();
      invalidateLineageCache();
    }
    
    // 更新追踪的存档名称
    lastSaveNameRef.current = currentSaveName;
  }, [scene, currentSaveName, refreshMap, refreshSpeciesList, refreshQueue]);

  // 加载全局配置（无论场景）
  useEffect(() => {
    fetchUIConfig()
      .then((config) => {
        console.log("[Game] 配置加载成功");
        setUIConfig(config);
      })
      .catch((err) => {
        console.error("[Game] 配置加载失败:", err);
        setUIConfig(defaultConfig);
      });
    fetchPressureTemplates().then(setPressureTemplates).catch(console.error);
  }, []);

  // 游戏场景初始化
  useEffect(() => {
    if (scene !== "game") return;
    refreshMap();
    refreshQueue();
    refreshSpeciesList(); // 【修复】确保物种列表也被刷新

    // 队列轮询（间隔延长到 10 秒，减少推演期间的超时错误）
    const interval = setInterval(refreshQueue, 10000);
    return () => clearInterval(interval);
  }, [scene, refreshMap, refreshQueue, refreshSpeciesList]);

  // ============ Context Value ============
  const value: GameContextValue = {
    // State
    mapData,
    reports,
    currentTurnIndex,
    speciesList,
    freshSpeciesList,
    lineageTree,
    lineageLoading,
    lineageError,
    uiConfig,
    pressureTemplates,
    queueStatus,
    loading,
    error,
    speciesRefreshTrigger,
    // Derived
    latestReport,
    previousReport,
    previousPopulations,
    // Actions
    refreshMap,
    setMapData,
    addReports,
    setReports,
    setCurrentTurnIndex,
    refreshSpeciesList,
    setFreshSpeciesList,
    triggerSpeciesRefresh,
    loadLineageTree,
    invalidateLineage,
    setLineageTree,
    setUIConfig,
    updateUIConfig: updateUIConfigAction,
    refreshQueue,
    setError,
    setLoading,
    clearError,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

// ============ Hook ============
export function useGame(): GameContextValue {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error("useGame must be used within GameProvider");
  }
  return context;
}

// 导出 Context 供高级用法
export { GameContext };
