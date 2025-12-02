/**
 * MortalitySection - 死亡率配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { MortalityConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, ActionButton, InfoBox } from "../common/Controls";
import { DEFAULT_MORTALITY_CONFIG } from "../constants";

interface Props {
  config: MortalityConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const MortalitySection = memo(function MortalitySection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<MortalityConfig>) => {
    dispatch({ type: "UPDATE_MORTALITY", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_MORTALITY" });
  };

  const c = { ...DEFAULT_MORTALITY_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="💀"
        title="死亡率配置"
        subtitle="控制物种死亡率的计算参数和压力因素"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 概念说明 */}
      <InfoBox variant="info" title="死亡率计算机制">
        每个物种每回合的死亡率由多种压力因素综合决定：环境适应度、种间竞争、营养级位置、资源可用性、捕食压力等。系统使用两种计算模型（加权模型和乘法模型）的混合结果，并应用体型和世代抗性后得出最终死亡率。
      </InfoBox>

      {/* 压力上限 */}
      <Card title="压力上限" icon="📊" desc="各类压力因素对死亡率的最大贡献">
        <InfoBox>
          每种压力因素都有一个上限值，防止单一因素导致必然灭绝。即使环境极端恶劣或竞争极其激烈，单一因素造成的死亡率增加也不会超过这些上限。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="环境压力上限"
            desc="环境因素（温度、湿度与物种偏好不匹配）导致的最大死亡率。例如70%表示即使物种完全不适应当前环境，环境因素最多只贡献70%死亡率。"
            value={c.env_pressure_cap ?? 0.7}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ env_pressure_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="竞争压力上限"
            desc="种间竞争（与其他物种争夺资源）导致的最大死亡率。竞争压力来自生态位重叠的物种。例如45%表示激烈竞争最多贡献45%死亡率。"
            value={c.competition_pressure_cap ?? 0.45}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_pressure_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="营养级压力上限"
            desc="营养级位置带来的固有压力上限。高营养级物种能量获取效率低，本身就承受更大的生存压力。"
            value={c.trophic_pressure_cap ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ trophic_pressure_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="资源压力上限"
            desc="资源匮乏导致的最大死亡率。当栖息地资源不足（过度利用、干旱等）时产生的压力上限。"
            value={c.resource_pressure_cap ?? 0.45}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_pressure_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="捕食压力上限"
            desc="被捕食导致的最大死亡率。当捕食者数量多、捕食效率高时产生的压力。例如55%表示即使捕食者泛滥，捕食最多贡献55%死亡率。"
            value={c.predation_pressure_cap ?? 0.55}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ predation_pressure_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="植物竞争上限"
            desc="植物（T1生产者）之间竞争导致的最大死亡率。植物竞争主要争夺光照、水分和养分，与动物竞争机制不同。"
            value={c.plant_competition_cap ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ plant_competition_cap: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </div>
      </Card>

      {/* 权重配置 */}
      <Card title="加权模型权重" icon="⚖️" desc="加权求和模型中各压力因素的重要性">
        <InfoBox>
          加权模型将各压力因素按权重求和得出死亡率：死亡率 = Σ(压力值 × 权重)。权重越高，该因素对最终死亡率的影响越大。所有权重不需要总和为1，因为最终会与乘法模型混合。
        </InfoBox>
        <ConfigGroup title="各类压力的计算权重">
          <SliderRow
            label="环境权重"
            desc="环境适应度在加权模型中的重要性。较高值使温度、湿度的不适应对死亡率影响更大。"
            value={c.env_weight ?? 0.55}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ env_weight: v })}
          />
          <SliderRow
            label="竞争权重"
            desc="种间竞争在加权模型中的重要性。较高值使竞争激烈时死亡率更高。"
            value={c.competition_weight ?? 0.3}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_weight: v })}
          />
          <SliderRow
            label="营养级权重"
            desc="营养级固有压力的权重。较高值使高营养级物种生存更困难。"
            value={c.trophic_weight ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ trophic_weight: v })}
          />
          <SliderRow
            label="资源权重"
            desc="资源可用性的权重。较高值使资源匮乏对死亡率影响更大。"
            value={c.resource_weight ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_weight: v })}
          />
          <SliderRow
            label="捕食权重"
            desc="捕食压力的权重。较高值使被捕食风险对死亡率影响更大。"
            value={c.predation_weight ?? 0.35}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ predation_weight: v })}
          />
        </ConfigGroup>
      </Card>

      {/* 乘法模型系数 */}
      <Card title="乘法模型系数" icon="✖️" desc="乘法模型中各因素的影响强度">
        <InfoBox>
          乘法模型通过连续相乘计算存活率：存活率 = Π(1 - 压力值 × 系数)，然后死亡率 = 1 - 存活率。这种模型中，各因素相互增强，多重压力的组合效果更显著。系数越高，该因素在乘法中的影响越强。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="环境乘数"
            desc="环境因素在乘法模型中的系数。较高值使环境不适应的惩罚在乘法计算中更重。"
            value={c.env_mult_coef ?? 0.65}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ env_mult_coef: v })}
          />
          <SliderRow
            label="竞争乘数"
            desc="竞争压力在乘法模型中的系数。"
            value={c.competition_mult_coef ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ competition_mult_coef: v })}
          />
          <SliderRow
            label="营养级乘数"
            desc="营养级压力在乘法模型中的系数。"
            value={c.trophic_mult_coef ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ trophic_mult_coef: v })}
          />
          <SliderRow
            label="资源乘数"
            desc="资源压力在乘法模型中的系数。"
            value={c.resource_mult_coef ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ resource_mult_coef: v })}
          />
          <SliderRow
            label="捕食乘数"
            desc="捕食压力在乘法模型中的系数。"
            value={c.predation_mult_coef ?? 0.6}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => handleUpdate({ predation_mult_coef: v })}
          />
        </div>
      </Card>

      {/* 模型混合 */}
      <Card title="模型混合" icon="🔀" desc="两种计算模型的混合比例">
        <InfoBox>
          最终死亡率是加权模型和乘法模型结果的加权平均。加权模型更稳定、可预测；乘法模型让多重压力的组合更致命。通过调整混合比例，可以控制系统的「宽容度」。
        </InfoBox>
        <SliderRow
          label="加权模型权重"
          desc="加权求和模型在最终结果中的占比。例如55%表示最终死亡率 = 加权结果×55% + 乘法结果×45%。较高值使系统更稳定，较低值使多重压力更致命。"
          value={c.additive_model_weight ?? 0.55}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => handleUpdate({ additive_model_weight: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 抗性系数 */}
      <Card title="抗性系数" icon="🛡️" desc="体型和世代对死亡率的抵抗能力">
        <InfoBox>
          物种可以通过体型和演化世代获得一定的死亡率抵抗。大型物种通常更能抵抗环境波动，而经历多代演化的物种往往具有更好的适应性。抗性会直接减少最终计算的死亡率。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="体型抗性/10cm"
            desc="每10厘米体型带来的死亡率减免。例如-1.5%表示一个50cm的物种获得7.5%的死亡率减免。大型物种天然更能抵抗环境压力。"
            value={c.size_resistance_per_10cm ?? 0.015}
            min={0}
            max={0.05}
            step={0.005}
            onChange={(v) => handleUpdate({ size_resistance_per_10cm: v })}
            formatValue={(v) => `-${(v * 100).toFixed(1)}%`}
          />
          <SliderRow
            label="世代抗性系数"
            desc="演化世代数带来的抗性系数。经历更多代演化的物种往往更适应环境。每增加一代，抗性增加此系数。"
            value={c.generation_resistance_coef ?? 0.04}
            min={0}
            max={0.1}
            step={0.01}
            onChange={(v) => handleUpdate({ generation_resistance_coef: v })}
          />
          <SliderRow
            label="最大抗性"
            desc="体型和世代抗性的总和上限。无论物种多大或演化多久，总抗性不会超过此值。例如18%表示最多减免18%死亡率。"
            value={c.max_resistance ?? 0.18}
            min={0}
            max={0.5}
            step={0.02}
            onChange={(v) => handleUpdate({ max_resistance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </div>
      </Card>

      {/* 死亡率边界 */}
      <Card title="死亡率边界" icon="📏" desc="死亡率的最终上下限">
        <InfoBox>
          无论压力计算结果如何，最终死亡率都会被限制在这个范围内。最低死亡率确保即使完美适应的物种也有自然死亡；最高死亡率防止必然灭绝，给物种一线生机。
        </InfoBox>
        <div className="card-grid">
          <SliderRow
            label="最低死亡率"
            desc="任何物种每回合的最低死亡率。即使完美适应、无竞争、无捕食，也有这么多个体会自然死亡。这代表衰老、疾病、意外等不可避免的死亡。"
            value={c.min_mortality ?? 0.03}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ min_mortality: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="最高死亡率"
            desc="任何物种每回合的最高死亡率。即使面临极端压力，死亡率也不会超过此值，给物种留下繁殖恢复的机会。设为100%则允许单回合全灭。"
            value={c.max_mortality ?? 0.92}
            min={0.5}
            max={1}
            step={0.02}
            onChange={(v) => handleUpdate({ max_mortality: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </div>
      </Card>
    </div>
  );
});
