/**
 * SpeciationSection - 物种分化配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { SpeciationConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton, InfoBox } from "../common/Controls";
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
      <Card title="基础参数" icon="⚙️" desc="分化的基本控制参数，决定分化的整体频率">
        <div className="card-grid">
          <NumberInput
            label="冷却回合"
            desc="同一物种在分化后需要等待多少回合才能再次分化。设为0则无限制，物种可连续分化。建议设置2-5回合，避免同一物种爆发式产生大量后代。"
            value={c.cooldown_turns ?? 3}
            min={0}
            max={20}
            step={1}
            onChange={(v) => handleUpdate({ cooldown_turns: v })}
            suffix="回合"
          />
          <NumberInput
            label="物种软上限"
            desc="当存活物种总数达到此值后，所有物种的分化概率会逐渐降低。这是一个「软」上限，不会完全阻止分化，但会显著减少分化频率，防止物种数量失控。"
            value={c.species_soft_cap ?? 60}
            min={10}
            max={200}
            step={5}
            onChange={(v) => handleUpdate({ species_soft_cap: v })}
            suffix="种"
          />
          <SliderRow
            label="基础分化率"
            desc="当物种满足分化条件（压力、资源、演化潜力等达标）时，实际触发分化的基础概率。较高值会导致更频繁的分化事件，较低值则让分化更稀少珍贵。"
            value={c.base_speciation_rate ?? 0.20}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ base_speciation_rate: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <NumberInput
            label="单次子种数"
            desc="一次分化事件最多能产生多少个子种。通常为1-2个，设置过高会导致爆发式演化（辐射演化）。正常情况下建议保持较低值，辐射演化会单独处理。"
            value={c.max_offspring_count ?? 2}
            min={1}
            max={6}
            step={1}
            onChange={(v) => handleUpdate({ max_offspring_count: v })}
            suffix="种"
          />
        </div>
      </Card>

      {/* 后代数量限制 */}
      <Card title="后代数量限制" icon="🌳" desc="限制单一物种产生的直接后代数量，使演化更像一条主线而非扇形爆发">
        <InfoBox>
          此设置解决「同一祖先分化出过多直接后代」的问题。真实演化中，一个物种通常只会分化出少数后代种，然后由后代继续演化。这使得族谱更像一棵树，而非一个平面的扇形。
        </InfoBox>
        <div className="card-grid">
          <NumberInput
            label="最大直接后代"
            desc="一个物种最多能分化出多少个直接后代。达到上限后，该物种将无法继续分化，演化的「接力棒」会传递给它的后代物种。建议设置为2-4。"
            value={c.max_direct_offspring ?? 3}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ max_direct_offspring: v })}
            suffix="种"
          />
          <div className="toggle-row">
            <div className="toggle-info">
              <span className="toggle-label">只计存活后代</span>
              <span className="toggle-desc">
                开启：只有存活的后代计入上限，已灭绝的后代不算，这样祖先物种可以「补充」后代。关闭：所有历史后代都计入上限，更严格地限制分化。
              </span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={c.count_only_alive_offspring ?? true}
                onChange={(e) => handleUpdate({ count_only_alive_offspring: e.target.checked })}
              />
              <span className="toggle-slider" />
            </label>
          </div>
        </div>
      </Card>

      {/* 早期优化 */}
      <Card title="早期优化" icon="🌱" desc="游戏早期的分化加速机制，帮助生态系统快速建立">
        <InfoBox>
          模拟初期物种较少，需要更宽松的分化条件来快速建立物种多样性。这些参数控制「早期」的定义和加速程度。随着回合推进，这些优惠会逐渐消失。
        </InfoBox>
        <div className="card-grid">
          <NumberInput
            label="早期回合数"
            desc="前多少回合被视为「早期」阶段。在此期间，分化条件会更宽松，帮助快速建立初始生态系统。建议设置为5-15回合。"
            value={c.early_game_turns ?? 10}
            min={1}
            max={30}
            step={1}
            onChange={(v) => handleUpdate({ early_game_turns: v })}
            suffix="回合"
          />
          <SliderRow
            label="早期门槛折减"
            desc="早期阶段，分化所需的压力/资源/演化潜力门槛会乘以这个系数。例如0.3表示门槛降低到正常的30%，更容易触发分化。越接近1表示折扣越小。"
            value={c.early_threshold_min_factor ?? 0.3}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ early_threshold_min_factor: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <NumberInput
            label="跳过冷却期"
            desc="前N回合完全跳过分化冷却检查，允许物种连续分化。这确保游戏开局能快速产生多样性。建议比「早期回合数」小一些。"
            value={c.early_skip_cooldown_turns ?? 5}
            min={0}
            max={20}
            step={1}
            onChange={(v) => handleUpdate({ early_skip_cooldown_turns: v })}
            suffix="回合"
          />
        </div>
      </Card>

      {/* 触发阈值 */}
      <Card title="触发阈值" icon="📊" desc="物种需要达到这些条件才有资格分化">
        <InfoBox>
          分化不是随机发生的，物种需要面临足够的选择压力才会演化。这里定义了三类触发条件：环境压力、资源压力和演化潜力。早期和后期有不同的阈值要求。
        </InfoBox>
        
        <ConfigGroup title="环境压力阈值 — 物种承受的环境不适应度">
          <SliderRow
            label="后期压力阈值"
            desc="后期阶段，物种需要承受多大的环境压力（温度、湿度不适应等）才有资格分化。较高值意味着只有真正「挣扎」的物种才会分化。"
            value={c.pressure_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期压力阈值"
            desc="早期阶段的环境压力要求，通常较低以促进分化。例如0.4表示40%的环境压力就足以触发分化检查。"
            value={c.pressure_threshold_early ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="资源压力阈值 — 可用资源的紧张程度">
          <SliderRow
            label="后期资源阈值"
            desc="后期阶段，物种栖息地的资源紧张程度需要达到此值才能分化。较高值意味着只有资源非常紧缺时才会逼迫物种演化出新形态。"
            value={c.resource_threshold_late ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期资源阈值"
            desc="早期阶段的资源压力要求，较低值让物种更容易分化以开拓新的生态位。"
            value={c.resource_threshold_early ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="演化潜力阈值 — 物种的遗传可塑性">
          <SliderRow
            label="后期演化潜力"
            desc="后期阶段，物种的演化潜力值需要达到此阈值。演化潜力代表物种基因的可塑性，高演化潜力的物种更容易产生有益变异。"
            value={c.evo_potential_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ evo_potential_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期演化潜力"
            desc="早期阶段对演化潜力的要求较低，让更多物种有机会分化。"
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
      <Card title="辐射演化" icon="💫" desc="特殊情况下的爆发性分化，如大灭绝后的快速适应">
        <InfoBox>
          辐射演化（Adaptive Radiation）是指物种在短时间内快速分化出多个后代种，填补空缺的生态位。通常发生在大灭绝后或进入新环境时。例如恐龙灭绝后哺乳动物的爆发式演化。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="基础概率"
            desc="每次分化检查时，有此概率触发辐射演化而非普通分化。辐射演化会产生更多子种。建议保持较低值（5%以下），因为这是罕见事件。"
            value={c.radiation_base_chance ?? 0.05}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ radiation_base_chance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期加成"
            desc="早期阶段辐射演化概率的额外加成。早期生态位空缺较多，辐射演化更可能发生。例如+15%表示早期阶段辐射概率为 基础+15%。"
            value={c.radiation_early_bonus ?? 0.15}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ radiation_early_bonus: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期概率上限"
            desc="早期阶段辐射演化概率的最大值，防止过于频繁的爆发式分化。"
            value={c.radiation_max_chance_early ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ radiation_max_chance_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="后期概率上限"
            desc="后期阶段辐射演化概率的最大值。后期生态系统成熟，辐射演化应该更少见。"
            value={c.radiation_max_chance_late ?? 0.25}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ radiation_max_chance_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </div>
      </Card>

      {/* 惩罚系数 */}
      <Card title="隔离与惩罚系数" icon="⚖️" desc="地理隔离和生态位重叠对分化的影响">
        <InfoBox>
          地理隔离是异域物种形成（Allopatric Speciation）的关键条件。没有隔离时，基因流动会阻止种群分化。这里的参数控制「无隔离」和「生态位重叠」情况下的分化难度。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="无隔离惩罚(早期)"
            desc="早期阶段，如果物种没有地理隔离，分化概率会乘以这个系数。例如×0.8表示概率降低20%。早期惩罚较轻，因为需要快速建立多样性。"
            value={c.no_isolation_penalty_early ?? 0.8}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ no_isolation_penalty_early: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="无隔离惩罚(后期)"
            desc="后期阶段的无隔离惩罚。后期生态系统稳定，没有隔离的分化应该更困难。×0.5表示概率减半。"
            value={c.no_isolation_penalty_late ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ no_isolation_penalty_late: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="无隔离门槛乘数"
            desc="无地理隔离时，分化所需的压力/资源门槛会乘以这个系数。例如×1.8表示门槛提高80%，需要更高的选择压力才能分化。"
            value={c.threshold_multiplier_no_isolation ?? 1.8}
            min={1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ threshold_multiplier_no_isolation: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="高重叠门槛乘数"
            desc="当物种与其他物种的生态位高度重叠时，分化门槛会乘以这个系数。高重叠意味着激烈竞争，此时分化可能是逃避竞争的方式，但也可能因为资源不足而失败。"
            value={c.threshold_multiplier_high_overlap ?? 1.2}
            min={1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ threshold_multiplier_high_overlap: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
        </div>
      </Card>

      {/* 杂交参数 */}
      <Card title="杂交参数" icon="🧬" desc="控制物种间自然杂交的频率和成功率">
        <InfoBox>
          杂交（Hybridization）是两个不同物种之间交配产生后代的过程。在自然界中，近缘物种在重叠分布区域可能发生杂交，产生具有双方特征的杂交种。杂交种可能拥有独特的适应优势，也可能不育。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="杂交检测概率"
            desc="每回合系统检查同域（栖息地重叠）近缘物种杂交可能性的基础概率。此值决定了杂交事件被「考虑」的频率。实际杂交还需通过成功率骰点。"
            value={c.auto_hybridization_chance ?? 0.08}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ auto_hybridization_chance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="杂交成功率"
            desc="通过检测后，杂交实际成功产生可育后代的概率。自然界中大多数杂交尝试会失败或产生不育后代，因此此值不宜过高。建议30-50%。"
            value={c.hybridization_success_rate ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ hybridization_success_rate: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <NumberInput
            label="每回合上限"
            desc="每回合最多产生多少个杂交种。限制杂交频率，防止杂交种过多导致生态系统混乱。建议1-3个。"
            value={c.max_hybrids_per_turn ?? 2}
            min={0}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ max_hybrids_per_turn: v })}
            suffix="个"
          />
        </div>
      </Card>
    </div>
  );
});
