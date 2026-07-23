from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(f"{__package__}.speciation")


def add_differentiation_noise(
    trait_changes: dict[str, float],
    lineage_code: str,
) -> dict[str, float]:
    """【差异化机制】为不同子代添加随机偏移

    原理：同一次分化的多个子代应该有不同的演化方向
    - 基于谱系编码的最后字符（a, b, c...）确定偏移模式
    - 确保兄弟物种之间有明显差异

    Args:
        trait_changes: 当前变化字典
        lineage_code: 谱系编码（如 "A1a", "A1b", "A1c"）

    Returns:
        添加差异化后的变化字典
    """
    import random
    import hashlib

    if not trait_changes:
        return trait_changes

    # 基于完整谱系编码生成唯一随机种子
    seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    # 提取最后一个字符来确定子代编号
    last_char = lineage_code[-1] if lineage_code else 'a'
    offspring_index = ord(last_char.lower()) - ord('a')  # a=0, b=1, c=2...

    # 定义演化方向偏好（不同子代偏向不同方向）
    # 偏好模式：每个子代有2-3个属性获得额外加成，另外2-3个属性减少
    direction_patterns = [
        {"favor": ["耐寒性", "耐热性"], "disfavor": ["运动能力", "繁殖速度"]},  # 温度适应型
        {"favor": ["运动能力", "攻击性"], "disfavor": ["耐寒性", "社会性"]},     # 活动型
        {"favor": ["繁殖速度", "社会性"], "disfavor": ["攻击性", "运动能力"]},   # 繁殖型
        {"favor": ["防御性", "耐旱性"], "disfavor": ["繁殖速度", "攻击性"]},      # 防御型
        {"favor": ["耐盐性", "耐旱性"], "disfavor": ["社会性", "防御性"]},        # 环境适应型
    ]

    pattern = direction_patterns[offspring_index % len(direction_patterns)]

    adjusted = dict(trait_changes)

    # 对偏好属性添加额外加成（±0.3到±1.0）
    for trait in pattern["favor"]:
        if trait in adjusted:
            bonus = rng.uniform(0.2, 0.8)
            adjusted[trait] = round(adjusted[trait] + bonus, 2)
        else:
            # 即使AI没提议，也添加小幅增加
            adjusted[trait] = round(rng.uniform(0.3, 0.8), 2)

    # 对不偏好属性添加额外减少
    for trait in pattern["disfavor"]:
        if trait in adjusted:
            penalty = rng.uniform(0.2, 0.6)
            adjusted[trait] = round(adjusted[trait] - penalty, 2)
        else:
            # 添加小幅减少
            adjusted[trait] = round(-rng.uniform(0.2, 0.5), 2)

    # 添加额外的随机噪声（确保即使相同模式也有差异）
    for trait_name in list(adjusted.keys()):
        noise = rng.uniform(-0.3, 0.3)
        adjusted[trait_name] = round(adjusted[trait_name] + noise, 2)

    logger.debug(
        f"[差异化] {lineage_code}: 偏好{pattern['favor']}, "
        f"变化总和={sum(adjusted.values()):.2f}"
    )

    return adjusted


def apply_tradeoff_penalties(
    proposed_changes: dict[str, float],
    current_traits: dict[str, float],
    tradeoff_calculator: Any,
) -> dict[str, float]:
    """基于自动代价计算器为增益添加权衡代价。"""
    if not proposed_changes or not tradeoff_calculator:
        return proposed_changes

    gains = {k: v for k, v in proposed_changes.items() if v > 0}
    if not gains:
        return proposed_changes

    try:
        penalties = tradeoff_calculator.calculate_penalties(
            gains, current_traits or {}
        )
    except Exception as e:
        logger.debug(f"[权衡计算] 计算失败，跳过自动代价: {e}")
        return proposed_changes

    if not penalties:
        return proposed_changes

    merged = dict(proposed_changes)
    for trait, delta in penalties.items():
        merged[trait] = merged.get(trait, 0.0) + delta
    logger.debug(f"[权衡计算] 自动代价: {penalties}")
    return merged


def clamp_traits_to_limit(
    traits: dict,
    parent_traits: dict,
    trophic_level: float,
    get_attribute_limits: Callable[[float], dict],
) -> dict:
    """智能钳制属性到营养级限制范围内

    策略：
    1. 单个属性不超过特化上限
    2. 属性总和不超过营养级上限和父代+5.0
    3. 最多2个属性超过基础上限
    """
    limits = get_attribute_limits(trophic_level)

    clamped = dict(traits)

    # 1. 钳制单个属性到特化上限
    for k, v in clamped.items():
        if v > limits["specialized"]:
            clamped[k] = limits["specialized"]

    # 2. 检查并钳制总和
    current_sum = sum(clamped.values())
    parent_sum = sum(parent_traits.values())

    # 总和最多增加5.0（保守的演化步长，比原本允许的8更严格）
    max_increase = 5.0
    target_max_sum = min(limits["total"], parent_sum + max_increase)

    if current_sum > target_max_sum:
        # 计算需要缩减的量
        excess = current_sum - target_max_sum
        # 只缩减增加的属性（保持权衡原则）
        increased_traits = {
            k: v
            for k, v in clamped.items()
            if v > parent_traits.get(k, 0)
        }

        if increased_traits:
            # 按增加量比例分配缩减（增加多的缩减多）
            total_increase = sum(
                v - parent_traits.get(k, 0)
                for k, v in increased_traits.items()
            )
            if total_increase > 0:
                for k, v in increased_traits.items():
                    increase = v - parent_traits.get(k, 0)
                    reduction = excess * (increase / total_increase)
                    clamped[k] = max(parent_traits.get(k, 0), v - reduction)

        # 如果还是超了（说明没有增加的属性或不足以缩减），全局缩放
        current_sum = sum(clamped.values())
        if current_sum > target_max_sum:
            scale = target_max_sum / current_sum
            for k in clamped:
                clamped[k] *= scale

    # 3. 确保最多2个属性超过基础上限
    base_limit = limits["base"]
    specialized_traits = [
        (k, v) for k, v in clamped.items() if v > base_limit
    ]
    if len(specialized_traits) > 2:
        # 保留最高的2个，其余降到基础上限
        specialized_traits.sort(key=lambda x: x[1], reverse=True)
        keep_specialized = {k for k, _ in specialized_traits[:2]}

        for k, v in clamped.items():
            if v > base_limit and k not in keep_specialized:
                clamped[k] = base_limit

    return {k: round(v, 2) for k, v in clamped.items()}


def enforce_trait_tradeoffs(
    current_traits: dict[str, float],
    proposed_changes: dict[str, float],
    lineage_code: str,
) -> dict[str, float]:
    """【强制权衡机制】确保属性变化有增必有减

    原理：50万年的演化不应该是纯粹的"升级"，而是适应性权衡
    - 如果提议的变化只增不减，自动添加减少项
    - 确保属性总和不会无限增长

    Args:
        current_traits: 当前属性字典
        proposed_changes: AI提议的变化 {"耐寒性": 2.0, "运动能力": 1.0}
        lineage_code: 谱系编码（用于确定哪些属性减少）

    Returns:
        调整后的变化字典
    """
    import random
    import hashlib

    if not proposed_changes:
        return proposed_changes

    # 计算总变化
    increases = {k: v for k, v in proposed_changes.items() if v > 0}
    decreases = {k: v for k, v in proposed_changes.items() if v < 0}

    total_increase = sum(increases.values())
    total_decrease = abs(sum(decreases.values()))

    # 如果已经有足够的减少，直接返回
    if total_decrease >= total_increase * 0.3:
        return proposed_changes

    # 需要添加的减少量（至少抵消30%的增加）
    needed_decrease = total_increase * 0.4 - total_decrease
    if needed_decrease <= 0:
        return proposed_changes

    # 基于谱系编码生成确定性随机种子（确保同一物种每次结果一致）
    seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    # 选择要减少的属性（优先选择当前值较高且未被增加的）
    adjusted = dict(proposed_changes)
    candidate_traits = [
        (name, value)
        for name, value in current_traits.items()
        if name not in increases and value > 3.0  # 只减少中高值属性
    ]

    if not candidate_traits:
        # 如果没有合适的候选，从增加项中随机选一个减少幅度
        for trait_name in list(increases.keys()):
            if needed_decrease <= 0:
                break
            reduction = min(needed_decrease, increases[trait_name] * 0.5)
            adjusted[trait_name] = increases[trait_name] - reduction
            needed_decrease -= reduction
        return adjusted

    # 随机选择1-3个属性进行减少
    rng.shuffle(candidate_traits)
    num_to_reduce = min(len(candidate_traits), rng.randint(1, 3))

    for trait_name, current_value in candidate_traits[:num_to_reduce]:
        if needed_decrease <= 0:
            break
        # 减少幅度与当前值成比例（高值属性减更多）
        max_reduction = min(needed_decrease, current_value * 0.2, 3.0)
        reduction = rng.uniform(max_reduction * 0.5, max_reduction)
        adjusted[trait_name] = -round(reduction, 2)
        needed_decrease -= reduction
        logger.debug(
            f"[权衡] {lineage_code}: {trait_name} -{reduction:.2f} (权衡代价)"
        )

    return adjusted


def validate_trait_changes(
    old_traits: dict,
    new_traits: dict,
    trophic_level: float,
    get_attribute_limits: Callable[[float], dict],
) -> tuple[bool, str]:
    """验证属性变化是否符合营养级规则

    【修复】与 prompt 中的预算限制保持一致：
    - prompt 告诉 AI: max_increase=3.0
    - 这里的验证应该允许一定容错（考虑权衡后的净增益）
    - 硬限制改为 6.0（允许 AI 略微超出，但不能离谱）

    Returns:
        (验证是否通过, 错误信息)
    """
    # 获取营养级对应的属性上限
    limits = get_attribute_limits(trophic_level)

    # 1. 检查总和变化（与 prompt 中 max_increase=3.0 对应，但允许容错到 6.0）
    old_sum = sum(old_traits.values())
    new_sum = sum(new_traits.values())
    sum_diff = new_sum - old_sum

    # 【修改】净增益上限从 8 改为 6（prompt 要求 3，允许 2x 容错）
    # 超过 6 说明 AI 完全忽略了预算限制
    if sum_diff > 6.0:
        logger.warning(f"[属性验证] 净增益 {sum_diff:.1f} 超过上限 6.0（prompt 要求 ≤3.0）")
        return False, f"属性总和净增加{sum_diff:.1f}，超过上限6.0（建议≤3.0）"

    # 2. 检查总和是否超过营养级上限
    if new_sum > limits["total"]:
        return False, f"属性总和{new_sum:.1f}超过营养级T{trophic_level:.1f}的上限{limits['total']}"

    # 3. 检查单个属性是否超过特化上限
    above_specialized = [
        (k, v) for k, v in new_traits.items() if v > limits["specialized"]
    ]
    if above_specialized:
        return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]:.1f}超过特化上限{limits['specialized']}"

    # 4. 检查超过基础上限的属性数量
    above_base_count = sum(1 for v in new_traits.values() if v > limits["base"])
    if above_base_count > 2:
        return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个"

    # 5. 检查权衡（有增必有减，除非是小幅提升）
    increases = sum(1 for k, v in new_traits.items() if v > old_traits.get(k, 0))
    decreases = sum(1 for k, v in new_traits.items() if v < old_traits.get(k, 0))

    # 【修改】放宽权衡检查：只有净增益 >4 且无任何减少时才拒绝
    if increases > 0 and decreases == 0 and sum_diff > 4.0:
        return False, f"净增益{sum_diff:.1f}但无权衡代价（需要至少一项属性降低）"

    return True, "验证通过"
