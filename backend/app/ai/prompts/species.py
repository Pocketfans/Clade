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
        "耐寒性": "0-10整数",
        "耐热性": "0-10整数",
        "耐旱性": "0-10整数",
        "耐盐性": "0-10整数",
        "耐酸碱性": "0-10整数",
        "光照需求": "0-10整数",
        "氧气需求": "0-10整数",
        "繁殖速度": "0-10整数",
        "运动能力": "0-10整数",
        "社会性": "0-10整数"
    }},
    "hidden_traits": {{
        "gene_diversity": "0.0-1.0",
        "environment_sensitivity": "0.0-1.0",
        "evolution_potential": "0.0-1.0",
        "mutation_rate": "0.0-1.0",
        "adaptation_speed": "0.0-1.0"
    }}
}}

要求：
- description严格100-120字，精简但包含所有关键生态信息
- 根据体型设置合理数量：微生物(10^5-10^6)、小型(10^4-10^5)、中型(10^3-10^4)、大型(10^2-10^3)
- 所有数值必须合理且符合生物学规律
- 只返回JSON，不要其他内容
""",
    "speciation": """你是演化生物学家，为分化物种生成完整演化数据（包含命名）。

【父系物种】
代码：{parent_lineage}
学名：{latin_name}
俗名：{common_name}
完整描述：{traits}

【演化环境】
环境压力：{environment_pressure:.2f}/10
幸存者：{survivors:,}个体
分化类型：{speciation_type}
地形变化：{map_changes_summary}
重大事件：{major_events_summary}

【任务】
返回JSON对象：
{{
    "latin_name": "拉丁学名（Genus species格式）",
    "common_name": "中文俗名",
    "description": "120-180字完整生物学描述",
    "key_innovations": ["1-3个关键演化创新"],
    "trait_changes": {{"trait_name": "+2.0或-1.5等浮点数变化"}},
    "morphology_changes": {{"stat_name": 变化倍数(0.8-1.5)}},
    "event_description": "30-50字描述分化事件（如：一小群个体因...隔离）",
    "speciation_type": "地理隔离|生态隔离|时间隔离|竞争排斥",
    "reason": "详细说明导致分化的生态学或地质学机制",
    
    "structural_innovations": [
        {{
            "category": "器官类别(locomotion/sensory/metabolic/digestive/defense/respiratory)",
            "type": "具体器官类型（中文，如'鞭毛'、'叶绿体'）",
            "parameters": {{
                "具体参数名": 数值,
                "efficiency": 相对父代的效率倍数(0.8-2.0)
            }},
            "description": "器官功能简述"
        }}
    ],
    
    "genetic_discoveries": {{
        "new_traits": {{
            "特质名": {{
                "max_value": 最大潜力值(1.0-15.0),
                "description": "特质描述",
                "activation_pressure": ["压力类型"]
            }}
        }},
        "new_organs": {{
            "器官名": {{
                "category": "器官类别",
                "type": "器官类型（中文）",
                "parameters": {{}},
                "description": "器官描述",
                "activation_pressure": ["压力类型"]
            }}
        }}
    }}
}}

【命名要求（必须唯一且有区分度）】
拉丁学名：
- 保留父系属名（如父系Protoflagella，子代也用Protoflagella）
- 种加词必须体现新物种的核心创新特征，禁止重复使用相同种加词
- 优先使用形态/生态/功能特征的拉丁词根：
  * 形态：longus(长), brevis(短), robustus(强壮), gracilis(纤细), acutus(尖锐), globosus(球形)
  * 运动：velox(快速), lentus(缓慢), natans(游泳), reptans(爬行)
  * 生态：profundus(深海), littoralis(浅海), thermophilus(喜热), cryophilus(喜冷)
  * 功能：vorax(贪食), filtrans(滤食), photosyntheticus(光合)
- 示例：Protoflagella velox（快速鞭毛虫）、Protoflagella profundus（深海鞭毛虫）

中文俗名：
- 结构：【1-2个字特征词】+【类群名】
- 特征词必须从key_innovations中提取最显著的一个
- 类群名保持与父系一致（如父系"鞭毛虫"，子代也用"鞭毛虫"）
- 示例特征词：快游、深水、透明、多鞭、耐盐、滤食、夜行、群居

【营养级与属性上限】
父系营养级：{parent_trophic_level:.2f}
根据description中的食性判断新物种营养级（T），并遵守属性上限：
- T 1.0-1.9（生产者/分解者）：基础上限5，特化上限8，总和≤30
- T 2.0-2.9（主要草食）：基础上限7，特化上限10，总和≤50
- T 3.0-3.9（中层捕食者）：基础上限9，特化上限12，总和≤80
- T 4.0-4.9（高层捕食者）：基础上限12，特化上限14，总和≤105
- T 5.0+（顶级掠食者）：基础上限14，特化上限15，总和≤135

营养级计算：T = 1 + Σ(prey_proportion × prey_T)
- 若以70%藻类(T=1.0) + 30%碎屑(T=1.0)为食 → T = 1 + 1.0 = 2.0（草食）
- 若捕食草食动物(T=2.0) → T = 1 + 2.0 = 3.0（中层捕食）
- 营养级提升时，允许属性总和+5（体现生物复杂度提升）

【属性权衡原则（强制）】
1. 属性总和变化：-5 ≤ Δ总和 ≤ +8（营养级提升时可+8）
2. 单属性变化：-4 ≤ Δ单属性 ≤ +4
3. 必须权衡：有属性+3则必须有属性-2；有+2则必须有-1
4. 特化税：每个属性超过基础上限1点，需要2点其他属性降低作为代价
5. 最多2个属性可超过基础上限（特化方向）
6. **支持动态属性**：你可以提出新的环境适应属性（如"耐高压"、"耐酸性"），只要符合营养级总和上限即可

【description要求（120-180字）】
必须包含以下所有要素：
1. 【父系继承】：保留的核心特征（如体型范围、基本形态、主要生理功能）
2. 【演化创新】：具体的结构或功能变化（不能笼统说"适应"）
   - 微生物级别：鞭毛数量/长度、膜结构变化、代谢途径转换、细胞器分化
   - 小型生物：触角/口器/壳体结构、运动方式变化、感官强化
   - 大型生物：器官分化、骨骼变化、感觉系统强化
3. 【生态位分化】：新物种与父系在资源利用上的明确差异
   - 空间：栖息深度/纬度/微环境的变化
   - 时间：昼夜活动节律、季节性变化
   - 资源：食物类型、粒径、营养模式的差异
4. 【适应形态】：针对当前压力的形态调整
   - 温度压力：耐热蛋白、脂质膜调整、体型变化
   - 干旱压力：保水结构、休眠机制、渗透压调节
   - 竞争压力：资源利用效率提升、生态位分离

【key_innovations要求】
必须列出1-3个具体的演化创新，禁止空洞描述：
- ✅ 好的例子："鞭毛由2根增至4根，游动速度提升50%"、"出现原始光感器，可感知光照梯度"、"壳体厚度增加，抗捕食能力增强"
- ❌ 禁止："适应能力增强"、"演化出新特征"、"变得更强"

【structural_innovations要求（新增，必须提供）】
必须为每个key_innovation提供对应的结构化器官数据：
1. **运动器官示例** (locomotion):
   - 鞭毛: {{"category": "locomotion", "type": "鞭毛", "parameters": {{"count": 4, "length_um": 12, "efficiency": 1.6}}, "description": "四根鞭毛，游动效率提升60%"}}
   - 纤毛: {{"category": "locomotion", "type": "纤毛", "parameters": {{"coverage": 0.8, "beat_frequency": 20}}, "description": "体表纤毛覆盖率80%"}}

2. **感觉器官示例** (sensory):
   - 眼点: {{"category": "sensory", "type": "简单眼点", "parameters": {{"light_sensitivity": 0.3, "wavelength_min": 400, "wavelength_max": 700}}, "description": "原始光感器，可感知400-700nm光"}}
   - 化学感受器: {{"category": "sensory", "type": "化学感受器", "parameters": {{"sensitivity": 0.5, "range_cm": 5}}, "description": "化学感受器，感知5cm内化学信号"}}

3. **代谢器官示例** (metabolic):
   - 叶绿体: {{"category": "metabolic", "type": "叶绿体", "parameters": {{"count": 10, "efficiency": 1.2}}, "description": "10个叶绿体，光合效率提升20%"}}

4. **防御结构示例** (defense):
   - 壳体: {{"category": "defense", "type": "钙质外壳", "parameters": {{"thickness_mm": 0.5, "hardness": 7}}, "description": "0.5mm厚壳体，硬度7级"}}

**注意**：
- 如果父系已有某器官，parameters中必须体现相对变化（如count从2→4）
- efficiency参数表示相对父代的效率（1.0=不变，1.5=提升50%，0.8=降低20%）
- 每个structural_innovation必须对应一个key_innovation

【genetic_discoveries要求（可选，极端环境时提供）】
此字段记录未立即表达的"遗传潜力"，这些基因会作为休眠基因存入属基因库，未来后代在相同压力下可能激活。

**触发条件**（满足任一即可考虑提供）：
- 环境极端：深海(>1000m)、极地、火山口、高盐湖等
- 压力强度：死亡率预期>60%的极端选择压力
- 生态位空白：进入全新未占领生态位

**示例1：极寒环境分化**
```json
"genetic_discoveries": {{
  "new_traits": {{
    "耐极寒": {{
      "max_value": 15.0,
      "description": "极端寒冷环境适应能力",
      "activation_pressure": ["extreme_cold", "polar"]
    }}
  }}
}}
```

**示例2：深海环境分化**
```json
"genetic_discoveries": {{
  "new_traits": {{
    "耐高压": {{
      "max_value": 14.0,
      "description": "深海高压环境适应",
      "activation_pressure": ["deep_ocean", "high_pressure"]
    }}
  }},
  "new_organs": {{
    "bioluminescence": {{
      "category": "sensory",
      "type": "发光器",
      "parameters": {{"intensity": 0.8, "wavelength": 480}},
      "description": "生物发光器官，480nm蓝光",
      "activation_pressure": ["darkness", "deep_ocean"]
    }}
  }}
}}
```

**命名规范**：
- new_traits: 使用现有特质体系（耐寒性、耐热性等）或新环境特质（耐极寒、耐高压等）
- new_organs: 使用中文名（发光器、电器官、抗冻腺体等）

**注意**：
- 不是每次分化都需要genetic_discoveries
- 只在极端环境、重大演化事件时提供
- 提供的基因应与当前环境压力强相关

【trait_changes要求】
基于环境压力，合理调整3-5个属性（支持浮点数精度）：
- 温度压力高 → 耐寒性/耐热性 +1.0到+3.5
- 干旱压力高 → 耐旱性 +2.0到+4.0
- 资源竞争激烈 → 繁殖速度 +1.0，运动能力 +1.5
- 所有变化值必须在±4.0以内，避免极端变化
- 支持小数调整（如+0.5），累积微小变化更符合渐进演化

    【morphology_changes要求】
    形态学变化应适度且合理：
    - body_length_cm: 0.8-1.3（微调，避免剧烈体型变化）
    - body_weight_g: 0.8-1.3（体重变化会通过Kleiber定律影响代谢率）
    - generation_time_days: 0.8-1.2
    - 注意：系统会自动根据体重计算代谢率，无需手动调整metabolic_rate

【speciation_type说明】
- 地理隔离：海平面上升、陆地分裂、火山形成障碍、冰川推进隔断种群
- 生态隔离：资源分化、栖息层分离、食性转变、繁殖时间错开
- 协同演化：捕食者-被捕食者军备竞赛、寄生-宿主协同演化、互利共生物种分化
- 极端环境特化：极端温度/压力/化学环境驱动的快速适应和种群分离

【重要】请根据{speciation_type}调整description：
- 地理隔离：强调形态分化（地理屏障两侧不同选择压力）
- 生态隔离：强调资源利用方式差异（同域物种的生态位分化）
- 协同演化：强调与其他物种的互动关系变化
- 极端环境特化：强调生理生化适应（耐受极限的突破）

【示例（仅供参考结构）】
{{
    "latin_name": "Protoflagella velox",
    "common_name": "快游鞭毛虫",
    "description": "原始鞭毛虫在干旱压力下分化形成快游型亚种。继承父系的梨形体态（体长15微米）和异养食性，但鞭毛数量由2根增至4根，游动速度提升约60%，能更快逃离不利水域。膜系统发展出更高效的渗透压调节蛋白，耐盐性显著增强。栖息环境向浅海高盐度区域转移，通过快速游动捕食微藻碎屑，与父系形成纵向分层的空间隔离。世代时间缩短至8天，繁殖速率提高，种群恢复能力更强。",
    "key_innovations": ["4根鞭毛系统，游动效率提升60%", "高效渗透压调节蛋白", "缩短世代时间至8天"],
    "trait_changes": {{"耐盐性": "+3.0", "运动能力": "+2.0", "繁殖速度": "+1.0"}},
    "morphology_changes": {{"generation_time_days": 0.8, "metabolic_rate": 1.1}},
    "event_description": "干旱压力驱动原始鞭毛虫分化，形成快游高盐耐受型，与父系实现空间生态位分离",
    "speciation_type": "生态隔离",
    "reason": "干旱导致浅海盐度升高，种群中耐盐性强且游速快的个体在高盐环境存活率更高，逐渐与栖息中层水域的原种群产生生殖隔离",
    "structural_innovations": [
        {{
            "category": "locomotion",
            "type": "四鞭毛",
            "parameters": {{
                "count": 4,
                "base_count": 2,
                "length_um": 12,
                "efficiency": 1.6
            }},
            "description": "鞭毛从2根进化到4根，长度12微米，游动效率提升60%"
        }},
        {{
            "category": "metabolic",
            "type": "渗透压调节蛋白",
            "parameters": {{
                "efficiency": 1.8,
                "salt_tolerance_ppt": 45
            }},
            "description": "高效渗透压调节蛋白，耐受盐度45ppt"
        }}
    ]
}}

只返回JSON，无需任何解释。
""",
}

