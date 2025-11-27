"""AI压力响应相关的 prompt 模板。

实现多种AI参与机制：
- 综合状态评估：评估物种状态、应对能力、是否需要紧急响应（合并了压力评估+紧急响应）
- 物种叙事：为Critical/Focus物种生成叙事描述（合并了Critical增润+Focus增润）
- 种群博弈仲裁：模拟物种间的互动博弈
- 迁徙决策参谋：智能规划迁徙路线（保留用于特殊情况）
"""

PRESSURE_RESPONSE_PROMPTS = {
    # ==================== 【新】综合状态评估（合并压力评估+紧急响应） ====================
    "species_status_eval": """你是生态学专家，综合评估物种的当前状态和应对能力。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 物种档案 ===
【基本信息】
学名：{latin_name} ({common_name})
谱系代码：{lineage_code}
营养级：T{trophic_level:.1f} ({trophic_category})
栖息地类型：{habitat_type}
当前种群：{population:,}
描述：{description}

【当前特质】（1-15分制）
{traits_summary}

【器官系统】
{organs_summary}

=== 当前压力情境 ===
总压力强度：{total_pressure:.1f}/10
压力来源：{pressure_sources}
重大事件：{major_events}

=== 规则引擎预估 ===
基础死亡率：{base_death_rate:.1%}
主要死因分解：
{death_causes_breakdown}
连续高危回合：{consecutive_danger_turns}

=== 周边生态情境 ===
【竞争者】{competitors}
【猎物/食物】{prey_info}
【捕食者威胁】{predator_info}
【栖息地状态】{habitat_status}

=== 任务 ===
1. 评估物种对当前压力的应对能力
2. 判断是否处于紧急状态（死亡率>60%或连续3回合高危）
3. 如处于紧急状态，给出应急策略

返回JSON：
{{
    "survival_modifier": 0.5-1.5,
    "modifier_reasoning": "修正系数的依据（30字内）",
    "response_strategy": "逃避/对抗/适应/忍耐/衰退",
    "key_factors": ["关键因素1", "关键因素2"],
    "population_behavior": "种群行为（聚集/分散/迁徙准备/休眠/正常）",
    
    "is_emergency": true/false,
    "emergency_level": "critical/warning/stable",
    "emergency_action": {{
        "primary_strategy": "migration/behavior_change/rapid_adaptation/diet_shift/none",
        "action_detail": "具体措施（如果is_emergency=true）",
        "expected_benefit": 0.0-0.3
    }},
    
    "should_migrate": true/false,
    "migration_urgency": "immediate/next_turn/optional/none",
    
    "brief_narrative": "60-80字描述物种当前状态和应对方式"
}}

=== 修正系数指南 ===
- 0.5-0.7: 物种特质与压力高度匹配，显著优势
- 0.7-0.9: 物种有一定应对能力，小幅优势
- 0.9-1.1: 中性，规则引擎计算基本准确
- 1.1-1.3: 物种较脆弱，面临额外风险
- 1.3-1.5: 物种与压力严重不匹配，高危状态

=== 紧急状态判定 ===
- critical: 死亡率>70% 或 连续4+回合高危
- warning: 死亡率50-70% 或 连续2-3回合高危
- stable: 其他情况

只返回JSON对象。
""",

    # ==================== 【新】物种叙事（合并Critical+Focus增润） ====================
    "species_narrative": """你是生态叙事作家，为物种生成引人入胜的进化故事。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 回合概况 ===
当前回合：第 {turn_index} 回合
全球环境：{global_environment}
重大事件：{major_events}

=== 待描述物种列表 ===
{species_list}

每个物种信息包含：
- 基本信息（名称、营养级、栖息地）
- tier: critical（关键物种）或 focus（重点物种）
- 本回合经历：死亡率、迁徙、适应演化、分化等
- AI评估结果：应对策略、紧急状态

=== 任务 ===
为每个物种生成叙事描述：
- Critical物种：100-150字深度叙事，包含戏剧性和细节
- Focus物种：50-80字简要叙事，突出关键变化

返回JSON：
{{
    "narratives": [
        {{
            "lineage_code": "物种代码",
            "tier": "critical/focus",
            "headline": "标题式摘要（10字内）",
            "narrative": "叙事描述",
            "mood": "thriving/struggling/adapting/declining/critical",
            "highlight_event": "最重要的事件（20字内）"
        }}
    ],
    "cross_species_story": "50字描述物种间的互动或生态系统整体变化（可选）"
}}

=== 叙事风格指南 ===
【Critical物种叙事】
- 使用具体细节：具体的行为、环境变化
- 带入时间感："随着温度持续下降..."
- 突出戏剧性转折："然而..."、"出乎意料的是..."
- 展现物种的"性格"：顽强、机警、从容

【Focus物种叙事】
- 简洁有力，抓住核心变化
- 一两个关键动作或状态
- 避免流水账

【情绪基调】
- thriving: 积极向上，种群扩张
- struggling: 艰难求存，但仍在坚持
- adapting: 正在改变，充满可能性
- declining: 走下坡路，需要关注
- critical: 生死攸关，紧张感

只返回JSON对象。
""",


    # ==================== 方案A：压力评估顾问 ====================
    "pressure_assessment": """你是生态学专家，评估物种对当前环境压力的应对能力。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 物种档案 ===
【基本信息】
学名：{latin_name} ({common_name})
谱系代码：{lineage_code}
营养级：T{trophic_level:.1f} ({trophic_category})
栖息地类型：{habitat_type}
描述：{description}

【当前特质】（1-15分制）
{traits_summary}

【器官系统】
{organs_summary}

【历史高光】
{history_highlights}

=== 当前压力情境 ===
总压力强度：{total_pressure:.1f}/10
压力来源：{pressure_sources}
重大事件：{major_events}

=== 规则引擎预估 ===
基础死亡率：{base_death_rate:.1%}
主要死因分解：
{death_causes_breakdown}

=== 周边生态情境 ===
【竞争者】{competitors}
【猎物/食物】{prey_info}
【捕食者威胁】{predator_info}
【栖息地状态】{habitat_status}

=== 任务 ===
综合评估该物种面对当前压力的真实应对能力。考虑：
1. 物种的特质是否能应对当前压力？（如耐寒物种面对降温）
2. 器官系统是否提供额外优势？（如厚皮毛、穴居能力）
3. 生态位是否受到挤压？（竞争者、食物链变化）
4. 历史上该物种是否经历过类似压力？

返回JSON：
{{
    "survival_modifier": 0.5-1.5,  // 死亡率修正系数 (<1=更易存活, >1=更难存活)
    "modifier_reasoning": "修正系数的依据（50字内）",
    "response_strategy": "逃避/对抗/适应/忍耐/衰退",
    "key_survival_factors": ["关键生存因素1", "关键生存因素2"],
    "key_risk_factors": ["关键风险因素1", "关键风险因素2"],
    "population_behavior": "种群行为预测（聚集/分散/迁徙/休眠/正常）",
    "trait_utilization": {{"特质名": "如何利用该特质应对压力"}},
    "narrative": "80-100字描述该物种如何应对当前压力，带有叙事感"
}}

=== 修正系数指南 ===
- 0.5-0.7: 物种特质与压力高度匹配，显著优势（如极地物种面对降温）
- 0.7-0.9: 物种有一定应对能力，小幅优势
- 0.9-1.1: 中性，规则引擎计算基本准确
- 1.1-1.3: 物种较脆弱，面临额外风险
- 1.3-1.5: 物种与压力严重不匹配，高危状态

只返回JSON对象。
""",

    # ==================== 方案B：种群博弈仲裁 ====================
    "species_interaction": """你是生态学仲裁员，判定两个物种间的博弈结果。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 物种A（{interaction_role_a}）===
学名：{species_a_latin} ({species_a_common})
营养级：T{species_a_trophic:.1f}
特质摘要：{species_a_traits}
种群规模：{species_a_population:,}

=== 物种B（{interaction_role_b}）===
学名：{species_b_latin} ({species_b_common})
营养级：T{species_b_trophic:.1f}
特质摘要：{species_b_traits}
种群规模：{species_b_population:,}

=== 互动类型 ===
{interaction_type}
- predation: 捕食关系（A捕食B或B捕食A）
- competition: 竞争关系（争夺相同资源/生态位）
- mutualism: 互利共生
- parasitism: 寄生关系

=== 互动背景 ===
栖息地重叠度：{habitat_overlap:.0%}
资源竞争强度：{resource_competition:.1f}/10
历史互动：{interaction_history}

=== 当前环境 ===
{environment_context}

=== 任务 ===
判定本回合这两个物种互动的结果：

返回JSON：
{{
    "interaction_outcome": "a_wins/b_wins/draw/mutual_benefit/mutual_harm",
    "a_effects": {{
        "mortality_delta": -0.15到0.25,  // 死亡率变化（负=降低，正=增加）
        "territory_change": "expand/shrink/stable",
        "resource_access": "improved/reduced/stable",
        "behavior_adaptation": "行为适应描述"
    }},
    "b_effects": {{
        "mortality_delta": -0.15到0.25,
        "territory_change": "expand/shrink/stable",
        "resource_access": "improved/reduced/stable",
        "behavior_adaptation": "行为适应描述"
    }},
    "ecological_consequence": "这次互动对生态系统的影响",
    "narrative": "80-120字描述这次物种互动的过程和结果，带有戏剧感"
}}

=== 博弈逻辑指南 ===
【捕食关系】
- 捕食者成功: predator mortality_delta -0.05~-0.1, prey +0.1~+0.2
- 猎物逃脱: predator +0.02~+0.05, prey -0.02~-0.05
- 考虑体型、速度、防御机制

【竞争关系】
- 竞争优势方: mortality_delta -0.05, territory expand
- 竞争劣势方: mortality_delta +0.05~+0.15, territory shrink
- 资源充足时双方影响都较小

【共生关系】
- 互利共生: 双方 mortality_delta -0.03~-0.08
- 偏利共生: 受益方 -0.05, 另一方 0

只返回JSON对象。
""",

    # ==================== 方案C：紧急响应系统 ====================
    "emergency_response": """这是生态紧急状态！请为该物种制定应急生存策略。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 紧急状态警报 ===
⚠️ 触发原因：{trigger_reason}
⚠️ 当前死亡率：{current_death_rate:.1%}
⚠️ 连续高危回合：{consecutive_danger_turns}
⚠️ 预计灭绝时间：{extinction_eta} 回合（若无干预）

=== 物种档案 ===
学名：{latin_name} ({common_name})
营养级：T{trophic_level:.1f}
当前种群：{population:,}
栖息地：{habitat_type}

【关键特质】
{key_traits}

【器官系统】
{organs_summary}

【历史韧性】
过去类似危机：{past_crises}
存活策略记录：{survival_history}

=== 环境威胁详情 ===
{threat_details}

=== 可用生存选项 ===
请从以下策略中选择并详细规划：

1. **紧急迁徙** - 迁往更安全的区域
   - 代价：迁徙途中10-20%额外死亡
   - 潜在目的地：{potential_destinations}

2. **行为改变** - 改变活动模式
   - 选项：休眠/穴居/夜行化/群居化/分散化
   - 代价：繁殖速度降低，但存活率提高

3. **快速适应** - 紧急特质调整
   - 可调整特质：{adjustable_traits}
   - 代价：其他特质会退化

4. **食性改变** - 尝试新的食物来源
   - 可能的替代食物：{alternative_food}
   - 代价：效率降低，竞争新生态位

5. **接受灭绝** - 如果所有策略都不可行
   - 记录该物种的最后时刻

=== 任务 ===
制定最佳紧急响应计划：

返回JSON：
{{
    "primary_strategy": "migration/behavior_change/rapid_adaptation/diet_shift/accept_extinction",
    "secondary_strategy": "备用策略（可选）",
    "survival_probability": 0.0-1.0,  // 执行策略后的存活概率
    "mortality_reduction": 0.0-0.5,   // 预期死亡率降低幅度
    
    "immediate_actions": [
        "立即执行的措施1",
        "立即执行的措施2"
    ],
    
    "strategy_details": {{
        "migration": {{
            "destination": "目标区域",
            "route": "迁徙路线",
            "migration_cost": 0.1-0.3  // 迁徙损失
        }},
        "behavior_change": {{
            "new_behavior": "新行为模式",
            "duration": "持续时间（回合）"
        }},
        "trait_changes": {{
            "特质名": "+/-变化值"
        }}
    }},
    
    "long_term_outlook": "危机后的长期预测",
    "narrative": "120-150字描述该物种的绝地求生过程，要有紧张感和戏剧性"
}}

=== 决策原则 ===
- 优先保存种群核心（宁可牺牲边缘个体）
- 利用物种已有的优势特质
- 考虑策略的可执行性（微生物无法迁徙太远）
- 历史上成功的策略更可能再次成功

只返回JSON对象。
""",

    # ==================== 方案D：迁徙决策参谋 ====================
    "migration_advisor": """你是迁徙顾问，为该物种规划最佳迁徙路线。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 迁徙物种 ===
学名：{latin_name} ({common_name})
营养级：T{trophic_level:.1f}
栖息地类型：{habitat_type}
迁徙能力：{migration_capability}（范围：{migration_range}格）

【关键需求】
- 温度偏好：{temp_preference}
- 湿度需求：{humidity_requirement}
- 食物需求：{food_requirement}

=== 迁徙触发原因 ===
{migration_trigger}

=== 当前位置 ===
区域：{current_region}
当前死亡率：{current_mortality:.1%}
问题：{current_problems}

=== 候选目的地（规则引擎筛选）===
{candidate_destinations}

每个候选地包含：
- 地块ID、坐标、生物群落
- 预估适宜度
- 猎物密度（对消费者）
- 竞争压力
- 距离

=== 任务 ===
从候选目的地中选择最佳迁徙方案：

返回JSON：
{{
    "recommended_destination": "地块ID",
    "destination_score": 0.0-1.0,  // 目的地综合评分
    "selection_reasoning": "选择该目的地的原因（80字内）",
    
    "route_plan": {{
        "distance": "迁徙距离",
        "estimated_duration": "预计耗时（回合）",
        "waypoints": ["途经点"],
        "hazards": ["途中风险"]
    }},
    
    "expected_outcomes": {{
        "mortality_change": -0.3到0.1,  // 迁徙后死亡率变化
        "resource_access": "improved/stable/reduced",
        "competition_level": "high/medium/low",
        "food_availability": "abundant/adequate/scarce"
    }},
    
    "migration_cost": {{
        "journey_mortality": 0.05-0.2,  // 迁徙途中损失
        "energy_cost": "high/medium/low",
        "separation_risk": 0.0-0.3  // 种群分离风险
    }},
    
    "alternative_recommendation": {{
        "destination": "备选地块ID",
        "reason": "为什么是备选"
    }},
    
    "narrative": "60-80字描述这次迁徙的过程和预期"
}}

=== 选择原则 ===
1. 消费者（T2+）必须有足够的猎物
2. 距离不宜过远（考虑迁徙损失）
3. 避开高竞争区域
4. 环境适宜度 > 0.5
5. 优先选择与当前栖息地类型相似的区域

只返回JSON对象。
""",

    # ==================== 批量处理版本 ====================
    "pressure_assessment_batch": """你是生态学专家，批量评估多个物种对当前环境压力的应对能力。

**重要：必须返回纯JSON格式，不要使用markdown或其他格式。**

=== 全局环境压力 ===
总压力强度：{total_pressure:.1f}/10
压力来源：{pressure_sources}
重大事件：{major_events}

=== 待评估物种列表 ===
{species_list}

=== 任务 ===
为每个物种评估其应对压力的能力，返回JSON数组：

{{
    "assessments": [
        {{
            "lineage_code": "物种代码",
            "survival_modifier": 0.5-1.5,
            "response_strategy": "逃避/对抗/适应/忍耐/衰退",
            "key_factor": "最关键的生存/风险因素",
            "population_behavior": "种群行为预测",
            "brief_narrative": "40-60字简述"
        }}
    ]
}}

=== 修正系数指南 ===
- 0.5-0.7: 显著优势（特质高度匹配压力）
- 0.7-0.9: 小幅优势
- 0.9-1.1: 中性
- 1.1-1.3: 较脆弱
- 1.3-1.5: 高危

只返回JSON对象。
"""
}

