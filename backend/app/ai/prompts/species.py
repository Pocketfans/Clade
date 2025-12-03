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
2. **适度变化**：单次变化幅度在 ±0.5 到 ±1.5 之间，总变化量有增有减
3. **压力响应**：变化应直接回应当前环境压力
4. **禁止纯升级**：不存在没有代价的进化

=== ⚠️ 极端环境特殊规则 ===
【识别极端条件】（从压力上下文推断）
- "冰河时期"/"极度寒冷"：极端低温，耐寒性必须提升，否则死亡率>60%
- "温室效应"/"高温"：极端高温，耐热性必须提升
- "干旱"/"荒漠化"：极度缺水，耐旱性/保水能力是生存关键
- "缺氧事件"/"硫化事件"：化学危机，解毒/厌氧适应必须强化

【极端环境下的演化响应】
- 如果检测到极端条件词汇，recommended_changes中必须包含对应特质的显著增强（≥+1.0）
- 极端环境下代价更大：增强1点核心特质需要减少1.2点其他特质
- priority必须设为"high"

【失败后果】
- 如果面对极端压力却只进行温和适应（如+0.3），系统会判定适应不足
- 适应不足的物种将遭受额外死亡率惩罚（每回合+15%）

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

=== 🌍 地质时代背景 ===
{era_summary}

=== ⚠️ 语言与命名绝对规则 ===
1. **全中文输出**：所有名称（common_name, structure_name）、描述（description）必须完全使用中文。
2. **禁止英文**：organ_evolution 中的 structure_name 严禁出现英文单词（如 "Fin" ❌ -> "鳍" ✅）。
3. **标准分类**：organ_evolution 中的 category 必须从以下列表中选择最接近的一项：
   - 动物类：locomotion(运动), sensory(感官), metabolic(代谢), digestive(消化), defense(防御), reproduction(繁殖), nervous(神经), respiratory(呼吸), circulatory(循环)
   - 植物类：photosynthetic(光合), root_system(根系), stem(茎干), reproductive(繁殖), protection(保护), vascular(维管), storage(储存)
   - ⚠️ 如果是全新奇特器官，请归入 "special(特殊)" 并赋予一个中文名（如 "量子感应器"）。

⚠️ 重要：当前时代的生物复杂度受限！
- 早期时代（太古宙/元古宙）：只有简单生物，属性上限较低
- 演化是渐进的：新特征需要多代积累，每次分化只能小幅提升
- 你的创意应符合当前时代的生物特征（如太古宙不应出现复杂器官）

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

=== ⚠️ 极端环境警告 ===
【压力等级判定】
- 压力≤3: 🟢 温和环境 - 常规适应
- 压力4-6: 🟡 中等压力 - 需要显著适应
- 压力7-8: 🔴 高压环境 - 必须强化核心生存特质
- 压力≥9: ⛔ 极端危机 - 生存优先，分化需牺牲非必要特质

【当前压力响应要求】（根据上方压力强度）
- 如果压力≥7：必须优先增强与压力直接相关的特质（如冰河期→耐寒性）
- 如果压力≥9：trait_changes中增强项必须≥1.5，且必须有≥1.0的减弱项作为代价
- 极端环境下"保守演化"会被惩罚 - 系统会降低分化成功率

【分化失败成本】
- 如果新物种特质不匹配环境，将在下回合遭受额外30%死亡率
- 描述中必须明确说明如何应对当前环境压力
- 如果压力>8且未增强相关特质，该分化将被视为"不适应"并可能被自然选择淘汰

=== ⚠️ 硬性约束（必须遵守，否则会被系统强制修正）===

【属性权衡预算 + 时代上限】
{trait_budget_summary}
- ❌ 违规示例：增加总和超过上限、没有减少项、单项变化超过±3.0、超过时代上限
- ✅ 正确示例：{{"耐寒性": "+1.5", "繁殖速度": "-1.0", "运动能力": "-0.5"}} (增+1.5, 减-1.5, 净变化0)
- 📊 渐进式演化：每次分化是小步前进，多代积累才能突破

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

=== 🌱 植物演化专用规则（仅对营养级<2.0的物种生效）===
【植物阶段升级】
- 阶段0（原核）→1（真核）：多细胞程度 >= 1.5
- 阶段1→2（群体化）：多细胞程度 >= 3.0
- 阶段2→3（登陆）⚠️关键：保水能力 >= 5.0 且 耐旱性 >= 4.0
- 阶段3→4（真根）：根系发达度 >= 5.0
- 阶段4→5（种子）：种子化程度 >= 5.0
- 阶段5→6（开花）：种子化程度 >= 8.0 且 散布能力 >= 7.0
- 成为树木：木质化程度 >= 7.0 且 阶段 >= 5

【植物专用字段】（植物物种必须返回）
- "life_form_stage": 当前阶段或+1（不可跳级）
- "growth_form": "aquatic/moss/herb/shrub/tree"（必须符合阶段）
- "milestone_triggered": 里程碑ID或null

【植物器官类别】（使用这些替代动物器官）
- photosynthetic: 光合器官（叶绿体→类囊体膜→真叶→阔叶）
- root_system: 根系（假根→原始根→须根系→直根系）
- stem: 茎（匍匐茎→草本茎→木质茎→乔木干）
- reproductive: 繁殖（孢子囊→胚珠→球果→花→果实）
- protection: 保护（粘液层→角质层→蜡质表皮→树皮）
- vascular: 维管（原始维管束→维管束→次生木质部）

【植物权衡代价】
- 增强光合效率 → 降低耐旱性（需更多水）
- 增加木质化 → 降低繁殖速度
- 发展根系 → 降低散布能力

=== 命名规则（重要！）===
名字应像真实生物那样"有依据"，给人"可能真实存在"的感觉。以下为参考，可自由组合创造！

【拉丁学名】保留属名，种加词用拉丁/希腊词根体现特征（可自由组合词根）：
- 地理：borealis(北)、australis(南)、montanus(山)、fluvialis(河)、oceanicus(洋)、lacustris(湖)、insularis(岛)、orientalis(东)
- 形态：longus(长)、brevis(短)、crassus(厚)、gracilis(细长)、spinosus(多刺)、pinnatus(鳍状)、cornuta(有角)、squamosus(鳞片)、barbatus(有须)
- 颜色：ruber/rubra(红)、niger(黑)、albus/alba(白)、viridis(绿)、aureus(金)、caeruleus(蓝)、griseus(灰)、maculatus(斑点)
- 生态：noctis(夜)、abyssalis(深渊)、thermalis(热泉)、glacialis(冰川)、fossoria(穴居)、pelagicus(远洋)、littoralis(沿岸)
- 行为：velox(快速)、vorax(贪食)、raptor(掠食)、errans(漫游)、natans(游泳)、volans(飞行)
- 组合示例：Aurecosteus(金肋)、Cryopinna(冰鳍)、Talpaptera(掘翼)、Abyssognathus(深渊颌)、Nivalisaurus(雪蜥)

【中文俗名】自然、有画面感、有叙述性（4-8字）：
- 可用环境意象：风崖、暮林、霜岭、赤湾、玄渊、碧潭、烟谷、云脊、寒泽、焰原、幽谷、晨滩、雾沼、断崖、深壑、荒漠、冰原...
- 可用形态特征：长鳍、厚甲、弯棘、尖吻、阔口、细足、羽鳍、裂唇、环纹、刺背、扁躯、盘尾...
- 可用行为习性：潜沙、逐雾、碎岩、钻泥、追波、伏底、漂游、穴居、攀岩、滑翔...
- 可用类群后缀：—鱼、—虫、—兽、—螈、—蜥、—蟹、—贝、—龙、—鳗、—鸟、—蛾...
- 示例：风崖长鳍鱼、暮林攀枝兽、霜岭游鹿、玄渊盲螈、碧潭钻泥蟹、焰原厚甲蜥、云脊滑翔蛾
- 避免：搞笑/卡通化/纯音译/无意义随机组合
- 目标：读起来自然、有生态画面感、像真实物种名

=== 任务 ===
生成新物种的**创意性内容**：
1. 拉丁学名（按上述规则）
2. 中文俗名（自然有画面感）
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
            "category": "从标准分类列表中选择",
            "action": "enhance/initiate",
            "current_stage": 与上方父系阶段一致,
            "target_stage": current_stage+1或+2,
            "structure_name": "具体的器官中文名称（如：眼点、鞭毛、外骨骼）",
            "description": "变化描述"
        }}
    ],
    "life_form_stage": "🌱植物专用：当前阶段或+1（0-6整数）",
    "growth_form": "🌱植物专用：aquatic/moss/herb/shrub/tree",
    "milestone_triggered": "🌱植物专用：里程碑ID或null"
}}

【捕食关系规则】
- 通常继承父系的食性类型和猎物，但可以因环境压力调整
- 如果分化导致营养级变化，需要相应调整猎物范围
- 新猎物必须是当前生态系统中存在的物种
- 如果灭绝事件导致原猎物消失，需要寻找替代食物源

=== 示例1：动物分化（父系器官sensory当前阶段=1，草食性，猎物为A1）===
{{
    "latin_name": "Protoflagella oculocava",
    "common_name": "碧潭凹眼虫",
    "description": "浅海环境促使感光点内陷形成眼凹结构，提高光线方向感知能力。繁殖速度下降以维持复杂感觉结构。主要滤食蓝藻A1，栖息于阳光充足的浅海礁区。",
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

=== 示例2：🌱植物分化（阶段2群体藻类，保水能力=5.2，耐旱性=4.5，准备登陆）===
{{
    "latin_name": "Bryophytella littoricola",
    "common_name": "潮岩先锋苔",
    "description": "首批登陆的植物先驱，从潮间带向内陆扩展。发展出原始角质层减少水分散失，假根固着于岩石缝隙。作为自养生产者，光合效率略降，但获得了陆地生存的关键能力。",
    "habitat_type": "coastal",
    "trophic_level": 1.0,
    "diet_type": "autotroph",
    "prey_species": [],
    "prey_preferences": {{}},
    "key_innovations": ["首次登陆陆地", "角质层保水"],
    "trait_changes": {{"保水能力": "+1.0", "耐旱性": "+0.8", "光合效率": "-0.5", "繁殖速度": "-0.3"}},
    "morphology_changes": {{"body_length_cm": 1.2}},
    "event_description": "群体藻类成功登陆，成为苔藓类先驱",
    "speciation_type": "生态隔离",
    "reason": "潮间带干湿交替环境促进保水结构演化",
    "organ_evolution": [
        {{"category": "protection", "action": "initiate", "current_stage": 0, "target_stage": 1, "structure_name": "角质层", "description": "发展原始角质层防止水分散失"}},
        {{"category": "root_system", "action": "initiate", "current_stage": 0, "target_stage": 1, "structure_name": "假根", "description": "简单假根固着岩石"}}
    ],
    "life_form_stage": 3,
    "growth_form": "moss",
    "milestone_triggered": "first_land_plant"
}}

只返回JSON。
""",
    
    "endosymbiosis": """你是演化生物学家。正在模拟一个极其罕见的【内共生事件】！

=== 事件背景 ===
捕食者（宿主）：{host_name}
被吞噬者（共生体）：{symbiont_name}
环境压力：{pressure_context}

=== 演化剧本 ===
捕食者在极度饥饿/压力下吞噬了猎物，但由于某种基因突变，消化酶失效了。
猎物在宿主体内幸存下来，并开始为宿主提供能量（光合作用/ATP合成等），形成互利共生关系。
这类似于线粒体或叶绿体的起源。

=== 任务 ===
创建一个新物种（宿主的后代），它拥有一个源自猎物的【新器官】。

**必须返回纯JSON格式。**
**命名规则：必须全中文。**

=== 输出格式 ===
{{
    "latin_name": "新物种学名 (基于宿主)",
    "common_name": "新物种中文俗名 (体现共生特征)",
    "description": "描述这个共生体的诞生过程，以及它如何改变了宿主的生存方式（150字左右）。",
    "habitat_type": "继承宿主",
    "trophic_level": 宿主营养级 + 0.1 (能量效率提升),
    "diet_type": "继承宿主或混合",
    "key_innovations": ["内共生体", "能量革命"],
    "trait_changes": {{"代谢效率": "+2.5", "能量需求": "-1.0"}},
    "new_organ": {{
        "category": "metabolic",
        "structure_name": "源自{symbiont_name}的共生器官名（如：紫菌体、共生藻）",
        "description": "描述该器官如何利用猎物的能力为宿主供能",
        "evolution_stage": 2
    }},
    "speciation_type": "内共生突变",
    "reason": "消化系统突变导致猎物保留并转化为细胞器"
}}
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
1. 属性权衡：增加必有减少，必须有增有减
2. 形态稳定：体长变化0.8-1.3倍
3. 器官演化：每次最多提升2阶段，新器官从阶段1开始
4. 营养级：通常与父代相近(±0.5)

只返回JSON对象。
""",
    "speciation_batch": """你是演化生物学家，批量推演动物物种的分化事件。

**必须返回JSON格式，包含所有请求物种的分化结果。**

=== 环境背景 ===
压力强度：{average_pressure:.2f}/10 | 压力来源：{pressure_summary}
地形变化：{map_changes_summary} | 重大事件：{major_events_summary}

=== 待分化物种 ===
{species_list}

=== ⚠️ 硬性约束（违反将被系统强制修正）===

【属性权衡】⚠️ 最重要！查看每个物种的【属性预算】：
- 增加的属性值总和 ≤ 预算中的"增加≤+X"值（通常+2~+4）
- 减少的属性值总和 ≥ 预算中的"减少≥-X"值（通常-1~-2）
- 单项变化不超过±2.0
- 必须有增有减，增减要平衡！
- ✅ 正确: {{"耐寒性": "+1.0", "光照需求": "+0.5", "繁殖速度": "-0.8"}} (增+1.5, 减-0.8)
- ❌ 错误: {{"耐寒性": "+3.0", "体型": "+2.0", "速度": "+1.5"}} (增+6.5超预算, 无减少)

【营养级】只能变化±0.5（见每个物种条目的允许范围）

【器官演化】⚠️ 最常见错误！
- current_stage 必须与【器官约束】中给出的当前阶段一致
- 新器官：current_stage=0 → target_stage=1
- 已有器官：target_stage ≤ current_stage + 2
- ✅ 父系sensory=1 → {{"current_stage": 1, "target_stage": 2}}
- ❌ 父系sensory=1 → {{"current_stage": 4}} 会被修正

【分化策略】
- 高压区域（死亡率>50%）：演化抗逆性特征
- 低压区域（死亡率<30%）：演化竞争性特征
- 地理隔离：不同区域应有性状分歧

=== 输出格式 ===
{{
    "results": [
        {{
            "request_id": "请求ID",
            "latin_name": "拉丁学名",
            "common_name": "中文俗名",
            "description": "100-150字描述",
            "habitat_type": "marine/coastal/freshwater/terrestrial/aerial",
            "trophic_level": 父代±0.5,
            "key_innovations": ["创新点"],
            "trait_changes": {{"增强属性": "+值", "减弱属性": "-值"}},
            "morphology_changes": {{"body_length_cm": 0.8-1.3倍}},
            "event_description": "30字分化摘要",
            "reason": "分化原因",
            "organ_evolution": [
                {{"category": "器官类别", "action": "enhance/initiate", "current_stage": 当前阶段, "target_stage": 目标阶段, "structure_name": "结构名", "description": "变化描述"}}
            ]
        }}
    ]
}}

=== 命名规则 ===
名字要像真实物种，自然、有依据。可自由组合创造！

【拉丁学名】常用词根组合：
- 地理/栖息地：borealis(北方)、australis(南方)、orientalis(东方)、montanus(山地)、abyssalis(深渊)、littoralis(沿岸)、pelagicus(远洋)
- 形态特征：longus(长)、brevis(短)、magnus(大)、spinosus(多刺)、pinnatus(有鳍)、cornutus(有角)、armatus(有甲)、dentatus(有齿)
- 颜色：niger(黑)、albus(白)、ruber(红)、aureus(金)、viridis(绿)、caeruleus(蓝)
- 生态/习性：thermalis(热泉)、glacialis(冰川)、noctis(夜行)、velox(快速)、vorax(贪食)、ferox(凶猛)
- 人名后缀：-i(属格，如darwini达尔文的)、-orum(复数属格)、-ae(女性属格)
- 地名化：sinensis(中国)、japonicus(日本)、americanus(美洲)

【中文俗名】多种风格可选：
- 环境+形态+类群：风崖长鳍鱼、玄渊盲螈、霜脊游龙
- 人名+氏+类群：邓氏鱼、李氏螈、陈氏虫（纪念发现者/科学家）
- 地名+类群：澄江虫、热河鸟、辽西龙
- 特征直译：三叶虫、盾皮鱼、棘皮动物
- 行为/习性：伏击蟹、滤食贝、穴居蛇
- ❌ 避免搞笑/卡通化/无意义组合

只返回JSON。
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
""",

    # 【新增】植物专用描述更新Prompt
    "plant_description_update": """你是古植物学记录员。该植物物种经历了漫长的渐进式演化，其数值特征已发生显著变化，但文字描述尚未更新。请重写描述以匹配当前数值。

=== 环境背景 ===
当前环境压力：{pressure_context}
{plant_context}

=== 植物档案 ===
【基本信息】
学名：{latin_name} ({common_name})
演化阶段：{life_form_stage_name}
生长形式：{growth_form}
原描述：{old_description}

【数值变化检测】
{trait_diffs}

【器官系统状态】
{plant_organs_summary}

=== 植物特征变化对应关系 ===
数值变化请转化为以下植物学特征：
- 光合效率↑ → "叶绿体密度增加/叶片表面积扩大/出现聚光结构"
- 根系发达度↑ → "根系向土壤深层延伸/发展出侧根网络/出现根毛结构"
- 保水能力↑ → "角质层加厚/气孔下陷/发展出储水组织"
- 木质化程度↑ → "维管束壁增厚/出现次生生长/茎部木质化"
- 化学防御↑ → "分泌单宁/生物碱含量增加/发展出乳汁管"
- 物理防御↑ → "表皮刺状突起增多/硅质沉积增加/发展出厚壁组织"
- 种子化程度↑ → "孢子演化为原始胚珠/发展出种皮结构"
- 散布能力↑ → "孢子变轻/种子附属结构(翅/羽毛)发展"
- 多细胞程度↑ → "细胞分化程度加深/组织类型增多"

=== 任务要求 ===
1. 重写 `description`（120-150字）：
   - 必须保留物种的基本植物身份和生态位。
   - 将数值变化转化为植物形态学和生理学特征。
   - 结合环境背景解释适应性变化的演化意义。
   - 如有特征退化，描述其权衡意义（如"为节约能量..."）。
   - 体现植物静态生活的特点（不能移动，通过形态和生理适应环境）。
2. 符合当前演化阶段的特征限制。

=== 输出格式 ===
返回标准 JSON 对象：
{{
    "new_description": "更新后的植物学描述..."
}}
""",

    # ==================== 杂交物种生成Prompt ====================
    "hybridization": """你是演化生物学家，负责为物种杂交生成新物种的详细数据。

**必须返回纯JSON格式。**

=== 杂交亲本信息 ===
【亲本A】
代码：{parent1_lineage}
学名：{parent1_latin_name} ({parent1_common_name})
栖息地：{parent1_habitat}
营养级：T{parent1_trophic:.1f}
描述：{parent1_description}

【亲本B】
代码：{parent2_lineage}
学名：{parent2_latin_name} ({parent2_common_name})
栖息地：{parent2_habitat}
营养级：T{parent2_trophic:.1f}
描述：{parent2_description}

=== 杂交背景 ===
遗传距离：{genetic_distance:.2f}（0=完全相同，1=完全不同）
预期可育性：{fertility:.0%}
杂交种编码：{hybrid_code}

=== 杂交物种命名规则 ===
1. **拉丁学名**：使用 "Genus × epithet" 格式
   - 属名继承自亲本A
   - 种加词融合双亲特征，可组合词根或创造新词
   - 组合方式：marina+thermalis→marithermis、glacialis+tropicus→cryotropicus
   - 示例：Protoflagella × halothermis（盐热）、× cryofervens（冷热）、× pelagoabyssalis（远洋深渊）
   
2. **中文俗名**：自然有画面感，体现双亲特征融合（4-8字）
   - 可用格式：[融合特征]+[类群]、[环境]+中间型/杂合[类群]
   - 示例："盐热间型虫"、"冰火杂合螈"、"浅深过渡鱼"、"岩沙混栖蟹"
   - ✅ 目标：让人一眼看出是两种生态型的杂交
   - ❌ 避免：搞笑化、纯音译、无意义组合

=== 杂交遗传规则 ===
1. **杂交优势**：某些特质可能超过双亲（但需权衡）
2. **中间型**：大多数特质取双亲平均值±小幅波动
3. **隐性表达**：部分隐性特质可能在杂交种中表达
4. **权衡代价**：杂交优势必须伴随某些特质的下降
5. **营养级**：继承双亲中较高者±0.3

=== 输出格式 ===
{{
    "latin_name": "Genus × epithet（杂交种学名）",
    "common_name": "简洁的中文俗名（最多8字）",
    "description": "100-150字，描述杂交种的形态特征、遗传来源、杂交优势和生态位",
    "habitat_type": "从双亲栖息地中选择或取交集",
    "trophic_level": 双亲较高者±0.3,
    "diet_type": "继承双亲食性",
    "key_traits": ["2-3个杂交优势特征"],
    "trait_balance": {{
        "优势特质": "+数值（杂交优势）",
        "代价特质": "-数值（权衡代价）"
    }},
    "hybrid_description": "30-50字的杂交事件描述"
}}

=== 示例 ===
亲本A：海洋鞭毛虫（耐盐性高）
亲本B：热泉鞭毛虫（耐热性高）
{{
    "latin_name": "Protoflagella × halothermis",
    "common_name": "盐热间型虫",
    "description": "海洋鞭毛虫与热泉鞭毛虫的杂交后代，继承了双亲的环境耐受特征。具有较高的耐盐性和耐热性，能够在热泉口附近的高盐度热水中生存。但繁殖速度较双亲均有所下降，杂交优势主要体现在环境适应范围的扩大上。",
    "habitat_type": "marine",
    "trophic_level": 2.0,
    "diet_type": "herbivore",
    "key_traits": ["双重环境耐受", "扩展生态位"],
    "trait_balance": {{
        "耐盐性": "+0.5",
        "耐热性": "+0.3",
        "繁殖速度": "-0.6"
    }},
    "hybrid_description": "海洋与热泉生态型杂交产生具有广泛环境耐受性的新类型"
}}

只返回JSON对象。
""",

    # ==================== 强行杂交（跨属/幻想杂交）Prompt ====================
    "forced_hybridization": """你是一位疯狂的基因工程师和幻想生物设计师！

玩家正在进行**强行杂交**实验——跨越自然界限，将两个完全不同的物种强行融合！
这是科幻/奇幻风格的实验，请发挥创意，设计一个有趣、独特、令人印象深刻的嵌合体生物！

**必须返回纯JSON格式。**

=== 实验对象 ===
【物种A】
代码：{parent1_lineage}
名称：{parent1_latin_name} ({parent1_common_name})
描述：{parent1_description}
特征关键词：{parent1_traits}

【物种B】
代码：{parent2_lineage}  
名称：{parent2_latin_name} ({parent2_common_name})
描述：{parent2_description}
特征关键词：{parent2_traits}

=== 强行杂交背景 ===
- 这是**违背自然规律**的基因工程实验
- 两个物种可能来自完全不同的分类群
- 结果是一个**嵌合体**或**奇美拉**生物
- 可能具有双亲的外形特征混合
- 通常生育率比较低
- 可能有**基因不稳定性**（变异、退化风险）

=== 设计指南 ===

1. **命名创意**：
   - 拉丁学名：× Chimera [组合拉丁词根]，保持科学感
   - 词根组合：felis(猫)+anthropus(人)、ichthys(鱼)+pteron(翼)、serpens(蛇)+pes(足)
   - 中文俗名：形象、有画面感，可带诗意或神话感（4-8字）
   - 命名灵感：环境+融合特征、神话意象、形态描写
   - 例如：猫科×灵长 → "× Chimera felinanthropus" / "月影猫人"、"暮林灵猫"
   - 例如：鱼×鸟 → "× Chimera ichthyoptera" / "翔鳍兽"、"破浪飞鱼"
   - 例如：蛇×蜥蜴 → "× Chimera serpentilacerta" / "游沙鳞蛇"
   - ✅ 目标：独特但不荒诞，像神话/科幻中可能存在的生物
   - ❌ 避免：纯搞笑/网络梗/过度卡通化

2. **外形设计**：
   - 融合双亲最具特色的外形特征
   - 可以是：上半身A+下半身B、A的身体+B的器官、镶嵌式融合等
   - 描述要生动有趣，让人能想象出这个生物的样子

3. **能力特点**：
   - 可能获得双亲的**独特能力组合**
   - 但也有**代价和缺陷**（不稳定、虚弱、短命等）
   - 体现"逆天改命"的代价

4. **性格/行为**（可选，增加趣味性）：
   - 可能有双亲的行为习性混合
   - 可能有独特的性格特点

=== 输出格式 ===
{{
    "latin_name": "× Chimera [创意名称]",
    "common_name": "有趣的中文名（2-6字，可以玩梗）",
    "description": "150-200字生动描述：外形特征、融合方式、独特能力、性格行为、生存方式",
    "appearance": "50-80字外形速写：让人一眼能想象出这个生物的样子",
    "abilities": ["3-5个独特能力或特征"],
    "weaknesses": ["2-3个缺陷或代价"],
    "personality": "20-40字性格描述（可选，增加趣味）",
    "habitat_type": "适合的栖息环境",
    "trophic_level": 营养级数值,
    "stability": "stable/unstable/volatile（基因稳定性）",
    "fertility": "sterile/very_low/low（可育性）",
    "trait_bonuses": {{
        "特质名": +数值（继承或增强的特质）
    }},
    "trait_penalties": {{
        "特质名": -数值（代价或缺陷）
    }},
    "chimera_event": "30-50字的实验/诞生事件描述"
}}

=== 创意示例 ===

【示例1：猫科 × 灵长类】
{{
    "latin_name": "× Chimera felinanthropus",
    "common_name": "月影猫人",
    "description": "基因工程的奇迹产物，融合了猫科动物的敏捷优雅与灵长类的智慧。拥有人形身体、尖锐猫耳和长尾，瞳孔在光线变化时会收缩成猫眼形态。继承了猫的夜视能力、敏锐听觉和惊人的反射神经，同时保留了灵长类的抓握能力和社交智慧。然而基因不稳定导致其寿命较短，且对某些环境因素敏感。",
    "appearance": "人形身躯覆有细软绒毛，头顶一对三角猫耳会随情绪转动，身后长尾巴保持平衡。竖瞳在暗处发出微光。",
    "abilities": ["暗视能力", "超敏捷反应", "听觉增强", "精细操作", "攀爬"],
    "weaknesses": ["基因不稳定", "寿命缩短", "环境敏感"],
    "personality": "警觉而好奇，独居倾向但能形成小型社群。",
    "habitat_type": "terrestrial",
    "trophic_level": 3.0,
    "stability": "unstable",
    "fertility": "very_low",
    "trait_bonuses": {{
        "运动能力": "+3.0",
        "社会性": "+2.0",
        "感知能力": "+2.5"
    }},
    "trait_penalties": {{
        "繁殖速度": "-4.0",
        "环境敏感度": "+2.0"
    }},
    "chimera_event": "疯狂基因工程师的禁忌实验，将猫科与灵长类基因融合，创造出这一传说中的生物。"
}}

【示例2：鲨鱼 × 章鱼】
{{
    "latin_name": "× Chimera selachocephalopoda",
    "common_name": "玄渊触鲨",
    "description": "深海噩梦般的捕食者，拥有鲨鱼的流线型身躯和锋利牙齿，却长着章鱼的八条触腕和变色能力。能在追逐猎物时展现鲨鱼的速度，也能用触腕缠绕并释放墨汁逃脱。双重呼吸系统让它能在不同水深活动，但神经系统的冲突导致它行为有时混乱不可预测。",
    "appearance": "鲨鱼般的头部和躯干，体侧长出八条粗壮触腕替代了普通鳍。皮肤能像章鱼一样变色伪装。",
    "abilities": ["极速游泳", "触腕缠绕", "墨汁喷射", "变色伪装", "双重呼吸"],
    "weaknesses": ["神经冲突", "行为不稳定", "能量消耗大"],
    "personality": "狩猎本能与好奇心的矛盾结合体，时而凶猛时而呆萌。",
    "habitat_type": "marine",
    "trophic_level": 4.5,
    "stability": "volatile",
    "fertility": "sterile",
    "trait_bonuses": {{
        "运动能力": "+4.0",
        "捕食效率": "+3.0",
        "隐蔽性": "+2.0"
    }},
    "trait_penalties": {{
        "社会性": "-3.0",
        "繁殖速度": "-5.0",
        "精神稳定": "-2.0"
    }},
    "chimera_event": "深海实验室的意外泄露，两种顶级捕食者的基因融合产生了这一终极猎手。"
}}

发挥你的创意，设计一个独特有趣的嵌合体生物！只返回JSON对象。
"""
}

# ==================== Atomic Prompt Fragments (v2 System) ====================

ADAPTATION_FRAGMENTS = {
    "base_role": """你是演化生物学家，负责分析物种对环境压力的适应性演化。
**必须返回纯JSON格式。**
""",
    "context_intro": """=== 物种档案 ===
学名：{latin_name} ({common_name})
栖息地：{habitat_type}
营养级：{trophic_level:.1f}
特质：{traits_summary}
器官：{organs_summary}
""",
    "pressure_context": """=== 环境压力 ===
{pressure_context}
""",
    "budget_strict": """===  能量预算 (严格权衡) ===
最大变化幅度：{magnitude_cap}
规则：增强某属性必须牺牲其他属性。
公式：||V_new|| ≈ ||V_old||
约束：你有 {budget} 个演化点数预算。
""",
    "extreme_rules": """===  检测到极端环境 ===
条件：{extreme_condition}
要求：必须针对该压力进化出显著抗性 (>= +1.0)。
惩罚：如果适应不足，将面临高死亡率。
""",
    "output_format": """=== 输出格式 ===
返回JSON：
{{
    "analysis": "演化分析...",
    "recommended_changes": {{"特质名": 数值}},
    "organ_changes": [{{ "category": "...", "change_type": "...", "parameter": "...", "delta": ... }}],
    "priority": "high/medium/low",
    "rationale": "机制解释"
}}
"""
}

SPECIATION_FRAGMENTS = {
    "role": """你是演化生物学家。基于分化事件生成新物种。
**必须返回纯JSON格式。**
""",
    "era_context": """=== 地质时代：{era_name} ===
{era_summary}
约束：{era_constraint}
""",
    "parent_info": """=== 父系物种 ===
名称：{latin_name}
特质：{traits}
器官：{current_organs_summary}
""",
    "eco_region": """=== 生态-地理区域：{region_name} ===
环境：{environment_summary}
压力源：{pressure_summary}
生物背景：{biotic_context}
""",
    "task_speciation": """=== 任务：物种分化 ===
类型：{speciation_type}
原因：{speciation_reason}
创建一个适应此特定区域的异域/同域分化物种。
""",
    "constraints": """=== 约束条件 ===
1. 权衡：净变化必须平衡（有增必有减）。
2. 创新：必须回应区域特定的压力。
3. 营养级：保持在 {trophic_range} 范围内。
4. 预算：{trait_budget_summary}
""",
     "output_format": """=== 输出格式 ===
{{
    "latin_name": "Genus species",
    "common_name": "中文俗名",
    "description": "描述...",
    "habitat_type": "...",
    "trophic_level": ...,
    "key_innovations": [...],
    "trait_changes": {{"增强属性": "+值", "减弱属性": "-值"}},
    "morphology_changes": {{...}},
    "event_description": "...",
    "speciation_type": "{speciation_type}",
    "reason": "...",
    "organ_evolution": [...]
}}
"""
}

