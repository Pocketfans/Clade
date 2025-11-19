"""物种生成与分化相关的 prompt 模板。"""

SPECIES_PROMPTS = {
    "species_generation": """你是生物学专家，基于用户描述生成物种数据。

用户描述：{user_prompt}

返回JSON对象（不要学名和俗名，系统会单独生成）：
{{
    "description": "生物学描述（100-120字），包含：体型大小、形态特征、运动方式、食性、繁殖方式、栖息环境、生态位角色",
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

【JSON 示例（One-Shot）】
{{
    "description": "一种生活在深海热泉附近的化学合成细菌，体型微小，呈杆状。通过氧化硫化物获取能量，无需光照。具有厚实的细胞壁以抵抗高压和高温。繁殖迅速，常形成菌席。",
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
- 根据体型设置合理数量：微生物(10^5-10^6)、小型(10^4-10^5)、中型(10^3-10^4)、大型(10^2-10^3)
- 所有数值必须合理且符合生物学规律
- Ensure the output is valid JSON only.
""",
    "speciation": """你是演化生物学家，负责推演物种分化事件。基于父系特征、环境压力和分化类型，生成新物种的详细演化数据。
    
    === 系统上下文 ===
    【父系物种】
    代码：{parent_lineage}
    学名：{latin_name}
    俗名：{common_name}
    完整描述：{traits}
    历史高光：{history_highlights}
    父系营养级：{parent_trophic_level:.2f}
    
    【演化环境】
    环境压力：{environment_pressure:.2f}/10
幸存者：{survivors:,}个体
分化类型：{speciation_type}
地形变化：{map_changes_summary}
重大事件：{major_events_summary}

=== 任务目标 ===
生成一个新物种（JSON格式），它必须：
1. **继承**父系的核心特征（如基本体型、代谢模式）。
2. **创新**以适应当前压力（如耐旱、耐寒、新器官）。
3. **符合**生物学数值规律（不违反能量守恒，属性有增必有减）。

=== 输出格式规范 ===
返回标准 JSON 对象：
{{
    "latin_name": "拉丁学名（Genus species格式，使用拉丁词根体现特征）",
    "common_name": "中文俗名（特征词+类群名，可适当发挥）",
    "description": "120-180字完整生物学描述，强调演化差异。必须包含明确的食性描述。",
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
1. **属性权衡 (Trade-offs)**:
   - 属性变化 (`trait_changes`) 的总和必须在 [-5.0, +8.0] 之间。
   - 如果有属性显著增强 (+3.0)，必须有其他属性削弱 (-2.0) 以维持平衡。
   - 单个属性变化幅度限制在 ±4.0 以内。

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

=== JSON 示例 (One-Shot) ===
{{
    "latin_name": "Protoflagella salinus",
    "common_name": "耐盐鞭毛虫",
    "description": "在干旱导致的高盐环境中分化出的耐盐亚种。继承了父系的单细胞结构，但细胞膜上演化出高效的钠钾泵系统，能主动排出多余盐分。体型略微缩小以减少渗透压负担。原有的单根鞭毛分化为双鞭毛，虽然单根长度变短，但协调摆动增强了在粘稠盐水中的游动能力。主要以耐盐的蓝藻和有机碎屑为食（混合营养）。主要栖息在浅海蒸发泻湖。",
    "trophic_level": 1.5,
    "key_innovations": ["高效钠钾泵系统", "双鞭毛结构", "细胞体积缩小"],
    "trait_changes": {{
        "耐盐性": "+4.0",
        "运动能力": "+1.5",
        "代谢率": "+0.5",
        "繁殖速度": "-1.0",
        "体型大小": "-0.5"
    }},
    "morphology_changes": {{
        "body_length_cm": 0.9,
        "body_weight_g": 0.85,
        "metabolic_rate": 1.1
    }},
    "event_description": "干旱导致泻湖盐度升高，种群发生生态隔离，演化出耐盐特质",
    "speciation_type": "生态隔离",
    "reason": "持续的高盐度环境构成了强烈的选择压力，拥有耐盐基因突变的个体存活率显著高于普通个体，随着时间推移，两个种群在生理和生殖上产生隔离。",
    "structural_innovations": [
        {{
            "category": "metabolic",
            "type": "钠钾泵",
            "parameters": {{"efficiency": 1.8, "energy_cost": 1.2}},
            "description": "高效排出盐分，维持渗透压平衡"
        }},
        {{
            "category": "locomotion",
            "type": "双鞭毛",
            "parameters": {{"count": 2, "length_um": 8, "efficiency": 1.3}},
            "description": "双鞭毛协同摆动，适应高粘度水体"
        }}
    ],
    "genetic_discoveries": {{
        "new_traits": {{
            "极端耐盐": {{
                "max_value": 14.0,
                "description": "适应盐度超过100ppt的卤水环境",
                "activation_pressure": ["high_salinity", "drought"]
            }}
        }}
    }}
}}

    Ensure the output is valid JSON only.
""",
    "species_description_update": """你是科学记录员。该物种经历了漫长的渐进式演化，其数值特征已发生显著变化，但文字描述尚未更新。请重写描述以匹配当前数值。

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
   - 如果有属性退化，也要提及（例如：视觉退化 -> "眼睛逐渐退化为感光点"）。
2. 保持科学性与沉浸感。

=== 输出格式 ===
返回标准 JSON 对象：
{{
    "new_description": "更新后的生物学描述..."
}}
"""
}
