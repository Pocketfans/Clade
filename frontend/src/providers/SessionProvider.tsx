/**
 * SessionProvider - 会话管理
 * 
 * 职责：
 * - 管理场景切换 (menu/loading/game)
 * - 会话持久化（localStorage）
 * - 后端状态验证（检测后端重启）
 * - 会话恢复逻辑
 */

import { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import type { StartPayload } from "@/components/MainMenu";
import type { Scene, SessionState, SessionActions } from "./types";
import { fetchGameState } from "@/services/api";

// ============ Constants ============
const SESSION_STORAGE_KEY = "evosandbox:session";

type StoredSession = {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
  backendSessionId?: string;
};

// ============ Storage Helpers ============
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
      backendSessionId: parsed.backendSessionId,
    };
  } catch {
    return null;
  }
}

function persistSession(payload: StoredSession) {
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    console.warn("[Session] 持久化失败");
  }
}

function clearStoredSession() {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// ============ Context ============
interface SessionContextValue extends SessionState, SessionActions {}

const SessionContext = createContext<SessionContextValue | null>(null);

// ============ Provider ============
interface SessionProviderProps {
  children: ReactNode;
}

export function SessionProvider({ children }: SessionProviderProps) {
  // 尝试恢复会话
  const storedSession = typeof window !== "undefined" ? readStoredSession() : null;

  const [scene, setSceneRaw] = useState<Scene>(storedSession ? "loading" : "menu");
  const [sessionInfo, setSessionInfo] = useState<StartPayload | null>(
    storedSession?.sessionInfo ?? null
  );
  const [currentSaveName, setCurrentSaveName] = useState<string>(
    storedSession?.currentSaveName ?? storedSession?.sessionInfo?.save_name ?? ""
  );
  const [backendSessionId, setBackendSessionId] = useState<string>(
    storedSession?.backendSessionId ?? ""
  );

  // 场景切换包装：自动处理持久化
  const setScene = useCallback((newScene: Scene) => {
    setSceneRaw(newScene);
  }, []);

  // 后端状态验证（检测后端重启）
  useEffect(() => {
    if (scene !== "loading") return;

    fetchGameState()
      .then((state) => {
        const storedBackendId = storedSession?.backendSessionId;
        const currentBackendId = state?.backend_session_id;

        if (!currentBackendId) {
          console.log("[Session] 后端未返回会话ID，回到主菜单");
          clearStoredSession();
          setSceneRaw("menu");
          return;
        }

        if (storedBackendId && storedBackendId !== currentBackendId) {
          console.log("[Session] 后端已重启，会话ID不匹配，回到主菜单");
          clearStoredSession();
          setSceneRaw("menu");
          return;
        }

        if (state && state.turn_index >= 0) {
          console.log("[Session] 后端状态有效，恢复游戏");
          setBackendSessionId(currentBackendId);
          setSceneRaw("game");
        } else {
          console.log("[Session] 后端状态无效，回到主菜单");
          clearStoredSession();
          setSceneRaw("menu");
        }
      })
      .catch((err) => {
        console.log("[Session] 后端连接失败:", err);
        clearStoredSession();
        setSceneRaw("menu");
      });
  }, [scene]);

  // 持久化逻辑
  useEffect(() => {
    if (scene === "game") {
      persistSession({ scene, sessionInfo, currentSaveName, backendSessionId });
    } else if (scene === "menu") {
      clearStoredSession();
    }
  }, [scene, sessionInfo, currentSaveName, backendSessionId]);

  // Actions
  const startGame = useCallback((payload: StartPayload) => {
    setSessionInfo(payload);
    setCurrentSaveName(payload.save_name || `存档_${Date.now()}`);
    setSceneRaw("game");
  }, []);

  const backToMenu = useCallback(() => {
    setSceneRaw("menu");
  }, []);

  const resetSession = useCallback(() => {
    setSessionInfo(null);
    setCurrentSaveName("");
    setBackendSessionId("");
    clearStoredSession();
    setSceneRaw("menu");
  }, []);

  const value: SessionContextValue = {
    // State
    scene,
    sessionInfo,
    currentSaveName,
    backendSessionId,
    // Actions
    startGame,
    backToMenu,
    setScene,
    setBackendSessionId,
    resetSession,
  };

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

// ============ Hook ============
export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return context;
}

// 导出 Context 供高级用法
export { SessionContext };

