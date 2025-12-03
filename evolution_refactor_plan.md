# 演化系统重构方案：矩阵驱动与区域适应 v2.0

本方案旨在解决现有演化系统中的核心问题，并综合了历史讨论中的**协同环境压力**、**严格物理约束**和**地质时代限制**等关键点。

## 0. 问题总结与改进目标 (User Feedback Summary)

基于用户的反馈，现有系统存在以下关键缺陷需要修复：

1.  **能量守恒缺失 (Lack of Trade-offs)**:
    *   **问题**: 物种属性在演化中往往“只增不减”，缺乏生物学上必然的代价（Trade-off）。例如，耐寒性增加时，代谢成本或繁殖速度理应下降。
    *   **目标**: 引入数学上的强制归一化，确保“有得必有失”，模拟有限的生物能量预算。

2.  **计算效率低下 (Inefficient Computation)**:
    *   **问题**: 目前的演化计算基于 Python 循环遍历地块和物种，在大规模模拟时效率低下。
    *   **目标**: 全面转向 Numpy 矩阵运算，利用向量广播机制提升性能。

3.  **演化碎片化与同质化 (Fragmentation & Redundancy)**:
    *   **问题**: 基于单个地块的独立演化导致产生大量微小差异的重复物种（物种大爆炸），且缺乏宏观的地理隔离逻辑。
    *   **目标**: 引入“生态-地理区域”（Eco-Geo Region）聚类，只在区域层面上触发显著分化，抑制微观噪音。

4.  **系统整合度不足 (Loose Integration)**:
    *   **问题**: 适应性检查、分化触发和环境压力计算（如协同压力）分散在不同模块，缺乏统一利用。
    *   **目标**: 整合 `AdaptationService` 和 `SpeciationService`，统一使用环境矩阵和压力逻辑。

---

## 1. 核心机制：矩阵驱动的能量守恒 (Matrix-Driven Energetics)

我们将演化过程数学化，所有 LLM 的叙事都必须服从底层的数学约束。

### 1.1 特征向量与能量预算
将物种的 `abstract_traits` 视为向量 $V_{traits}$。引入 **特征模长 (Magnitude)** 限制，强制执行有增有减。

*   **归一化公式 (L2 Norm Constraint)**:
    $$ V_{new} = V_{old} + \alpha \cdot V_{delta} $$
    $$ V_{final} = V_{new} \cdot \frac{\|V_{old}\|}{\|V_{new}\|} $$
*   **效果**: 当一个属性（如耐寒性）增加时，为了保持总模长不变，其他所有属性（如繁殖速度、代谢率）会按比例自动微幅下降。
*   **时代限制 (Era Cap)**: 模长的上限 $\|V_{max}\|$ 受限于地质时代。早期生物（如太古宙）的 $\|V_{max}\|$ 较小，限制了其演化出极端特质的能力；随着时代演进，生物复杂性增加，$\|V_{max}\|$ 逐渐解锁。

### 1.2 Numpy 矩阵化计算
利用 Numpy 广播机制，批量计算适应方向。

*   **环境压力矩阵 ($M_{env}$)**: $N_{tiles} \times N_{dims}$ 
    *   包含归一化的温度、湿度、海拔。
    *   **关键补充**: 包含 **协同压力 (Synergistic Pressure)** 指标（如湿球温度、高海拔紫外线、低温高湿），不仅仅是单一维度。
*   **物种分布掩码 ($M_{dist}$)**: $N_{tiles} \times N_{species}$ (加权种群数量)
*   **区域聚合**: 通过矩阵乘法快速计算每个物种在不同区域的加权平均环境压力，无需 Python 循环。

---

## 2. 演化流程重构：区域聚类与双轨制 (Dual-Track Evolution)

演化不再是随机的，而是基于“区域差异”的判定。

### 2.1 区域识别 (Eco-Geo Region Identification)
为了避免“地块级碎片化演化”，我们引入 **Eco-Geo Region** 概念。

1.  **物理聚类**: 基于连通性识别地块簇 (Clusters)。
2.  **环境均质性**: 检查 Cluster 内部环境方差。如果方差过大，进一步分裂。
3.  **显著性过滤**: 忽略种群数量 < 5% 总种群的边缘碎片区域。
4.  **严格物理约束检查**: 在定义区域时，排除那些对该物种**绝对致死**的地块（基于 strict habitability 规则，如纯陆生生物排除深海地块），防止演化出不合逻辑的怪物。

### 2.2 双轨演化路径

系统每回合对每个物种执行以下检查：

#### **Track A: 渐进式适应 (Progressive Adaptation) - "用进废退"**
*   **触发条件**: 物种在所有主要区域的 $V_{ideal}$ 差异较小 (Cosine Similarity > 0.9)。
*   **操作**:
    *   计算全域加权平均的目标向量 $V_{target}$。
    *   物种特征向量向 $V_{target}$ 移动一小步 (Step Size $\eta$)。
    *   执行能量守恒归一化。
*   **结果**: 原物种数值更新，不产生新物种。

#### **Track B: 分化演化 (Speciation) - "同种异梦"**
*   **触发条件**: 物种在两个不同区域 (Region A, Region B) 的 $V_{ideal}$ 差异显著 (Cosine Similarity < 0.85)。
*   **操作**:
    *   计算 Region A 的特化向量 $V_A$ 和 Region B 的特化向量 $V_B$。
    *   **硬性约束生成**: 识别 $V_A$ 中必须满足的硬性门槛。
        *   **协同压力约束**: 如果 Region A 存在高湿热压力，强制要求 `耐热性` 提升。
        *   **物理约束**: 如果 Region A 是深海，强制维持 `耐压性` 和 `游动能力`。
    *   **调用 LLM**: 发送 Region A 的环境摘要和 $V_A$ 的数值约束。
*   **结果**: 产生新物种（亚种），且该亚种**仅分配**到 Region A 的地块上。

---

## 3. Prompt 工程优化：高信噪比的情报与决策

为了平衡 **LLM 的灵活性** 与 **Token 成本**，我们采用 **"Python 聚合情报 -> LLM 战略决策 -> Python 审计执行"** 的流程。

### 3.1 核心策略：有限预算下的自由决策
我们不剥夺 LLM 的决策权，而是为其提供高质量的决策依据和物理约束。

*   **Python 侧工作 (情报与审计)**:
    *   **区域情报聚合**: 将成百上千个地块的数据矩阵聚合为一份"区域简报"（例如：平均气温-15℃，肉食生物密度高）。
    *   **计算能量预算**: 根据物种等级和时代，划定本回合允许的**最大变化幅度**（Evolution Budget，如 ±2.0）。
    *   **合规性检查**: 确保 LLM 返回的数值变化符合能量守恒（有增必有减）。
*   **LLM 侧工作 (战略决策)**:
    *   **自主选择进化路径**: 面对寒冷，是选择"长毛"（耐寒↑），还是"冬眠"（代谢↓），亦或是"迁徙"（运动↑）？由 LLM 综合判断。
    *   **主动权衡 (Trade-off)**: 决定为了获得优势，牺牲哪些次要属性。
    *   **优势**: 保留了演化的多样性和不可预测性，同时利用"区域聚合"大幅降低了 Token 消耗。

### 3.2 动态 Prompt 组装 (Dynamic Context Assembly)
仅发送对当前决策至关重要的信息，去除噪音。

| 模块 | 触发条件 | 注入内容示例 |
| :--- | :--- | :--- |
| **Regional Intel** | 必须 | "Region: Tundra. Stressors: Extreme Cold (-20C), High Predation." |
| **Budget** | 必须 | "Budget: You can shift traits by total magnitude of 2.0." |
| **Biotic Context** | 捕食/竞争高 | "Dominant Predator: 'Ice Wolf' (Fast, Pack hunter)." |
| **Era Constraint** | 早期时代 | "Constraint: Simple organisms only. No complex organs permitted." |

### 3.3 新 Prompt 结构示例
```json
{
    "context": {
        "region_summary": {
            "environment": ["Extreme Cold", "Low Oxygen"],
            "biotic_pressure": ["High Predation (Ambush predators)"]
        },
        "current_state": {"Cold_Res": 2.0, "Speed": 5.0, "Defense": 1.0},
        "budget": {
            "max_change": 2.0,
            "requirement": "MUST trade-off. Gain must equal Loss."
        }
    },
    "task": "Decide evolutionary strategy. 1. Choose adaptations to survive Cold & Predation. 2. Choose sacrifices. 3. Return changes JSON."
}
```
*通过区域化和结构化数据，在保留 LLM 思考空间的同时，将 Token 消耗控制在合理范围。*

---

## 4. 代码修改计划

1.  **`backend/app/services/species/adaptation.py`**:
    *   重写 `apply_adaptations_async`: 移除旧的随机逻辑，改为 Numpy 矩阵计算 `G_evo`。
    *   实现 `_normalize_traits`: 执行向量归一化，并加入 `era_cap` (时代上限) 逻辑。
    *   **[New]** 实现 `_apply_plasticity_buffer`: 引入表型可塑性缓冲池，优先消耗缓冲而非直接死亡。

2.  **`backend/app/services/species/speciation.py`**:
    *   实现 `_identify_eco_regions`: 基于 `clusters` 和环境数据聚合区域。
    *   实现 `_calculate_regional_vectors`: 计算区域代表向量，包含协同压力计算。
    *   **[New]** 实现 `_calculate_biotic_pressure`: 计算捕食和竞争压力矩阵，并在分化逻辑中加入同域分化 (Sympatric) 检查。
    *   **[New]** 重构 Prompt 调用：使用 `PromptBuilder` 类根据条件动态组装 Prompt 片段。

3.  **`backend/app/simulation/tile_based_mortality.py`**:
    *   确保 `_tile_env_matrix` 包含最新的环境数据供其他服务调用。

4.  **`backend/app/services/species/dispersal_engine.py`**:
    *   复用其中的连通性计算逻辑 (`_tile_land_labels`, `_tile_water_labels`) 辅助区域识别。
    *   **[New]** 增加 `check_isolation_status()`: 定期检查物种的连通性分布，更新 `isolation_turns` 计数器。

5.  **`backend/app/ai/prompts/species.py`**:
    *   拆分 `speciation` 和 `pressure_adaptation` 为多个原子化模板（Base, Geo, Biotic, Extreme）。

这个方案将确保演化系统既高效（矩阵计算），又真实（能量守恒 + 协同压力 + 生物博弈），且宏观合理（基于区域而非碎片），同时通过 Token 经济学优化保证了运行性能。
