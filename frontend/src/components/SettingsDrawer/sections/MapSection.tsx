/**
 * MapSection - 地图环境配置
 */

import { memo, type Dispatch } from "react";
import type { MapEnvironmentConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionCard, ConfigGroup, SliderRow, NumberInput, ToggleRow, ActionButton } from "../common";
import { DEFAULT_MAP_ENVIRONMENT_CONFIG } from "../constants";

interface MapSectionProps {
  config: MapEnvironmentConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const MapSection = memo(function MapSection({
  config,
  dispatch,
}: MapSectionProps) {
  const handleUpdate = (updates: Partial<MapEnvironmentConfig>) => {
    dispatch({ type: "UPDATE_MAP_ENV", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_MAP_ENV" });
  };

  const c = { ...DEFAULT_MAP_ENVIRONMENT_CONFIG, ...config };

  return (
    <div className="settings-section">
      <div className="section-header-bar">
        <div>
          <h2>🗺️ 地图环境配置</h2>
          <p className="section-subtitle">控制地图气候、地形和灾害事件</p>
        </div>
        <ActionButton label="恢复默认" onClick={handleReset} variant="secondary" icon="↻" />
      </div>

      <SectionCard title="气候偏移" icon="🌡️" desc="全局气候参数调整">
        <SliderRow
          label="全局温度偏移"
          value={c.global_temperature_offset ?? 0}
          min={-10}
          max={10}
          step={0.5}
          onChange={(v) => handleUpdate({ global_temperature_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}°C`}
        />
        <SliderRow
          label="全局湿度偏移"
          value={c.global_humidity_offset ?? 0}
          min={-0.3}
          max={0.3}
          step={0.05}
          onChange={(v) => handleUpdate({ global_humidity_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="极端气候频率"
          value={c.extreme_climate_frequency ?? 0.05}
          min={0}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ extreme_climate_frequency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="极端气候幅度"
          value={c.extreme_climate_amplitude ?? 0.3}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ extreme_climate_amplitude: v })}
        />
      </SectionCard>

      <SectionCard title="海平面与地形" icon="🌊" desc="海洋和地形变化">
        <SliderRow
          label="海平面偏移"
          value={c.sea_level_offset ?? 0}
          min={-50}
          max={50}
          step={5}
          onChange={(v) => handleUpdate({ sea_level_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v}m`}
        />
        <SliderRow
          label="海平面变化率"
          desc="每回合海平面变化"
          value={c.sea_level_change_rate ?? 0}
          min={-1}
          max={1}
          step={0.1}
          onChange={(v) => handleUpdate({ sea_level_change_rate: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}m/回合`}
        />
        <SliderRow
          label="地形侵蚀率"
          value={c.terrain_erosion_rate ?? 0.01}
          min={0}
          max={0.1}
          step={0.005}
          onChange={(v) => handleUpdate({ terrain_erosion_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(1)}%`}
        />
      </SectionCard>

      <SectionCard title="生物群系承载力" icon="🏞️" desc="不同生物群系的承载力倍数">
        <ConfigGroup title="陆地生物群系">
          <SliderRow
            label="热带雨林"
            value={c.biome_capacity_rainforest ?? 1.5}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_rainforest: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="温带森林"
            value={c.biome_capacity_temperate ?? 1.2}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_temperate: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="草原"
            value={c.biome_capacity_grassland ?? 1.0}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_grassland: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="沙漠"
            value={c.biome_capacity_desert ?? 0.3}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ biome_capacity_desert: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="苔原"
            value={c.biome_capacity_tundra ?? 0.4}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ biome_capacity_tundra: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
        </ConfigGroup>

        <ConfigGroup title="海洋生物群系">
          <SliderRow
            label="深海"
            value={c.biome_capacity_deep_sea ?? 0.5}
            min={0.1}
            max={2}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_deep_sea: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="浅海"
            value={c.biome_capacity_shallow_sea ?? 1.3}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_shallow_sea: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
        </ConfigGroup>
      </SectionCard>

      <SectionCard title="地质灾害" icon="🌋" desc="自然灾害的频率和强度">
        <ConfigGroup title="火山">
          <SliderRow
            label="频率"
            value={c.volcano_frequency ?? 0.02}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ volcano_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="影响半径"
            value={c.volcano_impact_radius ?? 3}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ volcano_impact_radius: v })}
            suffix="格"
          />
          <SliderRow
            label="破坏强度"
            value={c.volcano_damage_intensity ?? 0.8}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ volcano_damage_intensity: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="洪水">
          <SliderRow
            label="频率"
            value={c.flood_frequency ?? 0.03}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ flood_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="影响范围"
            value={c.flood_impact_radius ?? 2}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ flood_impact_radius: v })}
            suffix="格"
          />
        </ConfigGroup>

        <ConfigGroup title="干旱">
          <SliderRow
            label="频率"
            value={c.drought_frequency ?? 0.04}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ drought_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="持续时间"
            value={c.drought_duration ?? 2}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ drought_duration: v })}
            suffix="回合"
          />
        </ConfigGroup>

        <ConfigGroup title="地震">
          <SliderRow
            label="频率"
            value={c.earthquake_frequency ?? 0.01}
            min={0}
            max={0.05}
            step={0.005}
            onChange={(v) => handleUpdate({ earthquake_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
        </ConfigGroup>
      </SectionCard>

      <SectionCard title="密度惩罚" icon="👥" desc="地块过度拥挤的惩罚">
        <SliderRow
          label="同地块密度惩罚"
          value={c.same_tile_density_penalty ?? 0.15}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ same_tile_density_penalty: v })}
        />
        <SliderRow
          label="过度拥挤阈值"
          value={c.overcrowding_threshold ?? 0.7}
          min={0.3}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ overcrowding_threshold: v })}
        />
        <SliderRow
          label="拥挤惩罚上限"
          value={c.overcrowding_max_penalty ?? 0.4}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ overcrowding_max_penalty: v })}
        />
      </SectionCard>

      <SectionCard title="地图叠加层" icon="🗺️" desc="可视化热力图开关">
        <ToggleRow
          label="资源热力图"
          checked={c.show_resource_overlay ?? false}
          onChange={(v) => handleUpdate({ show_resource_overlay: v })}
        />
        <ToggleRow
          label="猎物丰度图"
          checked={c.show_prey_overlay ?? false}
          onChange={(v) => handleUpdate({ show_prey_overlay: v })}
        />
        <ToggleRow
          label="宜居度热力图"
          checked={c.show_suitability_overlay ?? false}
          onChange={(v) => handleUpdate({ show_suitability_overlay: v })}
        />
        <ToggleRow
          label="竞争压力图"
          checked={c.show_competition_overlay ?? false}
          onChange={(v) => handleUpdate({ show_competition_overlay: v })}
        />
        <ToggleRow
          label="温度分布图"
          checked={c.show_temperature_overlay ?? false}
          onChange={(v) => handleUpdate({ show_temperature_overlay: v })}
        />
        <ToggleRow
          label="湿度分布图"
          checked={c.show_humidity_overlay ?? false}
          onChange={(v) => handleUpdate({ show_humidity_overlay: v })}
        />
      </SectionCard>
    </div>
  );
});

