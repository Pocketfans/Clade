/**
 * EcologySection - 生态平衡配置
 * 单列布局，控制种群动态和生态系统平衡
 */

import { memo, type Dispatch } from "react";
import type { EcologyBalanceConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton, InfoBox } from "../common/Controls";
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

      {/* 概念说明 */}
      <InfoBox variant="info" title="生态平衡机制">
        生态系统中，物种通过捕食、竞争、共生等关系相互影响。这些参数控制种群增长、死亡和分布的核心计算，影响整个模拟的动态平衡。
      </InfoBox>

      {/* 食物匮乏 */}
      <Card title="食物匮乏" icon="🍖" desc="猎物不足时对消费者的惩罚">
        <InfoBox>
          消费者（捕食者）需要足够的猎物才能维持种群。当猎物丰富度低于阈值时，消费者会因饥饿而增加死亡率。
        </InfoBox>
        <SliderRow
          label="匮乏阈值"
          desc="当消费者能获取的猎物丰富度（0-1）低于此值时，开始施加饥饿惩罚"
          value={c.food_scarcity_threshold ?? 0.3}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ food_scarcity_threshold: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="匮乏惩罚"
          desc="食物匮乏时额外增加的死亡率"
          value={c.food_scarcity_penalty ?? 0.4}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ food_scarcity_penalty: v })}
          formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="稀缺权重"
          desc="食物稀缺因素在综合死亡率计算中的权重"
          value={c.scarcity_weight ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ scarcity_weight: v })}
        />
        <NumberInput
          label="猎物搜索地块"
          desc="消费者搜索猎物时考虑的最大地块数量"
          value={c.prey_search_top_k ?? 5}
          min={1}
          max={20}
          step={1}
          onChange={(v) => handleUpdate({ prey_search_top_k: v })}
          suffix="格"
        />
      </Card>

      {/* 竞争强度 */}
      <Card title="竞争强度" icon="⚔️" desc="物种间资源竞争的参数">
        <InfoBox>
          种间竞争是指不同物种争夺相同资源的现象。生态位重叠的物种竞争最激烈，竞争压力会增加死亡率。
        </InfoBox>
        <SliderRow
          label="基础竞争系数"
          desc="计算竞争影响时的基础乘数"
          value={c.competition_base_coefficient ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ competition_base_coefficient: v })}
        />
        <SliderRow
          label="单竞争者上限"
          desc="单个竞争物种对目标物种造成的最大影响上限"
          value={c.competition_per_species_cap ?? 0.35}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ competition_per_species_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="总竞争上限"
          desc="所有竞争者的累积影响上限"
          value={c.competition_total_cap ?? 0.8}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ competition_total_cap: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="同级竞争系数"
          desc="相同营养级之间的额外竞争强度"
          value={c.same_level_competition_k ?? 0.15}
          min={0}
          max={0.5}
          step={0.05}
          onChange={(v) => handleUpdate({ same_level_competition_k: v })}
        />
        <SliderRow
          label="生态位重叠惩罚"
          desc="生态位高度重叠时的额外竞争惩罚系数"
          value={c.niche_overlap_penalty_k ?? 0.2}
          min={0}
          max={0.5}
          step={0.05}
          onChange={(v) => handleUpdate({ niche_overlap_penalty_k: v })}
        />
      </Card>

      {/* 营养传递 */}
      <Card title="营养传递" icon="🔗" desc="能量在食物链中的传递效率">
        <InfoBox>
          营养级描述物种在食物链中的位置。能量在传递中会大量损失（约10-15%），因此高营养级物种的种群规模受限。
        </InfoBox>
        <SliderRow
          label="传递效率"
          desc="能量从猎物传递到捕食者的比例。真实生态系统约10-15%"
          value={c.trophic_transfer_efficiency ?? 0.15}
          min={0.05}
          max={0.3}
          step={0.01}
          onChange={(v) => handleUpdate({ trophic_transfer_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="高营养级繁殖惩罚"
          desc="高营养级物种的繁殖效率乘数"
          value={c.high_trophic_birth_penalty ?? 0.7}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ high_trophic_birth_penalty: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <SliderRow
          label="顶级捕食者惩罚"
          desc="顶级捕食者（T4+）的额外繁殖惩罚乘数"
          value={c.apex_predator_penalty ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ apex_predator_penalty: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
      </Card>

      {/* 扩散行为 */}
      <Card title="扩散行为" icon="🦅" desc="物种在不同地块间的分布与迁移">
        <InfoBox>
          物种会根据栖息地适宜度分布在多个地块上。不同生态类型的物种扩散能力不同。
        </InfoBox>
        <ConfigGroup title="扩散地块数 — 物种最多同时占据的地块数">
          <NumberInput
            label="陆生物种"
            desc="陆地栖息物种能同时占据的最大地块数"
            value={c.terrestrial_top_k ?? 4}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ terrestrial_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海洋物种"
            desc="纯海洋物种能同时占据的最大地块数"
            value={c.marine_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ marine_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海岸物种"
            desc="海岸/两栖物种能同时占据的最大地块数"
            value={c.coastal_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ coastal_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="空中物种"
            desc="飞行物种能同时占据的最大地块数"
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
            desc="地块宜居度低于此值时，不会被考虑作为扩散目标"
            value={c.suitability_cutoff ?? 0.25}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ suitability_cutoff: v })}
          />
          <SliderRow
            label="高营养级扩散阻尼"
            desc="高营养级物种的扩散能力衰减系数"
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
        <InfoBox>
          每个地块拥有资源容量，资源被消耗后会逐渐恢复。恢复速度影响生态系统的稳定性。
        </InfoBox>
        <SliderRow
          label="恢复速率"
          desc="资源每回合恢复的比例（相对于缺失量）"
          value={c.resource_recovery_rate ?? 0.15}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ resource_recovery_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%/回合`}
        />
        <NumberInput
          label="恢复滞后"
          desc="资源被过度消耗后，需要等待多少回合才开始恢复"
          value={c.resource_recovery_lag ?? 1}
          min={0}
          max={5}
          step={1}
          onChange={(v) => handleUpdate({ resource_recovery_lag: v })}
          suffix="回合"
        />
        <SliderRow
          label="最小恢复率"
          desc="即使资源几乎耗尽，每回合也保证恢复的最小量"
          value={c.resource_min_recovery ?? 0.05}
          min={0}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ resource_min_recovery: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="资源上限倍数"
          desc="地块资源容量的全局乘数"
          value={c.resource_capacity_multiplier ?? 1.0}
          min={0.5}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ resource_capacity_multiplier: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </Card>

      {/* 环境扰动 */}
      <Card title="环境扰动" icon="🌪️" desc="随机环境波动">
        <InfoBox>
          真实生态系统存在随机波动：丰年与荒年、气候异常等。这些参数为模拟增加自然的随机性。
        </InfoBox>
        <SliderRow
          label="资源扰动"
          desc="每回合地块资源的随机波动幅度"
          value={c.resource_perturbation ?? 0.05}
          min={0}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ resource_perturbation: v })}
          formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="气候扰动"
          desc="每回合气候参数（温度、湿度）的随机波动幅度"
          value={c.climate_perturbation ?? 0.02}
          min={0}
          max={0.1}
          step={0.01}
          onChange={(v) => handleUpdate({ climate_perturbation: v })}
          formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="环境噪声"
          desc="综合环境因素的背景噪声"
          value={c.environment_noise ?? 0.03}
          min={0}
          max={0.1}
          step={0.01}
          onChange={(v) => handleUpdate({ environment_noise: v })}
          formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
        />
      </Card>
    </div>
  );
});
