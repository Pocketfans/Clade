/**
 * MapSection - 地图环境配置
 * 单列布局，控制地图气候、地形和灾害事件
 */

import { memo, type Dispatch } from "react";
import type { MapEnvironmentConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ToggleRow, ActionButton, InfoBox } from "../common/Controls";
import { DEFAULT_MAP_ENVIRONMENT_CONFIG } from "../constants";

interface Props {
  config: MapEnvironmentConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const MapSection = memo(function MapSection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<MapEnvironmentConfig>) => {
    dispatch({ type: "UPDATE_MAP_ENV", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_MAP_ENV" });
  };

  const c = { ...DEFAULT_MAP_ENVIRONMENT_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🗺️"
        title="地图环境配置"
        subtitle="控制地图气候、地形和灾害事件的参数"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 概念说明 */}
      <InfoBox variant="info" title="环境与物种适应">
        地图由多个地块组成，每个地块有独特的气候（温度、湿度）和资源条件。物种根据自身的环境偏好分布在不同地块上。
      </InfoBox>

      {/* 气候偏移 */}
      <Card title="气候偏移" icon="🌡️" desc="全局气候参数调整">
        <InfoBox>
          气候偏移会应用到所有地块，模拟全球性的气候变化，如冰期、温室效应等长期趋势。
        </InfoBox>
        <SliderRow
          label="全局温度偏移"
          desc="所有地块温度的统一调整。+值表示全球变暖，-值表示全球变冷"
          value={c.global_temperature_offset ?? 0}
          min={-10}
          max={10}
          step={0.5}
          onChange={(v) => handleUpdate({ global_temperature_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}°C`}
        />
        <SliderRow
          label="全局湿度偏移"
          desc="所有地块湿度的统一调整。+值表示更湿润，-值表示更干燥"
          value={c.global_humidity_offset ?? 0}
          min={-0.3}
          max={0.3}
          step={0.05}
          onChange={(v) => handleUpdate({ global_humidity_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="极端气候频率"
          desc="每回合发生极端气候事件的概率"
          value={c.extreme_climate_frequency ?? 0.05}
          min={0}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ extreme_climate_frequency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="极端气候幅度"
          desc="极端气候事件的强度系数"
          value={c.extreme_climate_amplitude ?? 0.3}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ extreme_climate_amplitude: v })}
        />
      </Card>

      {/* 海平面与地形 */}
      <Card title="海平面与地形" icon="🌊" desc="海洋边界和地形演变">
        <InfoBox>
          海平面变化影响海岸线位置。上升会淹没低洼陆地，下降则露出新的陆地。
        </InfoBox>
        <SliderRow
          label="海平面偏移"
          desc="相对于基准线的海平面高度变化"
          value={c.sea_level_offset ?? 0}
          min={-50}
          max={50}
          step={5}
          onChange={(v) => handleUpdate({ sea_level_offset: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v}m`}
        />
        <SliderRow
          label="海平面变化率"
          desc="每回合海平面的持续变化量"
          value={c.sea_level_change_rate ?? 0}
          min={-1}
          max={1}
          step={0.1}
          onChange={(v) => handleUpdate({ sea_level_change_rate: v })}
          formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}m/回合`}
        />
        <SliderRow
          label="地形侵蚀率"
          desc="每回合地形高度的自然侵蚀比例"
          value={c.terrain_erosion_rate ?? 0.01}
          min={0}
          max={0.1}
          step={0.005}
          onChange={(v) => handleUpdate({ terrain_erosion_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(1)}%`}
        />
      </Card>

      {/* 生物群系承载力 */}
      <Card title="生物群系承载力" icon="🏞️" desc="不同环境类型能支持的生物量差异">
        <InfoBox>
          不同生物群系的初级生产力差异很大：热带雨林资源丰富，沙漠则资源稀缺。承载力倍数决定各群系能支持多少生物。
        </InfoBox>
        <ConfigGroup title="陆地生物群系">
          <SliderRow
            label="热带雨林"
            desc="温暖湿润的热带雨林，生物多样性最高"
            value={c.biome_capacity_rainforest ?? 1.5}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_rainforest: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="温带森林"
            desc="四季分明的温带落叶林或针叶林"
            value={c.biome_capacity_temperate ?? 1.2}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_temperate: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="草原"
            desc="以草本植物为主的开阔地带"
            value={c.biome_capacity_grassland ?? 1.0}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_grassland: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="沙漠"
            desc="极度干旱的地区，资源稀缺"
            value={c.biome_capacity_desert ?? 0.3}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ biome_capacity_desert: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="苔原"
            desc="极地或高山的寒冷地带"
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
            desc="大洋深处（200米以下），光线无法到达"
            value={c.biome_capacity_deep_sea ?? 0.5}
            min={0.1}
            max={2}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_deep_sea: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="浅海"
            desc="大陆架浅海区域，阳光充足，生产力高"
            value={c.biome_capacity_shallow_sea ?? 1.3}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ biome_capacity_shallow_sea: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
        </ConfigGroup>
      </Card>

      {/* 地质灾害 */}
      <Card title="地质灾害" icon="🌋" desc="自然灾害的频率和强度">
        <InfoBox>
          地质灾害会突然改变局部环境，灾后的空白生态位为新物种提供机会。
        </InfoBox>
        <ConfigGroup title="火山活动">
          <SliderRow
            label="频率"
            desc="每回合发生火山喷发的概率"
            value={c.volcano_frequency ?? 0.02}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ volcano_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="影响半径"
            desc="火山喷发影响的地块范围"
            value={c.volcano_impact_radius ?? 3}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ volcano_impact_radius: v })}
            suffix="格"
          />
          <SliderRow
            label="破坏强度"
            desc="火山喷发对影响区域的破坏程度"
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
            desc="每回合发生严重洪水的概率"
            value={c.flood_frequency ?? 0.03}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ flood_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="影响范围"
            desc="洪水影响的地块数量"
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
            desc="每回合开始严重干旱的概率"
            value={c.drought_frequency ?? 0.04}
            min={0}
            max={0.1}
            step={0.005}
            onChange={(v) => handleUpdate({ drought_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <NumberInput
            label="持续时间"
            desc="干旱持续的回合数"
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
            desc="每回合发生破坏性地震的概率"
            value={c.earthquake_frequency ?? 0.01}
            min={0}
            max={0.05}
            step={0.005}
            onChange={(v) => handleUpdate({ earthquake_frequency: v })}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
        </ConfigGroup>
      </Card>

      {/* 密度惩罚 */}
      <Card title="密度惩罚" icon="👥" desc="地块过度拥挤时的负面效应">
        <InfoBox>
          当太多物种聚集在同一地块时，会产生拥挤效应：资源竞争加剧、疾病传播加快。
        </InfoBox>
        <SliderRow
          label="同地块密度惩罚"
          desc="每增加一个共存物种带来的死亡率惩罚系数"
          value={c.same_tile_density_penalty ?? 0.15}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ same_tile_density_penalty: v })}
        />
        <SliderRow
          label="过度拥挤阈值"
          desc="地块承载力使用率达到此值时开始施加拥挤惩罚"
          value={c.overcrowding_threshold ?? 0.7}
          min={0.3}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ overcrowding_threshold: v })}
        />
        <SliderRow
          label="拥挤惩罚上限"
          desc="过度拥挤导致的最大死亡率增加"
          value={c.overcrowding_max_penalty ?? 0.4}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ overcrowding_max_penalty: v })}
        />
      </Card>

      {/* 地图叠加层 */}
      <Card title="地图叠加层" icon="🗺️" desc="可视化调试工具">
        <InfoBox>
          这些开关控制地图上显示的数据叠加层，帮助您直观地了解地块的各种属性。
        </InfoBox>
        <ToggleRow
          label="资源热力图"
          desc="显示各地块的资源丰富程度"
          checked={c.show_resource_overlay ?? false}
          onChange={(v) => handleUpdate({ show_resource_overlay: v })}
        />
        <ToggleRow
          label="猎物丰度图"
          desc="显示各地块的猎物密度"
          checked={c.show_prey_overlay ?? false}
          onChange={(v) => handleUpdate({ show_prey_overlay: v })}
        />
        <ToggleRow
          label="宜居度热力图"
          desc="显示当前选中物种在各地块的宜居度"
          checked={c.show_suitability_overlay ?? false}
          onChange={(v) => handleUpdate({ show_suitability_overlay: v })}
        />
        <ToggleRow
          label="竞争压力图"
          desc="显示各地块的种间竞争强度"
          checked={c.show_competition_overlay ?? false}
          onChange={(v) => handleUpdate({ show_competition_overlay: v })}
        />
        <ToggleRow
          label="温度分布图"
          desc="显示各地块的温度分布"
          checked={c.show_temperature_overlay ?? false}
          onChange={(v) => handleUpdate({ show_temperature_overlay: v })}
        />
        <ToggleRow
          label="湿度分布图"
          desc="显示各地块的湿度分布"
          checked={c.show_humidity_overlay ?? false}
          onChange={(v) => handleUpdate({ show_humidity_overlay: v })}
        />
      </Card>
    </div>
  );
});
