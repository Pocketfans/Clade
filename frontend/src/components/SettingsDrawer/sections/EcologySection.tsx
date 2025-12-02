/**
 * EcologySection - 生态平衡配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { EcologyBalanceConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton } from "../common/Controls";
import { DEFAULT_ECOLOGY_BALANCE_CONFIG } from "../constants";

interface Props {
  config: EcologyBalanceConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const EcologySection = memo(function EcologySection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<EcologyBalanceConfig>) => {
    dispatch({ type: "UPDATE_ECOLOGY", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_ECOLOGY" });
  };

  const c = { ...DEFAULT_ECOLOGY_BALANCE_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🌿"
        title="生态平衡配置"
        subtitle="控制种群动态和生态系统平衡的参数"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 食物匮乏 */}
      <Card title="食物匮乏" icon="🍖" desc="猎物不足时的惩罚机制">
        <div className="card-grid">
          <SliderRow
            label="匮乏阈值"
            desc="猎物丰富度低于此值时触发惩罚"
            value={c.food_scarcity_threshold ?? 0.3}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ food_scarcity_threshold: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="匮乏惩罚"
            desc="食物匮乏时的死亡率增加"
            value={c.food_scarcity_penalty ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ food_scarcity_penalty: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="稀缺权重"
            value={c.scarcity_weight ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ scarcity_weight: v })}
          />
          <NumberInput
            label="猎物搜索地块"
            desc="消费者搜索猎物的最大地块数"
            value={c.prey_search_top_k ?? 5}
            min={1}
            max={20}
            step={1}
            onChange={(v) => handleUpdate({ prey_search_top_k: v })}
            suffix="格"
          />
        </div>
      </Card>

      {/* 竞争强度 */}
      <Card title="竞争强度" icon="⚔️" desc="种间竞争的参数">
        <div className="card-grid">
          <SliderRow
            label="基础竞争系数"
            value={c.competition_base_coefficient ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_base_coefficient: v })}
          />
          <SliderRow
            label="单竞争者上限"
            desc="单个竞争者的最大影响"
            value={c.competition_per_species_cap ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_per_species_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="总竞争上限"
            value={c.competition_total_cap ?? 0.8}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_total_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="同级竞争系数"
            desc="相同营养级间的竞争强度"
            value={c.same_level_competition_k ?? 0.15}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ same_level_competition_k: v })}
          />
          <SliderRow
            label="生态位重叠惩罚"
            value={c.niche_overlap_penalty_k ?? 0.2}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ niche_overlap_penalty_k: v })}
          />
        </div>
      </Card>

      {/* 营养传递 */}
      <Card title="营养传递" icon="🔗" desc="能量在食物链中的传递效率">
        <div className="card-grid">
          <SliderRow
            label="传递效率"
            desc="能量从猎物传递到捕食者的比例"
            value={c.trophic_transfer_efficiency ?? 0.15}
            min={0.05}
            max={0.3}
            step={0.01}
            onChange={(v) => handleUpdate({ trophic_transfer_efficiency: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="高营养级繁殖惩罚"
            value={c.high_trophic_birth_penalty ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ high_trophic_birth_penalty: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="顶级捕食者惩罚"
            value={c.apex_predator_penalty ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ apex_predator_penalty: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
        </div>
      </Card>

      {/* 扩散行为 */}
      <Card title="扩散行为" icon="🦅" desc="物种在地块间的分布">
        <ConfigGroup title="扩散地块数">
          <NumberInput
            label="陆生物种"
            value={c.terrestrial_top_k ?? 4}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ terrestrial_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海洋物种"
            value={c.marine_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ marine_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海岸物种"
            value={c.coastal_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ coastal_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="空中物种"
            value={c.aerial_top_k ?? 5}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ aerial_top_k: v })}
            suffix="格"
          />
        </ConfigGroup>

        <ConfigGroup title="扩散参数">
          <SliderRow
            label="宜居度截断"
            desc="低于此值的地块不考虑"
            value={c.suitability_cutoff ?? 0.25}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ suitability_cutoff: v })}
          />
          <SliderRow
            label="高营养级扩散阻尼"
            value={c.high_trophic_dispersal_damping ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ high_trophic_dispersal_damping: v })}
          />
        </ConfigGroup>
      </Card>

      {/* 资源再生 */}
      <Card title="资源再生" icon="♻️" desc="地块资源的恢复机制">
        <div className="card-grid">
          <SliderRow
            label="恢复速率"
            value={c.resource_recovery_rate ?? 0.15}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_recovery_rate: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%/回合`}
          />
          <NumberInput
            label="恢复滞后"
            desc="资源耗尽后延迟恢复的回合数"
            value={c.resource_recovery_lag ?? 1}
            min={0}
            max={5}
            step={1}
            onChange={(v) => handleUpdate({ resource_recovery_lag: v })}
            suffix="回合"
          />
          <SliderRow
            label="最小恢复率"
            value={c.resource_min_recovery ?? 0.05}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_min_recovery: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="资源上限倍数"
            value={c.resource_capacity_multiplier ?? 1.0}
            min={0.5}
            max={2}
            step={0.1}
            onChange={(v) => handleUpdate({ resource_capacity_multiplier: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
        </div>
      </Card>

      {/* 环境扰动 */}
      <Card title="环境扰动" icon="🌪️" desc="随机环境波动">
        <div className="card-grid">
          <SliderRow
            label="资源扰动"
            value={c.resource_perturbation ?? 0.05}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_perturbation: v })}
            formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="气候扰动"
            value={c.climate_perturbation ?? 0.02}
            min={0}
            max={0.1}
            step={0.01}
            onChange={(v) => handleUpdate({ climate_perturbation: v })}
            formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="环境噪声"
            value={c.environment_noise ?? 0.03}
            min={0}
            max={0.1}
            step={0.01}
            onChange={(v) => handleUpdate({ environment_noise: v })}
            formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
          />
        </div>
      </Card>
    </div>
  );
});
