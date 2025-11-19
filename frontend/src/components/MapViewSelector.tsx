import { useState } from "react";

export type ViewMode = "terrain" | "terrain_type" | "elevation" | "biodiversity" | "climate" | "suitability";

interface Props {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export function MapViewSelector({ currentMode, onModeChange }: Props) {
  const modes: Array<{ value: ViewMode; label: string; description: string }> = [
    { value: "terrain", label: "基本地图", description: "真实世界地图风格，综合地形、覆盖物与气候" },
    { value: "terrain_type", label: "地形图", description: "纯地形分类（深海/浅海/平原/丘陵/山地）" },
    { value: "elevation", label: "海拔图", description: "海拔高度渐变色阶（-11000m至8848m）" },
    { value: "biodiversity", label: "生物热力图", description: "物种分布与多样性热力图" },
    { value: "climate", label: "气候图", description: "气候带与温度分布" },
    { value: "suitability", label: "适宜度", description: "当前选中物种的生存适宜度分布" },
  ];

  return (
    <div className="map-view-selector">
      {modes.map((mode) => (
        <button
          key={mode.value}
          type="button"
          className={`view-mode-btn ${currentMode === mode.value ? "active" : ""}`}
          onClick={() => onModeChange(mode.value)}
          title={mode.description}
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}

