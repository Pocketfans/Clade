from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence, Callable, Awaitable, Any

from ...models.species import LineageEvent, Species
from ...ai.model_router import staggered_gather

logger = logging.getLogger(__name__)
from ...repositories.genus_repository import genus_repository
from ...repositories.species_repository import species_repository
from ...schemas.responses import BranchingEvent
from .gene_library import GeneLibraryService
from .genetic_distance import GeneticDistanceCalculator
from .trait_config import TraitConfig
from .trophic import TrophicLevelCalculator
from ...core.config import get_settings

# 获取配置
_settings = get_settings()


class SpeciationService:
    """根据存活数据和演化潜力，生成新的谱系并记录事件。"""

    def __init__(self, router) -> None:
        self.router = router
        self.trophic_calculator = TrophicLevelCalculator()
        self.genetic_calculator = GeneticDistanceCalculator()
        self.gene_library_service = GeneLibraryService()
        self.max_speciation_per_turn = 20
        self.max_deferred_requests = 60
        self._deferred_requests: list[dict[str, Any]] = []

    async def process_async(
        self,
        mortality_results,
        existing_codes: set[str],
        average_pressure: float,
        turn_index: int,
        map_changes: list = None,
        major_events: list = None,
        pressures: Sequence = None,  # 新增：ParsedPressure 列表
        trophic_interactions: dict[str, float] = None,  # 新增：营养级互动信息
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> list[BranchingEvent]:
        """处理物种分化 (异步并发版)"""
        import random
        import math
        
        # 保存营养级互动信息，供后续使用
        self._current_trophic_interactions = trophic_interactions or {}
        
        # 提取压力描述摘要
        pressure_summary = "无显著环境压力"
        if pressures:
            # 使用 set 去重描述，避免重复
            narratives = sorted(list(set(p.narrative for p in pressures)))
            pressure_summary = "; ".join(narratives)
        elif major_events:
            pressure_summary = "重大地质/气候变迁"
        elif average_pressure > 5.0:
            pressure_summary = f"高环境压力 ({average_pressure:.1f}/10)"
        
        # 生成食物链状态描述（用于AI）
        self._food_chain_summary = self._summarize_food_chain_status(trophic_interactions)
        
        # 动态分化限制 (Dynamic Speciation Limiting)
        # 【优化】收紧限制，依赖淘汰机制来控制物种数量
        current_species_count = len(mortality_results)
        # 软上限从配置读取，默认40
        soft_cap = _settings.species_soft_cap
        density_damping = 1.0 / (1.0 + max(0, current_species_count - soft_cap) / float(soft_cap))
        
        # 1. 准备阶段：筛选候选并生成任务
        entries: list[dict[str, Any]] = []
        
        for result in mortality_results:
            species = result.species
            # 【关键修复】使用当前种群（繁殖增长后），而不是死亡率评估时的 survivors
            # mortality_results 是在繁殖增长之前生成的，survivors 是过时的数据
            # species.morphology_stats["population"] 是繁殖增长后的最新值
            current_population = int(species.morphology_stats.get("population", 0) or 0)
            survivors = current_population  # 使用最新种群数据
            death_rate = result.death_rate
            resource_pressure = result.resource_pressure
            
            # 条件1：计算该物种的动态分化门槛
            base_threshold = self._calculate_speciation_threshold(species)
            min_population = int(base_threshold * 1.6)
            
            if current_population < min_population:
                continue
            
            # 条件2：演化潜力（放宽门槛 + 累积压力补偿）
            # 【修复】默认值从0.0改为0.5，门槛从0.7降到0.5
            evo_potential = species.hidden_traits.get("evolution_potential", 0.5)
            speciation_pressure = species.morphology_stats.get("speciation_pressure", 0.0) or 0.0
            
            # 【新增】分化冷却期检查：刚分化出的物种需要"稳定期"才能继续分化
            # 冷却期从配置读取，默认3回合（150万年）
            cooldown = _settings.speciation_cooldown_turns
            last_speciation_turn = species.morphology_stats.get("last_speciation_turn", -999)
            turns_since_speciation = turn_index - last_speciation_turn
            if turns_since_speciation < cooldown:
                logger.debug(
                    f"[分化冷却] {species.common_name} 仍在冷却期 "
                    f"({turns_since_speciation}/3回合)"
                )
                continue
            
            # 放宽条件：演化潜力≥0.5，或者累积了足够的分化压力（连续多回合满足其他条件）
            if evo_potential < 0.5 and speciation_pressure < 0.3:
                continue
            
            # 条件3：压力或资源饱和
            has_pressure = (1.5 <= average_pressure <= 15.0) or (resource_pressure > 0.8)
            
            # 自然辐射演化（繁荣物种分化）
            # 【修复】提高辐射演化概率，让繁荣物种更容易分化
            if not has_pressure:
                # 种群规模加成：种群越大，辐射演化概率越高
                pop_factor = min(1.0, survivors / (min_population * 3))
                # 累积压力加成：连续满足条件但未分化的物种更容易辐射演化
                radiation_chance = 0.03 + (pop_factor * 0.05) + (speciation_pressure * 0.2)
                
                if survivors > min_population * 1.5 and random.random() < radiation_chance:
                    has_pressure = True
                    speciation_type = "辐射演化"
                    logger.info(f"[辐射演化] {species.common_name} 触发辐射演化 (种群:{survivors:,}, 概率:{radiation_chance:.1%})")
                else:
                    continue
            
            # 条件4：适应压力（扩大死亡率窗口）
            # 【修复】从5%-60%扩大到3%-70%，给繁荣物种和濒危物种更多机会
            if death_rate < 0.03 or death_rate > 0.70:
                continue
            
            # 条件5：随机性 (应用密度制约)
            # 【优化】世代时间影响分化概率，但采用更温和的曲线
            generation_time = species.morphology_stats.get("generation_time_days", 365)
            # 50万年 = 1.825亿天
            total_days = 500_000 * 365
            generations = total_days / max(1.0, generation_time)
            
            # 【调整】世代加成大幅降低，每多一个数量级只增加0.02（原0.08）
            # 这样微生物和大型动物的分化概率差距不会太大
            # 大型动物 (30年=1万代) -> log10(10000)=4 -> bonus=0.08
            # 微生物 (1天=1.8亿代) -> log10(1.8e8)=8.2 -> bonus=0.16
            generation_bonus = math.log10(max(10, generations)) * 0.02
            
            # 【调整】基础分化率从配置读取，默认0.15
            # 50万年虽长，但分化需要严格的生态隔离条件
            # 公式：(基础率 + 演化潜力加成) × 0.8 + 世代加成，再乘以密度阻尼
            base_rate = _settings.base_speciation_rate
            base_chance = ((base_rate + (evo_potential * 0.25)) * 0.8 + generation_bonus) * density_damping
            
            speciation_bonus = 0.0
            speciation_type = "生态隔离"
            
            # 检测地理隔离机会
            if map_changes:
                for change in (map_changes or []):
                    change_type = change.get("change_type", "") if isinstance(change, dict) else getattr(change, "change_type", "")
                    if change_type in ["uplift", "volcanic", "glaciation"]:
                        speciation_bonus += 0.15
                        speciation_type = "地理隔离"
                        break
            
            # 检测极端环境特化
            if major_events:
                for event in (major_events or []):
                    severity = event.get("severity", "") if isinstance(event, dict) else getattr(event, "severity", "")
                    if severity in ["extreme", "catastrophic"]:
                        speciation_bonus += 0.10
                        speciation_type = "极端环境特化"
                        break
            
            # 检测协同演化
            if result.niche_overlap > 0.4:
                speciation_bonus += 0.08
                speciation_type = "协同演化"
            
            # 【修复】将累积分化压力加入概率计算
            # 每回合满足条件但未分化的物种，下回合分化概率+10%
            speciation_chance = base_chance + speciation_bonus + speciation_pressure
            
            if random.random() > speciation_chance:
                # 【调整】分化失败时累积压力，增速降低（0.05），上限降低（0.3）
                # 这样需要6回合才能达到上限，且上限较低不会强制分化
                new_pressure = min(0.3, speciation_pressure + 0.05)
                species.morphology_stats["speciation_pressure"] = new_pressure
                species_repository.upsert(species)
                logger.debug(
                    f"[分化累积] {species.common_name} 分化失败, "
                    f"累积压力: {speciation_pressure:.1%} → {new_pressure:.1%}"
                )
                continue
            
            # 分化成功，重置累积压力，并记录分化时间（用于冷却期计算）
            species.morphology_stats["speciation_pressure"] = 0.0
            species.morphology_stats["last_speciation_turn"] = turn_index
            
            # ========== 【优化】动态子种数量（考虑物种密度） ==========
            # 决定分化出几个子种（基于种群规模和物种密度，不再依赖世代数）
            if _settings.enable_dynamic_speciation:
                # 计算同谱系物种数量（用于属内阻尼）
                sibling_count = sum(
                    1 for r in mortality_results 
                    if r.species.lineage_code.startswith(species.lineage_code[:2])  # 共享前缀
                    and r.species.lineage_code != species.lineage_code
                )
                
                num_offspring = self._calculate_dynamic_offspring_count(
                    generations, survivors, evo_potential,
                    current_species_count=current_species_count,
                    sibling_count=sibling_count
                )
                logger.info(
                    f"[分化] {species.common_name} 将分化出 {num_offspring} 个子种 "
                    f"(物种总数:{current_species_count}, 同属:{sibling_count})"
                )
            else:
                # 传统模式：固定2-3个
                num_offspring = random.choice([2, 2, 3])
                logger.info(f"[分化] {species.common_name} 将分化出 {num_offspring} 个子种")
            
            # 种群分配（保证子代获得非零种群）
            retention_ratio = random.uniform(0.60, 0.80)
            proposed_parent = max(50, int(survivors * retention_ratio))
            max_parent_allowed = survivors - num_offspring
            if max_parent_allowed <= 0:
                logger.warning(
                    f"[分化终止] {species.common_name} 幸存者不足以生成子种 "
                    f"(survivors={survivors}, offspring={num_offspring})"
                )
                continue
            
            parent_remaining = min(proposed_parent, max_parent_allowed)
            child_pool = survivors - parent_remaining
            
            if child_pool < num_offspring:
                # 借用部分亲代个体，确保每个子种至少获得1个体
                needed = num_offspring - child_pool
                transferable = max(0, parent_remaining - 50)
                if transferable <= 0:
                    logger.warning(
                        f"[分化终止] {species.common_name} 无法为子种分配个体 "
                        f"(parent_remaining={parent_remaining})"
                    )
                    continue
                borrowed = min(needed, transferable)
                parent_remaining -= borrowed
                child_pool = survivors - parent_remaining
            
            if child_pool < num_offspring:
                logger.warning(
                    f"[分化终止] {species.common_name} 子代可用个体仍不足 "
                    f"(child_pool={child_pool}, offspring={num_offspring})"
                )
                continue
            
            pop_splits = self._allocate_offspring_population(child_pool, num_offspring)
            
            # 生成编码
            new_codes = self._generate_multiple_lineage_codes(
                species.lineage_code, existing_codes, num_offspring
            )
            for code in new_codes:
                existing_codes.add(code)
            
            # 立即更新父系物种种群（保持数据库状态一致性）
            species.morphology_stats["population"] = parent_remaining
            species_repository.upsert(species)
            
            # 为每个子种创建任务
            for idx, (new_code, population) in enumerate(zip(new_codes, pop_splits)):
                # 限制 history_highlights 长度，防止 Context Explosion
                # 只取最后2个事件，且截断长度
                safe_history = []
                if species.history_highlights:
                    for event in species.history_highlights[-2:]:
                        safe_history.append(event[:80] + "..." if len(event) > 80 else event)
                
                # 推断生物类群
                biological_domain = self._infer_biological_domain(species)
                
                ai_payload = {
                    "parent_lineage": species.lineage_code,
                    "latin_name": species.latin_name,
                    "common_name": species.common_name,
                    "habitat_type": species.habitat_type,
                    "biological_domain": biological_domain,  # 新增：生物类群限制
                    "current_organs_summary": self._summarize_organs(species),  # 新增：当前器官摘要
                    "environment_pressure": average_pressure,
                    "pressure_summary": pressure_summary,
                    "evolutionary_generations": int(generations),
                    "traits": species.description,
                    "history_highlights": "; ".join(safe_history) if safe_history else "无",
                    "survivors": population,
                    "speciation_type": speciation_type,
                    "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "",
                    "major_events_summary": self._summarize_major_events(major_events) if major_events else "",
                    "parent_trophic_level": species.trophic_level,
                    "offspring_index": idx + 1,
                    "total_offspring": num_offspring,
                    # 食物链状态，帮助AI做出合理的演化决策
                    "food_chain_status": self._food_chain_summary,
                }
                
                entries.append({
                    "ctx": {
                    "parent": species,
                    "new_code": new_code,
                    "population": population,
                    "ai_payload_input": ai_payload, # 原始输入，用于fallback
                        "speciation_type": speciation_type
                    },
                    "payload": ai_payload,
                })
        
        if not entries and not self._deferred_requests:
            return []

        # 合并上回合遗留请求，并限制本回合最大任务数
        pending = self._deferred_requests + entries
        if len(pending) > self.max_deferred_requests:
            pending = pending[:self.max_deferred_requests]
        active_batch = pending[: self.max_speciation_per_turn]
        self._deferred_requests = pending[self.max_speciation_per_turn :]

        if not active_batch:
            logger.info("[分化] 没有可执行的AI任务，本回合跳过")
            return []

        logger.info(f"[分化] 开始批量处理 {len(active_batch)} 个分化任务 (剩余排队 {len(self._deferred_requests)})")
        
        # 【优化】使用批量请求 + 间隔并行，提高效率
        # 每批最多处理 10 个物种
        batch_size = 10
        
        # 分割成多个批次
        batches = []
        for batch_start in range(0, len(active_batch), batch_size):
            batch_entries = active_batch[batch_start:batch_start + batch_size]
            batches.append(batch_entries)
        
        logger.info(f"[分化] 共 {len(batches)} 个批次，开始间隔并行执行")
        
        async def process_batch(batch_entries: list) -> list:
            """处理单个批次"""
            batch_payload = self._build_batch_payload(
                batch_entries, average_pressure, pressure_summary, 
                map_changes, major_events
            )
            batch_results = await self._call_batch_ai(batch_payload, stream_callback)
            return self._parse_batch_results(batch_results, batch_entries)
        
        # 【优化】间隔并行执行批次，每3秒启动一个，最多同时2个
        coroutines = [process_batch(batch) for batch in batches]
        batch_results_list = await staggered_gather(
            coroutines,
            interval=3.0,  # 每3秒启动一个批次
            max_concurrent=2,  # 最多同时2个批次（每批10个物种）
            task_name="分化批次"
        )
        
        # 合并所有批次的结果
        results = []
        for batch_idx, batch_result in enumerate(batch_results_list):
            if isinstance(batch_result, Exception):
                logger.error(f"[分化] 批次 {batch_idx + 1} 失败: {batch_result}")
                results.extend([batch_result] * len(batches[batch_idx]))
            else:
                success_count = len([r for r in batch_result if not isinstance(r, Exception)])
                logger.info(f"[分化] 批次 {batch_idx + 1} 完成，成功解析 {success_count} 个结果")
                results.extend(batch_result)

        # 3. 结果处理与写入
        logger.info(f"[分化] 开始处理 {len(results)} 个AI结果")
        new_species_events: list[BranchingEvent] = []
        for res, entry in zip(results, active_batch):
            ctx = entry["ctx"]  # 从entry中提取ctx
            
            if isinstance(res, Exception):
                logger.error(f"[分化AI异常] {res}")
                self._queue_deferred_request(entry)
                continue

            ai_content = res
            if not isinstance(ai_content, dict):
                logger.warning(f"[分化警告] AI返回的content不是dict类型: {type(ai_content)}, 内容: {ai_content}")
                self._queue_deferred_request(entry)
                continue

            required_fields = ["latin_name", "common_name", "description"]
            if any(not ai_content.get(field) for field in required_fields):
                logger.warning(
                    "[分化警告] AI返回缺少必要字段: %s",
                    {field: ai_content.get(field) for field in required_fields},
                )
                self._queue_deferred_request(entry)
                continue

            logger.info(
                "[分化AI返回] latin_name: %s, common_name: %s, description长度: %s",
                ai_content.get("latin_name"),
                ai_content.get("common_name"),
                len(str(ai_content.get("description", ""))),
            )

            new_species = self._create_species(
                parent=ctx["parent"],
                new_code=ctx["new_code"],
                survivors=ctx["population"],
                turn_index=turn_index,
                ai_payload=ai_content,
                average_pressure=average_pressure,
            )
            logger.info(f"[分化] 新物种 {new_species.common_name} created_turn={new_species.created_turn} (传入的turn_index={turn_index})")
            new_species = species_repository.upsert(new_species)
            logger.info(f"[分化] upsert后 {new_species.common_name} created_turn={new_species.created_turn}")
            
            # ⚠️ 关键修复：子代继承父代的栖息地分布
            # 而不是重新计算分布（因为分化通常发生在同一地点）
            self._inherit_habitat_distribution(parent=ctx["parent"], child=new_species, turn_index=turn_index)
            
            self._update_genetic_distances(new_species, ctx["parent"], turn_index)
            
            if ai_content.get("genetic_discoveries") and new_species.genus_code:
                self.gene_library_service.record_discovery(
                    genus_code=new_species.genus_code,
                    discoveries=ai_content["genetic_discoveries"],
                    discoverer_code=new_species.lineage_code,
                    turn=turn_index
                )
            
            if new_species.genus_code:
                genus = genus_repository.get_by_code(new_species.genus_code)
                if genus:
                    self.gene_library_service.inherit_dormant_genes(ctx["parent"], new_species, genus)
                    species_repository.upsert(new_species)
            
            species_repository.log_event(
                LineageEvent(
                    lineage_code=ctx["new_code"],
                    event_type="speciation",
                    payload={"parent": ctx["parent"].lineage_code, "turn": turn_index},
                )
            )
            
            event_desc = ai_content.get("event_description") if ai_content else None
            if not event_desc:
                event_desc = f"{ctx['parent'].common_name}在压力{average_pressure:.1f}条件下分化出{ctx['new_code']}"
            
            reason_text = ai_content.get("reason") or ai_content.get("speciation_reason")
            if not reason_text:
                if ctx["speciation_type"] == "地理隔离":
                    reason_text = f"{ctx['parent'].common_name}因地形剧变导致种群地理隔离，各隔离群体独立演化产生生殖隔离"
                elif ctx["speciation_type"] == "极端环境特化":
                    reason_text = f"{ctx['parent'].common_name}在极端环境压力下，部分种群演化出特化适应能力，与原种群形成生态分离"
                elif ctx["speciation_type"] == "协同演化":
                    reason_text = f"{ctx['parent'].common_name}与竞争物种的生态位重叠导致竞争排斥，促使种群分化到不同资源梯度"
                else:
                    reason_text = f"{ctx['parent'].common_name}种群在演化压力下发生生态位分化"
            
            new_species_events.append(
                BranchingEvent(
                    parent_lineage=ctx["parent"].lineage_code,
                    new_lineage=ctx["new_code"],
                    description=event_desc,
                    timestamp=datetime.utcnow(),
                    reason=reason_text,
                )
            )
            
        return new_species_events

    def _build_batch_payload(
        self,
        entries: list[dict],
        average_pressure: float,
        pressure_summary: str,
        map_changes: list,
        major_events: list
    ) -> dict:
        """构建批量分化请求的 payload"""
        # 构建物种列表文本
        species_list_parts = []
        for idx, entry in enumerate(entries):
            payload = entry["payload"]
            ctx = entry["ctx"]
            
            # 获取生物类群和器官摘要（可能在单独调用时已添加）
            biological_domain = payload.get('biological_domain', 'protist')
            organs_summary = payload.get('current_organs_summary', '无已记录的器官系统')
            
            species_info = f"""
【物种 {idx + 1}】
- request_id: {idx}
- 父系编码: {payload.get('parent_lineage')}
- 学名: {payload.get('latin_name')}
- 俗名: {payload.get('common_name')}
- 新编码: {ctx['new_code']}
- 栖息地: {payload.get('habitat_type')}
- 生物类群: {biological_domain}
- 营养级: {payload.get('parent_trophic_level', 2.0):.2f}
- 描述: {payload.get('traits', '')[:200]}
- 现有器官: {organs_summary[:100]}
- 幸存者: {payload.get('survivors', 0):,}
- 分化类型: {payload.get('speciation_type')}
- 子代编号: 第{payload.get('offspring_index', 1)}个（共{payload.get('total_offspring', 1)}个）"""
            species_list_parts.append(species_info)
        
        species_list = "\n".join(species_list_parts)
        
        return {
            "average_pressure": average_pressure,
            "pressure_summary": pressure_summary,
            "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "无显著地形变化",
            "major_events_summary": self._summarize_major_events(major_events) if major_events else "无重大事件",
            "species_list": species_list,
            "batch_size": len(entries),
        }
    
    async def _call_batch_ai(
        self, 
        payload: dict, 
        stream_callback: Callable[[str], Awaitable[None] | None] | None
    ) -> dict:
        """调用批量分化 AI 接口（非流式，更稳定）"""
        # 【优化】使用非流式调用，避免流式传输卡住
        # 【修复】添加硬超时保护，防止无限等待
        import asyncio
        try:
            response = await asyncio.wait_for(
                self.router.ainvoke("speciation_batch", payload),
                timeout=120  # 批量请求给更长的超时（120秒）
            )
        except asyncio.TimeoutError:
            logger.error("[分化批量] 请求超时（120秒），跳过本批次")
            return {}
        except Exception as e:
            logger.error(f"[分化批量] 请求异常: {e}")
            return {}
        return response.get("content") if isinstance(response, dict) else {}
    
    def _parse_batch_results(
        self, 
        batch_response: dict, 
        entries: list[dict]
    ) -> list[dict | Exception]:
        """解析批量响应，返回与 entries 对应的结果列表"""
        results = []
        
        if not isinstance(batch_response, dict):
            logger.warning(f"[分化批量] 响应不是字典类型: {type(batch_response)}")
            return [ValueError("Invalid batch response")] * len(entries)
        
        # 尝试从响应中提取 results 数组
        ai_results = batch_response.get("results", [])
        if not isinstance(ai_results, list):
            # 可能响应本身就是结果数组
            if isinstance(batch_response, list):
                ai_results = batch_response
            else:
                logger.warning(f"[分化批量] 响应中没有 results 数组")
                return [ValueError("No results in response")] * len(entries)
        
        # 建立 request_id 到结果的映射
        result_map = {}
        for item in ai_results:
            if isinstance(item, dict):
                req_id = item.get("request_id")
                if req_id is not None:
                    try:
                        result_map[int(req_id)] = item
                    except (ValueError, TypeError):
                        result_map[str(req_id)] = item
        
        # 按顺序匹配结果
        for idx, entry in enumerate(entries):
            # 尝试多种方式匹配
            matched_result = result_map.get(idx) or result_map.get(str(idx))
            
            if matched_result is None and idx < len(ai_results):
                # 如果没有 request_id，按顺序匹配
                matched_result = ai_results[idx] if isinstance(ai_results[idx], dict) else None
            
            if matched_result:
                # 验证必要字段
                required_fields = ["latin_name", "common_name", "description"]
                if all(matched_result.get(f) for f in required_fields):
                    results.append(matched_result)
                    logger.debug(f"[分化批量] 成功匹配结果 {idx}: {matched_result.get('common_name')}")
                else:
                    logger.warning(f"[分化批量] 结果 {idx} 缺少必要字段")
                    results.append(ValueError(f"Missing required fields for entry {idx}"))
            else:
                logger.warning(f"[分化批量] 无法匹配结果 {idx}")
                results.append(ValueError(f"No matching result for entry {idx}"))
        
        return results

    async def _call_ai_wrapper(self, payload: dict, stream_callback: Callable[[str], Awaitable[None] | None] | None) -> dict:
        """AI调用包装器（非流式，更稳定）"""
        # 【优化】使用非流式调用，避免流式传输卡住
        # 【修复】添加硬超时保护
        import asyncio
        try:
            response = await asyncio.wait_for(
                self.router.ainvoke("speciation", payload),
                timeout=90  # 硬超时90秒
            )
        except asyncio.TimeoutError:
            logger.error("[分化] 单个请求超时（90秒）")
            return {}
        except Exception as e:
            logger.error(f"[分化] 请求异常: {e}")
            return {}
        return response.get("content") if isinstance(response, dict) else {}

    # 保留 process 方法以兼容旧调用，直到全部迁移
    def process(self, *args, **kwargs):
        logger.warning("Deprecated: calling synchronous process(). Use process_async() instead.")
        # 临时实现：抛出错误提示修改，或者用 asyncio.run (不推荐在已有循环中)
        # 由于我们是一次性重构，可以假设不会再调用同步版，或者如果调用了说明漏改了
        raise NotImplementedError("Use process_async instead")

    def _queue_deferred_request(self, entry: dict[str, Any]) -> None:
        """将失败的AI请求放回队列，供下一回合重试。"""
        if len(self._deferred_requests) >= self.max_deferred_requests:
            return
        self._deferred_requests.append(entry)

    def _next_lineage_code(self, parent_code: str, existing_codes: set[str]) -> str:
        """生成单个子代编码（保留用于向后兼容）"""
        base = f"{parent_code}a"
        idx = 1
        new_code = f"{base}{idx}"
        while new_code in existing_codes:
            idx += 1
            new_code = f"{base}{idx}"
        return new_code
    
    def _generate_multiple_lineage_codes(
        self, parent_code: str, existing_codes: set[str], num_offspring: int
    ) -> list[str]:
        """生成多个子代编码，使用字母后缀 (A1→A1a, A1b, A1c)
        
        Args:
            parent_code: 父代编码 (如 "A1")
            existing_codes: 已存在的编码集合
            num_offspring: 需要生成的子代数量
            
        Returns:
            子代编码列表 (如 ["A1a", "A1b", "A1c"])
        """
        letters = "abcdefghijklmnopqrstuvwxyz"
        codes = []
        
        for i in range(num_offspring):
            letter = letters[i]
            new_code = f"{parent_code}{letter}"
            
            # 如果编码已存在，添加数字后缀
            if new_code in existing_codes:
                idx = 1
                while f"{new_code}{idx}" in existing_codes:
                    idx += 1
                new_code = f"{new_code}{idx}"
            
            codes.append(new_code)
        
        return codes
    
    def _allocate_offspring_population(self, total_population: int, num_offspring: int) -> list[int]:
        """随机划分子代种群，并确保每个子种至少拥有1个体。"""
        import random
        
        if num_offspring <= 0:
            return []
        if total_population <= 0:
            return [0] * num_offspring
        
        splits: list[int] = []
        remaining = total_population
        
        for idx in range(num_offspring):
            slots_left = num_offspring - idx
            if slots_left == 1:
                allocation = remaining
            else:
                min_allow = 1
                max_allow = remaining - (slots_left - 1)
                avg_share = remaining / slots_left
                lower_bound = max(min_allow, int(avg_share * 0.6))
                upper_bound = min(max_allow, max(lower_bound, int(avg_share * 1.4)))
                if upper_bound < lower_bound:
                    upper_bound = lower_bound
                allocation = random.randint(lower_bound, upper_bound)
            splits.append(allocation)
            remaining -= allocation
        
        return splits

    def _create_species(
        self,
        parent: Species,
        new_code: str,
        survivors: int,
        turn_index: int,
        ai_payload,
        average_pressure: float,
    ) -> Species:
        """创建新的分化物种。
        
        新物种从父代继承大部分属性，但有一些变化：
        - 基因多样性略微增加
        - 描述可能由 AI 修改以反映新特征
        
        种群分配逻辑：
        - 新物种从原物种中分离出20-40%的个体
        - 原物种保留60-80%
        - 总数略减（模拟分化过程的损耗）
        """
        # 种群分配逻辑已在上层处理，这里只负责对象创建
        
        morphology = dict(parent.morphology_stats)
        morphology["population"] = survivors
        
        hidden = dict(parent.hidden_traits)
        hidden["gene_diversity"] = min(1.0, hidden.get("gene_diversity", 0.5) + 0.05)
        
        # 继承父代的 abstract_traits，并应用 AI 建议的变化
        abstract = TraitConfig.merge_traits(parent.abstract_traits, {})
        trait_changes = ai_payload.get("trait_changes") or {}
        
        # 【关键修复】强制差异化和权衡机制
        # 1. 先应用AI建议的变化
        applied_changes = {}
        if isinstance(trait_changes, dict):
            for trait_name, change in trait_changes.items():
                try:
                    if isinstance(change, str):
                        change_value = float(change.replace("+", ""))
                    else:
                        change_value = float(change)
                    applied_changes[trait_name] = change_value
                except (ValueError, TypeError):
                    pass
        
        # 2. 强制权衡：如果只增不减，必须添加减少项
        applied_changes = self._enforce_trait_tradeoffs(abstract, applied_changes, new_code)
        
        # 3. 强制差异化：基于谱系编码添加随机偏移
        applied_changes = self._add_differentiation_noise(applied_changes, new_code)
        
        # 4. 应用最终变化
        for trait_name, change_value in applied_changes.items():
            current_value = abstract.get(trait_name, 5.0)
            new_val = current_value + change_value
            abstract[trait_name] = TraitConfig.clamp_trait(round(new_val, 2))
        
        # 应用形态学变化
        morphology_changes = ai_payload.get("morphology_changes") or {}
        if isinstance(morphology_changes, dict):
            for morph_name, change_factor in morphology_changes.items():
                if morph_name in morphology:
                    try:
                        # change_factor 是倍数，如 1.2 表示增大20%
                        factor = float(change_factor)
                        morphology[morph_name] = morphology[morph_name] * factor
                    except (ValueError, TypeError):
                        pass
        
        # 从AI响应中提取名称和描述
        latin = ai_payload.get("latin_name")
        common = ai_payload.get("common_name")
        description = ai_payload.get("description")
        
        # 如果AI未返回名称或描述，使用回退逻辑
        if not latin or not common or not description or len(str(description).strip()) < 80:
            logger.warning(f"[分化警告] AI返回不完整，使用回退命名: latin={latin}, common={common}")
            # 回退到规则命名
            if not latin:
                latin = self._fallback_latin_name(parent.latin_name, ai_payload)
            if not common:
                common = self._fallback_common_name(parent.common_name, ai_payload)
            if not description or len(str(description).strip()) < 80:
                key_innovations = ai_payload.get("key_innovations", [])
                innovations_text = "，演化出" + "、".join(key_innovations) if key_innovations else ""
                description = f"{parent.description}在环境压力{average_pressure:.1f}下发生适应性变化{innovations_text}。"
                if len(description) < 120:
                    description = parent.description
        
        # 【防重名】检查并处理重名情况
        latin = self._ensure_unique_latin_name(latin, new_code)
        common = self._ensure_unique_common_name(common, new_code)
        
        # 计算新物种的营养级
        # 优先级：AI判定 > 继承父代 > 关键词估算
        ai_trophic = ai_payload.get("trophic_level")
        if ai_trophic is not None:
            try:
                new_trophic = float(ai_trophic)
                # 范围钳制 (1.0-6.0)
                new_trophic = max(1.0, min(6.0, new_trophic))
                logger.info(f"[分化] 使用AI判定的营养级: T{new_trophic:.1f}")
            except (ValueError, TypeError):
                logger.warning(f"[分化] AI返回的营养级格式错误: {ai_trophic}")
                new_trophic = None
        else:
            logger.warning(f"[分化] AI未返回营养级")
            new_trophic = None

        if new_trophic is None:
            # 回退方案1：继承父代营养级（最合理的默认值）
            # 大多数分化事件不会改变营养级（生态位保守性）
            new_trophic = parent.trophic_level
            logger.info(f"[分化] 继承父代营养级: T{new_trophic:.1f}")
            
            # 如果父代营养级也无效，才使用关键词估算（应急回退）
            if new_trophic is None or new_trophic <= 0:
                all_species = species_repository.list_species()
                new_trophic = self.trophic_calculator.calculate_trophic_level(
                    Species(
                        lineage_code=new_code,
                        latin_name=latin,
                        common_name=common,
                        description=description,
                        morphology_stats=morphology,
                        abstract_traits=abstract,
                        hidden_traits=hidden,
                        ecological_vector=None,
                        trophic_level=2.0  # 默认为初级消费者
                    ),
                    all_species
                )
                logger.warning(f"[分化] 使用关键词估算营养级: T{new_trophic:.1f}")
        
        # 【克莱伯定律修正】基于体重和营养级重算代谢率
        # SMR ∝ Mass^-0.25
        mass_g = morphology.get("body_weight_g", 1.0)
        morphology["metabolic_rate"] = self.trophic_calculator.estimate_kleiber_metabolic_rate(
            mass_g, new_trophic
        )
        
        # 验证属性变化是否符合营养级规则
        validation_ok, validation_msg = self._validate_trait_changes(
            parent.abstract_traits, abstract, new_trophic
        )
        if not validation_ok:
            logger.warning(f"[分化警告] 属性验证失败: {validation_msg}，将自动钳制数值")
            # 智能钳制：根据营养级限制缩放属性，而不是直接回退
            abstract = self._clamp_traits_to_limit(abstract, parent.abstract_traits, new_trophic)

        
        # 继承并更新器官系统
        organs = self._inherit_and_update_organs(
            parent=parent,
            ai_payload=ai_payload,
            turn_index=turn_index
        )
        
        # 更新能力标签
        capabilities = self._update_capabilities(parent, organs)
        
        # 继承或更新栖息地类型
        new_habitat_type = ai_payload.get("habitat_type", parent.habitat_type)
        # 确保栖息地类型有效
        valid_habitats = ["marine", "deep_sea", "coastal", "freshwater", "amphibious", "terrestrial", "aerial"]
        if new_habitat_type not in valid_habitats:
            new_habitat_type = parent.habitat_type
        
        # 不再继承 ecological_vector，让系统基于 description 自动计算 embedding
        return Species(
            lineage_code=new_code,
            latin_name=latin,
            common_name=common,
            description=description,
            habitat_type=new_habitat_type,
            morphology_stats=morphology,
            abstract_traits=abstract,
            hidden_traits=hidden,
            ecological_vector=None,  # 不继承，让系统自动计算
            parent_code=parent.lineage_code,
            status="alive",
            created_turn=turn_index,
            trophic_level=new_trophic,
            organs=organs,
            capabilities=capabilities,
            genus_code=parent.genus_code,
            taxonomic_rank="subspecies",
        )
    
    def _inherit_habitat_distribution(self, parent: Species, child: Species, turn_index: int) -> None:
        """子代继承父代的栖息地分布
        
        风险修复：如果父代没有栖息地，立即为子代计算初始栖息地
        
        Args:
            parent: 父代物种
            child: 子代物种
            turn_index: 当前回合
        """
        from ...repositories.environment_repository import environment_repository
        from ...models.environment import HabitatPopulation
        
        # 获取父代的栖息地分布
        all_habitats = environment_repository.latest_habitats()
        parent_habitats = [h for h in all_habitats if h.species_id == parent.id]
        
        if not parent_habitats:
            logger.warning(f"[栖息地继承] 父代 {parent.common_name} 没有栖息地数据，立即为子代计算初始栖息地")
            # 【风险修复】立即计算子代的初始栖息地，而不是等待下次快照
            self._calculate_initial_habitat_for_child(child, parent, turn_index)
            return
            
        if child.id is None:
            logger.error(f"[栖息地继承] 严重错误：子代 {child.common_name} 没有 ID，无法继承栖息地")
            return
        
        # 子代继承父代的所有栖息地，保持相同的适宜度
        child_habitats = []
        for parent_hab in parent_habitats:
            child_habitats.append(
                HabitatPopulation(
                    tile_id=parent_hab.tile_id,
                    species_id=child.id,
                    population=0,  # 初始为0，会在回合结束时根据species.population更新
                    suitability=parent_hab.suitability,  # 继承父代的适宜度
                    turn_index=turn_index,
                )
            )
        
        if child_habitats:
            environment_repository.write_habitats(child_habitats)
            logger.info(f"[栖息地继承] {child.common_name} 继承了 {len(child_habitats)} 个栖息地")
    
    def _calculate_initial_habitat_for_child(self, child: Species, parent: Species, turn_index: int) -> None:
        """为没有栖息地的子代计算初始栖息地分布
        
        当父代没有栖息地数据时，基于子代的生态特征计算合适的栖息地
        
        Args:
            child: 子代物种
            parent: 父代物种（用于参考）
            turn_index: 当前回合
        """
        from ...repositories.environment_repository import environment_repository
        from ...models.environment import HabitatPopulation
        
        logger.info(f"[栖息地计算] 为 {child.common_name} 计算初始栖息地")
        
        # 1. 获取所有地块
        all_tiles = environment_repository.list_tiles()
        if not all_tiles:
            logger.error(f"[栖息地计算] 没有可用地块，无法为 {child.common_name} 计算栖息地")
            return
        
        # 2. 根据栖息地类型筛选地块
        habitat_type = getattr(child, 'habitat_type', 'terrestrial')
        suitable_tiles = []
        
        for tile in all_tiles:
            biome = tile.biome.lower()
            is_suitable = False
            
            if habitat_type == "marine" and ("浅海" in biome or "中层" in biome):
                is_suitable = True
            elif habitat_type == "deep_sea" and "深海" in biome:
                is_suitable = True
            elif habitat_type == "coastal" and ("海岸" in biome or "浅海" in biome):
                is_suitable = True
            elif habitat_type == "freshwater" and getattr(tile, 'is_lake', False):
                is_suitable = True
            elif habitat_type == "terrestrial" and "海" not in biome:
                is_suitable = True
            elif habitat_type == "amphibious" and ("海岸" in biome or ("平原" in biome and tile.humidity > 0.4)):
                is_suitable = True
            elif habitat_type == "aerial" and "海" not in biome and "山" not in biome:
                is_suitable = True
            
            if is_suitable:
                suitable_tiles.append(tile)
        
        if not suitable_tiles:
            logger.warning(f"[栖息地计算] {child.common_name} ({habitat_type}) 没有合适的地块")
            # 回退：使用前10个地块
            suitable_tiles = all_tiles[:10]
        
        # 3. 计算适宜度
        tile_suitability = []
        for tile in suitable_tiles:
            suitability = self._calculate_suitability_for_species(child, tile)
            if suitability > 0.1:  # 只保留适宜度>0.1的地块
                tile_suitability.append((tile, suitability))
        
        if not tile_suitability:
            logger.warning(f"[栖息地计算] {child.common_name} 没有适宜度>0.1的地块，使用前10个")
            tile_suitability = [(tile, 0.5) for tile in suitable_tiles[:10]]
        
        # 4. 选择top 10地块
        tile_suitability.sort(key=lambda x: x[1], reverse=True)
        top_tiles = tile_suitability[:10]
        
        # 5. 归一化适宜度（总和=1.0）
        total_suitability = sum(s for _, s in top_tiles)
        if total_suitability == 0:
            total_suitability = 1.0
        
        # 6. 创建栖息地记录
        child_habitats = []
        for tile, raw_suitability in top_tiles:
            normalized_suitability = raw_suitability / total_suitability
            child_habitats.append(
                HabitatPopulation(
                    tile_id=tile.id,
                    species_id=child.id,
                    population=0,
                    suitability=normalized_suitability,
                    turn_index=turn_index,
                )
            )
        
        if child_habitats:
            environment_repository.write_habitats(child_habitats)
            logger.info(f"[栖息地计算] {child.common_name} 计算得到 {len(child_habitats)} 个栖息地")
    
    def _calculate_suitability_for_species(self, species: Species, tile) -> float:
        """计算物种对地块的适宜度（简化版）"""
        # 温度适应性
        temp_pref = species.abstract_traits.get("耐热性", 5)
        cold_pref = species.abstract_traits.get("耐寒性", 5)
        
        if tile.temperature > 20:
            temp_score = temp_pref / 10.0
        elif tile.temperature < 5:
            temp_score = cold_pref / 10.0
        else:
            temp_score = 0.8
        
        # 湿度适应性
        drought_pref = species.abstract_traits.get("耐旱性", 5)
        humidity_score = 1.0 - abs(tile.humidity - (1.0 - drought_pref / 10.0))
        
        # 资源可用性
        resource_score = min(1.0, tile.resources / 500.0)
        
        # 综合评分
        return max(0.0, temp_score * 0.4 + humidity_score * 0.3 + resource_score * 0.3)
    
    def _calculate_speciation_threshold(self, species: Species) -> int:
        """计算物种的分化门槛 - 基于多维度生态学指标。
        
        综合考虑：
        1. 体型（体长、体重） - 主要因素
        2. 繁殖策略（世代时间、繁殖速度） - r/K策略
        3. 代谢率 - 能量周转速度
        4. 营养级 - 从描述推断
        
        Returns:
            最小种群数量（需要达到此数量才能分化）
        """
        import math
        
        # 1. 基于体型的基础门槛
        body_length_cm = species.morphology_stats.get("body_length_cm", 1.0)
        body_weight_g = species.morphology_stats.get("body_weight_g", 1.0)
        
        # 使用体长作为主要指标（更直观）
        if body_length_cm < 0.01:  # <0.1mm - 细菌级别
            base_threshold = 2_000_000  # 200万
        elif body_length_cm < 0.1:  # 0.1mm-1mm - 原生动物
            base_threshold = 1_000_000  # 100万
        elif body_length_cm < 1.0:  # 1mm-1cm - 小型无脊椎动物
            base_threshold = 100_000   # 10万
        elif body_length_cm < 10.0:  # 1cm-10cm - 昆虫、小鱼
            base_threshold = 10_000    # 1万
        elif body_length_cm < 50.0:  # 10cm-50cm - 中型脊椎动物
            base_threshold = 2_000     # 2千
        elif body_length_cm < 200.0:  # 50cm-2m - 大型哺乳动物
            base_threshold = 500       # 500
        else:  # >2m - 超大型动物（大象、鲸鱼）
            base_threshold = 100       # 100
        
        # 体重修正（提供额外验证）
        # 1g以下：微小生物
        # 1-1000g：小型生物
        # 1kg-100kg：中型生物
        # >100kg：大型生物
        if body_weight_g < 1.0:
            weight_factor = 1.2  # 微小生物需要更大种群
        elif body_weight_g < 1000:
            weight_factor = 1.0
        elif body_weight_g < 100_000:
            weight_factor = 0.8
        else:
            weight_factor = 0.6  # 大型生物门槛更低
        
        # 2. 繁殖策略修正
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        reproduction_speed = species.abstract_traits.get("繁殖速度", 5)
        
        # r策略物种（快繁殖，短世代）需要更大种群
        # K策略物种（慢繁殖，长世代）较小种群即可
        if generation_time < 30 and reproduction_speed >= 7:
            # r策略：微生物、昆虫
            repro_factor = 1.5
        elif generation_time < 365 and reproduction_speed >= 5:
            # 中等：小型哺乳动物、鸟类
            repro_factor = 1.0
        else:
            # K策略：大型哺乳动物
            repro_factor = 0.7
        
        # 3. 代谢率修正
        metabolic_rate = species.morphology_stats.get("metabolic_rate", 3.0)
        # 高代谢率（>5.0）= 需要更多个体维持种群
        # 低代谢率（<2.0）= 少量个体即可
        if metabolic_rate > 5.0:
            metabolic_factor = 1.3
        elif metabolic_rate > 3.0:
            metabolic_factor = 1.0
        else:
            metabolic_factor = 0.8
        
        # 4. 营养级修正（从描述推断）
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["顶级捕食", "apex", "大型捕食者", "食物链顶端"]):
            trophic_factor = 0.5  # 顶级捕食者种群小
        elif any(kw in desc_lower for kw in ["捕食", "carnivore", "肉食", "掠食"]):
            trophic_factor = 0.7  # 捕食者
        elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
            trophic_factor = 0.9
        elif any(kw in desc_lower for kw in ["草食", "herbivore", "食草"]):
            trophic_factor = 1.0  # 草食动物种群大
        elif any(kw in desc_lower for kw in ["生产者", "光合", "植物", "藻类", "producer", "photosyn"]):
            trophic_factor = 1.2  # 初级生产者种群最大
        else:
            trophic_factor = 1.0
        
        # 5. 综合计算
        threshold = int(
            base_threshold 
            * weight_factor 
            * repro_factor 
            * metabolic_factor 
            * trophic_factor
        )
        
        # 确保在合理范围内
        # 最小：50（濒危大型动物也需要一定基数）
        # 最大：500万（即使是细菌也不需要无限大）
        threshold = max(50, min(threshold, 5_000_000))
        
        return threshold
    
    def _summarize_food_chain_status(self, trophic_interactions: dict[str, float] | None) -> str:
        """总结食物链状态，供AI做演化决策参考
        
        这是一个关键函数！它告诉AI当前生态系统的营养级状态：
        - 哪些营养级的食物充足/稀缺
        - 是否有级联崩溃的风险
        
        Args:
            trophic_interactions: 营养级互动数据，包含 t2_scarcity, t3_scarcity 等
            
        Returns:
            人类可读的食物链状态描述
        """
        if not trophic_interactions:
            return "食物链状态未知"
        
        status_parts = []
        
        # 检查各级的食物稀缺度
        # scarcity: 0 = 充足, 1 = 紧张, 2 = 严重短缺
        t2_scarcity = trophic_interactions.get("t2_scarcity", 0.0)
        t3_scarcity = trophic_interactions.get("t3_scarcity", 0.0)
        t4_scarcity = trophic_interactions.get("t4_scarcity", 0.0)
        t5_scarcity = trophic_interactions.get("t5_scarcity", 0.0)
        
        def scarcity_level(value: float) -> str:
            if value < 0.3:
                return "充足"
            elif value < 1.0:
                return "紧张"
            elif value < 1.5:
                return "短缺"
            else:
                return "严重短缺"
        
        # T1 是生产者，不依赖其他营养级
        # T2 依赖 T1（生产者）
        if t2_scarcity > 0.5:
            status_parts.append(f"生产者(T1){'紧张' if t2_scarcity < 1.0 else '短缺'}，初级消费者(T2)面临食物压力")
        
        # T3 依赖 T2
        if t3_scarcity > 0.5:
            status_parts.append(f"初级消费者(T2){'紧张' if t3_scarcity < 1.0 else '短缺'}，次级消费者(T3)面临食物压力")
        
        # T4 依赖 T3
        if t4_scarcity > 0.5:
            status_parts.append(f"次级消费者(T3){'紧张' if t4_scarcity < 1.0 else '短缺'}，三级消费者(T4)面临食物压力")
        
        # T5 依赖 T4
        if t5_scarcity > 0.5:
            status_parts.append(f"三级消费者(T4){'紧张' if t5_scarcity < 1.0 else '短缺'}，顶级捕食者(T5)面临食物压力")
        
        # 检测级联崩溃风险
        if t2_scarcity > 1.5 and t3_scarcity > 1.0:
            status_parts.append("⚠️ 食物链底层崩溃，可能引发级联灭绝")
        
        if not status_parts:
            return "食物链稳定，各营养级食物充足"
        
        return "；".join(status_parts)
    
    def _summarize_map_changes(self, map_changes: list) -> str:
        """总结地图变化用于分化原因描述。"""
        if not map_changes:
            return ""
        
        change_types = []
        for change in map_changes[:3]:  # 最多取3个
            if isinstance(change, dict):
                ctype = change.get("change_type", "")
            else:
                ctype = getattr(change, "change_type", "")
            
            if ctype == "uplift":
                change_types.append("地壳抬升")
            elif ctype == "volcanic":
                change_types.append("火山活动")
            elif ctype == "glaciation":
                change_types.append("冰川推进")
            elif ctype == "subsidence":
                change_types.append("地壳下沉")
        
        return "、".join(change_types) if change_types else "地形变化"
    
    def _summarize_major_events(self, major_events: list) -> str:
        """总结重大事件用于分化原因描述。"""
        if not major_events:
            return ""
        
        for event in major_events[:1]:  # 取第一个
            if isinstance(event, dict):
                desc = event.get("description", "")
                severity = event.get("severity", "")
            else:
                desc = getattr(event, "description", "")
                severity = getattr(event, "severity", "")
            
            if desc:
                return f"{severity}级{desc}"
        
        return "重大环境事件"
    
    def _fallback_latin_name(self, parent_latin: str, ai_content: dict) -> str:
        """回退拉丁命名逻辑"""
        import hashlib
        # 提取父系属名
        genus = parent_latin.split()[0] if ' ' in parent_latin else "Species"
        # 基于key_innovations生成种加词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            # 从第一个创新中提取关键词
            innovation = innovations[0].lower()
            if "鞭毛" in innovation or "游" in innovation:
                epithet = "natans"
            elif "深" in innovation or "底" in innovation:
                epithet = "profundus"
            elif "快" in innovation or "速" in innovation:
                epithet = "velox"
            elif "慢" in innovation or "缓" in innovation:
                epithet = "lentus"
            elif "大" in innovation or "巨" in innovation:
                epithet = "magnus"
            elif "小" in innovation or "微" in innovation:
                epithet = "minutus"
            elif "透明" in innovation:
                epithet = "hyalinus"
            elif "耐盐" in innovation or "盐" in innovation:
                epithet = "salinus"
            elif "耐热" in innovation or "热" in innovation:
                epithet = "thermophilus"
            elif "耐寒" in innovation or "冷" in innovation:
                epithet = "cryophilus"
            else:
                # 使用hash确保唯一性
                hash_suffix = hashlib.md5(str(innovations).encode()).hexdigest()[:6]
                epithet = f"sp{hash_suffix}"
        else:
            # 完全随机
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:6]
            epithet = f"sp{hash_suffix}"
        return f"{genus} {epithet}"
    
    def _fallback_common_name(self, parent_common: str, ai_content: dict) -> str:
        """回退中文命名逻辑"""
        import hashlib
        # 提取类群名（通常是最后2-3个字）
        if len(parent_common) >= 2:
            taxon = parent_common[-2:] if parent_common[-1] in "虫藻菌类贝鱼" else parent_common[-3:]
        else:
            taxon = "生物"
        
        # 从key_innovations提取特征词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            innovation = innovations[0]
            # 提取前2个字作为特征词
            if "鞭毛" in innovation:
                if "多" in innovation or "4" in innovation or "增" in innovation:
                    feature = "多鞭"
                elif "长" in innovation:
                    feature = "长鞭"
                else:
                    feature = "异鞭"
            elif "游" in innovation or "速" in innovation:
                if "快" in innovation or "提升" in innovation:
                    feature = "快游"
                else:
                    feature = "慢游"
            elif "深" in innovation or "底" in innovation:
                feature = "深水"
            elif "浅" in innovation or "表" in innovation:
                feature = "浅水"
            elif "耐盐" in innovation or "盐" in innovation:
                feature = "耐盐"
            elif "透明" in innovation:
                feature = "透明"
            elif "大" in innovation or "巨" in innovation:
                feature = "巨型"
            elif "小" in innovation or "微" in innovation:
                feature = "微型"
            elif "滤食" in innovation:
                feature = "滤食"
            elif "夜" in innovation:
                feature = "夜行"
            else:
                # 提取前两个字
                words = [c for c in innovation if '\u4e00' <= c <= '\u9fff']
                feature = ''.join(words[:2]) if len(words) >= 2 else "变异"
        else:
            # 使用hash生成唯一标识
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:2]
            feature = f"型{hash_suffix}"
        
        return f"{feature}{taxon}"
    
    def _ensure_unique_latin_name(self, latin_name: str, lineage_code: str) -> str:
        """确保拉丁学名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用谱系编码作为亚种名
        
        Args:
            latin_name: AI生成的拉丁学名
            lineage_code: 谱系编码
            
        Returns:
            唯一的拉丁学名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.latin_name.lower() for sp in all_species}
        
        # 如果名称唯一，直接返回
        if latin_name.lower() not in existing_names:
            return latin_name
        
        logger.info(f"[防重名] 检测到拉丁学名重复: {latin_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{latin_name} {numeral}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用谱系编码作为亚种标识
        logger.info(f"[防重名] 罗马数字已超过V，使用谱系编码标识")
        parts = latin_name.split()
        if len(parts) >= 2:
            genus, species_name = parts[0], parts[1]
            subspecies_suffix = lineage_code.lower().replace("_", "")
            
            # 使用 subsp. 格式
            variant = f"{genus} {species_name} subsp. {subspecies_suffix}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用亚种标识: {variant}")
                return variant
        
        # 最终兜底：直接加谱系编码
        return f"{latin_name} [{lineage_code}]"
    
    def _ensure_unique_common_name(self, common_name: str, lineage_code: str) -> str:
        """确保中文俗名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用世代标记
        
        Args:
            common_name: AI生成的中文俗名
            lineage_code: 谱系编码
            
        Returns:
            唯一的中文俗名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.common_name for sp in all_species}
        
        # 如果名称唯一，直接返回
        if common_name not in existing_names:
            return common_name
        
        logger.info(f"[防重名] 检测到中文俗名重复: {common_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{common_name}{numeral}"
            if variant not in existing_names:
                logger.info(f"[防重名] 添加罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用世代标记
        logger.info(f"[防重名] 罗马数字已超过V，使用世代标记")
        for i in range(6, 50):
            variant = f"{common_name}-{i}代"
            if variant not in existing_names:
                logger.info(f"[防重名] 使用世代标记: {variant}")
                return variant
        
        # 最终兜底：添加谱系编码
        return f"{common_name}({lineage_code})"
    
    def _validate_trait_changes(
        self, old_traits: dict, new_traits: dict, trophic_level: float
    ) -> tuple[bool, str]:
        """验证属性变化是否符合营养级规则
        
        Returns:
            (验证是否通过, 错误信息)
        """
        # 获取营养级对应的属性上限
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        # 1. 检查总和变化
        old_sum = sum(old_traits.values())
        new_sum = sum(new_traits.values())
        sum_diff = new_sum - old_sum
        
        if sum_diff > 8:
            return False, f"属性总和增加{sum_diff}，超过上限8"
        
        # 2. 检查总和是否超过营养级上限
        if new_sum > limits["total"]:
            return False, f"属性总和{new_sum}超过营养级{trophic_level:.1f}的上限{limits['total']}"
        
        # 3. 检查单个属性是否超过特化上限
        above_specialized = [
            (k, v) for k, v in new_traits.items() if v > limits["specialized"]
        ]
        if above_specialized:
            return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]}超过特化上限{limits['specialized']}"
        
        # 4. 检查超过基础上限的属性数量
        above_base_count = sum(1 for v in new_traits.values() if v > limits["base"])
        if above_base_count > 2:
            return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个"
        
        # 5. 检查权衡（有增必有减，除非是营养级提升）
        increases = sum(1 for k, v in new_traits.items() if v > old_traits.get(k, 0))
        decreases = sum(1 for k, v in new_traits.items() if v < old_traits.get(k, 0))
        
        if increases > 0 and decreases == 0 and sum_diff > 3:
            return False, "有属性提升但无权衡代价"
        
        return True, "验证通过"
    
    def _inherit_and_update_organs(
        self, parent: Species, ai_payload: dict, turn_index: int
    ) -> dict:
        """继承父代器官并应用渐进式器官进化
        
        支持两种格式（优先使用新格式）：
        - organ_evolution: 新的渐进式进化格式（推荐）
        - structural_innovations: 旧格式（向后兼容）
        
        Args:
            parent: 父系物种
            ai_payload: AI返回的数据
            turn_index: 当前回合
            
        Returns:
            更新后的器官字典
        """
        # 1. 继承父代所有器官（深拷贝）
        organs = {}
        for category, organ_data in parent.organs.items():
            organs[category] = dict(organ_data)
            # 确保有进化阶段字段
            if "evolution_stage" not in organs[category]:
                organs[category]["evolution_stage"] = 4  # 旧数据默认完善
            if "evolution_progress" not in organs[category]:
                organs[category]["evolution_progress"] = 1.0
        
        # 2. 优先使用新的 organ_evolution 格式
        organ_evolution = ai_payload.get("organ_evolution", [])
        if organ_evolution and isinstance(organ_evolution, list):
            # 推断生物类群进行验证
            biological_domain = self._infer_biological_domain(parent)
            
            # 验证渐进式进化规则
            _, valid_evolutions = self._validate_gradual_evolution(
                organ_evolution, parent.organs, biological_domain
            )
            
            for evo in valid_evolutions:
                category = evo.get("category", "unknown")
                action = evo.get("action", "enhance")
                target_stage = evo.get("target_stage", 1)
                structure_name = evo.get("structure_name", "未知结构")
                description = evo.get("description", "")
                
                if action == "initiate":
                    # 开始发展新器官（从原基开始）
                    organs[category] = {
                        "type": structure_name,
                        "parameters": {},
                        "evolution_stage": target_stage,
                        "evolution_progress": target_stage / 4.0,  # 阶段对应进度
                        "acquired_turn": turn_index,
                        "is_active": target_stage >= 2,  # 阶段2+才有基础功能
                        "evolution_history": [
                            {
                                "turn": turn_index,
                                "from_stage": 0,
                                "to_stage": target_stage,
                                "description": description
                            }
                        ]
                    }
                    logger.info(
                        f"[渐进式演化] 开始发展{category}: {structure_name} (阶段0→{target_stage})"
                    )
                
                elif action == "enhance" and category in organs:
                    # 增强现有器官
                    current_stage = organs[category].get("evolution_stage", 4)
                    
                    organs[category]["type"] = structure_name
                    organs[category]["evolution_stage"] = target_stage
                    organs[category]["evolution_progress"] = target_stage / 4.0
                    organs[category]["modified_turn"] = turn_index
                    organs[category]["is_active"] = target_stage >= 2
                    
                    # 记录演化历史
                    if "evolution_history" not in organs[category]:
                        organs[category]["evolution_history"] = []
                    organs[category]["evolution_history"].append({
                        "turn": turn_index,
                        "from_stage": current_stage,
                        "to_stage": target_stage,
                        "description": description
                    })
                    
                    logger.info(
                        f"[渐进式演化] 增强{category}: {structure_name} "
                        f"(阶段{current_stage}→{target_stage})"
                    )
            
            return organs
        
        # 3. 兼容旧的 structural_innovations 格式（转换为渐进式）
        innovations = ai_payload.get("structural_innovations", [])
        if not isinstance(innovations, list):
            return organs
        
        for innovation in innovations:
            if not isinstance(innovation, dict):
                continue
            
            category = innovation.get("category", "unknown")
            organ_type = innovation.get("type", "unknown")
            parameters = innovation.get("parameters", {})
            
            if category in organs:
                # 器官改进：最多提升1个阶段
                current_stage = organs[category].get("evolution_stage", 4)
                new_stage = min(current_stage + 1, 4)
                
                organs[category]["type"] = organ_type
                organs[category]["parameters"] = parameters
                organs[category]["evolution_stage"] = new_stage
                organs[category]["evolution_progress"] = new_stage / 4.0
                organs[category]["modified_turn"] = turn_index
                organs[category]["is_active"] = True
                logger.info(
                    f"[器官演化-兼容] 改进器官: {category} → {organ_type} "
                    f"(阶段{current_stage}→{new_stage})"
                )
            else:
                # 新器官：从阶段1（原基）开始，而不是直接完善
                organs[category] = {
                    "type": organ_type,
                    "parameters": parameters,
                    "evolution_stage": 1,  # 从原基开始
                    "evolution_progress": 0.25,
                    "acquired_turn": turn_index,
                    "is_active": False,  # 阶段1还没有功能
                    "evolution_history": [{
                        "turn": turn_index,
                        "from_stage": 0,
                        "to_stage": 1,
                        "description": f"开始发展{organ_type}原基"
                    }]
                }
                logger.info(
                    f"[器官演化-兼容] 新器官原基: {category} → {organ_type} (阶段1)"
                )
        
        return organs
    
    def _update_capabilities(self, parent: Species, organs: dict) -> list[str]:
        """根据器官更新能力标签
        
        Args:
            parent: 父系物种
            organs: 当前器官字典
            
        Returns:
            能力标签列表（中文）
        """
        # 能力映射表：旧英文标签 -> 中文标签
        legacy_map = {
            "photosynthesis": "光合作用",
            "autotrophy": "自养",
            "flagellar_motion": "鞭毛运动",
            "chemical_detection": "化学感知",
            "heterotrophy": "异养",
            "chemosynthesis": "化能合成",
            "extremophile": "嗜极生物",
            "ciliary_motion": "纤毛运动",
            "limb_locomotion": "附肢运动",
            "swimming": "游泳",
            "light_detection": "感光",
            "vision": "视觉",
            "touch_sensation": "触觉",
            "aerobic_respiration": "有氧呼吸",
            "digestion": "消化",
            "armor": "盔甲",
            "spines": "棘刺",
            "venom": "毒素"
        }

        capabilities = set()
        
        # 继承并转换父代能力
        for cap in parent.capabilities:
            if cap in legacy_map:
                capabilities.add(legacy_map[cap])
            else:
                # 如果已经是中文或其他未映射的，直接保留
                capabilities.add(cap)
        
        # 根据活跃器官添加能力标签
        for category, organ_data in organs.items():
            if not organ_data.get("is_active", True):
                continue  # 跳过已退化的器官
            
            organ_type = organ_data.get("type", "").lower()
            
            # 运动能力
            if category == "locomotion":
                if "flagella" in organ_type or "flagellum" in organ_type or "鞭毛" in organ_type:
                    capabilities.add("鞭毛运动")
                elif "cilia" in organ_type or "纤毛" in organ_type:
                    capabilities.add("纤毛运动")
                elif "leg" in organ_type or "limb" in organ_type or "足" in organ_type or "肢" in organ_type:
                    capabilities.add("附肢运动")
                elif "fin" in organ_type or "鳍" in organ_type:
                    capabilities.add("游泳")
            
            # 感觉能力
            elif category == "sensory":
                if "eye" in organ_type or "ocellus" in organ_type or "眼" in organ_type:
                    capabilities.add("感光")
                    capabilities.add("视觉")
                elif "photoreceptor" in organ_type or "eyespot" in organ_type or "光感受" in organ_type or "眼点" in organ_type:
                    capabilities.add("感光")
                elif "mechanoreceptor" in organ_type or "机械感受" in organ_type:
                    capabilities.add("触觉")
                elif "chemoreceptor" in organ_type or "化学感受" in organ_type:
                    capabilities.add("化学感知")
            
            # 代谢能力
            elif category == "metabolic":
                if "chloroplast" in organ_type or "photosynthetic" in organ_type or "叶绿体" in organ_type or "光合" in organ_type:
                    capabilities.add("光合作用")
                elif "mitochondria" in organ_type or "线粒体" in organ_type:
                    capabilities.add("有氧呼吸")
            
            # 消化能力
            elif category == "digestive":
                if organ_data.get("is_active", True):
                    capabilities.add("消化")
            
            # 防御能力
            elif category == "defense":
                if "shell" in organ_type or "carapace" in organ_type or "壳" in organ_type or "甲" in organ_type:
                    capabilities.add("盔甲")
                elif "spine" in organ_type or "thorn" in organ_type or "刺" in organ_type or "棘" in organ_type:
                    capabilities.add("棘刺")
                elif "toxin" in organ_type or "毒" in organ_type:
                    capabilities.add("毒素")
        
        return list(capabilities)
    
    def _update_genetic_distances(self, offspring: Species, parent: Species, turn_index: int):
        """更新遗传距离矩阵"""
        if not parent.genus_code:
            return
        
        genus = genus_repository.get_by_code(parent.genus_code)
        if not genus:
            return
        
        all_species = species_repository.list_species()
        genus_species = [sp for sp in all_species if sp.genus_code == parent.genus_code and sp.status == "alive"]
        
        new_distances = {}
        for sibling in genus_species:
            if sibling.lineage_code == offspring.lineage_code:
                continue
            
            distance = self.genetic_calculator.calculate_distance(offspring, sibling)
            key = self._make_distance_key(offspring.lineage_code, sibling.lineage_code)
            new_distances[key] = distance
        
        genus_repository.update_distances(parent.genus_code, new_distances, turn_index)
    
    def _make_distance_key(self, code1: str, code2: str) -> str:
        """生成距离键"""
        if code1 < code2:
            return f"{code1}-{code2}"
        return f"{code2}-{code1}"
    
    def _clamp_traits_to_limit(self, traits: dict, parent_traits: dict, trophic_level: float) -> dict:
        """智能钳制属性到营养级限制范围内
        
        策略：
        1. 单个属性不超过特化上限
        2. 属性总和不超过营养级上限和父代+5.0
        3. 最多2个属性超过基础上限
        """
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        clamped = dict(traits)
        
        # 1. 钳制单个属性到特化上限
        for k, v in clamped.items():
            if v > limits["specialized"]:
                clamped[k] = limits["specialized"]
        
        # 2. 检查并钳制总和
        current_sum = sum(clamped.values())
        parent_sum = sum(parent_traits.values())
        
        # 总和最多增加5.0（保守的演化步长，比原本允许的8更严格）
        max_increase = 5.0
        target_max_sum = min(limits["total"], parent_sum + max_increase)
        
        if current_sum > target_max_sum:
            # 计算需要缩减的量
            excess = current_sum - target_max_sum
            # 只缩减增加的属性（保持权衡原则）
            increased_traits = {k: v for k, v in clamped.items() if v > parent_traits.get(k, 0)}
            
            if increased_traits:
                # 按增加量比例分配缩减（增加多的缩减多）
                total_increase = sum(v - parent_traits.get(k, 0) for k, v in increased_traits.items())
                if total_increase > 0:
                    for k, v in increased_traits.items():
                        increase = v - parent_traits.get(k, 0)
                        reduction = excess * (increase / total_increase)
                        clamped[k] = max(parent_traits.get(k, 0), v - reduction)
            
            # 如果还是超了（说明没有增加的属性或不足以缩减），全局缩放
            current_sum = sum(clamped.values())
            if current_sum > target_max_sum:
                scale = target_max_sum / current_sum
                for k in clamped:
                    clamped[k] *= scale
        
        # 3. 确保最多2个属性超过基础上限
        base_limit = limits["base"]
        specialized_traits = [(k, v) for k, v in clamped.items() if v > base_limit]
        if len(specialized_traits) > 2:
            # 保留最高的2个，其余降到基础上限
            specialized_traits.sort(key=lambda x: x[1], reverse=True)
            keep_specialized = {k for k, _ in specialized_traits[:2]}
            
            for k, v in clamped.items():
                if v > base_limit and k not in keep_specialized:
                    clamped[k] = base_limit
        
        return {k: round(v, 2) for k, v in clamped.items()}
    
    def _calculate_dynamic_offspring_count(
        self,
        num_generations: float,
        population: int,
        evo_potential: float,
        current_species_count: int = 0,
        sibling_count: int = 0
    ) -> int:
        """【优化版】根据生态条件动态计算分化子种数量
        
        核心改进：
        - 世代多≠更多子种（世代只影响分化概率，不影响子种数量）
        - 子种数量主要由「隔离机会」决定（种群规模、地理分布）
        - 引入物种密度阻尼（防止爆炸性增长）
        
        参数说明：
        - num_generations: 经历的世代数（仅用于日志，不影响计算）
        - population: 当前存活种群数
        - evo_potential: 演化潜力（0-1）
        - current_species_count: 当前物种总数（用于密度阻尼）
        - sibling_count: 同谱系物种数量（用于属内阻尼）
        
        返回值：
        - 子种数量（1-3个，极端情况最多4个）
        """
        import math
        import random
        
        # 基础分化数（固定2个，模拟典型的二歧分化）
        base_offspring = 2
        
        # 1. 【移除】世代数加成 - 世代多只意味着突变多，不意味着隔离多
        # 现实中，细菌虽然繁殖快，但分化出的稳定物种数量并不比大型动物多
        generation_bonus = 0
        
        # 2. 种群规模加成（非常大的种群才可能形成3个隔离亚群）
        # 提高门槛：需要10亿以上才考虑+1
        population_bonus = 0
        if population > 1_000_000_000:  # 10亿
            population_bonus = 1
        
        # 3. 演化潜力加成（只有极高潜力才+1）
        evo_bonus = 1 if evo_potential > 0.90 else 0
        
        # 4. 【关键】物种密度阻尼
        # 当物种数量过多时，强制降低子种数量
        density_penalty = 0
        if current_species_count > 50:
            density_penalty = 1  # 超过50种：-1
        if current_species_count > 100:
            density_penalty = 2  # 超过100种：-2（基本只能分化1个）
        
        # 5. 【新增】同属饱和阻尼
        # 当同一谱系下已有多个物种时，限制继续分化
        sibling_penalty = 0
        if sibling_count >= 3:
            sibling_penalty = 1  # 同属已有3+物种：-1
        if sibling_count >= 5:
            sibling_penalty = 2  # 同属已有5+物种：几乎不能分化
        
        # 6. 汇总（最少1个，最多4个）
        total_offspring = base_offspring + generation_bonus + population_bonus + evo_bonus
        total_offspring -= density_penalty + sibling_penalty
        
        # 边界约束（上限从配置读取，默认4）
        max_offspring = _settings.max_offspring_count
        total_offspring = max(1, min(max_offspring, total_offspring))
        
        # 随机扰动（避免所有物种都分化相同数量）
        if random.random() < 0.3 and total_offspring > 1:
            total_offspring -= 1
        
        return total_offspring
    
    def _enforce_trait_tradeoffs(
        self, 
        current_traits: dict[str, float], 
        proposed_changes: dict[str, float],
        lineage_code: str
    ) -> dict[str, float]:
        """【强制权衡机制】确保属性变化有增必有减
        
        原理：50万年的演化不应该是纯粹的"升级"，而是适应性权衡
        - 如果提议的变化只增不减，自动添加减少项
        - 确保属性总和不会无限增长
        
        Args:
            current_traits: 当前属性字典
            proposed_changes: AI提议的变化 {"耐寒性": 2.0, "运动能力": 1.0}
            lineage_code: 谱系编码（用于确定哪些属性减少）
            
        Returns:
            调整后的变化字典
        """
        import random
        import hashlib
        
        if not proposed_changes:
            return proposed_changes
        
        # 计算总变化
        increases = {k: v for k, v in proposed_changes.items() if v > 0}
        decreases = {k: v for k, v in proposed_changes.items() if v < 0}
        
        total_increase = sum(increases.values())
        total_decrease = abs(sum(decreases.values()))
        
        # 如果已经有足够的减少，直接返回
        if total_decrease >= total_increase * 0.3:
            return proposed_changes
        
        # 需要添加的减少量（至少抵消30%的增加）
        needed_decrease = total_increase * 0.4 - total_decrease
        if needed_decrease <= 0:
            return proposed_changes
        
        # 基于谱系编码生成确定性随机种子（确保同一物种每次结果一致）
        seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        # 选择要减少的属性（优先选择当前值较高且未被增加的）
        adjusted = dict(proposed_changes)
        candidate_traits = [
            (name, value) 
            for name, value in current_traits.items() 
            if name not in increases and value > 3.0  # 只减少中高值属性
        ]
        
        if not candidate_traits:
            # 如果没有合适的候选，从增加项中随机选一个减少幅度
            for trait_name in list(increases.keys()):
                if needed_decrease <= 0:
                    break
                reduction = min(needed_decrease, increases[trait_name] * 0.5)
                adjusted[trait_name] = increases[trait_name] - reduction
                needed_decrease -= reduction
            return adjusted
        
        # 随机选择1-3个属性进行减少
        rng.shuffle(candidate_traits)
        num_to_reduce = min(len(candidate_traits), rng.randint(1, 3))
        
        for trait_name, current_value in candidate_traits[:num_to_reduce]:
            if needed_decrease <= 0:
                break
            # 减少幅度与当前值成比例（高值属性减更多）
            max_reduction = min(needed_decrease, current_value * 0.2, 3.0)
            reduction = rng.uniform(max_reduction * 0.5, max_reduction)
            adjusted[trait_name] = -round(reduction, 2)
            needed_decrease -= reduction
            logger.debug(f"[权衡] {lineage_code}: {trait_name} -{reduction:.2f} (权衡代价)")
        
        return adjusted
    
    def _add_differentiation_noise(
        self, 
        trait_changes: dict[str, float],
        lineage_code: str
    ) -> dict[str, float]:
        """【差异化机制】为不同子代添加随机偏移
        
        原理：同一次分化的多个子代应该有不同的演化方向
        - 基于谱系编码的最后字符（a, b, c...）确定偏移模式
        - 确保兄弟物种之间有明显差异
        
        Args:
            trait_changes: 当前变化字典
            lineage_code: 谱系编码（如 "A1a", "A1b", "A1c"）
            
        Returns:
            添加差异化后的变化字典
        """
        import random
        import hashlib
        
        if not trait_changes:
            return trait_changes
        
        # 基于完整谱系编码生成唯一随机种子
        seed = int(hashlib.md5(lineage_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        
        # 提取最后一个字符来确定子代编号
        last_char = lineage_code[-1] if lineage_code else 'a'
        offspring_index = ord(last_char.lower()) - ord('a')  # a=0, b=1, c=2...
        
        # 定义演化方向偏好（不同子代偏向不同方向）
        # 偏好模式：每个子代有2-3个属性获得额外加成，另外2-3个属性减少
        direction_patterns = [
            {"favor": ["耐寒性", "耐热性"], "disfavor": ["运动能力", "繁殖速度"]},  # 温度适应型
            {"favor": ["运动能力", "攻击性"], "disfavor": ["耐寒性", "社会性"]},     # 活动型
            {"favor": ["繁殖速度", "社会性"], "disfavor": ["攻击性", "运动能力"]},   # 繁殖型
            {"favor": ["防御性", "耐旱性"], "disfavor": ["繁殖速度", "攻击性"]},      # 防御型
            {"favor": ["耐盐性", "耐旱性"], "disfavor": ["社会性", "防御性"]},        # 环境适应型
        ]
        
        pattern = direction_patterns[offspring_index % len(direction_patterns)]
        
        adjusted = dict(trait_changes)
        
        # 对偏好属性添加额外加成（±0.3到±1.0）
        for trait in pattern["favor"]:
            if trait in adjusted:
                bonus = rng.uniform(0.2, 0.8)
                adjusted[trait] = round(adjusted[trait] + bonus, 2)
            else:
                # 即使AI没提议，也添加小幅增加
                adjusted[trait] = round(rng.uniform(0.3, 0.8), 2)
        
        # 对不偏好属性添加额外减少
        for trait in pattern["disfavor"]:
            if trait in adjusted:
                penalty = rng.uniform(0.2, 0.6)
                adjusted[trait] = round(adjusted[trait] - penalty, 2)
            else:
                # 添加小幅减少
                adjusted[trait] = round(-rng.uniform(0.2, 0.5), 2)
        
        # 添加额外的随机噪声（确保即使相同模式也有差异）
        for trait_name in list(adjusted.keys()):
            noise = rng.uniform(-0.3, 0.3)
            adjusted[trait_name] = round(adjusted[trait_name] + noise, 2)
        
        logger.debug(
            f"[差异化] {lineage_code}: 偏好{pattern['favor']}, "
            f"变化总和={sum(adjusted.values()):.2f}"
        )
        
        return adjusted
    
    # ================ 渐进式器官进化相关方法 ================
    
    # 生物复杂度等级参考描述（用于embedding相似度比较）
    _COMPLEXITY_REFERENCES = {
        0: "原核生物，如细菌和古菌，没有细胞核，只有核糖体，通过二分裂繁殖，体型微小，单细胞",
        1: "简单真核生物，如变形虫、鞭毛虫、纤毛虫，有细胞核和细胞器，单细胞真核生物",
        2: "殖民型或简单多细胞生物，如团藻、海绵、水母，细胞开始分化但无真正组织",
        3: "组织级生物，如扁形虫、环节动物，有真正的组织分化，简单器官系统",
        4: "器官级生物，如软体动物、节肢动物、鱼类，有复杂器官系统，体节或体腔",
        5: "高等器官系统级生物，如两栖类、爬行类、鸟类、哺乳类，高度分化的器官系统和神经系统",
    }
    
    # 缓存embedding向量
    _complexity_embeddings: dict[int, list[float]] | None = None
    
    def _infer_biological_domain(self, species: Species) -> str:
        """根据物种特征推断其生物复杂度等级
        
        采用多层判断策略：
        1. 优先使用embedding相似度（如果服务可用）
        2. 结构化特征检测（器官数量、体型等）
        3. 关键词匹配作为补充
        
        返回值：复杂度等级字符串，格式为 "complexity_N"
        - complexity_0: 原核生物（细菌、古菌）
        - complexity_1: 简单真核（单细胞真核生物）
        - complexity_2: 殖民/简单多细胞（团藻、海绵等）
        - complexity_3: 组织级（扁形虫、环节动物等）
        - complexity_4: 器官级（节肢动物、鱼类等）
        - complexity_5: 高等器官系统（脊椎动物高等类群）
        """
        # 尝试使用embedding进行智能分类
        complexity_level = self._infer_complexity_by_embedding(species)
        
        if complexity_level is None:
            # 降级到基于规则的推断
            complexity_level = self._infer_complexity_by_rules(species)
        
        return f"complexity_{complexity_level}"
    
    def _infer_complexity_by_embedding(self, species: Species) -> int | None:
        """使用embedding相似度推断复杂度等级"""
        # 检查是否有可用的embedding服务
        if not hasattr(self, '_embedding_service') or self._embedding_service is None:
            # 尝试从router获取
            if hasattr(self.router, 'embedding_service'):
                self._embedding_service = self.router.embedding_service
            else:
                return None
        
        if self._embedding_service is None:
            return None
        
        try:
            # 懒加载参考描述的embedding
            if SpeciationService._complexity_embeddings is None:
                ref_descriptions = list(self._COMPLEXITY_REFERENCES.values())
                ref_vectors = self._embedding_service.embed(ref_descriptions, require_real=False)
                SpeciationService._complexity_embeddings = {
                    level: vec for level, vec in enumerate(ref_vectors)
                }
            
            # 获取物种描述的embedding
            species_vec = self._embedding_service.embed([species.description], require_real=False)[0]
            
            # 计算与各等级参考的余弦相似度
            import numpy as np
            species_arr = np.array(species_vec)
            species_norm = np.linalg.norm(species_arr)
            if species_norm == 0:
                return None
            species_arr = species_arr / species_norm
            
            best_level = 1  # 默认简单真核
            best_similarity = -1
            
            for level, ref_vec in self._complexity_embeddings.items():
                ref_arr = np.array(ref_vec)
                ref_norm = np.linalg.norm(ref_arr)
                if ref_norm == 0:
                    continue
                ref_arr = ref_arr / ref_norm
                
                similarity = float(np.dot(species_arr, ref_arr))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_level = level
            
            logger.debug(
                f"[复杂度推断-embedding] {species.common_name}: "
                f"等级{best_level} (相似度{best_similarity:.3f})"
            )
            return best_level
            
        except Exception as e:
            logger.warning(f"[复杂度推断] Embedding推断失败: {e}")
            return None
    
    def _infer_complexity_by_rules(self, species: Species) -> int:
        """基于规则推断复杂度等级（降级方案）"""
        description = (species.description or "").lower()
        common_name = (species.common_name or "").lower()
        organs = species.organs or {}
        body_length = species.morphology_stats.get("body_length_cm", 0.01)
        
        # 关键词映射
        level_keywords = {
            0: ["细菌", "杆菌", "球菌", "古菌", "原核", "bacteria", "archaea", "芽孢"],
            1: ["原生", "单细胞", "鞭毛虫", "纤毛虫", "变形虫", "眼虫", "草履虫", "protist", "amoeba"],
            2: ["团藻", "海绵", "水母", "珊瑚", "群体", "殖民", "简单多细胞", "colony"],
            3: ["扁形虫", "涡虫", "线虫", "环节", "蚯蚓", "水蛭", "组织分化"],
            4: ["节肢", "软体", "昆虫", "甲壳", "蜘蛛", "鱼", "章鱼", "蜗牛", "器官系统"],
            5: ["两栖", "爬行", "鸟", "哺乳", "脊椎", "蛙", "蜥蜴", "蛇", "恐龙", "鲸", "猫", "狗", "人"]
        }
        
        # 关键词匹配
        for level in range(5, -1, -1):  # 从高到低匹配
            if any(kw in description or kw in common_name for kw in level_keywords[level]):
                # 原核生物额外验证：不能有真核特征
                if level == 0:
                    eukaryote_features = ["叶绿体", "线粒体", "细胞核", "内质网", "高尔基体"]
                    if any(kw in description for kw in eukaryote_features):
                        continue
                return level
        
        # 基于器官复杂度推断
        organ_count = len([o for o in organs.values() if o.get("is_active", True)])
        if organ_count >= 5:
            return 4  # 器官级
        elif organ_count >= 3:
            return 3  # 组织级
        elif organ_count >= 1:
            return 2 if body_length > 0.1 else 1
        
        # 基于体型推断
        if body_length < 0.001:  # < 10微米
            return 0  # 原核生物
        elif body_length < 0.1:  # < 1毫米
            return 1  # 简单真核
        elif body_length < 1.0:  # < 1厘米
            return 2  # 简单多细胞
        elif body_length < 10.0:  # < 10厘米
            return 3  # 组织级
        else:
            return 4  # 器官级或更高
    
    def _get_complexity_constraints(self, complexity_level: str) -> dict:
        """获取复杂度等级的基础约束
        
        设计理念：允许自由演化，只限制"跳跃式"发展
        - 不限制能发展什么结构（让环境压力自然筛选）
        - 只限制原核/真核的基本分界（这是生物学硬约束）
        - 通过阶段系统保证渐进式发展
        """
        level = int(complexity_level.split("_")[1]) if "_" in complexity_level else 1
        
        # 极简约束：只区分原核/真核的根本差异
        if level == 0:  # 原核生物
            return {
                # 原核生物的唯一硬约束：不能有真核细胞器
                # （因为这需要内共生事件，不是渐进演化能达到的）
                "origin_type": "prokaryote",
                "hard_forbidden": ["真核鞭毛", "纤毛", "线粒体", "叶绿体", "细胞核", "内质网", "高尔基体"],
                "max_organ_stage": 4,
            }
        else:  # 真核生物（等级1-5）
            return {
                "origin_type": "eukaryote", 
                "hard_forbidden": [],  # 真核生物可以自由发展任何结构
                "max_organ_stage": 4,
            }
    
    def _summarize_organs(self, species: Species) -> str:
        """生成器官系统的文本摘要，包含进化阶段信息"""
        organs = species.organs or {}
        
        if not organs:
            return "无已记录的器官系统"
        
        summaries = []
        for category, organ_data in organs.items():
            if not organ_data.get("is_active", True):
                continue
            
            organ_type = organ_data.get("type", "未知")
            stage = organ_data.get("evolution_stage", 4)  # 默认已完善
            progress = organ_data.get("evolution_progress", 1.0)
            
            # 阶段描述
            stage_names = {0: "无", 1: "原基", 2: "初级", 3: "功能化", 4: "完善"}
            stage_name = stage_names.get(stage, "完善")
            
            # 构建摘要
            category_names = {
                "locomotion": "运动系统",
                "sensory": "感觉系统", 
                "metabolic": "代谢系统",
                "digestive": "消化系统",
                "defense": "防御系统",
                "reproductive": "生殖系统"
            }
            cat_name = category_names.get(category, category)
            
            if stage < 4:
                summaries.append(f"- {cat_name}: {organ_type}（阶段{stage}/{stage_name}，进度{progress*100:.0f}%）")
            else:
                summaries.append(f"- {cat_name}: {organ_type}（完善）")
        
        return "\n".join(summaries) if summaries else "无已记录的器官系统"
    
    def _validate_gradual_evolution(
        self, 
        organ_evolution: list, 
        parent_organs: dict,
        biological_domain: str
    ) -> tuple[bool, list]:
        """验证器官进化是否符合渐进式原则
        
        设计理念：最小限制，最大自由
        - 只验证"渐进式"（不能跳跃）
        - 只验证"原核/真核分界"（硬性生物学约束）
        - 其他一切都允许，让环境压力自然筛选
        
        返回：(是否有效, 过滤后的有效进化列表)
        """
        if not organ_evolution:
            return True, []
        
        valid_evolutions = []
        
        # 获取基础约束
        constraints = self._get_complexity_constraints(biological_domain)
        hard_forbidden = constraints.get("hard_forbidden", [])
        max_stage = constraints.get("max_organ_stage", 4)
        origin_type = constraints.get("origin_type", "eukaryote")
        
        for evo in organ_evolution:
            if not isinstance(evo, dict):
                continue
            
            category = evo.get("category", "")
            action = evo.get("action", "")
            current_stage = evo.get("current_stage", 0)
            target_stage = evo.get("target_stage", 0)
            structure_name = evo.get("structure_name", "")
            
            # === 核心验证1：阶段跳跃限制（渐进式核心） ===
            stage_jump = target_stage - current_stage
            if stage_jump > 2:
                logger.info(f"[渐进式] 修正跳跃: {structure_name} {current_stage}→{target_stage} 改为 →{min(current_stage + 2, max_stage)}")
                target_stage = min(current_stage + 2, max_stage)
                evo["target_stage"] = target_stage
            
            # === 核心验证2：新器官从原基开始 ===
            if action == "initiate" and target_stage > 1:
                logger.info(f"[渐进式] 新器官从原基开始: {structure_name}")
                evo["target_stage"] = 1
            
            # === 核心验证3：原核/真核硬性分界 ===
            # 这是唯一的"禁止"规则，因为这需要内共生事件
            if origin_type == "prokaryote" and hard_forbidden:
                if any(f in structure_name for f in hard_forbidden):
                    logger.warning(
                        f"[生物学约束] 原核生物不能发展真核结构: {structure_name} "
                        f"(需要内共生事件，非渐进演化)"
                    )
                    continue
            
            # === 验证4：enhance操作需要父代有该器官 ===
            if action == "enhance":
                if category not in parent_organs:
                    # 自动转为initiate，允许发展新器官
                    logger.debug(f"[器官] {category}不存在，转为新发展")
                    evo["action"] = "initiate"
                    evo["current_stage"] = 0
                    evo["target_stage"] = 1
                else:
                    # 使用父代实际阶段
                    actual_stage = parent_organs[category].get("evolution_stage", 4)
                    if current_stage != actual_stage:
                        evo["current_stage"] = actual_stage
                        if target_stage - actual_stage > 2:
                            evo["target_stage"] = min(actual_stage + 2, max_stage)
            
            valid_evolutions.append(evo)
        
        # 限制每次分化最多3个器官变化（放宽限制）
        if len(valid_evolutions) > 3:
            logger.info(f"[器官验证] 单次分化器官变化限制为3个")
            valid_evolutions = valid_evolutions[:3]
        
        return True, valid_evolutions

