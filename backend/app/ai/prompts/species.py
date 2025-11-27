"""物种生成与分化相关的 prompt 模板。"""

SPECIES_PROMPTS = {
    "pressure_adaptation": """你是演化生物学家，负责分析物种对环境压力的适应性演化。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 当前环境压力 ===
{pressure_context}

=== 物种档案 ===
【基本信息】
学名：{latin_name} ({common_name})
栖息地类型：{habitat_type}
营养级：{trophic_level:.1f}
描述：{description}

【当前特质】（1-15分制）
{traits_summary}

【器官系统】
{organs_summary}

=== 任务目标 ===
分析该物种在当前环境压力下最可能发生的适应性变化，并给出具体的演化建议。

=== 输出格式规范 ===
返回JSON对象：
{{
    "analysis": "50-80字的演化分析，解释为什么这些变化是合理的",
    "recommended_changes": {{
        "trait_name": "+/-数值"
    }},
    "organ_changes": [
        {{
            "category": "器官类别",
            "change_type": "enhance/degrade/new",
            "parameter": "参数名",
            "delta": 数值变化
        }}
    ],
    "priority": "high/medium/low",
    "rationale": "30字内的演化机制解释"
}}

=== 演化规则（50万年时间尺度）===
1. **强制属性权衡**：增强某属性时，必须有其他属性下降作为代价
2. **能量守恒**：变化总和应在 [-2.0, +3.0] 之间
3. **适度变化**：单次变化幅度在 ±0.5 到 ±1.5 之间（50万年足够发生明显变化）
4. **压力响应**：变化应直接回应当前环境压力
5. **禁止纯升级**：不存在没有代价的进化

=== 示例 ===
环境压力："冰河时期导致全球降温，气温下降"
物种：某海洋微藻
输出：
{{
    "analysis": "面对持续低温压力，该藻类演化出抗冻蛋白和不饱和脂肪酸合成能力。但合成抗冻物质需要额外能量，导致繁殖速度下降，光合效率也略有降低。",
    "recommended_changes": {{
        "耐寒性": "+1.2",
        "繁殖速度": "-0.8",
        "光照需求": "-0.3"
    }},
    "organ_changes": [],
    "priority": "high",
    "rationale": "耐寒适应以繁殖力为代价"
}}

只返回JSON对象。
""",
    "species_generation": """你是生物学专家，基于用户描述生成物种数据。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

用户描述：{user_prompt}

当前生态系统中的物种（用于推断食物关系）：
{existing_species_context}

返回JSON对象（不要学名和俗名，系统会单独生成）：
{{
    "description": "生物学描述（100-120字），包含：体型大小、形态特征、运动方式、食性、繁殖方式、栖息环境、生态位角色",
    "habitat_type": "栖息地类型（从下列选择一个）",
    "diet_type": "食性类型：autotroph(自养)/herbivore(草食)/carnivore(肉食)/omnivore(杂食)/detritivore(腐食)",
    "prey_species": ["猎物物种代码列表，从现有物种中选择，如A1、B2等，生产者留空[]"],
    "prey_preferences": {{"物种代码": 偏好比例0-1}},
    "morphology_stats": {{
        "body_length_cm": "体长（厘米，微生物用小数如0.001）",
        "body_weight_g": "体重（克）",
        "body_surface_area_cm2": "体表面积（平方厘米，可选）",
        "lifespan_days": "寿命（天）",
        "generation_time_days": "世代时间（天）",
        "metabolic_rate": "代谢率（0.1-10.0）"
    }},
    "abstract_traits": {{
        "耐寒性": "0.0-15.0浮点数",
        "耐热性": "0.0-15.0浮点数",
        "耐旱性": "0.0-15.0浮点数",
        "耐盐性": "0.0-15.0浮点数",
        "耐酸碱性": "0.0-15.0浮点数",
        "光照需求": "0.0-15.0浮点数",
        "氧气需求": "0.0-15.0浮点数",
        "繁殖速度": "0.0-15.0浮点数",
        "运动能力": "0.0-15.0浮点数",
        "社会性": "0.0-15.0浮点数"
    }},
    "hidden_traits": {{
        "gene_diversity": "0.0-1.0",
        "environment_sensitivity": "0.0-1.0",
        "evolution_potential": "0.0-1.0",
        "mutation_rate": "0.0-1.0",
        "adaptation_speed": "0.0-1.0"
    }}
}}

【栖息地类型说明】
- marine: 海洋（浅海、中层海域，需要盐水）
- deep_sea: 深海（深海平原、热液喷口、黑暗高压环境）
- coastal: 海岸（潮间带、海岸带、滨海区）
- freshwater: 淡水（湖泊、河流、池塘）
- amphibious: 两栖（水陆两栖，需要湿润环境）
- terrestrial: 陆生（陆地，从平原到山地）
- aerial: 空中（主要在空中活动的飞行生物）

【食性类型说明】
- autotroph: 自养生物（光合作用或化能合成，营养级T1.0-1.5，无需猎物）
- herbivore: 草食动物（以生产者为食，营养级T2.0-2.5）
- carnivore: 肉食动物（以其他动物为食，营养级T3.0+）
- omnivore: 杂食动物（植物和动物都吃，营养级T2.5-3.5）
- detritivore: 腐食/分解者（以有机碎屑为食，营养级T1.5）

【捕食关系规则】
- 自养生物(autotroph)的prey_species必须为空[]
- 草食动物(herbivore)只能捕食营养级<2.0的物种
- 肉食动物(carnivore)捕食比自己低0.5-1.5营养级的物种
- 杂食动物(omnivore)可以捕食比自己低0.5-2.0营养级的物种
- prey_preferences中所有值之和应为1.0

【JSON 示例1：自养生物（生产者）】
{{
    "description": "一种生活在深海热泉附近的化学合成细菌，体型微小，呈杆状。通过氧化硫化物获取能量，无需光照。具有厚实的细胞壁以抵抗高压和高温。繁殖迅速，常形成菌席。",
    "habitat_type": "deep_sea",
    "diet_type": "autotroph",
    "prey_species": [],
    "prey_preferences": {{}},
    "morphology_stats": {{
        "body_length_cm": 0.0002,
        "body_weight_g": 0.000001,
        "lifespan_days": 3,
        "generation_time_days": 0.5,
        "metabolic_rate": 8.5
    }},
    "abstract_traits": {{
        "耐寒性": 2.0,
        "耐热性": 9.5,
        "耐旱性": 5.0,
        "耐盐性": 8.2,
        "耐酸碱性": 7.5,
        "光照需求": 0.1,
        "氧气需求": 1.0,
        "繁殖速度": 9.0,
        "运动能力": 2.5,
        "社会性": 6.0
    }},
    "hidden_traits": {{
        "gene_diversity": 0.8,
        "environment_sensitivity": 0.3,
        "evolution_potential": 0.7,
        "mutation_rate": 0.6,
        "adaptation_speed": 0.8
    }}
}}

【JSON 示例2：草食动物】
{{
    "description": "一种小型滤食性原生动物，靠纤毛运动在浅海中游动。以浮游藻类和细菌为食，体表透明，卵生繁殖。喜好温暖水域，对温度变化敏感。",
    "habitat_type": "marine",
    "diet_type": "herbivore",
    "prey_species": ["A1", "A2"],
    "prey_preferences": {{"A1": 0.7, "A2": 0.3}},
    "morphology_stats": {{
        "body_length_cm": 0.02,
        "body_weight_g": 0.00001,
        "lifespan_days": 14,
        "generation_time_days": 3,
        "metabolic_rate": 5.0
    }},
    "abstract_traits": {{
        "耐寒性": 3.0,
        "耐热性": 6.0,
        "耐旱性": 1.0,
        "耐盐性": 7.0,
        "耐酸碱性": 5.0,
        "光照需求": 4.0,
        "氧气需求": 6.0,
        "繁殖速度": 7.5,
        "运动能力": 5.0,
        "社会性": 3.0
    }},
    "hidden_traits": {{
        "gene_diversity": 0.6,
        "environment_sensitivity": 0.5,
        "evolution_potential": 0.6,
        "mutation_rate": 0.4,
        "adaptation_speed": 0.5
    }}
}}

要求：
- description严格100-120字，精简但包含所有关键生态信息
- habitat_type必须根据描述选择最合适的类型
- 根据habitat_type设置合理的耐盐性、耐旱性等属性
- 根据体型设置合理数量：微生物(10^5-10^6)、小型(10^4-10^5)、中型(10^3-10^4)、大型(10^2-10^3)
- 所有数值必须合理且符合生物学规律
- 只返回JSON，不要使用markdown代码块标记
""",
    # ==================== 精简版分化Prompt（规则引擎处理约束） ====================
    "speciation": """你是演化生物学家，为物种分化生成创意性内容。

**必须返回纯JSON格式。**

=== 父系物种 ===
代码：{parent_lineage}
学名：{latin_name} ({common_name})
栖息地：{habitat_type}
营养级：T{parent_trophic_level:.1f}
食性类型：{diet_type}
当前猎物：{prey_species_summary}
描述：{traits}

【器官系统】
{current_organs_summary}

=== 环境背景 ===
压力强度：{environment_pressure:.2f}/10
压力来源：{pressure_summary}
幸存者：{survivors:,}
分化类型：{speciation_type}
{tile_context}

=== ⚠️ 硬性约束（必须遵守，否则会被系统强制修正）===

【属性权衡预算】
{trait_budget_summary}
- ❌ 违规示例：增加总和超过上限、没有减少项、单项变化超过±3.0
- ✅ 正确示例：{{"耐寒性": "+1.5", "繁殖速度": "-1.0", "运动能力": "-0.5"}} (增+1.5, 减-1.5, 净变化0)

【营养级限制】
允许范围：{trophic_range}（父代±0.5）
- ❌ 违规示例：父代T{parent_trophic_level:.1f}，返回T{parent_trophic_level:.1f}+1.0
- ✅ 必须在范围 {trophic_range} 内选择

【器官演化约束】（current_stage必须与下方父系阶段一致！）
{organ_constraints_summary}
规则：
- current_stage 必须填写上面列出的"当前阶段"值，不可随意编造
- 每次最多涉及2个器官系统
- 新器官只能从阶段1(原基)开始（即 current_stage=0, target_stage=1）
- 已有器官每次最多提升2阶段（target_stage ≤ current_stage + 2）

=== 建议（非强制）===
- 建议演化方向：{evolution_direction} - {direction_description}
- 建议增强：{suggested_increases}
- 建议减弱：{suggested_decreases}
- 可选栖息地：{habitat_options}

=== 任务 ===
生成新物种的**创意性内容**：
1. 拉丁学名（保留属名，种加词用拉丁词根体现特征）
2. 中文俗名（特征词+类群名）
3. 120-180字生物学描述（必须包含食性和栖息环境！）
4. 关键演化创新点
5. 分化事件摘要和原因

=== 输出格式 ===
{{
    "latin_name": "Genus species",
    "common_name": "中文俗名",
    "description": "120-180字，含食性、栖息环境、演化变化",
    "habitat_type": "从可选栖息地中选择",
    "trophic_level": 必须在{trophic_range}范围内,
    "diet_type": "继承或调整食性类型",
    "prey_species": ["继承或调整猎物列表"],
    "prey_preferences": {{"物种代码": 偏好比例}},
    "key_innovations": ["1-3个创新点"],
    "trait_changes": {{"增强属性": "+数值", "减弱属性": "-数值"}},
    "morphology_changes": {{"body_length_cm": 0.8-1.3倍}},
    "event_description": "30-50字分化摘要",
    "speciation_type": "{speciation_type}",
    "reason": "生态学/地质学解释",
    "organ_evolution": [
        {{
            "category": "locomotion/sensory/metabolic/digestive/defense/reproduction",
            "action": "enhance/initiate",
            "current_stage": 与上方父系阶段一致,
            "target_stage": current_stage+1或+2,
            "structure_name": "结构名",
            "description": "变化描述"
        }}
    ]
}}

【捕食关系规则】
- 通常继承父系的食性类型和猎物，但可以因环境压力调整
- 如果分化导致营养级变化，需要相应调整猎物范围
- 新猎物必须是当前生态系统中存在的物种
- 如果灭绝事件导致原猎物消失，需要寻找替代食物源

=== 示例（父系器官sensory当前阶段=1，草食性，猎物为A1）===
{{
    "latin_name": "Protoflagella ocularis",
    "common_name": "眼点鞭毛虫",
    "description": "浅海环境促使感光点内陷形成眼凹结构，提高光线方向感知能力。繁殖速度下降以维持复杂感觉结构。主要滤食蓝藻A1，栖息于阳光充足的浅海。",
    "habitat_type": "marine",
    "trophic_level": 2.0,
    "diet_type": "herbivore",
    "prey_species": ["A1"],
    "prey_preferences": {{"A1": 1.0}},
    "key_innovations": ["眼凹结构"],
    "trait_changes": {{"光照需求": "+1.5", "繁殖速度": "-1.0", "运动能力": "-0.5"}},
    "morphology_changes": {{"body_length_cm": 1.05}},
    "event_description": "浅海光照促进感光器官发展",
    "speciation_type": "生态隔离",
    "reason": "光感知优势带来生存收益，代价是维护成本增加。",
    "organ_evolution": [
        {{"category": "sensory", "action": "enhance", "current_stage": 1, "target_stage": 2, "structure_name": "眼凹", "description": "感光点内陷"}}
    ]
}}

只返回JSON。
""",
    
    # ==================== 原版分化Prompt（备份，兼容旧代码） ====================
    "speciation_legacy": """你是演化生物学家，负责推演物种分化事件。基于父系特征、环境压力和分化类型，生成新物种的详细演化数据。

**关键要求：你必须严格返回JSON格式，不要使用markdown标题或其他格式。**
    
    === 系统上下文 ===
    【父系物种】
    代码：{parent_lineage}
    学名：{latin_name}
    俗名：{common_name}
    栖息地类型：{habitat_type}
    生物类群：{biological_domain}
    完整描述：{traits}
    历史高光：{history_highlights}
    父系营养级：{parent_trophic_level:.2f}
    
    【现有器官系统】
    {current_organs_summary}
    
    【演化环境】
    环境压力：{environment_pressure:.2f}/10
    压力来源：{pressure_summary}
    幸存者：{survivors:,}个体
    分化类型：{speciation_type}
    地形变化：{map_changes_summary}
    重大事件：{major_events_summary}
    
    【地块级分化背景】
    {tile_context}
    区域死亡率：{region_mortality:.1%}（{region_pressure_level}）
    死亡率梯度：{mortality_gradient:.1%}
    隔离区域数：{num_isolation_regions}
    地理隔离：{'是' if is_geographic_isolation else '否'}

    【食物链状态】
    {food_chain_status}

=== 任务目标 ===
生成一个新物种（JSON格式），继承父系核心特征，渐进式创新适应压力，属性有增必有减。

=== 输出格式规范 ===
返回标准 JSON 对象：
{{
    "latin_name": "拉丁学名",
    "common_name": "中文俗名",
    "description": "120-180字生物学描述，含食性和栖息环境",
    "habitat_type": "栖息地类型",
    "trophic_level": 1.0-5.5,
    "key_innovations": ["演化创新点"],
    "trait_changes": {{"特质名称": "+数值"}}, 
    "morphology_changes": {{"统计名称": 倍数}},
    "event_description": "30-50字分化摘要",
    "speciation_type": "{speciation_type}",
    "reason": "分化机制解释",
    "organ_evolution": [
        {{
            "category": "locomotion/sensory/metabolic/digestive/defense",
            "action": "enhance/initiate",
            "current_stage": 0-4,
            "target_stage": 0-4,
            "structure_name": "结构名",
            "description": "变化描述"
        }}
    ],
    "genetic_discoveries": {{}}
}}

=== 关键规则 ===
1. 属性权衡：增加必有减少，总和在[-3.0, +5.0]之间
2. 形态稳定：体长变化0.8-1.3倍
3. 器官演化：每次最多提升2阶段，新器官从阶段1开始
4. 营养级：通常与父代相近(±0.5)

只返回JSON对象。
""",
    "speciation_batch": """你是演化生物学家，负责批量推演多个物种的分化事件。

**关键要求：必须严格返回JSON格式，包含所有请求物种的分化结果。**

=== 全局环境背景 ===
环境压力强度：{average_pressure:.2f}/10
压力来源：{pressure_summary}
地形变化：{map_changes_summary}
重大事件：{major_events_summary}

=== 待分化物种列表 ===
{species_list}

=== ⚠️ 硬性约束（必须遵守，违规会被系统强制修正）===

【1. 属性权衡预算】
- 增加总和上限: +5.0，减少总和下限: -3.0，单项变化上限: ±3.0
- 必须有增有减！纯增加会被系统强制添加减少项
- ❌ 违规: {{"耐寒性": "+8.0"}} → 会被缩减
- ✅ 正确: {{"耐寒性": "+2.0", "繁殖速度": "-1.5"}}

【2. 营养级限制】
- 只能变化±0.5（父代营养级在每个物种条目中给出）
- ❌ 违规: 父代T2.0，返回T3.5 → 会被修正为T2.5
- ✅ 正确: 父代T2.0，返回T2.0~T2.5

【3. 器官演化约束】⚠️ 最常见错误！
- current_stage 必须与父系实际阶段一致（在每个物种条目的器官约束中给出）
- 每次最多涉及2个器官系统
- 新器官从阶段0开始，只能发展到阶段1：current_stage=0, target_stage=1
- 已有器官每次最多提升2阶段：target_stage ≤ current_stage + 2
- ❌ 违规: 父系locomotion阶段=0，返回current_stage=4 → 会被修正为0
- ✅ 正确: 父系locomotion阶段=0，返回current_stage=0, target_stage=1

=== 地块级分化规则 ===
每个物种条目中包含器官约束信息，请严格按照给出的当前阶段填写：
- **高压区域**（死亡率>50%）：优先演化抗逆性
- **低压区域**（死亡率<30%）：可演化竞争性
- **地理隔离**：不同区域应有性状分歧

=== 渐进式演化原则 ===
器官进化阶段：0(无)→1(原基)→2(初级)→3(功能化)→4(完善)
- 单次分化只能提升1-2个阶段
- 新器官只能从原基(阶段1)开始，即 current_stage=0 → target_stage=1

=== 栖息地类型 ===
marine | deep_sea | coastal | freshwater | amphibious | terrestrial | aerial

=== 输出格式 ===
{{
    "results": [
        {{
            "request_id": "请求ID（与输入对应）",
            "latin_name": "拉丁学名",
            "common_name": "中文俗名",
            "description": "120-180字生物学描述，含食性和栖息环境",
            "habitat_type": "栖息地类型",
            "trophic_level": 父代±0.5范围内,
            "key_innovations": ["关键演化创新"],
            "trait_changes": {{"增强属性": "+数值", "减弱属性": "-数值"}},
            "morphology_changes": {{"body_length_cm": 0.8-1.3倍}},
            "event_description": "30-50字分化摘要",
            "reason": "分化机制解释",
            "organ_evolution": [
                {{
                    "category": "locomotion/sensory/metabolic/digestive/defense/reproduction",
                    "action": "enhance/initiate",
                    "current_stage": 与该物种器官约束中的当前阶段一致,
                    "target_stage": current_stage+1或+2,
                    "structure_name": "结构名",
                    "description": "渐进式变化描述"
                }}
            ]
        }}
    ]
}}

=== 正确示例（父系locomotion阶段=0, sensory阶段=1）===
{{
    "results": [
        {{
            "request_id": "req_001",
            "latin_name": "Protoflagella ocularis",
            "common_name": "眼点鞭毛虫",
            "description": "浅海环境促使感光点内陷形成眼凹结构。繁殖速度下降以维持复杂感觉结构。主要滤食蓝藻，栖息于阳光充足的浅海。",
            "habitat_type": "marine",
            "trophic_level": 2.0,
            "key_innovations": ["眼凹结构"],
            "trait_changes": {{"光照需求": "+1.5", "繁殖速度": "-1.0", "运动能力": "-0.5"}},
            "morphology_changes": {{"body_length_cm": 1.05}},
            "event_description": "浅海光照促进感光器官发展",
            "reason": "光感知优势带来生存收益",
            "organ_evolution": [
                {{"category": "sensory", "action": "enhance", "current_stage": 1, "target_stage": 2, "structure_name": "眼凹", "description": "感光点内陷"}}
            ]
        }}
    ]
}}

只返回JSON对象，不要返回markdown。
""",

    "species_description_update": """你是科学记录员。该物种经历了漫长的渐进式演化，其数值特征已发生显著变化，但文字描述尚未更新。请重写描述以匹配当前数值。

=== 环境背景 ===
当前环境压力：{pressure_context}

=== 物种档案 ===
【基本信息】
学名：{latin_name} ({common_name})
原描述：{old_description}

【数值变化检测】
{trait_diffs}

=== 任务要求 ===
1. 重写 `description`（120-150字）：
   - 必须保留原物种的核心身份（如"它仍是一种鱼"）。
   - 必须将【数值变化】转化为生物学特征（例如：耐寒性大幅提升 -> "演化出了厚实的皮下脂肪层"）。
   - 结合【环境背景】解释适应性变化的原因（例如："为应对冰河时期的严寒..."）。
   - 如果有属性退化，也要提及（例如：视觉退化 -> "眼睛逐渐退化为感光点"）。
2. 保持科学性与沉浸感。

=== 输出格式 ===
返回标准 JSON 对象：
{{
    "new_description": "更新后的生物学描述..."
}}
"""
}
