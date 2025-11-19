# Prompt 工程优化与模型推荐指南

本文档分析了当前后端各模块的 Prompt 设计，指出了潜在的优化空间，并根据任务类型推荐了最适合的 LLM 模型。

## 1. Prompt 优化分析与建议

### 1.1 通用优化建议 (所有模块)
*   **强制 JSON 模式**: 目前部分 Prompt 仅文字要求返回 JSON。建议在 API 调用层强制开启 `response_format={"type": "json_object"}`，并在 Prompt 结尾再次强调 "Ensure the output is valid JSON only."。
*   **One-Shot 示例**: `species_generation` 和 `speciation` 缺乏具体的 JSON 示例。提供一个完整的 One-shot 示例可以显著降低格式错误率。

### 1.2 模块级具体建议

#### 🧬 物种分化 (SpeciationService)
*   **现状**: Prompt 极其复杂，包含属性权衡、数值计算、命名规则等大量硬约束。代码中包含了大量兜底逻辑（如 `_clamp_traits_to_limit`）来修补 LLM 的数值错误。
*   **优化点**:
    1.  **数值解耦**: 不要让 LLM 做加减法（如 " trait: +2.0"）。改为让 LLM 只输出 **趋势描述**（"significantly increased"）和 **大概幅度**（1-10），具体的数值计算交给 Python 代码完成。LLM 擅长定性，不擅长定量。
    2.  **命名分离**: 命名规则非常复杂（拉丁词根等）。可以考虑将其拆分为两个步骤，或者让 LLM 只提供词根，由代码组合生成学名。
    3.  **思维链 (CoT)**: 增加 `reasoning` 字段，要求 LLM 先解释分化逻辑，再生成数值，可以提高逻辑一致性。

#### 🗺️ 地形演化 (TerrainEvolutionService)
*   **现状**: 需要基于板块阶段和地质规则进行推理。
*   **优化点**:
    1.  **规则前置**: 将"地质规则"部分提到 Prompt 最前面，作为 System Message 的核心部分。
    2.  **示例增强**: 提供一个"板块碰撞期 -> 造山运动"的具体推理示例。

#### 📜 叙事生成 (ReportBuilder)
*   **现状**: 纯文本生成，约束较少。
*   **优化点**:
    1.  **结构化标记**: 强制要求使用 Markdown 标题（如 `### 环境解析`）来分隔段落，方便前端解析和展示。
    2.  **风格控制**: 增加具体语气词的示例（如"沧海桑田"、"大灭绝"），增强史诗感。

---

## 2. LLM 模型选型推荐

根据任务的性质（创意写作 vs 逻辑推理），推荐使用不同的模型以获得最佳效果。

### 2.1 🧠 逻辑与数值核心 (Logic & Math)
**适用模块**: `SpeciationService`, `TerrainEvolutionService`, `SpeciesGenerator`
**任务特点**: 复杂的 JSON 结构、数值约束、逻辑推理、规则遵循。

| 推荐模型 | 理由 | 适用性 |
| :--- | :--- | :--- |
| **GPT-4o** | 目前指令遵循能力(Instruction Following)最强的模型，极少出现 JSON 格式错误或数值幻觉。 | ⭐⭐⭐⭐⭐ (首选) |
| **Claude 3.5 Sonnet** | 逻辑推理能力极强，且生成的生物学描述非常自然、专业。 | ⭐⭐⭐⭐⭐ (强力推荐) |
| **DeepSeek-V3** | 开源界最强逻辑模型，性价比极高，非常适合处理复杂的结构化数据。 | ⭐⭐⭐⭐ (高性价比) |

### 2.2 ✍️ 创意与叙事 (Creative Writing)
**适用模块**: `ReportBuilder` (Turn Report), `CriticalAnalyzer` (Critical Detail)
**任务特点**: 需要文采、史诗感、连贯性，对数值精确度要求不高。

| 推荐模型 | 理由 | 适用性 |
| :--- | :--- | :--- |
| **Claude 3.5 Sonnet** | 文笔优美，擅长模拟特定语气（如"严肃的演化生态学家"），比 GPT 更具"人味"。 | ⭐⭐⭐⭐⭐ (最佳文笔) |
| **GPT-4o** | 表现稳定，中规中矩。 | ⭐⭐⭐⭐ |
| **Qwen-2.5-72B** | 中文写作能力极强，非常适合生成中文战报。 | ⭐⭐⭐⭐ (中文最佳) |

### 2.3 ⚡ 高频批处理 (High Throughput)
**适用模块**: `FocusBatchProcessor` (Focus Batch)
**任务特点**: 任务简单、重复性高、调用量大，对成本和延迟敏感。

| 推荐模型 | 理由 | 适用性 |
| :--- | :--- | :--- |
| **GPT-4o-mini** | 速度极快，成本极低，足以处理简单的文本摘要任务。 | ⭐⭐⭐⭐⭐ (最佳性价比) |
| **Claude 3 Haiku** | 速度最快，适合实时性要求高的场景。 | ⭐⭐⭐⭐ |

---

## 3. 总结行动建议

1.  **立即行动**: 为所有 JSON 输出的 Prompt 添加 One-shot 示例（特别是物种生成）。
2.  **配置分离**: 在 `.env` 中配置不同的模型路由：
    *   `SPECIATION_MODEL=gpt-4o`
    *   `NARRATIVE_MODEL=claude-3-5-sonnet`
    *   `BATCH_MODEL=gpt-4o-mini`
3.  **代码减负**: 考虑简化 `speciation.py` 中的 Prompt，移除复杂的数值计算要求，改为让 AI 输出"变化等级(1-5)"，由代码映射为具体数值。

