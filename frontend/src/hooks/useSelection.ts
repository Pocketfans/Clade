import { useState, useMemo, useCallback } from "react";
import type { MapTileInfo, HabitatEntry, MapOverview, SpeciesDetail } from "@/services/api.types";
import { fetchSpeciesDetail } from "@/services/api";

export function useSelection(mapData: MapOverview | null) {
  const [selectedTileId, setSelectedTileId] = useState<number | null>(null);
  const [selectedSpecies, setSelectedSpecies] = useState<string | null>(null);
  const [speciesDetail, setSpeciesDetail] = useState<SpeciesDetail | null>(null);
  const [showSpeciesWindow, setShowSpeciesWindow] = useState(false);
  const [tileWindow, setTileWindow] = useState<{
    tileId: number;
    anchor: { x: number; y: number };
  } | null>(null);

  const selectedTile: MapTileInfo | null = useMemo(() => {
    if (!mapData || selectedTileId == null) return null;
    return mapData.tiles.find((tile) => tile.id === selectedTileId) ?? null;
  }, [mapData, selectedTileId]);

  const selectedTileHabitats: HabitatEntry[] = useMemo(() => {
    if (!mapData || selectedTileId == null) return [];
    return mapData.habitats.filter((hab) => hab.tile_id === selectedTileId);
  }, [mapData, selectedTileId]);

  const handleTileSelect = useCallback((
    tile: MapTileInfo,
    anchor: { x: number; y: number }
  ) => {
    setSelectedTileId(tile.id);
    setTileWindow({ tileId: tile.id, anchor });
    setSelectedSpecies(null);
    setShowSpeciesWindow(false);
  }, []);

  const handleSpeciesSelect = useCallback(async (code: string) => {
    setSelectedSpecies(code);
    try {
      const detail = await fetchSpeciesDetail(code);
      setSpeciesDetail(detail);
      setShowSpeciesWindow(true);
    } catch (error) {
      console.error("加载物种详情失败:", error);
    }
  }, []);

  const closeTileWindow = useCallback(() => {
    setTileWindow(null);
  }, []);

  const closeSpeciesWindow = useCallback(() => {
    setShowSpeciesWindow(false);
    setSelectedSpecies(null);
  }, []);

  return {
    selectedTileId,
    selectedSpecies,
    speciesDetail,
    showSpeciesWindow,
    tileWindow,
    selectedTile,
    selectedTileHabitats,
    setSelectedTileId,
    setSelectedSpecies,
    handleTileSelect,
    handleSpeciesSelect,
    closeTileWindow,
    closeSpeciesWindow,
  };
}

