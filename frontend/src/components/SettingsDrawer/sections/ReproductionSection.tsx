/**
 * ReproductionSection - 繁殖配置
 */

import { memo, type Dispatch } from "react";
import type { ReproductionConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionCard, ConfigGroup, SliderRow, ActionButton } from "../common";
import { DEFAULT_REPRODUCTION_CONFIG } from "../constants";

interface ReproductionSectionProps {
  config: ReproductionConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const ReproductionSection = memo(function ReproductionSection({
  config,
  dispatch,
}: ReproductionSectionProps) {
  const handleUpdate = (updates: Partial<ReproductionConfig>) => {
    dispatch({ type: "UPDATE_REPRODUCTION", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_REPRODUCTION" });
  };

  const c = { ...DEFAULT_REPRODUCTION_CONFIG, ...config };

  return (
    <div className="settings-section">
      <div className="section-header-bar">
        <div>
          <h2>🌱 繁殖配置</h2>
          <p className="section-subtitle">控制物种繁殖和种群增长</p>
        </div>
        <ActionButton label="恢复默认" onClick={handleReset} variant="secondary" icon="↻" />
      </div>

      <SectionCard title="基础增长" icon="📈" desc="种群增长的基本参数">
        <SliderRow
          label="繁殖速度增长率"
          desc="每点繁殖速度带来的增长率"
          value={c.growth_rate_per_repro_speed ?? 0.35}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ growth_rate_per_repro_speed: v })}
        />
        <SliderRow
          label="增长倍数下限"
          value={c.growth_multiplier_min ?? 0.5}
          min={0}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ growth_multiplier_min: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="增长倍数上限"
          value={c.growth_multiplier_max ?? 8.0}
          min={2}
          max={20}
          step={0.5}
          onChange={(v) => handleUpdate({ growth_multiplier_max: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </SectionCard>

      <SectionCard title="体型加成" icon="📏" desc="不同体型的繁殖加成">
        <SliderRow
          label="微生物加成"
          value={c.size_bonus_microbe ?? 1.6}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_microbe: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="小型生物加成"
          value={c.size_bonus_tiny ?? 1.3}
          min={1}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_tiny: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="中小型生物加成"
          value={c.size_bonus_small ?? 1.1}
          min={1}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_small: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </SectionCard>

      <SectionCard title="世代时间加成" icon="⏱️" desc="快速繁殖物种的额外加成">
        <SliderRow
          label="极快繁殖加成"
          desc="周级世代时间"
          value={c.repro_bonus_weekly ?? 1.5}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ repro_bonus_weekly: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="快速繁殖加成"
          desc="月级世代时间"
          value={c.repro_bonus_monthly ?? 1.25}
          min={1}
          max={2}
          step={0.05}
          onChange={(v) => handleUpdate({ repro_bonus_monthly: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <SliderRow
          label="中速繁殖加成"
          desc="半年级世代时间"
          value={c.repro_bonus_halfyear ?? 1.1}
          min={1}
          max={2}
          step={0.05}
          onChange={(v) => handleUpdate({ repro_bonus_halfyear: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
      </SectionCard>

      <SectionCard title="生存本能" icon="🛡️" desc="低种群时的繁殖补偿">
        <SliderRow
          label="激活阈值"
          desc="种群低于此比例时激活生存本能"
          value={c.survival_instinct_threshold ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ survival_instinct_threshold: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="最大加成"
          desc="生存本能提供的最大繁殖加成"
          value={c.survival_instinct_bonus ?? 0.4}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ survival_instinct_bonus: v })}
          formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>

      <SectionCard title="营养级惩罚" icon="🔗" desc="高营养级物种的繁殖效率降低">
        <SliderRow
          label="T2 繁殖效率"
          desc="初级消费者"
          value={c.t2_birth_efficiency ?? 0.85}
          min={0.3}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t2_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="T3 繁殖效率"
          desc="次级消费者"
          value={c.t3_birth_efficiency ?? 0.60}
          min={0.2}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t3_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="T4+ 繁殖效率"
          desc="顶级捕食者"
          value={c.t4_birth_efficiency ?? 0.40}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t4_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </SectionCard>
    </div>
  );
});

