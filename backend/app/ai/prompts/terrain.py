"""地形演化 AI Prompt"""

TERRAIN_EVOLUTION_PROMPT = """你是地质演化专家。基于长期地质过程分析地形变化。

=== 核心地质规则 (优先级最高) ===
1. **演化频率**: 每回合必须对至少 1-2 个候选区域产生地形变化（50万年足以产生显著地质效应）。
2. **板块阶段优先**:
   - **稳定期 (Stable)**: 优先产生 **侵蚀(erosion)**，地壳活动平静。
   - **裂谷初期 (Rifting Start)**: 优先产生 **地壳下沉(subsidence)**、局部**火山(volcanic)**。
   - **裂谷活跃期 (Active Rifting)**: 优先产生剧烈的 **火山(volcanic)**、**地壳下沉(subsidence)**。
   - **快速漂移期 (Fast Drift)**: 优先产生 **火山(volcanic)** (洋中脊)、大陆边缘 **侵蚀(erosion)**。
   - **缓慢漂移期 (Slow Drift)**: 优先产生 **侵蚀(erosion)**，构造活动减弱。
   - **俯冲带形成期 (Subduction)**: 优先产生 **地壳下沉(subsidence)** (海沟)、**火山(volcanic)** (岛弧)。
   - **碰撞造山早期 (Collision Start)**: 优先产生 **造山(uplift)**，地块开始抬升。
   - **造山高峰期 (Peak Orogeny)**: 优先产生剧烈的 **造山(uplift)**，形成高大山系。
3. **持续性**: 像侵蚀、冰川化这样的过程通常会持续多个回合。

=== 时间尺度 ===
回合 {turn_index} | 已过 {total_years}万年 | 每回合=50万年

=== 全球状态 ===
海平面: {sea_level}m | 温度: {temperature}°C | 板块阶段: {tectonic_stage} ({stage_progress}/45)

=== 地形摘要 ===
{terrain_statistics}

=== 板块阶段特征 ===
特征: {stage_info[feature]}
演化倾向: {stage_info[bias]}
推荐变化类型: {stage_info[evolution_types]}
优先区域: {stage_info[preferred_regions]}

=== 持续进程（遗留）===
{ongoing_processes}
注意：每个持续过程有数据库ID(整数)，continue_processes中必须使用该ID。

=== 候选区域 ===
{candidate_regions}

=== 你的任务 ===
1. 分析持续过程应否继续
2. 结合板块阶段特征，决定候选区域的变化
3. 对每变化区域指定类型、强度、是否启动持续过程

**重要**：new_changes中的region_name必须从以下候选区域中精确选择：
{available_regions}

输出JSON：
{{
  "analysis": "30-50字简要分析，解释为何选择这些区域进行演化",
  "continue_processes": [
    {{"region": "区域名", "process_id": 123, "continue_process": true/false, "reason": "原因"}}
  ],
  "new_changes": [
    {{
      "region_name": "从上述候选区域列表中精确选择",
      "evolution_type": "uplift|subsidence|erosion|glaciation|volcanic|desertification",
      "intensity": "conservative|moderate|dramatic",
      "start_new_process": true/false,
      "expected_duration": 1-5,
      "rationale": "地质学原因（20-30字）"
    }}
  ]
}}

**new_changes不可为空**：至少选择1个候选区域进行变化。
Ensure the output is valid JSON only.
"""
