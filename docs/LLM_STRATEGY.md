# LLM 集成与演化策略文档

本文档详细说明了 EvoSandbox 中大语言模型 (LLM) 的使用场景、消耗估算以及核心的节省算力的分层演化策略。

## 1. LLM 功能模块概览

系统采用混合架构，LLM 仅在关键节点介入。以下是按 **Token 消耗量 (从高到低)** 排列的核心功能模块。

| 排名 | 功能模块 (Service) | 对应 Key | 默认模型 | 预估 Token/次 | 触发频率 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **SpeciationService** (物种分化) | `speciation` | **GPT-4o-mini** | **2k - 4k** | 仅在分化事件触发时 |
| 2 | **ReportBuilder** (回合叙事) | `turn_report` | Local (Template) | 1k - 3k | 每回合一次 |
| 3 | **TerrainEvolutionService** (地形) | `terrain_evolution` | Local / Custom | 1k - 2k | 每回合一次 |
| 4 | **FocusBatchProcessor** (焦点推演) | `focus_batch` | Local (Template) | ~1k / batch | 每回合 N 次 (取决于 Focus 数量) |
| 5 | **SpeciesGenerator** (初始生成) | `species_generation` | **GPT-4o-mini** | 500 - 1k | 仅游戏开始或手动生成时 |
| 6 | **CriticalAnalyzer** (关键分析) | `critical_detail` | Local (Template) | ~300 | 按需触发 |

---

### 1.1 详细模块说明与 Prompt 范例

#### 🧬 1. 物种分化 (SpeciationService)
系统中最昂贵但也最核心的功能。它负责"创造"新物种，需要返回包含器官、基因、数值变化的复杂 JSON 结构。

*   **文件位置**: `backend/app/services/speciation.py`
*   **任务**: 基于父系特征、环境压力和幸存者数量，生成新物种。
*   **输入范例**:
    ```text
    【父系物种】
    代码: A1 | 学名: Protoflagella primus
    描述: 原始单细胞生物，依靠双鞭毛在浅海游动...
    
    【演化环境】
    环境压力: 8.5/10 (主要: 极端干旱)
    幸存者: 1,240 | 分化类型: 生态隔离
    地形变化: 海平面下降导致浅海干涸，形成高盐度泻湖。
    ```

#### 📜 2. 回合叙事报告 (ReportBuilder)
将模拟数据转化为类似《文明》或《群星》的游戏报告。

*   **文件位置**: `backend/app/services/report_builder.py`
*   **任务**: 阅读全回合统计数据，生成史诗感中文战报。
*   **输入范例**:
    ```text
    [环境摘要]
    回合: 125 | 全球气温: 28°C (+2°C) | 海平面: +15m
    
    [物种动态]
    - A1: 死亡 45,000 (热压力), 幸存 120,000
    - B2: 灭绝 (被捕食压力过大)
    
    [事件摘要]
    - 1 次物种分化事件 | 1 次火山喷发
    ```

#### 🗺️ 3. 地形演化 (TerrainEvolutionService)
决定地图板块运动与气候对地形的重塑。

*   **文件位置**: `backend/app/services/terrain_evolution.py`
*   **任务**: 分析地质阶段（如"板块碰撞期"），决定造山或沉降区域。
*   **输入范例**:
    ```text
    === 全球状态 ===
    回合: 50 | 板块阶段: 碰撞期 | 进度: 35/45
    
    === 候选区域 ===
    1. Region_A (原浅海): 位于板块交界处
    2. Region_B (平原): 长期受河流侵蚀
    
    === 任务 ===
    请决定上述候选区域的地质变化类型与强度。
    ```

#### 🔍 4. 焦点批次推演 (FocusBatchProcessor)
为了节省算力，系统将物种分批次发送给 LLM 进行简短生存分析。

*   **文件位置**: `backend/app/services/focus_processor.py`
*   **任务**: 对一批（如 8 个）物种进行简评，解释存活或死亡原因。
*   **输入范例**:
    ```text
    【批次数据】
    1. 物种 A1: 生产者, 死亡率 15%, 主要压力: 竞争
    2. 物种 B2: 消费者, 死亡率 80%, 主要压力: 饥饿
    
    【分析任务】
    为每个物种生成 80-120 字生态分析。
    ```

---

## 2. 三级演化分层策略 (Tiering Strategy)

为了在"无限多样性"与"有限算力"之间取得平衡，系统实现了严格的 **三级演化策略**。

### 2.1 架构设计
逻辑位于 `backend/app/services/tiering.py`。

#### 🥇 Level 1: Critical (关注层 / 主角)
*   **定义**: 玩家手动标记 (Watchlist) 或极度濒危/霸主级物种。
*   **处理**: 获得 **最详细** 的单体 AI 分析 (CriticalAnalyzer)。
*   **限制**: 通常锁定为 3-5 个。

#### 🥈 Level 2: Focus (重点层 / 配角)
*   **定义**: 生态强度 (Ecological Strength) 排名靠前的物种（核心生产者、掠食者）。
*   **处理**: 采用 **批量 AI 处理** (FocusBatchProcessor)。
*   **规模**: 覆盖 20-30 个核心物种。

#### 🥉 Level 3: Background (背景层 / 群演)
*   **定义**: 种群庞大但关注度低，或新生物种。
*   **处理**: **完全不使用 LLM**。仅依靠数值规则 (MortalityEngine) 模拟。
*   **规模**: 剩余所有物种。

### 2.2 自动分级算法
系统基于 **生态强度评分 (Ecological Strength Score)** 动态调整分级：

```python
Score = (营养级权重 * 基础分) + (种群规模对数分) + (濒危保护分) + (特殊角色分) + (玩家关注分)
```

*   **营养级权重**: 顶级掠食者 (T5) 权重最高，生产者 (T1) 较低。
*   **濒危保护**: 种群 < 10,000 时获得额外加分（保护稀有物种）。
*   **玩家关注**: Watchlist 中的物种获得巨大加分，强制进入 Critical 层。

### 2.3 动态流转
*   **晋升 (Promotion)**: 背景物种因环境机遇种群暴涨 -> 晋升为 Focus。
*   **降级 (Demotion)**: 霸主没落且不再被关注 -> 降级为 Background。
*   **重现 (Reemergence)**: 大灭绝后，系统会从 Background 中筛选高基因多样性的幸存者，强行晋升为 Focus 以填补生态位。

---

## 3. 配置与优化建议

### 3.1 调整算力消耗
在 `backend/app/core/config.py` 中配置：

```python
class Settings(BaseSettings):
    # 每一批处理多少个 Focus 物种
    focus_batch_size: int = 8
    
    # 每回合最多处理多少批 Focus 物种 (总数 = size * limit)
    # 调低此值可显著减少 Token 消耗
    focus_batch_limit: int = 3 
```

### 3.2 模型路由
在 `backend/app/ai/model_router.py` 或 `.env` 中可针对不同功能指定模型：
*   建议 `speciation` 使用最强模型 (GPT-4 / Claude 3.5 Sonnet) 以保证生物学合理性。
*   `turn_report` 和 `focus_batch` 可使用廉价模型 (GPT-4o-mini / Haiku) 或本地模型。

