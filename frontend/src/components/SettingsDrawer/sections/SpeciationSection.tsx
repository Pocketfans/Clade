/**
 * SpeciationSection - 物种分化配置
 * 单列布局，清晰的参数分组
 */

import { memo, type Dispatch } from "react";
import type { SpeciationConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton, InfoBox, ToggleRow } from "../common/Controls";
import { DEFAULT_SPECIATION_CONFIG } from "../constants";

interface Props {
  config: SpeciationConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const SpeciationSection = memo(function SpeciationSection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<SpeciationConfig>) => {
    dispatch({ type: "UPDATE_SPECIATION", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_SPECIATION" });
  };

  const c = { ...DEFAULT_SPECIATION_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🧬"
        title="物种分化配置"
        subtitle="控制物种分化的触发条件、频率和演化机制"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 概念说明 */}
      <InfoBox variant="info" title="什么是物种分化？">
        物种分化（Speciation）是指一个物种演变成两个或多个不同物种的过程。在本模拟中，当物种面临环境压力、资源竞争或地理隔离时，有概率产生新的子种，形成演化树的分支。分化是生物多样性产生的核心机制。
      </InfoBox>

      {/* 基础参数 */}
      <Card title="基础参数" icon="⚙️" desc="分化的基本控制参数">
        <NumberInput
          label="冷却回合"
          desc="同一物种在分化后需要等待多少回合才能再次分化。设为0则无限制，物种可连续分化。建议设置2-5回合。"
          value={c.cooldown_turns ?? 3}
          min={0}
          max={20}
          step={1}
          onChange={(v) => handleUpdate({ cooldown_turns: v })}
          suffix="回合"
        />
        <NumberInput
          label="物种软上限"
          desc="当存活物种总数达到此值后，所有物种的分化概率会逐渐降低。这是一个「软」上限，不会完全阻止分化。"
          value={c.species_soft_cap ?? 60}
          min={10}
          max={200}
          step={5}
          onChange={(v) => handleUpdate({ species_soft_cap: v })}
          suffix="种"
        />
        <SliderRow
          label="基础分化率"
          desc="当物种满足分化条件时，实际触发分化的基础概率。较高值会导致更频繁的分化事件。"
          value={c.base_speciation_rate ?? 0.20}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ base_speciation_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <NumberInput
          label="单次子种数"
          desc="一次分化事件最多能产生多少个子种。通常为1-2个，设置过高会导致爆发式演化。"
          value={c.max_offspring_count ?? 2}
          min={1}
          max={6}
          step={1}
          onChange={(v) => handleUpdate({ max_offspring_count: v })}
          suffix="种"
        />
      </Card>

      {/* 种群数量门槛 */}
      <Card title="生物量门槛" icon="📊" desc="分化和杂交的最小生物量要求">
        <InfoBox>
          在真实演化中，过小的种群很难分化出新物种——基因库太小会导致近亲繁殖。这些参数以生物量（kg）为单位，确保只有达到一定规模的种群才能分化。
        </InfoBox>
        <NumberInput
          label="分化生物量门槛"
          desc="物种的总生物量（kg）必须达到此值才能触发分化检查"
          value={c.min_population_for_speciation ?? 100000}
          min={1000}
          max={500000}
          step={5000}
          onChange={(v) => handleUpdate({ min_population_for_speciation: v })}
          suffix="kg"
        />
        <NumberInput
          label="新物种最小生物量"
          desc="分化产生的每个新物种的初始生物量不能低于此值"
          value={c.min_offspring_population ?? 20000}
          min={500}
          max={100000}
          step={500}
          onChange={(v) => handleUpdate({ min_offspring_population: v })}
          suffix="kg"
        />
        <SliderRow
          label="背景物种惩罚"
          desc="背景物种（低关注度的小型物种）的分化概率乘以这个系数"
          value={c.background_speciation_penalty ?? 0.2}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ background_speciation_penalty: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <NumberInput
          label="杂交生物量门槛"
          desc="参与杂交的每个亲本物种的生物量必须达到此值"
          value={c.min_population_for_hybridization ?? 20000}
          min={1000}
          max={200000}
          step={1000}
          onChange={(v) => handleUpdate({ min_population_for_hybridization: v })}
          suffix="kg"
        />
      </Card>

      {/* 后代数量限制 */}
      <Card title="后代数量限制" icon="🌳" desc="限制单一物种产生的直接后代数量">
        <InfoBox>
          此设置解决「同一祖先分化出过多直接后代」的问题。真实演化中，一个物种通常只会分化出少数后代种，然后由后代继续演化。
        </InfoBox>
        <NumberInput
          label="最大直接后代"
          desc="一个物种最多能分化出多少个直接后代。达到上限后，演化的「接力棒」会传递给后代物种"
          value={c.max_direct_offspring ?? 3}
          min={1}
          max={10}
          step={1}
          onChange={(v) => handleUpdate({ max_direct_offspring: v })}
          suffix="种"
        />
        <ToggleRow
          label="只计存活后代"
          desc="开启：只有存活的后代计入上限。关闭：所有历史后代都计入上限"
          checked={c.count_only_alive_offspring ?? true}
          onChange={(v) => handleUpdate({ count_only_alive_offspring: v })}
        />
      </Card>

      {/* 早期优化 */}
      <Card title="早期优化" icon="🌱" desc="游戏早期的分化加速机制">
        <InfoBox>
          模拟初期物种较少，需要更宽松的分化条件来快速建立物种多样性。这些参数控制「早期」的定义和加速程度。
        </InfoBox>
        <NumberInput
          label="早期回合数"
          desc="前多少回合被视为「早期」阶段，在此期间分化条件会更宽松"
          value={c.early_game_turns ?? 15}
          min={1}
          max={30}
          step={1}
          onChange={(v) => handleUpdate({ early_game_turns: v })}
          suffix="回合"
        />
        <SliderRow
          label="早期门槛折减"
          desc="早期阶段，分化所需的门槛会乘以这个系数。越接近0折扣越大"
          value={c.early_threshold_min_factor ?? 0.5}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ early_threshold_min_factor: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <NumberInput
          label="跳过冷却期"
          desc="前N回合完全跳过分化冷却检查，允许物种连续分化"
          value={c.early_skip_cooldown_turns ?? 5}
          min={0}
          max={20}
          step={1}
          onChange={(v) => handleUpdate({ early_skip_cooldown_turns: v })}
          suffix="回合"
        />
      </Card>

      {/* 触发阈值 */}
      <Card title="触发阈值" icon="📊" desc="物种需要达到这些条件才有资格分化">
        <InfoBox>
          分化不是随机发生的，物种需要面临足够的选择压力才会演化。这里定义了三类触发条件：环境压力、资源压力和演化潜力。
        </InfoBox>
        
        <ConfigGroup title="环境压力阈值">
          <SliderRow
            label="后期压力阈值"
            desc="后期阶段，物种需要承受多大的环境压力才有资格分化"
            value={c.pressure_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期压力阈值"
            desc="早期阶段的环境压力要求，通常较低以促进分化"
            value={c.pressure_threshold_early ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="资源压力阈值">
          <SliderRow
            label="后期资源阈值"
            desc="后期阶段，物种栖息地的资源紧张程度需要达到此值才能分化"
            value={c.resource_threshold_late ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期资源阈值"
            desc="早期阶段的资源压力要求，较低值让物种更容易分化"
            value={c.resource_threshold_early ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="演化潜力阈值">
          <SliderRow
            label="后期演化潜力"
            desc="后期阶段，物种的演化潜力值需要达到此阈值"
            value={c.evo_potential_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ evo_potential_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期演化潜力"
            desc="早期阶段对演化潜力的要求较低"
            value={c.evo_potential_threshold_early ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ evo_potential_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
      </Card>

      {/* 辐射演化 */}
      <Card title="辐射演化" icon="💫" desc="特殊情况下的爆发性分化">
        <InfoBox>
          辐射演化（Adaptive Radiation）是指物种在短时间内快速分化出多个后代种。通常发生在大灭绝后或进入新环境时，如恐龙灭绝后哺乳动物的爆发式演化。
        </InfoBox>
        <SliderRow
          label="基础概率"
          desc="每次分化检查时，有此概率触发辐射演化而非普通分化"
          value={c.radiation_base_chance ?? 0.05}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ radiation_base_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="早期加成"
          desc="早期阶段辐射演化概率的额外加成"
          value={c.radiation_early_bonus ?? 0.15}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ radiation_early_bonus: v })}
          formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="早期概率上限"
          desc="早期阶段辐射演化概率的最大值"
          value={c.radiation_max_chance_early ?? 0.35}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ radiation_max_chance_early: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="后期概率上限"
          desc="后期阶段辐射演化概率的最大值"
          value={c.radiation_max_chance_late ?? 0.25}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ radiation_max_chance_late: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 隔离惩罚系数 */}
      <Card title="隔离与惩罚系数" icon="⚖️" desc="地理隔离和生态位重叠对分化的影响">
        <InfoBox>
          地理隔离是异域物种形成（Allopatric Speciation）的关键条件。没有隔离时，基因流动会阻止种群分化。
        </InfoBox>
        <SliderRow
          label="无隔离惩罚(早期)"
          desc="早期阶段，如果物种没有地理隔离，分化概率会乘以这个系数"
          value={c.no_isolation_penalty_early ?? 0.8}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ no_isolation_penalty_early: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <SliderRow
          label="无隔离惩罚(后期)"
          desc="后期阶段的无隔离惩罚，后期生态系统稳定，没有隔离的分化应该更困难"
          value={c.no_isolation_penalty_late ?? 0.5}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ no_isolation_penalty_late: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <SliderRow
          label="无隔离门槛乘数"
          desc="无地理隔离时，分化所需的门槛会乘以这个系数"
          value={c.threshold_multiplier_no_isolation ?? 1.8}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ threshold_multiplier_no_isolation: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="高重叠门槛乘数"
          desc="当物种与其他物种的生态位高度重叠时，分化门槛会乘以这个系数"
          value={c.threshold_multiplier_high_overlap ?? 1.2}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ threshold_multiplier_high_overlap: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </Card>

      {/* 杂交参数 */}
      <Card title="杂交参数" icon="🧬" desc="控制物种间自然杂交的频率和成功率">
        <InfoBox>
          杂交（Hybridization）是两个不同物种之间交配产生后代的过程。近缘物种在重叠分布区域可能发生杂交，产生具有双方特征的杂交种。
        </InfoBox>
        <SliderRow
          label="杂交检测概率"
          desc="每回合系统检查同域近缘物种杂交可能性的基础概率"
          value={c.auto_hybridization_chance ?? 0.08}
          min={0}
          max={0.5}
          step={0.01}
          onChange={(v) => handleUpdate({ auto_hybridization_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="杂交成功率"
          desc="通过检测后，杂交实际成功产生可育后代的概率"
          value={c.hybridization_success_rate ?? 0.35}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ hybridization_success_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <NumberInput
          label="每回合上限"
          desc="每回合最多产生多少个杂交种"
          value={c.max_hybrids_per_turn ?? 2}
          min={0}
          max={10}
          step={1}
          onChange={(v) => handleUpdate({ max_hybrids_per_turn: v })}
          suffix="个"
        />
      </Card>
    </div>
  );
});
