"""地形演化 AI Prompt"""

TERRAIN_EVOLUTION_PROMPT = """你是地质演化专家。基于长期地质过程分析地形变化。

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
  "analysis": "30-50字简要分析",
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

=== 地质规则 ===
火山:2-3回合|造山:4-6回合|冰川:3-5回合|侵蚀:持续性|沙漠化:2-3回合
**演化频率**：每回合必须对至少1-2个候选区域产生地形变化（50万年足以产生显著地质效应）。
**板块阶段优先**：优先选择阶段推荐的变化类型（聚合期造山、裂谷期下沉、漂移期侵蚀、汇聚期火山）。
**new_changes不可为空**：至少选择1个候选区域进行变化。
"""

