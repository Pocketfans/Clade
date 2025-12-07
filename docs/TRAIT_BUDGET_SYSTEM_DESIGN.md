# 属性预算系统设计文档 (Trait Budget System)

> 版本: v1.0  
> 日期: 2024-12  
> 状态: 设计中

## 一、设计背景

### 1.1 问题描述

当前系统使用基于"时代+营养级"的硬性属性上限，导致：
1. 大量"激活失败: 属性总和XX超过上限YY"的警告
2. 基因激活系统"僵化"，无法正常运作
3. 上限设置不够灵活，无法反映生物复杂度的真实演化跨度

### 1.2 设计目标

1. **无硬上限**：属性预算随时间持续增长
2. **大跨度**：从原核细菌到人类级智慧生物，属性总和跨度应体现巨大的演化差距
3. **时代敏感**：考虑游戏不同时代的时间流速差异
4. **量变引发质变**：达到特定阈值时触发突破效果
5. **与基因库配合**：边际递减防止数值爆炸

---

## 二、时间流配置 (Chronos Flow)

### 2.1 游戏时间设置

根据 `simulation/constants.py` 的 `ERA_TIMELINE` 配置：

| 时代 | 回合范围 | 每回合年数 | 累计回合 | 真实时间 |
|------|----------|-----------|---------|----------|
| **太古宙** | 0-15 | 2000万年 | 15 | 28亿→25亿年前 |
| **元古宙** | 15-54 | 5000万年 | 39 | 25亿→5.4亿年前 |
| **古生代** | 54-343 | 100万年 | 289 | 5.4亿→2.5亿年前 |
| **中生代** | 343-715 | 50万年 | 372 | 2.5亿→0.66亿年前 |
| **新生代** | 715-979 | 25万年 | 264 | 0.66亿→现代 |
| **未来纪** | 979+ | 25万年 | - | 持续演化 |

**总计**：约 **980回合** 到达现代，**2000回合** 可达未来约2500万年后。

### 2.2 关键时间节点

| 回合 | 事件 | 生物学意义 |
|------|------|-----------|
| 0 | 游戏开始 | 原核细菌、最早生命 |
| ~10 | 太古宙中期 | 蓝藻、光合作用 |
| ~15 | 真核细胞出现 | 复杂度跃升 |
| ~40 | 多细胞生物 | 协作涌现 |
| **54** | **寒武纪大爆发** | **物种多样性激增** |
| ~150 | 鱼类时代 | 脊椎动物兴起 |
| ~280 | 登陆事件 | 两栖→陆地 |
| ~343 | 二叠纪大灭绝 | 古生代结束 |
| ~500 | 恐龙时代 | 中生代鼎盛 |
| ~715 | 恐龙灭绝 | K-Pg事件 |
| ~850 | 灵长类出现 | 智慧生物雏形 |
| ~979 | 现代 | 人类文明 |
| ~2000 | 远未来 | 后人类演化 |

---

## 三、属性预算公式

### 3.1 核心公式

```python
预算上限 = 基础值 × 时代因子 × 营养级因子 × 体型因子 × 器官因子
```

### 3.2 时代因子（核心）

基于回合数的**分段幂函数**，在关键节点加速：

```python
def get_era_factor(turn_index: int) -> float:
    """
    计算时代因子，体现演化复杂度的累积
    
    设计理念：
    - 太古宙（0-15）: 缓慢起步，1.0→1.5
    - 元古宙（15-54）: 稳定增长，1.5→4.0
    - 古生代（54-343）: 寒武纪爆发后加速！4.0→25.0
    - 中生代（343-715）: 持续增长，25.0→50.0
    - 新生代（715-979）: 精细演化，50.0→70.0
    - 未来（979+）: 无限可能
    """
    if turn_index <= 15:
        # 太古宙：线性起步
        return 1.0 + (turn_index / 15) * 0.5
    
    elif turn_index <= 54:
        # 元古宙：加速准备
        base = 1.5
        progress = (turn_index - 15) / (54 - 15)
        return base + progress * 2.5  # 1.5 → 4.0
    
    elif turn_index <= 343:
        # 古生代：寒武纪大爆发！指数增长
        base = 4.0
        progress = (turn_index - 54) / (343 - 54)
        # 使用幂函数加速：progress^1.3
        return base + (progress ** 1.3) * 21.0  # 4.0 → 25.0
    
    elif turn_index <= 715:
        # 中生代：稳定增长
        base = 25.0
        progress = (turn_index - 343) / (715 - 343)
        return base + progress * 25.0  # 25.0 → 50.0
    
    elif turn_index <= 979:
        # 新生代：精细演化
        base = 50.0
        progress = (turn_index - 715) / (979 - 715)
        return base + progress * 20.0  # 50.0 → 70.0
    
    else:
        # 未来：持续增长（对数减速）
        base = 70.0
        extra_turns = turn_index - 979
        return base + 15.0 * math.log(1 + extra_turns / 200)
```

### 3.3 营养级因子

高营养级生物需要更多能力（感知、运动、捕食等）：

```python
def get_trophic_factor(trophic_level: float) -> float:
    """
    营养级因子：T1→T5 逐级提升
    
    - T1.0 (生产者): 0.8
    - T2.0 (草食): 1.0
    - T3.0 (小肉食): 1.25
    - T4.0 (大肉食): 1.5
    - T5.0 (顶级): 1.8
    """
    return 0.6 + trophic_level * 0.24
```

### 3.4 体型因子

基于克莱伯定律（代谢率 ∝ 体重^0.75）：

```python
def get_size_factor(body_weight_g: float) -> float:
    """
    体型因子：大型生物可维持更高属性总和
    
    - 细菌 (10^-12g): 0.6
    - 单细胞 (10^-6g): 0.75
    - 1g 生物: 1.0
    - 1kg 生物: 1.2
    - 100kg 生物: 1.4
    - 10000kg 生物: 1.6
    """
    if body_weight_g <= 0:
        return 0.6
    
    log_weight = math.log10(body_weight_g)
    # 参考点：1g = 1.0
    factor = 1.0 + 0.08 * max(-5, min(5, log_weight))
    return max(0.5, min(1.8, factor))
```

### 3.5 器官因子

器官系统复杂度加成：

```python
def get_organ_factor(organ_count: int, mature_count: int) -> float:
    """
    器官因子：复杂器官系统允许更高属性
    
    - 0器官: 1.0
    - 5器官: 1.1
    - 10器官: 1.2
    - 成熟器官额外 +0.02 每个
    """
    base = 1.0 + min(organ_count, 15) * 0.02
    mature_bonus = min(mature_count, 10) * 0.02
    return min(1.5, base + mature_bonus)
```

### 3.6 基础值配置

```python
BASE_BUDGET = 15.0  # 最早生命的属性预算基础
```

---

## 四、预算计算示例

| 回合 | 时代 | 时代因子 | 营养级T2.0 | 体型1g | 器官5个 | **预算** |
|------|------|----------|-----------|--------|---------|----------|
| 0 | 太古宙初 | 1.0 | 1.08 | 1.0 | 1.0 | **16** |
| 10 | 太古宙中 | 1.33 | 1.08 | 0.9 | 1.02 | **20** |
| 15 | 太古宙末 | 1.5 | 1.08 | 0.95 | 1.04 | **25** |
| 40 | 元古宙中 | 3.1 | 1.08 | 0.95 | 1.06 | **52** |
| 54 | 寒武纪初 | 4.0 | 1.08 | 1.0 | 1.08 | **70** |
| 100 | 古生代早 | 7.5 | 1.08 | 1.1 | 1.1 | **147** |
| 200 | 古生代中 | 14.5 | 1.08 | 1.15 | 1.15 | **305** |
| 343 | 古生代末 | 25.0 | 1.08 | 1.2 | 1.2 | **583** |
| 500 | 中生代中 | 35.6 | 1.32 | 1.3 | 1.25 | **1144** |
| 715 | 中生代末 | 50.0 | 1.32 | 1.35 | 1.3 | **1730** |
| 850 | 新生代中 | 60.0 | 1.56 | 1.4 | 1.35 | **2656** |
| 979 | 现代 | 70.0 | 1.56 | 1.4 | 1.4 | **3218** |
| 2000 | 远未来 | 95.0 | 1.8 | 1.5 | 1.5 | **5775** |

**跨度**：16 → 5775+，约 **360倍**！

---

## 五、单属性上限

### 5.1 动态单属性上限

```python
def get_single_trait_cap(turn_index: int) -> float:
    """
    单属性上限随时代增长
    
    - 太古宙: 8-10
    - 元古宙: 10-15
    - 古生代: 15-25
    - 中生代: 25-40
    - 新生代: 40-50
    - 未来: 50+
    """
    if turn_index <= 15:
        return 8.0 + turn_index * 0.13
    elif turn_index <= 54:
        return 10.0 + (turn_index - 15) * 0.13
    elif turn_index <= 343:
        return 15.0 + (turn_index - 54) * 0.035
    elif turn_index <= 715:
        return 25.0 + (turn_index - 343) * 0.04
    elif turn_index <= 979:
        return 40.0 + (turn_index - 715) * 0.038
    else:
        return 50.0 + math.log(1 + (turn_index - 979) / 100) * 10
```

### 5.2 栖息地加成

特定栖息地允许相关属性超过普通上限：

```python
HABITAT_TRAIT_BONUS = {
    "deep_sea": {
        "耐高压": 5.0,
        "暗视觉": 3.0,
        "耐寒性": 2.0,
    },
    "terrestrial": {
        "运动能力": 3.0,
        "耐旱性": 3.0,
    },
    "aerial": {
        "运动能力": 5.0,
        "感知能力": 3.0,
    },
    "marine": {
        "耐盐性": 4.0,
        "渗透调节": 3.0,
    },
    "freshwater": {
        "渗透调节": 3.0,
        "耐缺氧": 2.0,
    },
}
```

### 5.3 器官加成

成熟器官解锁相关属性额外上限：

```python
ORGAN_TRAIT_BONUS = {
    "sensory": {
        "警觉性": 4.0,
        "感知能力": 4.0,
    },
    "locomotion": {
        "运动能力": 5.0,
        "迁徙能力": 3.0,
    },
    "defense": {
        "防御性": 4.0,
        "物理防御": 4.0,
    },
    "metabolic": {
        "耐寒性": 2.0,
        "耐热性": 2.0,
        "饥饿耐受": 3.0,
    },
    "respiratory": {
        "耐缺氧": 4.0,
        "高效呼吸": 3.0,
    },
    "nervous": {
        "智力": 5.0,
        "社会性": 3.0,
    },
}

# 加成按器官阶段缩放
# 阶段0(原基): 0%
# 阶段1(初级): 25%
# 阶段2(功能): 60%
# 阶段3(成熟): 100%
```

---

## 六、边际递减机制

### 6.1 基础边际递减

防止单属性无限堆叠：

```python
def get_diminishing_factor(current_value: float, turn_index: int) -> float:
    """
    边际递减：属性越高，新增益效率越低
    
    阈值基于当前单属性上限动态调整
    """
    cap = get_single_trait_cap(turn_index)
    
    # 相对阈值（基于上限的比例）
    t1 = cap * 0.5   # 50%上限：开始递减
    t2 = cap * 0.7   # 70%上限：加速递减
    t3 = cap * 0.85  # 85%上限：严重递减
    t4 = cap * 0.95  # 95%上限：接近极限
    
    if current_value < t1:
        return 1.0
    elif current_value < t2:
        return 0.6
    elif current_value < t3:
        return 0.3
    elif current_value < t4:
        return 0.1
    else:
        return 0.02  # 接近上限时几乎无法增长
```

### 6.2 突破减缓边际递减

达到突破阈值后，边际递减效果减弱：

```python
def apply_breakthrough_bonus(diminishing_factor: float, value: float, turn_index: int) -> float:
    """突破等级减缓边际递减"""
    
    cap = get_single_trait_cap(turn_index)
    
    # 专精突破（50%上限）：边际递减×1.3
    if value >= cap * 0.5:
        diminishing_factor *= 1.3
    
    # 大师突破（65%上限）：边际递减×1.5
    if value >= cap * 0.65:
        diminishing_factor *= 1.15
    
    # 卓越突破（80%上限）：边际递减×2.0
    if value >= cap * 0.8:
        diminishing_factor *= 1.33
    
    # 传奇突破（90%上限）：免疫边际递减
    if value >= cap * 0.9:
        return 1.0
    
    return min(1.0, diminishing_factor)
```

---

## 七、量变引发质变：突破系统

### 7.1 单属性突破

基于**相对于当前上限的比例**（而非绝对值）触发：

```python
TRAIT_BREAKTHROUGH_TIERS = {
    0.50: {
        "name": "专精",
        "effect": "该属性生态效果+30%",
        "bonus": {"eco_effect": 0.30}
    },
    0.65: {
        "name": "大师", 
        "effect": "边际递减减缓",
        "bonus": {"diminishing_reduction": 0.50}
    },
    0.80: {
        "name": "卓越",
        "effect": "该属性上限+15%",
        "bonus": {"cap_bonus_percent": 0.15}
    },
    0.90: {
        "name": "传奇",
        "effect": "免疫边际递减",
        "bonus": {"no_diminishing": True}
    },
    0.98: {
        "name": "神话",
        "effect": "该属性可协同增强相关属性",
        "bonus": {"synergy_unlock": True}
    },
}
```

### 7.2 总和突破

基于**相对于当前预算的比例**触发：

```python
TOTAL_BREAKTHROUGH_TIERS = {
    0.30: {
        "name": "简单生物",
        "effect": "器官槽位+1",
        "bonus": {"organ_slots": 1}
    },
    0.50: {
        "name": "复杂生物",
        "effect": "基因激活概率+20%",
        "bonus": {"activation_bonus": 0.20}
    },
    0.70: {
        "name": "高等生物",
        "effect": "新基因发现概率+30%",
        "bonus": {"discovery_bonus": 0.30}
    },
    0.85: {
        "name": "顶级生物",
        "effect": "竞争压力-15%",
        "bonus": {"competition_reduce": 0.15}
    },
    0.95: {
        "name": "顶点生物",
        "effect": "繁殖效率+20%",
        "bonus": {"reproduction_bonus": 0.20}
    },
    1.00: {
        "name": "传奇生物",
        "effect": "可获得稀有基因",
        "bonus": {"rare_genes": True}
    },
}
```

### 7.3 绝对阈值突破

某些里程碑基于绝对数值（不随时代变化）：

```python
ABSOLUTE_MILESTONES = {
    100: ("百点生物", "达成属性总和100"),
    500: ("精英生物", "达成属性总和500"),
    1000: ("卓越存在", "达成属性总和1000"),
    2000: ("超级生物", "达成属性总和2000"),
    5000: ("传奇存在", "达成属性总和5000"),
}
```

---

## 八、超预算处理

### 8.1 处理策略

```python
def handle_budget_overflow(species, budget, turn_index):
    """处理属性总和超出预算的情况"""
    
    current_total = sum(species.abstract_traits.values())
    overflow_ratio = current_total / budget - 1.0
    
    if overflow_ratio <= 0:
        return "normal", None
    
    elif overflow_ratio <= 0.15:
        # 超出≤15%：警告但允许（物种特化）
        return "warning", f"属性略超预算 ({overflow_ratio:.0%})"
    
    elif overflow_ratio <= 0.40:
        # 超出15-40%：自动权衡
        sacrifice_amount = (current_total - budget) * 0.7
        sacrifice_trait = find_lowest_priority_trait(species)
        
        species.abstract_traits[sacrifice_trait] = max(
            1.0, 
            species.abstract_traits[sacrifice_trait] - sacrifice_amount
        )
        return "tradeoff", f"权衡: {sacrifice_trait} 削减 {sacrifice_amount:.1f}"
    
    else:
        # 超出>40%：等比缩放
        scale = (budget * 1.4) / current_total
        for trait in species.abstract_traits:
            species.abstract_traits[trait] *= scale
        return "scaled", f"属性缩放至 {scale:.0%}"
```

---

## 九、与基因库的配合

### 9.1 基因激活时的预算检查

```python
def can_activate_gene(species, trait_name, gain_value, turn_index):
    """检查是否可以激活基因"""
    
    budget = calculate_budget(species, turn_index)
    current_total = sum(species.abstract_traits.values())
    
    # 应用边际递减
    current_value = species.abstract_traits.get(trait_name, 0)
    diminishing = get_diminishing_factor(current_value, turn_index)
    effective_gain = gain_value * diminishing
    
    # 检查单属性上限
    single_cap = get_single_trait_cap(turn_index)
    single_cap += get_habitat_bonus(species, trait_name)
    single_cap += get_organ_bonus(species, trait_name)
    
    if current_value + effective_gain > single_cap:
        effective_gain = single_cap - current_value
    
    # 检查总预算
    new_total = current_total + effective_gain
    overflow = new_total / budget - 1.0
    
    if overflow > 0.4:
        # 超出过多，需要权衡
        return True, effective_gain, "需要权衡"
    
    return True, effective_gain, None
```

### 9.2 LLM 生成基因的预算约束

在 LLM prompt 中提供预算信息：

```python
def get_budget_prompt_context(species, turn_index):
    """为LLM生成预算上下文"""
    
    budget = calculate_budget(species, turn_index)
    current_total = sum(species.abstract_traits.values())
    single_cap = get_single_trait_cap(turn_index)
    
    return f"""
【属性预算信息】
- 当前属性总和: {current_total:.0f}
- 预算上限: {budget:.0f}
- 剩余空间: {max(0, budget - current_total):.0f}
- 单属性上限: {single_cap:.0f}

【生成基因建议】
- 新基因潜力值范围: 3.0 - {min(8.0, single_cap * 0.3):.1f}
- 建议生成 1-3 个休眠基因
- 约 80% 有益/中性，20% 轻微有害
"""
```

---

## 十、配置类定义

```python
class TraitBudgetConfig(BaseModel):
    """属性预算系统配置"""
    model_config = ConfigDict(extra="ignore")
    
    # ========== 基础参数 ==========
    base_budget: float = Field(default=15.0, description="基础预算值")
    
    # ========== 时代因子参数 ==========
    # 太古宙 (回合0-15)
    archean_start: float = Field(default=1.0, description="太古宙起始因子")
    archean_end: float = Field(default=1.5, description="太古宙结束因子")
    
    # 元古宙 (回合15-54)
    proterozoic_end: float = Field(default=4.0, description="元古宙结束因子")
    
    # 古生代 (回合54-343) - 寒武纪大爆发！
    paleozoic_exponent: float = Field(default=1.3, description="古生代增长指数")
    paleozoic_end: float = Field(default=25.0, description="古生代结束因子")
    
    # 中生代 (回合343-715)
    mesozoic_end: float = Field(default=50.0, description="中生代结束因子")
    
    # 新生代 (回合715-979)
    cenozoic_end: float = Field(default=70.0, description="新生代结束因子")
    
    # 未来 (回合979+)
    future_growth_rate: float = Field(default=15.0, description="未来增长系数")
    future_scale: float = Field(default=200.0, description="未来增长缩放")
    
    # ========== 营养级因子 ==========
    trophic_base: float = Field(default=0.6, description="营养级基础")
    trophic_coefficient: float = Field(default=0.24, description="营养级系数")
    
    # ========== 体型因子 ==========
    size_coefficient: float = Field(default=0.08, description="体型系数")
    size_min: float = Field(default=0.5, description="体型因子下限")
    size_max: float = Field(default=1.8, description="体型因子上限")
    
    # ========== 器官因子 ==========
    organ_coefficient: float = Field(default=0.02, description="器官系数")
    organ_max_count: int = Field(default=15, description="计算器官数上限")
    mature_bonus: float = Field(default=0.02, description="成熟器官额外加成")
    
    # ========== 单属性上限 ==========
    single_cap_archean: float = Field(default=8.0, description="太古宙单属性上限")
    single_cap_proterozoic: float = Field(default=15.0, description="元古宙单属性上限")
    single_cap_paleozoic: float = Field(default=25.0, description="古生代单属性上限")
    single_cap_mesozoic: float = Field(default=40.0, description="中生代单属性上限")
    single_cap_cenozoic: float = Field(default=50.0, description="新生代单属性上限")
    
    # ========== 边际递减 ==========
    diminishing_t1_ratio: float = Field(default=0.5, description="第一递减阈值比例")
    diminishing_t2_ratio: float = Field(default=0.7, description="第二递减阈值比例")
    diminishing_t3_ratio: float = Field(default=0.85, description="第三递减阈值比例")
    diminishing_t4_ratio: float = Field(default=0.95, description="第四递减阈值比例")
    diminishing_f1: float = Field(default=0.6, description="第一区间系数")
    diminishing_f2: float = Field(default=0.3, description="第二区间系数")
    diminishing_f3: float = Field(default=0.1, description="第三区间系数")
    diminishing_f4: float = Field(default=0.02, description="第四区间系数")
    
    # ========== 突破阈值（相对比例）==========
    breakthrough_specialist: float = Field(default=0.50, description="专精阈值")
    breakthrough_master: float = Field(default=0.65, description="大师阈值")
    breakthrough_excellent: float = Field(default=0.80, description="卓越阈值")
    breakthrough_legend: float = Field(default=0.90, description="传奇阈值")
    breakthrough_myth: float = Field(default=0.98, description="神话阈值")
    
    # ========== 超预算处理 ==========
    overflow_warning: float = Field(default=0.15, description="警告阈值")
    overflow_tradeoff: float = Field(default=0.40, description="强制权衡阈值")
    tradeoff_efficiency: float = Field(default=0.70, description="权衡效率")
```

---

## 十一、实现路径

### 11.1 文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `models/config.py` | 添加 `TraitBudgetConfig` 配置类 |
| `services/species/trait_config.py` | 重构预算计算逻辑 |
| `services/species/gene_activation.py` | 应用新的预算检查 |
| `services/species/speciation.py` | 在分化时应用预算约束 |
| `ai/prompts/species.py` | 更新 prompt 中的预算信息 |

### 11.2 实现步骤

1. **第一阶段**：添加配置类和基础计算函数
2. **第二阶段**：重构 `trait_config.py` 的上限验证逻辑
3. **第三阶段**：修改 `gene_activation.py` 应用新机制
4. **第四阶段**：添加突破系统和事件日志
5. **第五阶段**：更新 LLM prompt 的预算上下文

---

## 十二、测试用例

### 12.1 预算计算测试

```python
def test_budget_calculation():
    # 太古宙
    assert 15 <= calculate_budget(turn=0, trophic=1.0, mass=1e-6) <= 20
    
    # 寒武纪初期
    assert 60 <= calculate_budget(turn=54, trophic=2.0, mass=1.0) <= 80
    
    # 古生代中期
    assert 250 <= calculate_budget(turn=200, trophic=2.5, mass=100) <= 350
    
    # 现代
    assert 2500 <= calculate_budget(turn=979, trophic=4.0, mass=70000) <= 4000
```

### 12.2 边际递减测试

```python
def test_diminishing_returns():
    # 低属性：无递减
    assert get_diminishing_factor(5.0, turn=100) == 1.0
    
    # 中属性：开始递减
    assert get_diminishing_factor(15.0, turn=100) < 1.0
    
    # 高属性：严重递减
    assert get_diminishing_factor(22.0, turn=100) < 0.3
```

---

## 附录：数值参考表

### A. 代表性物种属性预算

| 物种类型 | 回合 | 时代因子 | 营养级因子 | 体型因子 | 预算 |
|---------|------|----------|-----------|---------|------|
| 原核细菌 | 0 | 1.0 | 0.84 | 0.6 | 8 |
| 蓝藻 | 10 | 1.3 | 0.84 | 0.65 | 11 |
| 原生动物 | 40 | 3.1 | 1.08 | 0.75 | 38 |
| 三叶虫 | 60 | 4.5 | 1.08 | 1.0 | 73 |
| 盾皮鱼 | 150 | 10.0 | 1.20 | 1.15 | 207 |
| 两栖类 | 280 | 18.5 | 1.20 | 1.25 | 416 |
| 恐龙 | 500 | 35.6 | 1.44 | 1.5 | 1155 |
| 早期哺乳 | 715 | 50.0 | 1.32 | 1.2 | 1188 |
| 灵长类 | 900 | 65.0 | 1.44 | 1.35 | 1899 |
| 人类 | 979 | 70.0 | 1.56 | 1.4 | 2293 |

### B. 突破里程碑预览

以回合200（古生代中期）为例，预算约300：

| 属性总和 | 占预算比 | 突破状态 |
|---------|---------|----------|
| 90 | 30% | 简单生物 |
| 150 | 50% | 复杂生物 |
| 210 | 70% | 高等生物 |
| 255 | 85% | 顶级生物 |
| 285 | 95% | 顶点生物 |
| 300 | 100% | 传奇生物 |

---

## 十三、Prompt 工程优化方案

### 13.1 优化目标

将属性预算系统与 LLM prompt 深度整合，确保 AI 生成的演化内容符合预算约束，并能利用边际递减和突破系统的机制优化演化策略。

### 13.2 新增 Prompt 上下文

#### 13.2.1 增强的预算上下文函数

```python
def get_enhanced_budget_context(species, turn_index: int) -> dict:
    """生成增强的预算上下文（供 prompt 使用）
    
    返回：
    {
        "budget_summary": 预算总览文本,
        "diminishing_warning": 边际递减警告,
        "breakthrough_hints": 突破机会提示,
        "habitat_bonus": 栖息地特化加成,
        "recommended_strategy": 推荐演化策略
    }
    """
    budget = calculate_budget(species, turn_index)
    current_total = sum(species.abstract_traits.values())
    single_cap = get_single_trait_cap(turn_index)
    
    # 1. 预算总览
    usage_percent = current_total / budget if budget > 0 else 0
    remaining = max(0, budget - current_total)
    budget_summary = f"""
【属性预算总览】
- 当前属性总和: {current_total:.0f} / {budget:.0f} ({usage_percent:.0%})
- 剩余空间: {remaining:.0f}
- 单属性上限: {single_cap:.0f}
"""
    
    # 2. 边际递减警告
    diminishing_traits = []
    for trait, value in species.abstract_traits.items():
        ratio = value / single_cap if single_cap > 0 else 0
        if ratio >= 0.5:
            efficiency = get_diminishing_factor(value, turn_index)
            diminishing_traits.append(f"  - {trait}: {value:.1f} ({ratio:.0%}上限，增益效率{efficiency:.0%})")
    
    diminishing_warning = ""
    if diminishing_traits:
        diminishing_warning = f"""
【边际递减警告】
以下属性已进入递减区域（增益效率降低）：
{chr(10).join(diminishing_traits)}
建议：分散投资多个属性，或寻求突破阈值。
"""
    
    # 3. 突破机会提示
    breakthrough_hints = []
    for trait, value in species.abstract_traits.items():
        ratio = value / single_cap if single_cap > 0 else 0
        for threshold, tier in [(0.50, "专精"), (0.65, "大师"), (0.80, "卓越"), (0.90, "传奇")]:
            if ratio < threshold <= ratio + 0.15:
                gap = (threshold * single_cap) - value
                breakthrough_hints.append(f"  - {trait}: 再+{gap:.1f}可达「{tier}」突破")
                break
    
    breakthrough_text = ""
    if breakthrough_hints:
        breakthrough_text = f"""
【突破机会】
{chr(10).join(breakthrough_hints)}
突破后可获得特殊效果加成！
"""
    
    # 4. 栖息地特化加成
    habitat_bonus = get_habitat_trait_bonus(species.habitat_type)
    habitat_text = ""
    if habitat_bonus:
        bonus_lines = [f"  - {trait}: 上限+{bonus:.0f}" for trait, bonus in habitat_bonus.items()]
        habitat_text = f"""
【栖息地特化】
{species.habitat_type} 环境允许以下属性突破普通上限：
{chr(10).join(bonus_lines)}
"""
    
    return {
        "budget_summary": budget_summary,
        "diminishing_warning": diminishing_warning,
        "breakthrough_hints": breakthrough_text,
        "habitat_bonus": habitat_text,
        "usage_percent": usage_percent,
        "remaining_budget": remaining,
    }
```

#### 13.2.2 边际递减提示模板

```python
DIMINISHING_RETURNS_PROMPT = """
=== ⚖️ 边际递减机制 ===
属性越高，新增益效率越低：
- 属性 < {t1}（50%上限）: 100% 增益效率
- 属性 {t1}-{t2}（50-70%上限）: 60% 增益效率  
- 属性 {t2}-{t3}（70-85%上限）: 30% 增益效率
- 属性 > {t3}（>85%上限）: 10% 增益效率

{current_high_traits}

💡 策略建议：分散投资多个中等属性 > 集中堆叠单个高属性
"""
```

#### 13.2.3 突破系统提示模板

```python
BREAKTHROUGH_PROMPT = """
=== 🏆 突破系统（量变引发质变）===
当属性达到上限的特定比例时，触发突破效果：

【单属性突破】
- 50% 上限 → 「专精」: 该属性生态效果+30%
- 65% 上限 → 「大师」: 边际递减减缓50%
- 80% 上限 → 「卓越」: 该属性上限额外+15%
- 90% 上限 → 「传奇」: 免疫边际递减
- 98% 上限 → 「神话」: 协同增强相关属性

【当前突破状态】
{current_breakthroughs}

【接近突破】
{near_breakthroughs}
"""
```

### 13.3 修改的 Prompt 位置

#### 13.3.1 `speciation` Prompt 增强

在 `speciation` prompt 的约束部分添加：

```python
=== ⚠️ 硬性约束（必须遵守）===

【属性权衡预算】
{trait_budget_summary}

【边际递减提示】
{diminishing_returns_context}

【突破机会】  
{breakthrough_opportunities}

【栖息地特化】
{habitat_specialization_bonus}
```

#### 13.3.2 `speciation_batch` Prompt 增强

```python
=== ⚠️ 演化预算（硬性限制）===
- 📊 总增益上限: {max_increase}（基于时代因子 {era_factor:.1f}）
- 📏 单项上限: {single_max}
- 🏛️ 时代总预算: {era_budget:.0f}
- 📈 当前使用: {current_usage:.0f} ({usage_percent:.0%})
- 🔮 突破候选: {breakthrough_candidate}（差 {gap:.1f} 点）

【边际递减提示】
{diminishing_summary}

【演化策略建议】
{strategy_recommendation}
```

### 13.4 实现优先级

| 优先级 | 任务 | 文件 |
|--------|------|------|
| P0 | 实现 `get_enhanced_budget_context()` | `speciation_rules.py` |
| P0 | 添加边际递减计算函数 | `trait_config.py` |
| P0 | 添加突破检测函数 | `trait_config.py` |
| P1 | 更新 `speciation` prompt | `species.py` |
| P1 | 更新 `speciation_batch` prompt | `species.py` |
| P2 | 添加栖息地加成配置 | `trait_config.py` |
| P2 | 添加器官加成配置 | `trait_config.py` |

### 13.5 预期效果

1. **LLM 更好理解约束**：通过详细的预算信息，减少违规输出
2. **策略性演化**：LLM 可以主动追求突破阈值，设计更有深度的演化路径
3. **避免数值爆炸**：边际递减提示引导分散投资
4. **利用栖息地优势**：针对性强化栖息地特化属性

---

*文档结束*
