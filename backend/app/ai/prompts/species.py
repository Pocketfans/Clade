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

返回JSON对象（不要学名和俗名，系统会单独生成）：
{{
    "description": "生物学描述（100-120字），包含：体型大小、形态特征、运动方式、食性、繁殖方式、栖息环境、生态位角色",
    "habitat_type": "栖息地类型（从下列选择一个）",
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

【JSON 示例（One-Shot）】
{{
    "description": "一种生活在深海热泉附近的化学合成细菌，体型微小，呈杆状。通过氧化硫化物获取能量，无需光照。具有厚实的细胞壁以抵抗高压和高温。繁殖迅速，常形成菌席。",
    "habitat_type": "deep_sea",
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

要求：
- description严格100-120字，精简但包含所有关键生态信息
- habitat_type必须根据描述选择最合适的类型
- 根据habitat_type设置合理的耐盐性、耐旱性等属性
- 根据体型设置合理数量：微生物(10^5-10^6)、小型(10^4-10^5)、中型(10^3-10^4)、大型(10^2-10^3)
- 所有数值必须合理且符合生物学规律
- 只返回JSON，不要使用markdown代码块标记
""",
    "speciation": """你是演化生物学家，负责推演物种分化事件。基于父系特征、环境压力和分化类型，生成新物种的详细演化数据。

**关键要求：你必须严格返回JSON格式，不要使用markdown标题或其他格式。**
    
    === 系统上下文 ===
    【父系物种】
    代码：{parent_lineage}
    学名：{latin_name}
    俗名：{common_name}
    栖息地类型：{habitat_type}
    完整描述：{traits}
    历史高光：{history_highlights}
    父系营养级：{parent_trophic_level:.2f}
    
    【演化环境】
    环境压力：{environment_pressure:.2f}/10
    压力来源：{pressure_summary}
    幸存者：{survivors:,}个体
    分化类型：{speciation_type}
    地形变化：{map_changes_summary}
    重大事件：{major_events_summary}

=== 任务目标 ===
生成一个新物种（JSON格式），它必须：
1. **继承**父系的核心特征（如基本体型、代谢模式、栖息地类型）。
2. **创新**以适应当前压力（如耐旱、耐寒、新器官）。
3. **强制权衡**：属性有增必有减，不存在纯粹的"升级"。
4. **栖息地演化**：根据环境变化，可能改变栖息地类型。

 **子代差异化指令**：
- 当前子代编号：第 {offspring_index} 个（共 {total_offspring} 个）
- **关键要求**：每个子代必须有不同的演化方向！
- 根据子代编号选择不同的演化策略：
  * 第1个子代：偏向环境适应（耐寒/耐热/耐盐等增强，运动/繁殖减弱）
  * 第2个子代：偏向活动能力（运动/攻击增强，耐受性减弱）
  * 第3个子代：偏向繁殖策略（繁殖/社会性增强，其他属性减弱）
  * 第4个子代：偏向防御策略（防御性增强，攻击/运动减弱）
  * 第5个子代：偏向极端特化（1-2个属性大幅增强，其他大幅减弱）
- 这样不同子代会朝不同方向演化，由自然选择决定谁能存活。

=== 栖息地类型说明 ===
可选择的栖息地类型：
- marine: 海洋（浅海、中层海域，需要盐水）
- deep_sea: 深海（深海平原、热液喷口）
- coastal: 海岸（潮间带、滨海区）
- freshwater: 淡水（湖泊、河流）
- amphibious: 两栖（水陆两栖）
- terrestrial: 陆生（陆地环境）
- aerial: 空中（飞行生物）

**栖息地演化规则：**
- 通常继承父系栖息地类型
- 在强烈环境压力下可发生跨栖息地演化：
  * 海洋 ↔ 海岸 ↔ 陆生
  * 淡水 ↔ 两栖 ↔ 陆生
  * 陆生 → 空中（需发展飞行能力）
- 跨栖息地演化时，必须在description中详细说明适应性变化

=== 输出格式规范 ===
返回标准 JSON 对象：
{{
    "latin_name": "拉丁学名（Genus species格式，使用拉丁词根体现特征）",
    "common_name": "中文俗名（特征词+类群名，可适当发挥）",
    "description": "120-180字完整生物学描述，强调演化差异。必须包含明确的食性描述和栖息环境。",
    "habitat_type": "栖息地类型（从上述7种选择）",
    "trophic_level": "1.0-5.5浮点数 (根据食性判断)",
    "key_innovations": ["1-3个关键演化创新点"],
    "trait_changes": {{"特质名称": "+数值"}}, 
    "morphology_changes": {{"统计名称": 倍数}},
    "event_description": "30-50字分化事件摘要",
    "speciation_type": "{speciation_type}",
    "reason": "详细的生态学/地质学分化机制解释",
    "structural_innovations": [
        {{
            "category": "locomotion/sensory/metabolic/digestive/defense",
            "type": "具体器官名",
            "parameters": {{"参数名": 数值, "efficiency": 倍数}},
            "description": "功能简述"
        }}
    ],
    "genetic_discoveries": {{
        "new_traits": {{"特质名": {{"max_value": 15.0, "description": "...", "activation_pressure": ["..."]}}}},
        "new_organs": {{"器官名": {{"category": "...", "type": "...", "parameters": {{}}, "description": "...", "activation_pressure": ["..."]}}}}
    }}
}}

=== 关键规则 ===
1. **强制属性权衡 (Trade-offs) - 核心原则**:
   - **必须有增有减**：每个增加的属性，必须有至少一个减少的属性作为代价。
   - 属性变化总和限制在 [-3.0, +5.0] 之间。
   - 增加总量不得超过减少总量的2倍。例如：增加+4.0必须配合-2.0的减少。
   - 单个属性变化幅度限制在 ±3.0 以内（50万年的渐进演化）。
   - **禁止全属性提升**：纯粹的"升级"在生物学上不存在，必须体现权衡代价。
   - **栖息地相关属性**：
     * 海洋/深海生物：高耐盐性，低耐旱性
     * 淡水生物：低耐盐性，中等耐旱性
     * 陆生生物：低耐盐性，高耐旱性
     * 两栖生物：中等耐盐性和耐旱性

2. **形态稳定性**:
   - `morphology_changes` 是相对于父系的倍数（如 1.2 表示增大 20%）。
   - 体长 (`body_length_cm`) 变化应限制在 0.8 - 1.3 倍之间，避免突变成怪物。

3. **营养级判定 (Trophic Level)**:
   - 请根据新物种的食性描述，给出一个合理的营养级数值 (1.0 - 5.5)。
   - 1.0: 生产者 (光合自养)
   - 1.5: 分解者 (腐食)
   - 2.0: 初级消费者 (食草/滤食)
   - 3.0: 次级消费者 (捕食草食动物)
   - 5.0+: 顶级掠食者 (捕食其他肉食动物)
   - 必须在 `description` 中明确指出其食物来源与食性。

4. **命名规则**:
   - 拉丁名：保留属名，种加词使用拉丁词根（如 `velox` 快, `robustus` 强, `cryophilus` 耐寒）。
   - 中文名：提取最显著特征（如"耐寒"、"长鞭"）+ 父系类群名（如"藻"、"虫"）。

=== JSON 示例 (One-Shot) - 注意权衡！ ===
{{
    "latin_name": "Protoflagella salinus",
    "common_name": "耐盐鞭毛虫",
    "description": "在干旱导致的高盐环境中分化出的耐盐亚种。细胞膜上演化出高效的钠钾泵系统，能主动排出多余盐分。但为了维持高耗能的离子泵，其繁殖速度显著下降，且对低盐环境的耐受力也降低了。体型缩小10%以减少渗透压负担。主要以耐盐蓝藻为食。栖息在浅海蒸发泻湖。",
    "habitat_type": "coastal",
    "trophic_level": 1.5,
    "key_innovations": ["高效钠钾泵系统", "细胞体积缩小"],
    "trait_changes": {{
        "耐盐性": "+3.0",
        "耐热性": "+1.0",
        "繁殖速度": "-2.0",
        "社会性": "-1.0",
        "运动能力": "-0.5"
    }},
    "morphology_changes": {{
        "body_length_cm": 0.9,
        "body_weight_g": 0.85,
        "metabolic_rate": 1.15
    }},
    "event_description": "干旱导致泻湖盐度升高，种群发生生态隔离",
    "speciation_type": "生态隔离",
    "reason": "高盐度环境构成强烈选择压力。耐盐基因的代价是繁殖资源被重新分配到离子调节系统，导致繁殖速度下降。",
    "structural_innovations": [
        {{
            "category": "metabolic",
            "type": "钠钾泵",
            "parameters": {{"efficiency": 1.8, "energy_cost": 1.3}},
            "description": "高效排出盐分，但消耗更多能量"
        }}
    ],
    "genetic_discoveries": {{}}
}}

**权衡计算验证**：
- 增加：+3.0 + 1.0 = +4.0
- 减少：-2.0 - 1.0 - 0.5 = -3.5  
- 总和：+0.5（在合理范围内）
- 减少量 3.5 接近增加量 4.0 的87.5%，符合权衡原则 ✓

    只返回JSON对象，不要返回markdown或其他格式的文本。
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
