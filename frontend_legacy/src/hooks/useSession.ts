import { useState, useEffect, useCallback } from "react";
import type { StartPayload } from "../components/MainMenu";

type Scene = "menu" | "game";

type StoredSession = {
  scene: Scene;
  sessionInfo: StartPayload | null;
  currentSaveName: string;
};

const SESSION_STORAGE_KEY = "evosandbox:session";

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

export function useSession() {
  const restoredSession = typeof window !== "undefined" ? readStoredSession() : null;
  
  const [scene, setScene] = useState<Scene>(restoredSession?.scene ?? "menu");
  const [sessionInfo, setSessionInfo] = useState<StartPayload | null>(
    restoredSession?.sessionInfo ?? null
  );
  const [currentSaveName, setCurrentSaveName] = useState<string>(
    restoredSession?.currentSaveName ??
      restoredSession?.sessionInfo?.save_name ??
      ""
  );

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

  const startGame = useCallback((payload: StartPayload) => {
    setSessionInfo(payload);
    setCurrentSaveName(payload.save_name || `存档_${Date.now()}`);
    setScene("game");
  }, []);

  const backToMenu = useCallback(() => {
    setScene("menu");
  }, []);

  return {
    scene,
    sessionInfo,
    currentSaveName,
    setScene,
    setSessionInfo,
    setCurrentSaveName,
    startGame,
    backToMenu,
  };
}

