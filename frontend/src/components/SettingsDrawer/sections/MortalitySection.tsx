/**
 * MortalitySection - 死亡率配置
 */

import { memo, type Dispatch } from "react";
import type { MortalityConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionCard, ConfigGroup, SliderRow, ActionButton } from "../common";
import { DEFAULT_MORTALITY_CONFIG } from "../constants";

interface MortalitySectionProps {
  config: MortalityConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const MortalitySection = memo(function MortalitySection({
  config,
  dispatch,
}: MortalitySectionProps) {
  const handleUpdate = (updates: Partial<MortalityConfig>) => {
    dispatch({ type: "UPDATE_MORTALITY", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_MORTALITY" });
  };

  const c = { ...DEFAULT_MORTALITY_CONFIG, ...config };

  return (
    <div className="settings-section">
      <div className="section-header-bar">
        <div>
          <h2>💀 死亡率配置</h2>
          <p className="section-subtitle">控制物种死亡率的计算参数</p>
        </div>
        <ActionButton label="恢复默认" onClick={handleReset} variant="secondary" icon="↻" />
      </div>

      <SectionCard title="压力上限" icon="📊" desc="各类压力因素的最大影响值">
        <SliderRow
          label="环境压力上限"
          desc="环境因素导致的最大死亡率"
          value={c.env_pressure_cap ?? 0.7}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ env_pressure_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="竞争压力上限"
          desc="种间竞争导致的最大死亡率"
          value={c.competition_pressure_cap ?? 0.45}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ competition_pressure_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="营养级压力上限"
          value={c.trophic_pressure_cap ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ trophic_pressure_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="资源压力上限"
          value={c.resource_pressure_cap ?? 0.45}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ resource_pressure_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="捕食压力上限"
          value={c.predation_pressure_cap ?? 0.55}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ predation_pressure_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="植物竞争上限"
          value={c.plant_competition_cap ?? 0.35}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ plant_competition_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>

      <SectionCard title="权重配置" icon="⚖️" desc="各类压力因素的权重（加权模型）">
        <ConfigGroup title="压力权重">
          <SliderRow
            label="环境权重"
            value={c.env_weight ?? 0.55}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ env_weight: v })}
          />
          <SliderRow
            label="竞争权重"
            value={c.competition_weight ?? 0.3}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_weight: v })}
          />
          <SliderRow
            label="营养级权重"
            value={c.trophic_weight ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ trophic_weight: v })}
          />
          <SliderRow
            label="资源权重"
            value={c.resource_weight ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_weight: v })}
          />
          <SliderRow
            label="捕食权重"
            value={c.predation_weight ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ predation_weight: v })}
          />
        </ConfigGroup>
      </SectionCard>

      <SectionCard title="乘法模型系数" icon="✖️" desc="乘法死亡率模型的系数">
        <SliderRow
          label="环境乘数"
          value={c.env_mult_coef ?? 0.65}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ env_mult_coef: v })}
        />
        <SliderRow
          label="竞争乘数"
          value={c.competition_mult_coef ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ competition_mult_coef: v })}
        />
        <SliderRow
          label="营养级乘数"
          value={c.trophic_mult_coef ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ trophic_mult_coef: v })}
        />
        <SliderRow
          label="资源乘数"
          value={c.resource_mult_coef ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ resource_mult_coef: v })}
        />
        <SliderRow
          label="捕食乘数"
          value={c.predation_mult_coef ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ predation_mult_coef: v })}
        />
      </SectionCard>

      <SectionCard title="模型混合" icon="🔀" desc="加权模型与乘法模型的混合比例">
        <SliderRow
          label="加权模型权重"
          desc="加权求和模型的占比（剩余为乘法模型）"
          value={c.additive_model_weight ?? 0.55}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ additive_model_weight: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>

      <SectionCard title="抗性系数" icon="🛡️" desc="体型和世代对死亡率的抵抗">
        <SliderRow
          label="体型抗性/10cm"
          desc="每10厘米体型带来的死亡率抵抗"
          value={c.size_resistance_per_10cm ?? 0.015}
          min={0}
          max={0.05}
          step={0.005}
          onChange={(v) => handleUpdate({ size_resistance_per_10cm: v })}
          formatValue={(v) => `-${(v * 100).toFixed(1)}%`}
        />
        <SliderRow
          label="世代抗性系数"
          value={c.generation_resistance_coef ?? 0.04}
          min={0}
          max={0.1}
          step={0.01}
          onChange={(v) => handleUpdate({ generation_resistance_coef: v })}
        />
        <SliderRow
          label="最大抗性"
          desc="所有抗性因素的总上限"
          value={c.max_resistance ?? 0.18}
          min={0}
          max={0.5}
          step={0.02}
          onChange={(v) => handleUpdate({ max_resistance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>

      <SectionCard title="死亡率边界" icon="📏" desc="死亡率的最终上下限">
        <SliderRow
          label="最低死亡率"
          desc="任何情况下的最低死亡率"
          value={c.min_mortality ?? 0.03}
          min={0}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ min_mortality: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="最高死亡率"
          desc="任何情况下的最高死亡率"
          value={c.max_mortality ?? 0.92}
          min={0.5}
          max={1}
          step={0.02}
          onChange={(v) => handleUpdate({ max_mortality: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>
    </div>
  );
});

