/**
 * ReproductionSection - 繁殖配置
 * 单列布局，清晰的参数分组
 */

import { memo, type Dispatch } from "react";
import type { ReproductionConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, SliderRow, ActionButton, InfoBox } from "../common/Controls";
import { DEFAULT_REPRODUCTION_CONFIG } from "../constants";

interface Props {
  config: ReproductionConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const ReproductionSection = memo(function ReproductionSection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<ReproductionConfig>) => {
    dispatch({ type: "UPDATE_REPRODUCTION", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_REPRODUCTION" });
  };

  const c = { ...DEFAULT_REPRODUCTION_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🐣"
        title="繁殖配置"
        subtitle="控制物种繁殖和种群增长的参数"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 概念说明 */}
      <InfoBox variant="info" title="繁殖与种群动态">
        繁殖率决定了物种种群的增长速度。与死亡率共同作用，决定物种种群是增长还是衰退。繁殖受到物种特性（体型、世代时间）、环境条件和资源可用性的综合影响。
      </InfoBox>

      {/* 基础增长 */}
      <Card title="基础增长" icon="📈" desc="种群增长的基本参数">
        <InfoBox>
          基础增长参数决定了在理想条件下，种群能以多快的速度增长。实际增长还会受到资源限制、竞争、捕食等因素的影响。
        </InfoBox>
        <SliderRow
          label="繁殖速度增长率"
          desc="每点繁殖速度属性转化为增长倍数的系数。物种的繁殖速度属性（1-10）乘以这个值得到增长倍数。"
          value={c.growth_rate_per_repro_speed ?? 0.35}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ growth_rate_per_repro_speed: v })}
        />
        <SliderRow
          label="增长倍数下限"
          desc="种群增长倍数的最小值。即使繁殖条件很差，种群也至少能维持这个增长率。"
          value={c.growth_multiplier_min ?? 0.5}
          min={0}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ growth_multiplier_min: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="增长倍数上限"
          desc="种群增长倍数的最大值。即使条件完美，单回合增长也不会超过这个倍数。防止种群爆炸。"
          value={c.growth_multiplier_max ?? 8.0}
          min={2}
          max={20}
          step={0.5}
          onChange={(v) => handleUpdate({ growth_multiplier_max: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </Card>

      {/* 体型加成 */}
      <Card title="体型加成" icon="📏" desc="不同体型物种的繁殖效率差异">
        <InfoBox>
          小型物种通常繁殖更快（r选择策略），大型物种繁殖较慢但存活率高（K选择策略）。这里定义不同体型等级的繁殖效率加成。
        </InfoBox>
        <SliderRow
          label="微生物加成"
          desc="微型生物（如细菌、原生动物，体型<1mm）的繁殖倍数加成。微生物繁殖极快。"
          value={c.size_bonus_microbe ?? 1.6}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_microbe: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="小型生物加成"
          desc="小型生物（体型1mm-5cm，如昆虫、小型无脊椎动物）的繁殖倍数加成"
          value={c.size_bonus_tiny ?? 1.3}
          min={1}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_tiny: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="中小型生物加成"
          desc="中小型生物（体型5-30cm，如小型鱼类、两栖类）的繁殖倍数加成"
          value={c.size_bonus_small ?? 1.1}
          min={1}
          max={2}
          step={0.1}
          onChange={(v) => handleUpdate({ size_bonus_small: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </Card>

      {/* 世代时间加成 */}
      <Card title="世代时间加成" icon="⏱️" desc="快速繁殖物种的额外加成">
        <InfoBox>
          世代时间（Generation Time）是指从出生到繁殖的平均时间。世代时间短的物种能更快地适应环境变化。
        </InfoBox>
        <SliderRow
          label="极快繁殖加成"
          desc="周级世代时间（1-4周，如细菌、部分昆虫）的繁殖加成"
          value={c.repro_bonus_weekly ?? 1.5}
          min={1}
          max={3}
          step={0.1}
          onChange={(v) => handleUpdate({ repro_bonus_weekly: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="快速繁殖加成"
          desc="月级世代时间（1-3个月，如小型鱼类、许多昆虫）的繁殖加成"
          value={c.repro_bonus_monthly ?? 1.25}
          min={1}
          max={2}
          step={0.05}
          onChange={(v) => handleUpdate({ repro_bonus_monthly: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
        <SliderRow
          label="中速繁殖加成"
          desc="半年级世代时间（3-6个月，如部分小型哺乳动物）的繁殖加成"
          value={c.repro_bonus_halfyear ?? 1.1}
          min={1}
          max={2}
          step={0.05}
          onChange={(v) => handleUpdate({ repro_bonus_halfyear: v })}
          formatValue={(v) => `×${v.toFixed(2)}`}
        />
      </Card>

      {/* 生存本能 */}
      <Card title="生存本能" icon="🛡️" desc="濒危时的繁殖补偿机制">
        <InfoBox>
          当种群数量下降到危险水平时，许多物种会触发「生存本能」——提高繁殖率以挽救种群。这是一种密度依赖的负反馈机制。
        </InfoBox>
        <SliderRow
          label="激活阈值"
          desc="种群数量下降到承载力的多少比例时激活生存本能。越低加成越大。"
          value={c.survival_instinct_threshold ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ survival_instinct_threshold: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="最大加成"
          desc="生存本能提供的最大繁殖加成（当种群接近灭绝时）"
          value={c.survival_instinct_bonus ?? 0.4}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ survival_instinct_bonus: v })}
          formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 营养级惩罚 */}
      <Card title="营养级惩罚" icon="🔗" desc="高营养级物种的繁殖效率降低">
        <InfoBox>
          营养级（Trophic Level）越高的物种，获取能量越困难，通常繁殖效率越低。这是能量金字塔的自然结果。T1=生产者，T2=初级消费者，T3=次级消费者，T4+=顶级捕食者。
        </InfoBox>
        <SliderRow
          label="T2 繁殖效率"
          desc="初级消费者（草食动物、滤食者等）的繁殖效率"
          value={c.t2_birth_efficiency ?? 0.85}
          min={0.3}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t2_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="T3 繁殖效率"
          desc="次级消费者（小型肉食动物、杂食动物等）的繁殖效率"
          value={c.t3_birth_efficiency ?? 0.60}
          min={0.2}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t3_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="T4+ 繁殖效率"
          desc="顶级捕食者（大型肉食动物）的繁殖效率"
          value={c.t4_birth_efficiency ?? 0.40}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ t4_birth_efficiency: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>
    </div>
  );
});
