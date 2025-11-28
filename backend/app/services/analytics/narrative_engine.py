"""叙事生成引擎 - 基于 Embedding 检索生成演化故事

【核心功能】
1. 事件 Embedding 化 - 为游戏事件生成向量表示
2. 相似事件检索 - 找到历史上相似的事件（避免重复叙事）
3. 叙事生成 - 利用 LLM 生成连贯的演化故事
4. 时代划分 - 通过事件聚类识别演化"时代"
5. 物种传记 - 生成物种的完整演化历程叙事

【v2.0 优化】
- 使用批量 embedding 接口
- 利用 EmbeddingService 的事件索引
- 批量记录事件，减少 API 调用

【用途】
- 生成回合报告的叙事部分
- 创建演化史时间线
- 为玩家解释发生了什么
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ...ai.prompts.embedding import EMBEDDING_PROMPTS

if TYPE_CHECKING:
    from ...models.species import Species, LineageEvent
    from ...models.taxonomy import EmbeddedEvent
    from ..system.embedding import EmbeddingService
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


@dataclass
class EventRecord:
    """事件记录（内存结构）"""
    id: int
    event_type: str
    turn_index: int
    title: str
    description: str
    embedding: np.ndarray | None = None
    related_species: list[str] = field(default_factory=list)
    severity: float = 0.0
    novelty_score: float = 0.0
    payload: dict = field(default_factory=dict)


@dataclass
class Era:
    """演化时代"""
    name: str
    start_turn: int
    end_turn: int
    key_events: list[EventRecord]
    summary: str = ""
    defining_changes: list[str] = field(default_factory=list)


@dataclass
class NarrativeResult:
    """叙事生成结果"""
    narrative: str
    key_events: list[EventRecord]
    related_species: list[str]
    novelty_info: dict[str, float]  # 事件新颖度信息


class NarrativeEngine:
    """叙事生成引擎
    
    使用 embedding 检索和 LLM 生成演化叙事
    """
    
    # 事件类型描述模板
    EVENT_TEMPLATES = {
        "speciation": "物种{parent}分化产生了新物种{children}",
        "extinction": "物种{species}灭绝，从{region}消失",
        "mass_extinction": "发生大规模灭绝事件，{count}个物种消亡",
        "adaptation": "物种{species}演化出了{trait}特征",
        "migration": "物种{species}从{from_region}迁徙到{to_region}",
        "climate_change": "气候变化：{description}",
        "predation": "物种{predator}开始捕食{prey}",
        "symbiosis": "物种{species_a}与{species_b}形成{type}共生关系",
        "population_boom": "物种{species}种群爆发，数量增长{growth}%",
        "population_crash": "物种{species}种群崩溃，数量下降{decline}%",
    }

    def __init__(
        self,
        embedding_service: 'EmbeddingService',
        router: 'ModelRouter | None' = None
    ):
        self.embeddings = embedding_service
        self.router = router
        
        # 事件历史（按回合索引）
        self._events: list[EventRecord] = []
        self._event_counter = 0
        
        # 待索引的事件（批量处理）
        self._pending_events: list[EventRecord] = []

    def record_event(
        self,
        event_type: str,
        turn_index: int,
        title: str = "",
        description: str = "",
        related_species: list[str] | None = None,
        severity: float = 0.5,
        payload: dict | None = None
    ) -> EventRecord:
        """记录一个事件（延迟计算 embedding）"""
        self._event_counter += 1
        
        # 生成事件描述（如果没有提供）
        if not description and event_type in self.EVENT_TEMPLATES:
            description = self.EVENT_TEMPLATES[event_type].format(**(payload or {}))
        
        # 生成标题（如果没有提供）
        if not title:
            title = f"第{turn_index}回合: {event_type}"
        
        event = EventRecord(
            id=self._event_counter,
            event_type=event_type,
            turn_index=turn_index,
            title=title,
            description=description,
            embedding=None,  # 延迟计算
            related_species=related_species or [],
            severity=severity,
            payload=payload or {}
        )
        
        self._events.append(event)
        self._pending_events.append(event)
        
        return event
    
    def flush_pending_events(self) -> int:
        """批量处理待索引的事件（在回合结束时调用）
        
        【优化】使用批量新颖度计算，提高效率
        """
        if not self._pending_events:
            return 0
        
        # 批量生成 embedding
        texts = [f"{e.title}. {e.description}" for e in self._pending_events]
        try:
            embeddings = self.embeddings.embed(texts)
            
            # 更新事件的 embedding
            for event, emb in zip(self._pending_events, embeddings):
                event.embedding = np.array(emb)
            
            # 【优化】批量计算新颖度
            novelty_scores = self._compute_novelty_batch(self._pending_events)
            for event, score in zip(self._pending_events, novelty_scores):
                event.novelty_score = score
            
            # 批量索引事件
            events_to_index = [
                {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "metadata": {
                        "turn_index": e.turn_index,
                        "event_type": e.event_type,
                        "severity": e.severity,
                    }
                }
                for e in self._pending_events
            ]
            self.embeddings.index_events_batch(events_to_index)
            
        except Exception as e:
            logger.warning(f"[NarrativeEngine] 批量处理事件失败: {e}")
        
        count = len(self._pending_events)
        self._pending_events.clear()
        return count

    def _compute_novelty(self, event: EventRecord) -> float:
        """计算单个事件的新颖度（与历史事件的差异）"""
        if event.embedding is None or not self._events:
            return 1.0
        
        # 找到相同类型的历史事件
        same_type_events = [
            e for e in self._events 
            if e.event_type == event.event_type and e.embedding is not None
        ]
        
        if not same_type_events:
            return 1.0
        
        # 计算与历史事件的最大相似度
        max_similarity = 0.0
        event_norm = event.embedding / (np.linalg.norm(event.embedding) + 1e-8)
        
        for hist_event in same_type_events[-20:]:  # 只看最近20个同类事件
            hist_norm = hist_event.embedding / (np.linalg.norm(hist_event.embedding) + 1e-8)
            similarity = float(np.dot(event_norm, hist_norm))
            max_similarity = max(max_similarity, similarity)
        
        # 新颖度 = 1 - 最大相似度
        return 1.0 - max_similarity
    
    def _compute_novelty_batch(self, events: list[EventRecord]) -> list[float]:
        """【优化】批量计算事件新颖度
        
        使用向量化计算，比逐个计算更高效。
        
        Args:
            events: 要计算新颖度的事件列表
            
        Returns:
            新颖度分数列表
        """
        if not events:
            return []
        
        # 筛选有embedding的事件
        valid_events = [(i, e) for i, e in enumerate(events) if e.embedding is not None]
        if not valid_events:
            return [1.0] * len(events)
        
        # 按事件类型分组历史事件
        type_to_history: dict[str, list[np.ndarray]] = {}
        for e in self._events[-100:]:  # 只看最近100个事件
            if e.embedding is not None:
                if e.event_type not in type_to_history:
                    type_to_history[e.event_type] = []
                type_to_history[e.event_type].append(e.embedding)
        
        # 计算新颖度
        novelty_scores = [1.0] * len(events)
        
        for idx, event in valid_events:
            hist_embeddings = type_to_history.get(event.event_type, [])
            
            if not hist_embeddings:
                novelty_scores[idx] = 1.0
                continue
            
            # 使用最近20个同类事件
            hist_embeddings = hist_embeddings[-20:]
            
            # 向量化计算相似度
            event_norm = event.embedding / (np.linalg.norm(event.embedding) + 1e-8)
            hist_matrix = np.array(hist_embeddings)
            hist_norms = np.linalg.norm(hist_matrix, axis=1, keepdims=True)
            hist_norms[hist_norms == 0] = 1.0
            hist_normalized = hist_matrix / hist_norms
            
            similarities = hist_normalized @ event_norm
            max_similarity = float(np.max(similarities))
            
            novelty_scores[idx] = 1.0 - max(0.0, min(1.0, max_similarity))
        
        return novelty_scores
    
    def _reindex_events_to_store(self) -> int:
        """重新索引事件到EmbeddingService的向量存储
        
        在从存档加载后调用，确保事件搜索功能正常工作。
        
        Returns:
            索引的事件数量
        """
        events_with_embedding = [
            e for e in self._events if e.embedding is not None
        ]
        
        if not events_with_embedding:
            return 0
        
        events_to_index = [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "metadata": {
                    "turn_index": e.turn_index,
                    "event_type": e.event_type,
                    "severity": e.severity,
                }
            }
            for e in events_with_embedding
        ]
        
        try:
            count = self.embeddings.index_events_batch(events_to_index)
            logger.info(f"[NarrativeEngine] 重新索引 {count} 个事件")
            return count
        except Exception as e:
            logger.warning(f"[NarrativeEngine] 重新索引事件失败: {e}")
            return 0

    def find_similar_events(
        self,
        query: str | EventRecord,
        top_k: int = 5,
        exclude_recent: int = 0,
        event_type: str | None = None
    ) -> list[tuple[EventRecord, float]]:
        """找到相似的历史事件
        
        Args:
            query: 查询文本或事件
            top_k: 返回数量
            exclude_recent: 排除最近N回合的事件
            event_type: 限制事件类型
        
        Returns:
            [(事件, 相似度), ...]
        """
        # 获取查询文本
        if isinstance(query, EventRecord):
            query_text = f"{query.title}. {query.description}"
            current_turn = query.turn_index
        else:
            query_text = query
            current_turn = max((e.turn_index for e in self._events), default=0)
        
        # 使用向量索引搜索
        search_results = self.embeddings.search_events(query_text, top_k * 2, threshold=0.0)
        
        # 构建事件 ID 到对象的映射
        event_map = {e.id: e for e in self._events}
        
        results = []
        for r in search_results:
            event_id = int(r.id) if isinstance(r.id, str) else r.id
            event = event_map.get(event_id)
            if event is None:
                continue
            
            # 过滤条件
            if exclude_recent and event.turn_index > current_turn - exclude_recent:
                continue
            if event_type and event.event_type != event_type:
                continue
            
            results.append((event, r.score))
            
            if len(results) >= top_k:
                break
        
        return results

    async def generate_turn_narrative(
        self,
        turn_index: int,
        events: list[EventRecord] | None = None,
        species_changes: list[dict] | None = None
    ) -> NarrativeResult:
        """生成回合叙事"""
        # 获取本回合的事件
        if events is None:
            events = [e for e in self._events if e.turn_index == turn_index]
        
        if not events:
            return NarrativeResult(
                narrative="这一回合相对平静，生态系统继续稳定演化。",
                key_events=[],
                related_species=[],
                novelty_info={}
            )
        
        # 收集相关物种
        related_species = set()
        for e in events:
            related_species.update(e.related_species)
        
        # 计算新颖度信息
        novelty_info = {e.title: e.novelty_score for e in events}
        
        # 检索相似历史事件
        similar_events = []
        for event in events[:3]:  # 最多检索3个事件的相似事件
            similar = self.find_similar_events(event, top_k=2, exclude_recent=3)
            similar_events.extend(similar)
        
        # 生成叙事
        if self.router:
            narrative = await self._generate_narrative_with_llm(
                events, similar_events, species_changes
            )
        else:
            narrative = self._generate_narrative_simple(events)
        
        return NarrativeResult(
            narrative=narrative,
            key_events=events,
            related_species=list(related_species),
            novelty_info=novelty_info
        )

    def _generate_narrative_simple(self, events: list[EventRecord]) -> str:
        """简单叙事生成（不使用 LLM）"""
        parts = []
        
        # 按严重程度排序
        sorted_events = sorted(events, key=lambda e: e.severity, reverse=True)
        
        for event in sorted_events[:5]:
            if event.novelty_score > 0.7:
                prefix = "值得注意的是，"
            elif event.novelty_score > 0.3:
                prefix = ""
            else:
                prefix = "延续之前的趋势，"
            
            parts.append(f"{prefix}{event.description}")
        
        return " ".join(parts)

    async def _generate_narrative_with_llm(
        self,
        events: list[EventRecord],
        similar_events: list[tuple[EventRecord, float]],
        species_changes: list[dict] | None
    ) -> str:
        """使用 LLM 生成叙事"""
        # 构建事件列表
        event_desc = []
        for e in events:
            novelty_tag = "【新】" if e.novelty_score > 0.7 else ""
            event_desc.append(f"- {novelty_tag}{e.title}: {e.description}")
        
        # 构建相似历史事件参考
        similar_desc = []
        for e, sim in similar_events[:3]:
            similar_desc.append(f"- [回合{e.turn_index}] {e.title} (相似度{sim:.2f})")
        
        # 使用模板化 prompt
        prompt = EMBEDDING_PROMPTS["embedding_narrative"].format(
            events_description="\n".join(event_desc),
            similar_events="\n".join(similar_desc) if similar_desc else "无历史相似事件"
        )

        try:
            narrative = await self.router.chat(prompt, capability="turn_report")
            return narrative
        except Exception as e:
            logger.error(f"LLM 叙事生成失败: {e}")
            return self._generate_narrative_simple(events)

    def identify_eras(
        self,
        start_turn: int = 0,
        end_turn: int | None = None,
        min_events_per_era: int = 3
    ) -> list[Era]:
        """识别演化时代（通过事件聚类）"""
        # 筛选时间范围内的事件
        if end_turn is None:
            end_turn = max((e.turn_index for e in self._events), default=0)
        
        filtered_events = [
            e for e in self._events 
            if start_turn <= e.turn_index <= end_turn and e.embedding is not None
        ]
        
        if len(filtered_events) < min_events_per_era:
            return []
        
        # 简单的时代划分：基于事件密度和类型变化
        eras = []
        current_era_events = []
        current_era_start = start_turn
        
        for event in sorted(filtered_events, key=lambda e: e.turn_index):
            current_era_events.append(event)
            
            # 判断是否应该开始新时代（大灭绝或长时间间隔）
            should_split = False
            if event.event_type == "mass_extinction":
                should_split = True
            elif len(current_era_events) >= 10:
                should_split = True
            
            if should_split and len(current_era_events) >= min_events_per_era:
                era = Era(
                    name=self._generate_era_name(current_era_events),
                    start_turn=current_era_start,
                    end_turn=event.turn_index,
                    key_events=current_era_events.copy()
                )
                eras.append(era)
                current_era_events = []
                current_era_start = event.turn_index + 1
        
        # 处理最后一个时代
        if len(current_era_events) >= min_events_per_era:
            era = Era(
                name=self._generate_era_name(current_era_events),
                start_turn=current_era_start,
                end_turn=end_turn,
                key_events=current_era_events
            )
            eras.append(era)
        
        return eras

    def _generate_era_name(self, events: list[EventRecord]) -> str:
        """为时代生成名称"""
        # 统计事件类型
        type_counts = {}
        for e in events:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1
        
        dominant_type = max(type_counts, key=type_counts.get) if type_counts else "evolution"
        
        era_names = {
            "speciation": "物种大分化时代",
            "extinction": "灭绝时代",
            "mass_extinction": "大灭绝时代",
            "adaptation": "适应辐射时代",
            "migration": "大迁徙时代",
            "climate_change": "气候剧变时代",
        }
        
        return era_names.get(dominant_type, "演化时代")

    async def generate_species_biography(
        self,
        species: 'Species',
        lineage_events: list = None
    ) -> str:
        """生成物种传记"""
        # 收集与该物种相关的事件
        related_events = [
            e for e in self._events 
            if species.lineage_code in e.related_species
        ]
        
        if not related_events and not lineage_events:
            return f"{species.common_name}是一个相对稳定的物种，在其演化历程中没有经历重大事件。"
        
        # 按时间排序
        events_timeline = sorted(related_events, key=lambda e: e.turn_index)
        
        if self.router:
            # 使用模板化 prompt
            events_text = "\n".join([
                f"回合{e.turn_index}: {e.description}" 
                for e in events_timeline[:10]
            ]) or "尚无记录的演化事件"
            
            prompt = EMBEDDING_PROMPTS["embedding_biography"].format(
                species_name=species.common_name,
                latin_name=species.latin_name,
                description=species.description,
                created_turn=species.created_turn,
                status=species.status,
                parent_code=species.parent_code or "原始物种",
                events_timeline=events_text
            )

            try:
                return await self.router.chat(prompt, capability="turn_report")
            except Exception as e:
                logger.error(f"生成物种传记失败: {e}")
        
        # 简单传记
        parts = [f"{species.common_name}于第{species.created_turn}回合出现。"]
        for event in events_timeline[:5]:
            parts.append(f"在第{event.turn_index}回合，{event.description}")
        
        return " ".join(parts)

    def export_for_save(self) -> dict[str, Any]:
        """导出事件数据用于存档"""
        return {
            "version": "1.0",
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "turn_index": e.turn_index,
                    "title": e.title,
                    "description": e.description,
                    "embedding": e.embedding.tolist() if e.embedding is not None else None,
                    "related_species": e.related_species,
                    "severity": e.severity,
                    "novelty_score": e.novelty_score,
                    "payload": e.payload
                }
                for e in self._events
            ],
            "event_counter": self._event_counter
        }

    def import_from_save(self, data: dict[str, Any]) -> None:
        """从存档导入事件数据
        
        【优化】除了恢复事件数据，还要重新索引到EmbeddingService，
        确保搜索功能正常工作。
        """
        if not data or "events" not in data:
            return
        
        self._events.clear()
        self._event_counter = data.get("event_counter", 0)
        
        for e_data in data["events"]:
            embedding = np.array(e_data["embedding"]) if e_data.get("embedding") else None
            event = EventRecord(
                id=e_data["id"],
                event_type=e_data["event_type"],
                turn_index=e_data["turn_index"],
                title=e_data.get("title", ""),
                description=e_data.get("description", ""),
                embedding=embedding,
                related_species=e_data.get("related_species", []),
                severity=e_data.get("severity", 0.5),
                novelty_score=e_data.get("novelty_score", 0.0),
                payload=e_data.get("payload", {})
            )
            self._events.append(event)
        
        logger.info(f"从存档导入 {len(self._events)} 个事件记录")
        
        # 【优化】重新索引事件到EmbeddingService
        self._reindex_events_to_store()

    def get_event_stats(self) -> dict[str, Any]:
        """获取事件统计"""
        type_counts = {}
        for e in self._events:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1
        
        return {
            "total_events": len(self._events),
            "type_counts": type_counts,
            "turn_range": (
                min((e.turn_index for e in self._events), default=0),
                max((e.turn_index for e in self._events), default=0)
            ) if self._events else (0, 0),
            "avg_novelty": np.mean([e.novelty_score for e in self._events]) if self._events else 0.0
        }

