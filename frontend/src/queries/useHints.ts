/**
 * useHints - 游戏提示查询 Hook
 */

import { useState, useEffect, useCallback } from "react";
import { useSession } from "../providers/SessionProvider";
import { useGame } from "../providers/GameProvider";

interface HintsInfo {
  count: number;
  criticalCount: number;
  highCount: number;
}

interface Hint {
  priority: "critical" | "high" | "medium" | "low";
  message: string;
  category: string;
}

interface UseHintsResult {
  hintsInfo: HintsInfo;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useHints(): UseHintsResult {
  const { scene } = useSession();
  const { speciesRefreshTrigger } = useGame();
  
  const [hintsInfo, setHintsInfo] = useState<HintsInfo>({
    count: 0,
    criticalCount: 0,
    highCount: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (loading) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch("/api/hints");
      if (!res.ok) throw new Error("获取提示失败");
      
      const data = await res.json();
      const hints: Hint[] = data.hints || [];
      
      setHintsInfo({
        count: hints.length,
        criticalCount: hints.filter((h) => h.priority === "critical").length,
        highCount: hints.filter((h) => h.priority === "high").length,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "未知错误";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  // 游戏场景下自动轮询
  useEffect(() => {
    if (scene !== "game") return;

    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [scene, refresh, speciesRefreshTrigger]);

  return { hintsInfo, loading, error, refresh };
}
