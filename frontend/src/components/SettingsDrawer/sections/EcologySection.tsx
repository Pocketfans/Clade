/**
 * EcologySection - 生态平衡配置 (全新设计)
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
        生态系统中，物种通过捕食、竞争、共生等关系相互影响。这些参数控制种群增长、死亡和分布的核心计算，影响整个模拟的动态平衡。调整不当可能导致物种全灭或无限增长。
      </InfoBox>

      {/* 食物匮乏 */}
      <Card title="食物匮乏" icon="🍖" desc="猎物不足时对消费者的惩罚机制">
        <InfoBox>
          消费者（捕食者）需要足够的猎物才能维持种群。当猎物丰富度低于阈值时，消费者会因饥饿而增加死亡率。这模拟了食物链中「自下而上」的控制作用。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="匮乏阈值"
            desc="当消费者能获取的猎物丰富度（0-1）低于此值时，开始施加饥饿惩罚。例如0.3表示当猎物丰度低于30%时触发。越高意味着消费者越「挑食」。"
            value={c.food_scarcity_threshold ?? 0.3}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ food_scarcity_threshold: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="匮乏惩罚"
            desc="食物匮乏时额外增加的死亡率。例如+40%表示严重饥饿时死亡率会增加40个百分点。这是维持食物链平衡的关键参数。"
            value={c.food_scarcity_penalty ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ food_scarcity_penalty: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="稀缺权重"
            desc="食物稀缺因素在综合死亡率计算中的权重。较高值使食物供应对种群存活影响更大。与其他压力因素（环境、竞争等）共同决定最终死亡率。"
            value={c.scarcity_weight ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ scarcity_weight: v })}
          />
          <NumberInput
            label="猎物搜索地块"
            desc="消费者搜索猎物时考虑的最大地块数量。更大的搜索范围让消费者更容易找到猎物，但也意味着更广的捕食压力分布。"
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
      <Card title="竞争强度" icon="⚔️" desc="物种间资源竞争的计算参数">
        <InfoBox>
          种间竞争（Interspecific Competition）是指不同物种争夺相同资源的现象。生态位重叠的物种竞争最激烈。竞争压力会增加死亡率、降低繁殖率。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="基础竞争系数"
            desc="计算竞争影响时的基础乘数。较高值使竞争效应更显著，物种间相互抑制更强。这影响生态位重叠物种的共存能力。"
            value={c.competition_base_coefficient ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_base_coefficient: v })}
          />
          <SliderRow
            label="单竞争者上限"
            desc="单个竞争物种对目标物种造成的最大影响上限。防止一个强势竞争者完全压制其他物种。例如35%表示单个竞争者最多增加35%死亡压力。"
            value={c.competition_per_species_cap ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_per_species_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="总竞争上限"
            desc="所有竞争者的累积影响上限。即使面临多个强势竞争者，总竞争压力不会超过此值。这防止竞争压力叠加导致必然灭绝。"
            value={c.competition_total_cap ?? 0.8}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_total_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="同级竞争系数"
            desc="相同营养级（如两种草食动物）之间的额外竞争强度。同级物种竞争更直接，因为它们争夺完全相同类型的资源。"
            value={c.same_level_competition_k ?? 0.15}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ same_level_competition_k: v })}
          />
          <SliderRow
            label="生态位重叠惩罚"
            desc="生态位高度重叠时的额外竞争惩罚系数。生态位越相似（食性、栖息地、活动时间等），竞争越激烈，这个惩罚越大。"
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
        <InfoBox>
          营养级（Trophic Level）描述物种在食物链中的位置：T1=生产者（植物）、T2=初级消费者（草食）、T3=次级消费者（小型肉食）、T4+=顶级捕食者。能量在传递中会大量损失（仅约10-15%传递到下一级），因此高营养级物种的种群规模受限。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="传递效率"
            desc="能量从猎物传递到捕食者的比例。真实生态系统约10-15%。较高值使高营养级物种更容易维持种群，较低值则使食物链顶端更脆弱。"
            value={c.trophic_transfer_efficiency ?? 0.15}
            min={0.05}
            max={0.3}
            step={0.01}
            onChange={(v) => handleUpdate({ trophic_transfer_efficiency: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="高营养级繁殖惩罚"
            desc="高营养级物种的繁殖效率乘数。例如×0.7表示T3+物种繁殖率降低30%。这模拟了高营养级物种获取能量困难、繁殖成本高的现实。"
            value={c.high_trophic_birth_penalty ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ high_trophic_birth_penalty: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="顶级捕食者惩罚"
            desc="顶级捕食者（T4+）的额外繁殖惩罚乘数。顶级捕食者往往体型大、繁殖慢、数量少。例如×0.5表示繁殖效率再降低50%。"
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
      <Card title="扩散行为" icon="🦅" desc="物种在不同地块间的分布与迁移">
        <InfoBox>
          物种会根据栖息地适宜度分布在多个地块上。不同生态类型（陆生、海洋、空中等）的物种扩散能力不同。扩散地块数越多，物种分布越广，但也意味着种群更分散。
        </InfoBox>
        <ConfigGroup title="扩散地块数 — 物种最多同时占据的地块数量">
          <NumberInput
            label="陆生物种"
            desc="陆地栖息物种能同时占据的最大地块数。陆生物种受地形限制较大，通常扩散范围较小。"
            value={c.terrestrial_top_k ?? 4}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ terrestrial_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海洋物种"
            desc="纯海洋物种能同时占据的最大地块数。海洋连通性好，但深海物种可能受海底地形限制。"
            value={c.marine_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ marine_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="海岸物种"
            desc="海岸/两栖物种能同时占据的最大地块数。这类物种需要陆地和水体的交界带，分布受海岸线限制。"
            value={c.coastal_top_k ?? 3}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ coastal_top_k: v })}
            suffix="格"
          />
          <NumberInput
            label="空中物种"
            desc="飞行物种能同时占据的最大地块数。飞行使扩散能力大幅增强，不受地形阻隔。"
            value={c.aerial_top_k ?? 5}
            min={1}
            max={20}
            onChange={(v) => handleUpdate({ aerial_top_k: v })}
            suffix="格"
          />
        </ConfigGroup>

        <ConfigGroup title="扩散参数 — 影响扩散计算的其他因素">
          <SliderRow
            label="宜居度截断"
            desc="地块宜居度（0-1）低于此值时，不会被考虑作为扩散目标。这防止物种扩散到极不适宜的区域。例如0.25表示宜居度低于25%的地块被排除。"
            value={c.suitability_cutoff ?? 0.25}
            min={0}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ suitability_cutoff: v })}
          />
          <SliderRow
            label="高营养级扩散阻尼"
            desc="高营养级物种的扩散能力衰减系数。顶级捕食者种群密度低、领地需求大，扩散能力受限。例如×0.7表示扩散范围缩小30%。"
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
          每个地块拥有资源容量，代表该地块能支持的生物量。资源被消耗后会逐渐恢复。恢复速度和机制影响生态系统的稳定性和周期性波动。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="恢复速率"
            desc="资源每回合恢复的比例（相对于缺失量）。例如15%表示若资源缺失50，下回合恢复50×15%=7.5。较高值使生态系统恢复更快，但可能导致频繁的种群波动。"
            value={c.resource_recovery_rate ?? 0.15}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_recovery_rate: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%/回合`}
          />
          <NumberInput
            label="恢复滞后"
            desc="资源被过度消耗后，需要等待多少回合才开始恢复。模拟生态系统遭受严重破坏后的恢复延迟。0表示立即开始恢复。"
            value={c.resource_recovery_lag ?? 1}
            min={0}
            max={5}
            step={1}
            onChange={(v) => handleUpdate({ resource_recovery_lag: v })}
            suffix="回合"
          />
          <SliderRow
            label="最小恢复率"
            desc="即使资源几乎耗尽，每回合也保证恢复的最小量（占总容量的比例）。这防止资源完全归零后无法恢复的死局。"
            value={c.resource_min_recovery ?? 0.05}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_min_recovery: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="资源上限倍数"
            desc="地块资源容量的全局乘数。增大此值会提高所有地块的承载力，减小则让资源更紧缺。影响整个生态系统的规模。"
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
      <Card title="环境扰动" icon="🌪️" desc="随机环境波动，增加模拟的不确定性">
        <InfoBox>
          真实生态系统存在随机波动：丰年与荒年、气候异常等。这些参数为模拟增加随机性，使种群动态更自然、更难预测。过高的扰动可能导致系统不稳定。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="资源扰动"
            desc="每回合地块资源的随机波动幅度。例如±5%表示资源会在-5%到+5%之间随机变化。模拟气候对植被生产力的影响。"
            value={c.resource_perturbation ?? 0.05}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ resource_perturbation: v })}
            formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="气候扰动"
            desc="每回合气候参数（温度、湿度）的随机波动幅度。影响物种的栖息地适宜度计算。过大可能导致物种频繁迁移或灭绝。"
            value={c.climate_perturbation ?? 0.02}
            min={0}
            max={0.1}
            step={0.01}
            onChange={(v) => handleUpdate({ climate_perturbation: v })}
            formatValue={(v) => `±${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="环境噪声"
            desc="综合环境因素的背景噪声，影响死亡率和繁殖率的随机波动。这是最基础的随机性来源，让每个回合的结果略有不同。"
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
