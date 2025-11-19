import { useState, useCallback } from "react";

export type OverlayView = "none" | "genealogy" | "chronicle" | "niche";

export function useModals() {
  const [overlay, setOverlay] = useState<OverlayView>("none");
  const [showSettings, setShowSettings] = useState(false);
  const [showGameSettings, setShowGameSettings] = useState(false);
  const [showPressureModal, setShowPressureModal] = useState(false);

  const openOverlay = useCallback((view: OverlayView) => {
    setOverlay(view);
  }, []);

  const closeOverlay = useCallback(() => {
    setOverlay("none");
  }, []);

  const toggleSettings = useCallback(() => {
    setShowSettings(prev => !prev);
  }, []);

  const toggleGameSettings = useCallback(() => {
    setShowGameSettings(prev => !prev);
  }, []);

  const togglePressureModal = useCallback(() => {
    setShowPressureModal(prev => !prev);
  }, []);

  return {
    overlay,
    showSettings,
    showGameSettings,
    showPressureModal,
    setOverlay,
    setShowSettings,
    setShowGameSettings,
    setShowPressureModal,
    openOverlay,
    closeOverlay,
    toggleSettings,
    toggleGameSettings,
    togglePressureModal,
  };
}

