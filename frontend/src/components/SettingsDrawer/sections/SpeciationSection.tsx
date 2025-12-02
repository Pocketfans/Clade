/**
 * SpeciationSection - 物种分化配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { SpeciationConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton } from "../common/Controls";
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

      {/* 基础参数 */}
      <Card title="基础参数" icon="⚙️" desc="分化的基本控制">
        <div className="card-grid">
          <NumberInput
            label="冷却回合"
            desc="同一物种分化后需要等待的回合数（0=无限制）"
            value={c.cooldown_turns ?? 3}
            min={0}
            max={20}
            step={1}
            onChange={(v) => handleUpdate({ cooldown_turns: v })}
            suffix="回合"
          />
          <NumberInput
            label="物种软上限"
            desc="达到此值后分化概率降低"
            value={c.species_soft_cap ?? 60}
            min={10}
            max={200}
            step={5}
            onChange={(v) => handleUpdate({ species_soft_cap: v })}
            suffix="种"
          />
          <SliderRow
            label="基础分化率"
            desc="满足条件时的基础分化概率"
            value={c.base_speciation_rate ?? 0.20}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ base_speciation_rate: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <NumberInput
            label="单次子种数"
            desc="单次分化最多产生的子种数量"
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
      <Card title="后代数量限制" icon="🌳" desc="限制一个物种能产生的直接后代数量，促进演化向下传递">
        <div className="card-grid">
          <NumberInput
            label="最大直接后代"
            desc="一个物种最多能分化出多少个直接后代"
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
                开启后，只有存活的后代计入限制；关闭则计算所有历史后代
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
      <Card title="早期优化" icon="🌱" desc="游戏早期的分化加速机制">
        <div className="card-grid">
          <NumberInput
            label="早期回合数"
            desc="被视为'早期'的回合数阈值"
            value={c.early_game_turns ?? 10}
            min={1}
            max={30}
            step={1}
            onChange={(v) => handleUpdate({ early_game_turns: v })}
            suffix="回合"
          />
          <SliderRow
            label="早期门槛折减"
            desc="早期分化门槛的最小折减系数"
            value={c.early_threshold_min_factor ?? 0.3}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ early_threshold_min_factor: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <NumberInput
            label="跳过冷却期"
            desc="前 N 回合跳过分化冷却检查"
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
      <Card title="触发阈值" icon="📊" desc="各类触发条件的阈值设置">
        <ConfigGroup title="压力阈值">
          <SliderRow
            label="后期压力阈值"
            value={c.pressure_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期压力阈值"
            value={c.pressure_threshold_early ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ pressure_threshold_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>

        <ConfigGroup title="资源阈值">
          <SliderRow
            label="后期资源阈值"
            value={c.resource_threshold_late ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期资源阈值"
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
            value={c.evo_potential_threshold_late ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ evo_potential_threshold_late: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期演化潜力"
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
      <Card title="辐射演化" icon="💫" desc="爆发性分化的参数控制">
        <div className="card-grid">
          <SliderRow
            label="基础概率"
            desc="辐射演化的基础触发概率"
            value={c.radiation_base_chance ?? 0.05}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ radiation_base_chance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期加成"
            desc="早期辐射演化的额外概率加成"
            value={c.radiation_early_bonus ?? 0.15}
            min={0}
            max={0.5}
            step={0.01}
            onChange={(v) => handleUpdate({ radiation_early_bonus: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="早期概率上限"
            value={c.radiation_max_chance_early ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ radiation_max_chance_early: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="后期概率上限"
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
      <Card title="惩罚系数" icon="⚖️" desc="特殊情况下的分化惩罚">
        <div className="card-grid">
          <SliderRow
            label="无隔离惩罚(早期)"
            desc="早期无地理隔离时的概率惩罚"
            value={c.no_isolation_penalty_early ?? 0.8}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ no_isolation_penalty_early: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="无隔离惩罚(后期)"
            desc="后期无地理隔离时的概率惩罚"
            value={c.no_isolation_penalty_late ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ no_isolation_penalty_late: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="无隔离门槛乘数"
            value={c.threshold_multiplier_no_isolation ?? 1.8}
            min={1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ threshold_multiplier_no_isolation: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
          <SliderRow
            label="高重叠门槛乘数"
            desc="生态位高度重叠时的门槛乘数"
            value={c.threshold_multiplier_high_overlap ?? 1.2}
            min={1}
            max={3}
            step={0.1}
            onChange={(v) => handleUpdate({ threshold_multiplier_high_overlap: v })}
            formatValue={(v) => `×${v.toFixed(1)}`}
          />
        </div>
      </Card>
    </div>
  );
});
