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
  const { scene } = useSession();

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
  const speciesList = useMemo(() => {
    const reportSpecies = latestReport?.species || [];
    if (freshSpeciesList.length === 0) return reportSpecies;

    const merged: SpeciesSnapshot[] = [];
    const seen = new Set<string>();

    for (const s of reportSpecies) {
      merged.push(s);
      seen.add(s.lineage_code);
    }

    for (const s of freshSpeciesList) {
      if (!seen.has(s.lineage_code)) {
        merged.push(s);
      }
    }

    return merged;
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
      console.error("刷新队列状态失败:", err);
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // ============ 初始化 Effects ============

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

    // 队列轮询
    const interval = setInterval(refreshQueue, 5000);
    return () => clearInterval(interval);
  }, [scene, refreshMap, refreshQueue]);

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
