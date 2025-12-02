/**
 * useDivinePowers - 神力系统数据管理 Hook
 */

import { useState, useCallback, useEffect } from "react";
import { dispatchEnergyChanged } from "../../EnergyBar";
import type {
  TabId,
  PathInfo,
  CurrentPath,
  SkillInfo,
  FaithSummary,
  Follower,
  MiracleInfo,
  WagerType,
  ActiveWager,
  WagerHistory,
} from "../types";

interface UseDivinePowersResult {
  // 当前标签页
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;

  // 神格路径数据
  availablePaths: PathInfo[];
  currentPath: CurrentPath | null;
  skills: SkillInfo[];

  // 信仰数据
  faithSummary: FaithSummary | null;

  // 神迹数据
  miracles: MiracleInfo[];
  currentEnergy: number;

  // 预言赌注数据
  wagerTypes: WagerType[];
  activeWagers: ActiveWager[];
  wagerHistory: WagerHistory[];

  // 状态
  loading: boolean;
  error: string | null;
  success: string | null;

  // 操作
  choosePath: (path: string) => Promise<boolean>;
  useSkill: (skillId: string, targetSpecies?: string) => Promise<boolean>;
  blessSpecies: (lineageCode: string) => Promise<boolean>;
  sanctifySpecies: (lineageCode: string) => Promise<boolean>;
  activateMiracle: (miracleId: string, targetData?: Record<string, unknown>) => Promise<boolean>;
  placeWager: (wagerType: string, betAmount: number, targetSpecies: string, secondarySpecies?: string) => Promise<boolean>;

  // 刷新
  refreshAll: () => Promise<void>;
  clearMessages: () => void;
}

export function useDivinePowers(): UseDivinePowersResult {
  const [activeTab, setActiveTab] = useState<TabId>("path");

  // 神格路径
  const [availablePaths, setAvailablePaths] = useState<PathInfo[]>([]);
  const [currentPath, setCurrentPath] = useState<CurrentPath | null>(null);
  const [skills, setSkills] = useState<SkillInfo[]>([]);

  // 信仰
  const [faithSummary, setFaithSummary] = useState<FaithSummary | null>(null);

  // 神迹
  const [miracles, setMiracles] = useState<MiracleInfo[]>([]);
  const [currentEnergy, setCurrentEnergy] = useState(0);

  // 赌注
  const [wagerTypes, setWagerTypes] = useState<WagerType[]>([]);
  const [activeWagers, setActiveWagers] = useState<ActiveWager[]>([]);
  const [wagerHistory, setWagerHistory] = useState<WagerHistory[]>([]);

  // 状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 加载神格路径
  const loadPaths = useCallback(async () => {
    try {
      const res = await fetch("/api/divine/paths");
      if (!res.ok) throw new Error("获取神格路径失败");
      const data = await res.json();
      setAvailablePaths(data.available_paths || []);
      setCurrentPath(data.current_path || null);
    } catch (err: unknown) {
      console.error("加载神格路径失败:", err);
    }
  }, []);

  // 加载技能
  const loadSkills = useCallback(async () => {
    try {
      const res = await fetch("/api/divine/skills");
      if (!res.ok) throw new Error("获取技能失败");
      const data = await res.json();
      setSkills(data.skills || []);
    } catch (err: unknown) {
      console.error("加载技能失败:", err);
    }
  }, []);

  // 加载信仰
  const loadFaith = useCallback(async () => {
    try {
      const res = await fetch("/api/divine/faith");
      if (!res.ok) throw new Error("获取信仰数据失败");
      const data = await res.json();
      setFaithSummary(data);
    } catch (err: unknown) {
      console.error("加载信仰失败:", err);
    }
  }, []);

  // 加载神迹
  const loadMiracles = useCallback(async () => {
    try {
      const res = await fetch("/api/divine/miracles");
      if (!res.ok) throw new Error("获取神迹失败");
      const data = await res.json();
      setMiracles(data.miracles || []);
      setCurrentEnergy(data.current_energy || 0);
    } catch (err: unknown) {
      console.error("加载神迹失败:", err);
    }
  }, []);

  // 加载赌注
  const loadWagers = useCallback(async () => {
    try {
      const res = await fetch("/api/divine/wagers");
      if (!res.ok) throw new Error("获取赌注失败");
      const data = await res.json();
      setWagerTypes(data.wager_types || []);
      setActiveWagers(data.active_wagers || []);
      setWagerHistory(data.history || []);
      setCurrentEnergy(data.current_energy || 0);
    } catch (err: unknown) {
      console.error("加载赌注失败:", err);
    }
  }, []);

  // 刷新所有数据
  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadPaths(), loadSkills(), loadFaith(), loadMiracles(), loadWagers()]);
    } finally {
      setLoading(false);
    }
  }, [loadPaths, loadSkills, loadFaith, loadMiracles, loadWagers]);

  // 选择神格路径
  const choosePath = useCallback(async (path: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/choose-path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "选择路径失败");
      }
      setSuccess("神格路径已选择！");
      await loadPaths();
      await loadSkills();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadPaths, loadSkills]);

  // 使用技能
  const useSkill = useCallback(async (skillId: string, targetSpecies?: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/use-skill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_id: skillId, target_species: targetSpecies }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "技能施放失败");
      }
      const data = await res.json();
      setSuccess(data.message || "技能施放成功！");
      dispatchEnergyChanged();
      await loadSkills();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadSkills]);

  // 祝福物种
  const blessSpecies = useCallback(async (lineageCode: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/bless", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lineage_code: lineageCode }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "祝福失败");
      }
      setSuccess("物种已获得祝福！");
      dispatchEnergyChanged();
      await loadFaith();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadFaith]);

  // 圣化物种
  const sanctifySpecies = useCallback(async (lineageCode: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/sanctify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lineage_code: lineageCode }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "圣化失败");
      }
      setSuccess("物种已圣化！");
      dispatchEnergyChanged();
      await loadFaith();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadFaith]);

  // 激活神迹
  const activateMiracle = useCallback(async (miracleId: string, targetData?: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/activate-miracle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ miracle_id: miracleId, ...targetData }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "神迹激活失败");
      }
      const data = await res.json();
      setSuccess(data.message || "神迹已激活！");
      dispatchEnergyChanged();
      await loadMiracles();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadMiracles]);

  // 下注
  const placeWager = useCallback(async (
    wagerType: string,
    betAmount: number,
    targetSpecies: string,
    secondarySpecies?: string
  ): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/divine/place-wager", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wager_type: wagerType,
          bet_amount: betAmount,
          target_species: targetSpecies,
          secondary_species: secondarySpecies,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "下注失败");
      }
      setSuccess("预言赌注已下！");
      dispatchEnergyChanged();
      await loadWagers();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadWagers]);

  const clearMessages = useCallback(() => {
    setError(null);
    setSuccess(null);
  }, []);

  // 初始化
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  return {
    activeTab,
    setActiveTab,
    availablePaths,
    currentPath,
    skills,
    faithSummary,
    miracles,
    currentEnergy,
    wagerTypes,
    activeWagers,
    wagerHistory,
    loading,
    error,
    success,
    choosePath,
    useSkill,
    blessSpecies,
    sanctifySpecies,
    activateMiracle,
    placeWager,
    refreshAll,
    clearMessages,
  };
}

