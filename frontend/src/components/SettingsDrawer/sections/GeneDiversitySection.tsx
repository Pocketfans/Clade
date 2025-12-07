/**
 * GeneDiversitySection - 基因多样性配置
 * 控制基于 Embedding 的基因多样性半径机制
 */

import { memo, type Dispatch } from "react";
import type { GeneDiversityConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ConfigGroup, SliderRow, NumberInput, ActionButton, InfoBox } from "../common/Controls";
import { DEFAULT_GENE_DIVERSITY_CONFIG } from "../constants";

interface Props {
  config: GeneDiversityConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const GeneDiversitySection = memo(function GeneDiversitySection({
  config,
  dispatch,
}: Props) {
  const handleUpdate = (updates: Partial<GeneDiversityConfig>) => {
    dispatch({ type: "UPDATE_GENE_DIVERSITY", updates });
  };

  const handleReset = () => {
    dispatch({ type: "RESET_GENE_DIVERSITY" });
  };

  const c = { ...DEFAULT_GENE_DIVERSITY_CONFIG, ...config };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🧬"
        title="基因多样性配置"
        subtitle="控制物种的演化潜力与基因库范围"
        actions={<ActionButton label="恢复默认" onClick={handleReset} variant="ghost" icon="↻" />}
      />

      {/* 概念说明 */}
      <InfoBox variant="info" title="🧬 核心概念：基因多样性半径">
        <strong>简单理解：</strong>基因多样性半径就像物种的"演化潜力池"，决定了物种能往哪些方向演化。
        <br /><br />
        <strong>工作原理：</strong>
        <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
          <li>每个物种有一个"生态向量"（表示当前特征）</li>
          <li>基因多样性半径 = 以这个向量为圆心，能够"触及"的演化范围</li>
          <li>休眠基因只有在这个半径范围内才能被激活</li>
        </ul>
        <strong>影响因素：</strong>种群越大 → 半径越容易增长；种群瓶颈 → 半径快速衰减（近亲繁殖效应）
      </InfoBox>

      {/* 基础参数 */}
      <Card title="基础参数" icon="⚙️" desc="控制基因多样性半径的增减规则">
        <InfoBox variant="warning">
          <strong>⚠️ 半径太小会导致基因无法激活！</strong>当物种的基因多样性半径小于压力方向的距离时，
          系统会判定该压力方向"不可达"，休眠基因将无法被激活。建议保持 min_radius ≥ 0.05。
        </InfoBox>
        <SliderRow
          label="最小半径（保底演化能力）"
          desc="物种的基因多样性不会低于此值。值越大，即使经历瓶颈也能保持演化潜力。建议 0.05-0.10"
          value={c.min_radius ?? 0.05}
          min={0.01}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ min_radius: v })}
          formatValue={(v) => v.toFixed(2)}
        />
        <SliderRow
          label="最大衰减率（每回合上限）"
          desc="种群减少时，基因多样性每回合最多衰减的比例。防止大灭绝后演化能力瞬间归零"
          value={c.max_decay_per_turn ?? 0.05}
          min={0.01}
          max={0.15}
          step={0.01}
          onChange={(v) => handleUpdate({ max_decay_per_turn: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%/回合`}
        />
        <SliderRow
          label="激活消耗（每次激活扣除）"
          desc="每激活一个休眠基因，半径会缩小此比例。模拟使用演化潜力的代价。建议 0-5%"
          value={c.activation_cost ?? 0.02}
          min={0}
          max={0.1}
          step={0.005}
          onChange={(v) => handleUpdate({ activation_cost: v })}
          formatValue={(v) => `${(v * 100).toFixed(1)}%`}
        />
        <NumberInput
          label="瓶颈系数（小种群惩罚强度）"
          desc="公式：衰减 = 系数 / √种群 × 压力。种群1万时约0.5%衰减，种群100时约5%衰减。值越大惩罚越重"
          value={c.bottleneck_coefficient ?? 50}
          min={10}
          max={200}
          step={5}
          onChange={(v) => handleUpdate({ bottleneck_coefficient: v })}
        />
        <NumberInput
          label="恢复阈值（正增长门槛）"
          desc="种群超过此值时，基因多样性每回合自然增长（按时代增长率）。低于此值则只会衰减"
          value={c.recovery_threshold ?? 50000}
          min={10000}
          max={200000}
          step={5000}
          onChange={(v) => handleUpdate({ recovery_threshold: v })}
          suffix="kg生物量"
        />
      </Card>

      {/* 杂交与发现 */}
      <Card title="杂交与发现加成" icon="🔬" desc="增加基因多样性半径的途径">
        <InfoBox>
          <strong>💡 增加基因多样性半径的主要方式：</strong>
          <br />1. <strong>杂交</strong>：两个物种杂交产生的后代，获得双亲的基因混合，半径大幅增加
          <br />2. <strong>新基因发现</strong>：通过突变或分化发现新基因时，演化范围扩展
          <br />3. <strong>自然增长</strong>：种群健康时，每回合按时代增长率缓慢增加
        </InfoBox>
        <ConfigGroup title="杂交后代半径加成">
          <SliderRow
            label="杂交提升（下限）"
            desc="杂交后代的半径 = max(父母半径) × (1 + 加成)。这是加成的最小值"
            value={c.hybrid_bonus_min ?? 0.20}
            min={0.05}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ hybrid_bonus_min: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="杂交提升（上限）"
            desc="杂交加成的最大值。实际加成在[下限, 上限]之间随机"
            value={c.hybrid_bonus_max ?? 0.40}
            min={0.1}
            max={0.8}
            step={0.05}
            onChange={(v) => handleUpdate({ hybrid_bonus_max: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <ConfigGroup title="发现新基因时半径加成">
          <SliderRow
            label="发现提升（下限）"
            desc="发现新基因或器官时，半径扩展的最小比例"
            value={c.discovery_bonus_min ?? 0.05}
            min={0.01}
            max={0.2}
            step={0.01}
            onChange={(v) => handleUpdate({ discovery_bonus_min: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="发现提升（上限）"
            desc="发现新基因或器官时，半径扩展的最大比例"
            value={c.discovery_bonus_max ?? 0.12}
            min={0.05}
            max={0.3}
            step={0.01}
            onChange={(v) => handleUpdate({ discovery_bonus_max: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
      </Card>

      {/* 太古宙参数 */}
      <Card title="太古宙（第 1-50 回合）" icon="🌋" desc="生命起源，基因多样性爆发期">
        <InfoBox>
          <strong>🌋 太古宙特点：</strong>早期生命简单但基因潜力巨大，是演化最活跃的时期。
          <br />• 初始半径大 → 新物种一出生就有很大的演化空间
          <br />• 增长率高 → 基因多样性快速积累
          <br />• 继承完整 → 分化时几乎不损失演化潜力
        </InfoBox>
        <SliderRow
          label="初始半径"
          desc="太古宙新创建/分化物种的起始基因多样性半径。建议 0.5-0.8，值越大起始演化空间越大"
          value={c.archean_initial_radius ?? 0.50}
          min={0.3}
          max={0.9}
          step={0.05}
          onChange={(v) => handleUpdate({ archean_initial_radius: v })}
          formatValue={(v) => v.toFixed(2)}
        />
        <SliderRow
          label="增长率"
          desc="种群健康时（超过恢复阈值），每回合半径自然增长的比例。太古宙增长最快"
          value={c.archean_growth_rate ?? 0.03}
          min={0.01}
          max={0.10}
          step={0.005}
          onChange={(v) => handleUpdate({ archean_growth_rate: v })}
          formatValue={(v) => `+${(v * 100).toFixed(1)}%/回合`}
        />
        <ConfigGroup title="分化继承系数（子代继承父代多少演化潜力）">
          <SliderRow
            label="继承下限"
            desc="子物种至少继承父物种半径的此比例。95%表示几乎完整继承"
            value={c.archean_inherit_min ?? 0.95}
            min={0.7}
            max={1.0}
            step={0.01}
            onChange={(v) => handleUpdate({ archean_inherit_min: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="继承上限"
            desc="子物种最多继承父物种半径的此比例。100%表示可能完全继承"
            value={c.archean_inherit_max ?? 1.00}
            min={0.8}
            max={1.0}
            step={0.01}
            onChange={(v) => handleUpdate({ archean_inherit_max: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <SliderRow
          label="突变发现概率"
          desc="每回合自发发现新基因、扩展演化范围的概率。高死亡率环境下概率更高"
          value={c.archean_mutation_chance ?? 0.15}
          min={0.05}
          max={0.4}
          step={0.01}
          onChange={(v) => handleUpdate({ archean_mutation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 元古宙参数 */}
      <Card title="元古宙（第 50-150 回合）" icon="🌊" desc="真核生物时代，增长趋缓">
        <InfoBox>
          <strong>🌊 元古宙特点：</strong>真核生物和多细胞生命出现，演化速度开始放缓。
          <br />• 分化时的"奠基者效应"开始显现 → 子代继承的演化潜力略有损失
        </InfoBox>
        <SliderRow
          label="初始半径"
          desc="元古宙新物种的起始半径，比太古宙略小"
          value={c.proterozoic_initial_radius ?? 0.40}
          min={0.25}
          max={0.6}
          step={0.05}
          onChange={(v) => handleUpdate({ proterozoic_initial_radius: v })}
          formatValue={(v) => v.toFixed(2)}
        />
        <SliderRow
          label="增长率"
          desc="种群健康时每回合半径增长比例，比太古宙慢"
          value={c.proterozoic_growth_rate ?? 0.02}
          min={0.005}
          max={0.05}
          step={0.005}
          onChange={(v) => handleUpdate({ proterozoic_growth_rate: v })}
          formatValue={(v) => `+${(v * 100).toFixed(1)}%/回合`}
        />
        <ConfigGroup title="分化继承系数">
          <SliderRow
            label="继承下限"
            desc="子物种至少继承父物种半径的此比例"
            value={c.proterozoic_inherit_min ?? 0.90}
            min={0.6}
            max={0.98}
            step={0.01}
            onChange={(v) => handleUpdate({ proterozoic_inherit_min: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="继承上限"
            desc="子物种最多继承父物种半径的此比例"
            value={c.proterozoic_inherit_max ?? 0.98}
            min={0.7}
            max={1.0}
            step={0.01}
            onChange={(v) => handleUpdate({ proterozoic_inherit_max: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <SliderRow
          label="突变发现概率"
          desc="每回合自发发现新基因的概率，比太古宙略低"
          value={c.proterozoic_mutation_chance ?? 0.10}
          min={0.03}
          max={0.2}
          step={0.01}
          onChange={(v) => handleUpdate({ proterozoic_mutation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 古生代及以后参数 */}
      <Card title="古生代及以后（第 150+ 回合）" icon="🦖" desc="复杂生命时代，演化趋稳">
        <InfoBox>
          <strong>🦖 古生代后特点：</strong>生命形式复杂稳定，演化放缓但更精细。
          <br />• 分化损失更大 → 但大灭绝幸存者仍可恢复（只是需要更长时间）
        </InfoBox>
        <SliderRow
          label="初始半径"
          desc="古生代及以后新物种的起始半径"
          value={c.phanerozoic_initial_radius ?? 0.35}
          min={0.2}
          max={0.5}
          step={0.05}
          onChange={(v) => handleUpdate({ phanerozoic_initial_radius: v })}
          formatValue={(v) => v.toFixed(2)}
        />
        <SliderRow
          label="增长率"
          desc="种群健康时每回合半径增长比例，最慢的时代"
          value={c.phanerozoic_growth_rate ?? 0.015}
          min={0.005}
          max={0.03}
          step={0.005}
          onChange={(v) => handleUpdate({ phanerozoic_growth_rate: v })}
          formatValue={(v) => `+${(v * 100).toFixed(1)}%/回合`}
        />
        <ConfigGroup title="分化继承系数">
          <SliderRow
            label="继承下限"
            desc="子物种至少继承父物种半径的此比例"
            value={c.phanerozoic_inherit_min ?? 0.85}
            min={0.5}
            max={0.95}
            step={0.01}
            onChange={(v) => handleUpdate({ phanerozoic_inherit_min: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="继承上限"
            desc="子物种最多继承父物种半径的此比例"
            value={c.phanerozoic_inherit_max ?? 0.95}
            min={0.6}
            max={1.0}
            step={0.01}
            onChange={(v) => handleUpdate({ phanerozoic_inherit_max: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <SliderRow
          label="突变发现概率"
          desc="每回合自发发现新基因的概率，复杂生命时代更低"
          value={c.phanerozoic_mutation_chance ?? 0.08}
          min={0.02}
          max={0.15}
          step={0.01}
          onChange={(v) => handleUpdate({ phanerozoic_mutation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 激活机制 */}
      <Card title="🔑 休眠基因激活（关键！）" icon="🔓" desc="决定基因能否成功激活的核心参数">
        <InfoBox variant="warning">
          <strong>⚠️ 基因激活必须同时满足以下条件：</strong>
          <ol style={{ margin: "8px 0", paddingLeft: "20px" }}>
            <li><strong>死亡率超标</strong>：特质需要 &gt;25%，器官需要 &gt;30%</li>
            <li><strong>暴露次数达标</strong>：至少暴露压力 1 次</li>
            <li><strong>方向可达</strong>：压力方向在基因多样性半径范围内（is_reachable）</li>
            <li><strong>概率检定</strong>：30%基础 × (1 + 演化潜力) × 压力匹配加成</li>
          </ol>
          如果物种很难激活新基因，检查：半径是否太小？死亡率是否太低？
        </InfoBox>
        <SliderRow
          label="基础激活概率"
          desc="每个休眠基因每回合的基础激活概率。实际概率 = 基础 × (1 + 演化潜力) × 压力匹配加成"
          value={c.activation_chance_per_turn ?? 0.30}
          min={0.05}
          max={0.50}
          step={0.05}
          onChange={(v) => handleUpdate({ activation_chance_per_turn: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="压力匹配加成倍数"
          desc="当休眠基因的压力类型与当前环境压力匹配时，激活概率乘以此值。例如耐热性基因在高温压力下更容易激活"
          value={c.pressure_match_bonus ?? 2.5}
          min={1.0}
          max={5.0}
          step={0.25}
          onChange={(v) => handleUpdate({ pressure_match_bonus: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <SliderRow
          label="器官发现概率"
          desc="分化时有机会发现全新器官（不是激活已有休眠器官）。新器官会扩展演化范围"
          value={c.organ_discovery_chance ?? 0.20}
          min={0.05}
          max={0.40}
          step={0.05}
          onChange={(v) => handleUpdate({ organ_discovery_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="激活死亡率阈值"
          desc="物种必须承受至少此死亡率才能激活休眠特质。值越低越容易激活，但会降低压力选择的意义"
          value={c.activation_death_rate_threshold ?? 0.25}
          min={0.10}
          max={0.50}
          step={0.05}
          onChange={(v) => handleUpdate({ activation_death_rate_threshold: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%死亡率`}
        />
        <NumberInput
          label="最小暴露次数"
          desc="休眠基因必须暴露压力至少此次数才能激活。1次=第一回合就可能激活"
          value={c.activation_min_exposure ?? 1}
          min={1}
          max={5}
          step={1}
          onChange={(v) => handleUpdate({ activation_min_exposure: v })}
          suffix="次"
        />
      </Card>

      {/* 分化时的基因继承 - v3.0 基于环境压力的机制 */}
      <Card title="🧬 分化时基因继承（v3.0）" icon="👶" desc="基于环境压力的智能基因丢失机制">
        <InfoBox variant="info">
          <strong>📋 v3.0 新机制：</strong>
          <br />1. <strong>完整继承</strong>：子代默认 100% 继承父代的所有休眠基因
          <br />2. <strong>压力筛选</strong>：高压力环境下，不适应的基因会被自然选择淘汰
          <br />3. <strong>智能保留</strong>：与当前环境压力匹配的基因几乎不会丢失
          <br />4. <strong>有害突变加速淘汰</strong>：显性有害突变在高压力下更容易丢失
          <br /><br />
          <strong>🎯 设计理念：</strong>低压力 = 遗传稳定；高压力 = 自然选择（适者生存）
        </InfoBox>
        <SliderRow
          label="压力阈值（丢失开始点）"
          desc="环境压力低于此值时，基因几乎不会丢失。高于此值后，丢失率随压力增加"
          value={c.gene_loss_pressure_threshold ?? 2.0}
          min={0}
          max={5.0}
          step={0.5}
          onChange={(v) => handleUpdate({ gene_loss_pressure_threshold: v })}
          formatValue={(v) => `压力 > ${v.toFixed(1)}`}
        />
        <SliderRow
          label="丢失率增长系数"
          desc="每超过阈值 1 点压力，基因丢失率增加此比例"
          value={c.gene_loss_rate_per_pressure ?? 0.02}
          min={0.01}
          max={0.05}
          step={0.005}
          onChange={(v) => handleUpdate({ gene_loss_rate_per_pressure: v })}
          formatValue={(v) => `+${(v * 100).toFixed(1)}%/压力`}
        />
        <SliderRow
          label="最大丢失率上限"
          desc="无论压力多高，基因丢失率不会超过此值（保护机制）"
          value={c.max_gene_loss_rate ?? 0.15}
          min={0.05}
          max={0.30}
          step={0.01}
          onChange={(v) => handleUpdate({ max_gene_loss_rate: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <ConfigGroup title="智能保留机制">
          <SliderRow
            label="压力匹配保留加成"
            desc="当基因的压力类型与当前环境匹配时，保留率额外增加。例如：耐旱基因在干旱环境下更难丢失"
            value={c.pressure_match_retain_bonus ?? 0.10}
            min={0.05}
            max={0.25}
            step={0.01}
            onChange={(v) => handleUpdate({ pressure_match_retain_bonus: v })}
            formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="器官基因稳定性"
            desc="器官基因比特质基因更稳定，丢失率乘以此系数。0.5 = 丢失率减半"
            value={c.organ_gene_stability_factor ?? 0.50}
            min={0.25}
            max={1.0}
            step={0.05}
            onChange={(v) => handleUpdate({ organ_gene_stability_factor: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
        </ConfigGroup>
        <ConfigGroup title="有害突变淘汰">
          <SliderRow
            label="显性有害突变保留率"
            desc="显性有害突变更容易被自然选择淘汰，保留率乘以此系数"
            value={c.dominant_harmful_retain_factor ?? 0.70}
            min={0.3}
            max={1.0}
            step={0.05}
            onChange={(v) => handleUpdate({ dominant_harmful_retain_factor: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
          <SliderRow
            label="轻微有害突变保留率"
            desc="轻微有害突变的保留率略低于正常基因"
            value={c.mildly_harmful_retain_factor ?? 0.90}
            min={0.6}
            max={1.0}
            step={0.05}
            onChange={(v) => handleUpdate({ mildly_harmful_retain_factor: v })}
            formatValue={(v) => `×${v.toFixed(2)}`}
          />
        </ConfigGroup>
        <InfoBox variant="warning">
          <strong>📊 示例计算（压力=8.0 时）：</strong>
          <br />• 基础丢失率 = (8.0 - 2.0) × 2% = 12%
          <br />• 普通基因保留率 = 88%
          <br />• 压力匹配基因保留率 = 88% + 10% = 98%
          <br />• 器官基因丢失率 = 12% × 0.5 = 6%（保留率 94%）
          <br />• 显性有害突变保留率 = 88% × 0.7 = 62%
        </InfoBox>
      </Card>

      {/* ========== v2.0 新功能卡片 ========== */}
      
      {/* 有害突变（遗传负荷） */}
      <Card title="☠️ 有害突变（遗传负荷）" icon="🧬" desc="模拟真实生物学中的有害基因积累">
        <InfoBox variant="info">
          <strong>🔬 生物学背景：</strong>大多数随机突变是中性或有害的，只有少数是有益的。
          有害突变通常是隐性的，被自然选择"隐藏"起来，但会在种群中积累。
          <br /><br />
          <strong>游戏影响：</strong>有害突变激活后会降低物种的适应性（减少某些特质值）。
          隐性有害突变更容易遗传，显性有害突变会被自然选择快速淘汰。
        </InfoBox>
        <SliderRow
          label="新物种有害突变概率"
          desc="新创建的物种携带有害休眠基因的概率。值越高，演化越真实但也更具挑战性"
          value={c.harmful_mutation_chance ?? 0.15}
          min={0}
          max={0.40}
          step={0.05}
          onChange={(v) => handleUpdate({ harmful_mutation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="有害突变激活惩罚"
          desc="有害突变的激活概率 = 基础概率 × 此系数。值越低，有害基因越难被激活（被选择抑制）"
          value={c.harmful_activation_penalty ?? 0.30}
          min={0.1}
          max={1.0}
          step={0.1}
          onChange={(v) => handleUpdate({ harmful_activation_penalty: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
        <ConfigGroup title="有害突变遗传概率">
          <SliderRow
            label="隐性有害突变继承"
            desc="隐性有害突变更容易被遗传（被自然选择隐藏），这是遗传负荷积累的原因"
            value={c.recessive_harmful_inherit_chance ?? 0.70}
            min={0.3}
            max={0.95}
            step={0.05}
            onChange={(v) => handleUpdate({ recessive_harmful_inherit_chance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="显性有害突变继承"
            desc="显性有害突变难以遗传，因为表达出来的个体会被自然选择淘汰"
            value={c.dominant_harmful_inherit_chance ?? 0.20}
            min={0.05}
            max={0.50}
            step={0.05}
            onChange={(v) => handleUpdate({ dominant_harmful_inherit_chance: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <SliderRow
          label="子代新突变概率"
          desc="分化时子代产生全新有害突变的概率（de novo mutation）"
          value={c.de_novo_mutation_chance ?? 0.10}
          min={0}
          max={0.30}
          step={0.02}
          onChange={(v) => handleUpdate({ de_novo_mutation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>

      {/* 显隐性遗传 */}
      <Card title="🔠 显隐性遗传" icon="🧪" desc="基因表达效果受显隐性影响">
        <InfoBox variant="info">
          <strong>🎓 显隐性类型：</strong>
          <br />• <strong>显性 (D)</strong>：杂合即表达，100% 潜力值
          <br />• <strong>共显性 (C)</strong>：中间表型，60% 潜力值
          <br />• <strong>隐性 (R)</strong>：需要纯合/高压才能表达，25% 潜力值
          <br />• <strong>超显性 (O)</strong>：杂合优势，115% 潜力值（比纯合更强）
        </InfoBox>
        <ConfigGroup title="表达系数（激活后实际获得的特质值比例）">
          <SliderRow
            label="显性表达"
            desc="显性基因激活后，获得潜力值的比例"
            value={c.dominant_expression_factor ?? 1.0}
            min={0.8}
            max={1.2}
            step={0.05}
            onChange={(v) => handleUpdate({ dominant_expression_factor: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="共显性表达"
            desc="共显性基因激活后，获得潜力值的比例（中间表型）"
            value={c.codominant_expression_factor ?? 0.60}
            min={0.4}
            max={0.8}
            step={0.05}
            onChange={(v) => handleUpdate({ codominant_expression_factor: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="隐性表达"
            desc="隐性基因激活后，获得潜力值的比例（表达受限）"
            value={c.recessive_expression_factor ?? 0.25}
            min={0.1}
            max={0.5}
            step={0.05}
            onChange={(v) => handleUpdate({ recessive_expression_factor: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="超显性表达"
            desc="超显性基因激活后，获得潜力值的比例（杂合优势，可超过100%）"
            value={c.overdominant_expression_factor ?? 1.15}
            min={1.0}
            max={1.5}
            step={0.05}
            onChange={(v) => handleUpdate({ overdominant_expression_factor: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
      </Card>

      {/* 器官渐进发育 */}
      <Card title="🔬 器官渐进发育" icon="🌱" desc="复杂器官需要多阶段逐步发育">
        <InfoBox variant="info">
          <strong>📈 发育阶段：</strong>
          <br />0. <strong>原基</strong> (0% 功能) → 细胞开始分化
          <br />1. <strong>初级结构</strong> (25% 功能) → 基础形态形成
          <br />2. <strong>功能原型</strong> (60% 功能) → 开始发挥部分作用
          <br />3. <strong>成熟器官</strong> (100% 功能) → 完整功能
          <br /><br />
          每个阶段需要若干回合发育，期间有概率发育失败退化。
        </InfoBox>
        <SliderRow
          label="启用渐进发育"
          desc="开启后，器官需要经历4个发育阶段才能完全成熟"
          value={c.enable_organ_development ? 1 : 0}
          min={0}
          max={1}
          step={1}
          onChange={(v) => handleUpdate({ enable_organ_development: v === 1 })}
          formatValue={(v) => v === 1 ? "✅ 开启" : "❌ 关闭"}
        />
        <ConfigGroup title="各阶段发育所需回合数">
          <NumberInput
            label="原基→初级"
            desc="从原基发育到初级结构需要的回合数"
            value={c.organ_stage_0_turns ?? 2}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ organ_stage_0_turns: v })}
            suffix="回合"
          />
          <NumberInput
            label="初级→功能"
            desc="从初级结构发育到功能原型需要的回合数"
            value={c.organ_stage_1_turns ?? 3}
            min={1}
            max={10}
            step={1}
            onChange={(v) => handleUpdate({ organ_stage_1_turns: v })}
            suffix="回合"
          />
          <NumberInput
            label="功能→成熟"
            desc="从功能原型发育到成熟器官需要的回合数"
            value={c.organ_stage_2_turns ?? 5}
            min={1}
            max={15}
            step={1}
            onChange={(v) => handleUpdate({ organ_stage_2_turns: v })}
            suffix="回合"
          />
        </ConfigGroup>
        <ConfigGroup title="各阶段发育失败（退化）概率">
          <SliderRow
            label="原基阶段失败率"
            desc="原基阶段每回合发育失败的概率，失败则退化消失"
            value={c.organ_failure_chance_primordium ?? 0.15}
            min={0}
            max={0.40}
            step={0.05}
            onChange={(v) => handleUpdate({ organ_failure_chance_primordium: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="初级阶段失败率"
            desc="初级阶段每回合发育失败的概率，失败则退化到原基"
            value={c.organ_failure_chance_primitive ?? 0.10}
            min={0}
            max={0.30}
            step={0.05}
            onChange={(v) => handleUpdate({ organ_failure_chance_primitive: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="功能阶段失败率"
            desc="功能阶段每回合发育失败的概率，失败则退化到初级"
            value={c.organ_failure_chance_functional ?? 0.05}
            min={0}
            max={0.20}
            step={0.01}
            onChange={(v) => handleUpdate({ organ_failure_chance_functional: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
      </Card>

      {/* 基因连锁 */}
      <Card title="🔗 基因连锁" icon="⛓️" desc="相关基因一起激活，伴随演化代价">
        <InfoBox variant="info">
          <strong>🧬 连锁效应：</strong>某些基因在染色体上位置相近，会一起遗传和激活。
          <br /><br />
          <strong>示例：</strong>
          <br />• 耐寒性 → 连锁激活代谢调节，但代价是耐热性 -1.5
          <br />• 运动能力 → 连锁激活肌肉发达，但代价是代谢效率 -1.0
          <br />• 防护外壳 → 连锁激活表皮强度，但代价是运动能力 -1.5
        </InfoBox>
        <SliderRow
          label="启用基因连锁"
          desc="开启后，激活某些基因时会自动激活连锁基因，并附带代价"
          value={c.enable_gene_linkage ? 1 : 0}
          min={0}
          max={1}
          step={1}
          onChange={(v) => handleUpdate({ enable_gene_linkage: v === 1 })}
          formatValue={(v) => v === 1 ? "✅ 开启" : "❌ 关闭"}
        />
        <SliderRow
          label="连锁激活概率"
          desc="当主基因激活时，连锁基因同时激活的概率"
          value={c.linkage_activation_chance ?? 0.80}
          min={0.3}
          max={1.0}
          step={0.1}
          onChange={(v) => handleUpdate({ linkage_activation_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <SliderRow
          label="连锁代价倍数"
          desc="连锁触发的代价效果倍数。1.0 = 正常代价，0.5 = 代价减半"
          value={c.linkage_tradeoff_multiplier ?? 1.0}
          min={0.5}
          max={2.0}
          step={0.1}
          onChange={(v) => handleUpdate({ linkage_tradeoff_multiplier: v })}
          formatValue={(v) => `×${v.toFixed(1)}`}
        />
      </Card>

      {/* 水平基因转移 */}
      <Card title="🦠 水平基因转移 (HGT)" icon="↔️" desc="微生物特有的基因获取方式">
        <InfoBox variant="info">
          <strong>🔬 HGT 是什么：</strong>不同物种之间直接交换基因的过程，主要发生在原核生物（细菌、古菌）中。
          这是微生物快速获得抗生素抗性、毒素耐受等能力的重要机制。
          <br /><br />
          <strong>游戏中的应用：</strong>仅适用于营养级 ≤ 1.5 的物种（模拟微生物）。
          每回合有概率从附近的其他微生物获取新特质。
        </InfoBox>
        <SliderRow
          label="启用 HGT"
          desc="开启后，微生物物种可以通过 HGT 从其他微生物获取基因"
          value={c.enable_hgt ? 1 : 0}
          min={0}
          max={1}
          step={1}
          onChange={(v) => handleUpdate({ enable_hgt: v === 1 })}
          formatValue={(v) => v === 1 ? "✅ 开启" : "❌ 关闭"}
        />
        <SliderRow
          label="HGT 适用营养级上限"
          desc="只有营养级不超过此值的物种才能进行 HGT。建议 ≤ 1.5（单细胞/简单多细胞）"
          value={c.hgt_max_trophic_level ?? 1.5}
          min={1.0}
          max={2.5}
          step={0.1}
          onChange={(v) => handleUpdate({ hgt_max_trophic_level: v })}
          formatValue={(v) => `T${v.toFixed(1)}`}
        />
        <SliderRow
          label="HGT 基础概率"
          desc="每回合微生物发生 HGT 的基础概率"
          value={c.hgt_base_chance ?? 0.12}
          min={0.05}
          max={0.30}
          step={0.02}
          onChange={(v) => handleUpdate({ hgt_base_chance: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%/回合`}
        />
        <SliderRow
          label="同域物种加成"
          desc="当有其他微生物在相同地块时，HGT 概率额外增加"
          value={c.hgt_sympatric_bonus ?? 0.08}
          min={0}
          max={0.20}
          step={0.02}
          onChange={(v) => handleUpdate({ hgt_sympatric_bonus: v })}
          formatValue={(v) => `+${(v * 100).toFixed(0)}%`}
        />
        <ConfigGroup title="HGT 转移效率（获得原基因值的比例）">
          <SliderRow
            label="效率下限"
            desc="HGT 转移效率的最小值"
            value={c.hgt_efficiency_min ?? 0.50}
            min={0.3}
            max={0.7}
            step={0.05}
            onChange={(v) => handleUpdate({ hgt_efficiency_min: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <SliderRow
            label="效率上限"
            desc="HGT 转移效率的最大值"
            value={c.hgt_efficiency_max ?? 0.80}
            min={0.5}
            max={1.0}
            step={0.05}
            onChange={(v) => handleUpdate({ hgt_efficiency_max: v })}
            formatValue={(v) => `${(v * 100).toFixed(0)}%`}
          />
        </ConfigGroup>
        <SliderRow
          label="整合稳定概率"
          desc="HGT 获得的基因成功整合到基因组的概率。失败则基因丢失"
          value={c.hgt_integration_stability ?? 0.70}
          min={0.3}
          max={0.95}
          step={0.05}
          onChange={(v) => handleUpdate({ hgt_integration_stability: v })}
          formatValue={(v) => `${(v * 100).toFixed(0)}%`}
        />
      </Card>
    </div>
  );
});

