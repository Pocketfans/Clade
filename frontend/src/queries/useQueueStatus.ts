/**
 * useQueueStatus - 队列状态查询 Hook
 */

import { useState, useEffect, useCallback } from "react";
import { useSession } from "@/providers/SessionProvider";
import { fetchQueueStatus } from "@/services/api";
import type { ActionQueueStatus } from "@/services/api.types";

interface UseQueueStatusResult {
  status: ActionQueueStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useQueueStatus(): UseQueueStatusResult {
  const { scene } = useSession();
  
  const [status, setStatus] = useState<ActionQueueStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (loading) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await fetchQueueStatus();
      setStatus(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "未知错误";
      setError(message);
      console.error("队列状态获取失败:", err);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  // 游戏场景下自动轮询
  useEffect(() => {
    if (scene !== "game") return;

    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [scene, refresh]);

  return { status, loading, error, refresh };
}
