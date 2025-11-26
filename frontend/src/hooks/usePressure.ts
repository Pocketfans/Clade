import { useState, useCallback } from "react";
import type { PressureDraft } from "../services/api.types";

export function usePressure() {
  const [pendingPressures, setPendingPressures] = useState<PressureDraft[]>([]);

  const addPressure = useCallback((pressure: PressureDraft) => {
    setPendingPressures(prev => [...prev, pressure]);
  }, []);

  const removePressure = useCallback((index: number) => {
    setPendingPressures(prev => prev.filter((_, i) => i !== index));
  }, []);

  const clearPressures = useCallback(() => {
    setPendingPressures([]);
  }, []);

  const updatePressure = useCallback((index: number, pressure: PressureDraft) => {
    setPendingPressures(prev => prev.map((p, i) => i === index ? pressure : p));
  }, []);

  return {
    pendingPressures,
    setPendingPressures,
    addPressure,
    removePressure,
    clearPressures,
    updatePressure,
  };
}

