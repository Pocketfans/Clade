# 植物演化系统开发方案

## 概述

本文档描述了双轨制演化系统的设计方案，使游戏能够真正演化出植物，从28亿年前的原核光合生物逐步发展到多细胞陆地植物。

### 设计目标

1. **双轨并行**：动物演化路径基本不动，植物走独立系统
2. **阶段递进**：模拟真实的植物演化史
3. **里程碑驱动**：关键节点有成就和叙事
4. **Embedding增强**：使用向量预测提高演化智能性
5. **与现有系统兼容**：通过结构化字段+关键词回退

---

## 一、核心架构

```
                    ┌─────────────────────────────────┐
                    │         物种演化触发            │
                    └───────────────┬─────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │  判定演化路径类型  │
                          │  (trophic_level)  │
                          └────────┬──────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
     ┌────────▼────────┐                     ┌──────────▼──────────┐
     │  T >= 2.0       │                     │  T < 2.0            │
     │  动物演化路径   │                     │  植物演化路径       │
     │  (现有系统)     │                     │  (新系统)           │
     └────────┬────────┘                     └──────────┬──────────┘
              │                                         │
     ┌────────▼────────┐                     ┌──────────▼──────────┐
     │ 动物特质系统    │                     │ 植物特质系统        │
     │ 动物器官系统    │                     │ 植物器官系统        │
     │ 动物Prompt      │                     │ 植物Prompt          │
     └─────────────────┘                     └─────────────────────┘
```

---

## 二、植物分类与演化阶段

### 2.1 植物生命形式（Plant Life Form）

| 阶段 | 英文 | 说明 | 典型代表 | 最早出现 |
|------|------|------|----------|----------|
| 0 | prokaryotic | 原核光合生物 | 蓝藻、光合细菌 | 28亿年前 |
| 1 | unicellular | 单细胞真核藻类 | 绿藻、硅藻 | 20亿年前 |
| 2 | colonial | 群体/丝状藻类 | 团藻、水绵 | 10亿年前 |
| 3 | bryophyte | 苔藓类（无根） | 苔藓、地衣 | 4.5亿年前 |
| 4 | pteridophyte | 蕨类（有根无种子） | 蕨类、石松 | 4亿年前 |
| 5 | gymnosperm | 裸子植物（有种子） | 松、杉、银杏 | 3亿年前 |
| 6 | angiosperm | 被子植物（有花） | 草、花、阔叶树 | 1.3亿年前 |

### 2.2 生长形式（Growth Form）

| 类型 | 说明 | 与生命形式关系 |
|------|------|----------------|
| aquatic | 水生 | 阶段0-2必须为此 |
| moss | 苔藓状 | 阶段3 |
| herb | 草本 | 阶段4-6 |
| shrub | 灌木 | 阶段5-6 |
| tree | 乔木 | 阶段5-6，需木质化程度>7 |

---

## 三、数据模型扩展

### 3.1 Species模型新增字段

```python
class Species(SQLModel, table=True):
    # ... 现有字段 ...
    
    # 植物专属字段（仅当 trophic_level < 2.0 时有效）
    life_form_stage: int = Field(default=0)  # 0-6，对应演化阶段
    growth_form: str = Field(default="aquatic")  # aquatic/moss/herb/shrub/tree
    achieved_milestones: list[str] = Field(default=[], sa_column=Column(JSON))
```

---

## 四、植物特质系统

### 4.1 新增植物专属特质

```python
PLANT_TRAITS = {
    # 光合与代谢
    "光合效率": 5.0,       # 光能转化效率（替代动物的"运动能力"）
    "固碳能力": 5.0,       # CO2固定效率
    
    # 水分与养分
    "根系发达度": 0.0,     # 0=无根, 10=发达根系（陆生必需）
    "保水能力": 3.0,       # 水分保持（登陆必需）
    "养分吸收": 5.0,       # 土壤养分利用
    
    # 结构与繁殖
    "多细胞程度": 1.0,     # 1=单细胞, 10=复杂组织分化
    "木质化程度": 0.0,     # 0=无, 10=完全木质化（成为树木必需）
    "种子化程度": 0.0,     # 0=孢子繁殖, 10=完全种子繁殖
    "散布能力": 3.0,       # 孢子/种子传播范围
    
    # 防御与适应
    "化学防御": 3.0,       # 毒素、单宁等（替代动物的"攻击性"）
    "物理防御": 3.0,       # 刺、硬壳等（替代动物的"防御性"）
}
```

### 4.2 特质替换映射

当检测到植物时，部分动物特质会被替换：

| 动物特质 | 植物替换 | 说明 |
|----------|----------|------|
| 运动能力 | 光合效率 | 植物不需要移动，需要高效光合 |
| 攻击性 | 化学防御 | 植物通过化学物质防御 |
| 社会性 | 散布能力 | 植物通过繁殖体扩散 |
| 防御性 | 物理防御 | 保留概念但换名称 |

---

## 五、植物器官系统

### 5.1 植物器官类别

```python
PLANT_ORGAN_CATEGORIES = {
    # 光合器官
    "photosynthetic": {
        "原始色素体": {"efficiency": 0.5, "stage": 0},
        "叶绿体": {"efficiency": 1.0, "stage": 1},
        "类囊体膜": {"efficiency": 1.5, "stage": 2},
        "原始叶片": {"efficiency": 2.0, "stage": 3},
        "真叶": {"efficiency": 3.0, "stage": 4},
    },
    
    # 根系
    "root_system": {
        "假根": {"depth_cm": 0.5, "absorption": 0.3, "stage": 3},
        "原始根": {"depth_cm": 5, "absorption": 0.5, "stage": 4},
        "须根系": {"depth_cm": 30, "absorption": 0.8, "stage": 5},
        "直根系": {"depth_cm": 100, "absorption": 1.0, "stage": 5},
    },
    
    # 茎/支撑
    "stem": {
        "匍匐茎": {"height_cm": 1, "support": 0.2, "stage": 3},
        "草本茎": {"height_cm": 50, "support": 0.5, "stage": 4},
        "木质茎": {"height_cm": 500, "support": 1.0, "stage": 5},
        "乔木干": {"height_cm": 3000, "support": 2.0, "stage": 6},
    },
    
    # 繁殖器官
    "reproductive": {
        "孢子囊": {"dispersal_km": 0.1, "stage": 3},
        "球果": {"dispersal_km": 0.5, "stage": 5},
        "花/果实": {"dispersal_km": 5, "stage": 6},
    },
    
    # 保护结构
    "protection": {
        "粘液层": {"uv_resist": 0.5, "drought_resist": 0.3, "stage": 0},
        "细胞壁加厚": {"uv_resist": 0.8, "drought_resist": 0.5, "stage": 2},
        "角质层": {"uv_resist": 1.0, "drought_resist": 0.8, "stage": 3},
        "蜡质表皮": {"uv_resist": 1.5, "drought_resist": 1.0, "stage": 4},
    },
}
```

---

## 六、演化里程碑系统

### 6.1 里程碑定义

```python
PLANT_MILESTONES = {
    # 阶段升级里程碑
    "first_eukaryote": {
        "name": "真核化",
        "from_stage": 0, "to_stage": 1,
        "requirements": {"多细胞程度": 1.5},
        "unlock_traits": ["叶绿体"],
        "narrative": "生命史上的重大飞跃：真核细胞的诞生"
    },
    "first_multicellular": {
        "name": "多细胞化",
        "from_stage": 1, "to_stage": 2,
        "requirements": {"多细胞程度": 3.0},
        "unlock_organs": ["类囊体膜"],
        "narrative": "细胞开始协作，形成原始组织"
    },
    "first_land_plant": {
        "name": "植物登陆",
        "from_stage": 2, "to_stage": 3,
        "requirements": {"保水能力": 5.0, "耐旱性": 4.0},
        "unlock_organs": ["假根", "角质层"],
        "achievement": "开荒先锋",
        "narrative": "生命征服陆地的第一步"
    },
    "first_true_root": {
        "name": "真根演化",
        "from_stage": 3, "to_stage": 4,
        "requirements": {"根系发达度": 5.0},
        "unlock_organs": ["原始根", "维管束"],
        "narrative": "根系深入土壤，植物真正站稳陆地"
    },
    "first_seed": {
        "name": "种子革命",
        "from_stage": 4, "to_stage": 5,
        "requirements": {"种子化程度": 5.0},
        "unlock_organs": ["球果"],
        "narrative": "种子诞生，植物摆脱对水的繁殖依赖"
    },
    "first_flower": {
        "name": "开花时代",
        "from_stage": 5, "to_stage": 6,
        "requirements": {"种子化程度": 8.0, "散布能力": 7.0},
        "unlock_organs": ["花/果实"],
        "achievement": "繁花似锦",
        "narrative": "被子植物登场，与昆虫共同演化"
    },
    
    # 形态里程碑
    "first_tree": {
        "name": "首棵树木",
        "requirements": {"木质化程度": 7.0, "life_form_stage": 5},
        "unlock_organs": ["乔木干"],
        "achievement": "参天巨木",
        "narrative": "森林的奠基者诞生"
    },
}
```

---

## 七、Embedding集成架构

### 7.1 新增向量索引

```python
# 向量索引扩展
- plants: 植物物种向量索引
- plant_stages: 阶段原型向量
- plant_milestones: 里程碑向量
```

### 7.2 PlantReferenceLibrary（植物参考向量库）

核心功能：
1. 存储各演化阶段的原型向量
2. 存储里程碑事件的语义向量
3. 提供压力-适应映射向量
4. 支持跨物种的演化模式匹配

### 7.3 PlantEvolutionPredictor（植物演化预测器）

核心功能：
1. 基于压力向量预测特质变化
2. 评估阶段升级准备度
3. 生成演化提示供AI使用
4. 追踪演化历史模式

---

## 八、Prompt模板

### 8.1 植物分化Prompt

```
你是古植物学专家，为分化的植物物种设计新特征。

=== 亲本植物 ===
{parent_info}

=== 当前环境压力 ===
{pressure_context}

=== 【Embedding预测参考】===
{embedding_context}

=== 分化规则 ===
1. 【参考预测】优先考虑Embedding预测的特质变化方向
2. 【阶段约束】如果接近里程碑，可以触发阶段升级
3. 【参考物种】可以借鉴相似物种的成功适应模式
4. 【能量守恒】特质变化总和在 [-2.0, +3.0]
5. 【权衡机制】增强某特质时，需要其他特质作为代价
```

---

## 九、文件修改清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `models/species.py` | 新增字段 | life_form_stage, growth_form, achieved_milestones |
| `services/species/trait_config.py` | 新增配置 | PLANT_TRAITS, 特质映射 |
| `services/species/speciation.py` | 新增方法 | _process_plant_speciation(), 路径判定 |
| `ai/prompts/plant.py` | **新建** | 植物专属Prompt模板 |
| `services/species/plant_evolution.py` | **新建** | 植物演化核心逻辑 + 里程碑 |
| `services/species/plant_reference_library.py` | **新建** | 植物参考向量库 |
| `services/species/plant_evolution_predictor.py` | **新建** | 植物演化预测器 |
| `services/system/embedding.py` | 扩展 | 新增植物索引 |
| `services/analytics/embedding_integration.py` | 扩展 | 集成植物服务 |
| `services/geo/vegetation_cover.py` | 修改 | 使用结构化字段判定 |
| `core/seed.py` | 修改 | 初始物种添加植物字段 |

---

## 十、实现优先级

| 阶段 | 内容 | 预估工作量 |
|------|------|------------|
| P1 | Species模型扩展 + 路径判定 | 0.5天 |
| P2 | 植物特质系统 + 特质映射 | 0.5天 |
| P3 | 植物Prompt模板 | 0.5天 |
| P4 | plant_evolution.py 核心逻辑 | 1天 |
| P5 | 里程碑系统 | 0.5天 |
| P6 | PlantReferenceLibrary | 0.5天 |
| P7 | PlantEvolutionPredictor | 0.5天 |
| P8 | Embedding集成 | 0.5天 |
| P9 | 植被覆盖联动 | 0.5天 |

**总计：约 4-5 天**

---

## 十一、示例演化流程

```
回合0: 海洋微藻 (A1)
├── life_form_stage: 1 (单细胞真核)
├── growth_form: aquatic
├── 特质: 光合效率=5, 多细胞程度=1
└── 器官: 叶绿体

回合10: 压力"浅海养分竞争加剧"
├── AI判定: 增加多细胞程度有利于竞争
├── 多细胞程度: 1 → 3.2
├── 触发里程碑: "多细胞化"
└── 新物种: 原始丝藻 (A2), life_form_stage=2

回合30: 压力"潮间带干湿交替"
├── 物种 A2-1 在潮间带受压
├── AI判定: 发展保水能力应对潮间带
├── 保水能力: 3 → 5.5, 耐旱性: 3 → 4.2
├── 新器官: 角质层
├── 触发里程碑: "植物登陆" 🎉
├── 成就解锁: "开荒先锋"
└── 新物种: 原始苔 (A3), life_form_stage=3, growth_form=moss

回合50: 地块覆盖变化
├── A3种群在陆地地块扩张
├── 植被密度达到阈值
└── 地块覆盖: 裸地 → 苔原 ✅
```

