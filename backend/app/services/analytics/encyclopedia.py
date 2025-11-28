"""智能百科系统 - 基于 Embedding 的语义搜索和问答

【核心功能】
1. 语义搜索 - 用自然语言搜索物种、事件、概念
2. 智能问答 (RAG) - 检索相关信息后用 LLM 回答问题
3. 演化解释 - 解释物种为什么这样演化
4. 智能提示 - 为玩家提供游戏建议

【v2.0 优化】
- 使用 EmbeddingService 的向量索引，支持大规模物种
- 批量操作接口，减少 API 调用
- 增量索引更新

【用途】
- 百科搜索：用户输入"会飞的捕食者"找到相关物种
- 问答：用户问"为什么这个物种有毒刺？"获得解释
- 对比分析：对比两个物种的差异
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from ...ai.prompts.embedding import EMBEDDING_PROMPTS
from ..system.species_cache import get_species_cache

if TYPE_CHECKING:
    from ...models.species import Species
    from ..system.embedding import EmbeddingService
    from ..system.vector_store import SearchResult as VectorSearchResult
    from ...ai.model_router import ModelRouter
    from .taxonomy import TaxonomyResult
    from .narrative_engine import NarrativeEngine, EventRecord

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    result_type: str  # "species", "event", "concept"
    id: str | int
    title: str
    description: str
    similarity: float
    metadata: dict = field(default_factory=dict)


@dataclass
class QAResponse:
    """问答响应"""
    question: str
    answer: str
    sources: list[SearchResult]
    confidence: float
    follow_up_questions: list[str] = field(default_factory=list)


@dataclass
class EvolutionExplanation:
    """演化解释"""
    species_code: str
    species_name: str
    explanation: str
    key_factors: list[str]
    trait_explanations: dict[str, str]
    related_events: list[dict]


@dataclass
class GameHint:
    """游戏提示"""
    hint_type: str  # "evolution", "competition", "warning", "opportunity"
    message: str
    priority: str  # "low", "medium", "high", "critical"
    related_species: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)


class EncyclopediaService:
    """智能百科服务
    
    提供语义搜索、问答、解释等功能
    
    【v2.0 优化】
    - 使用 EmbeddingService 的向量索引功能
    - 批量操作，支持大规模物种
    - 增量更新索引
    """

    # 预定义的游戏概念（用于搜索）
    GAME_CONCEPTS = {
        "营养级": {
            "description": "营养级表示生物在食物链中的位置。T1是生产者（如植物），T2是初级消费者（草食动物），T3及以上是捕食者。",
            "keywords": ["食物链", "捕食", "生产者", "消费者"]
        },
        "生态位": {
            "description": "生态位是物种在生态系统中的功能角色，包括其栖息地、食物来源、活动时间等。生态位重叠会导致竞争。",
            "keywords": ["竞争", "资源", "栖息地", "适应"]
        },
        "物种分化": {
            "description": "物种分化是一个物种演化成多个新物种的过程，通常由地理隔离、生态隔离或行为隔离触发。",
            "keywords": ["演化", "隔离", "新物种", "分支"]
        },
        "适应辐射": {
            "description": "适应辐射是物种快速分化以填充不同生态位的演化模式，通常在新环境开放或竞争者灭绝后发生。",
            "keywords": ["快速分化", "多样化", "生态位"]
        },
        "大灭绝": {
            "description": "大灭绝是短时间内大量物种灭绝的事件，通常由环境剧变引起。灭绝后常伴随幸存者的适应辐射。",
            "keywords": ["灭绝", "环境变化", "生存危机"]
        },
        "趋同演化": {
            "description": "趋同演化是不同物种在相似环境压力下演化出相似特征的现象，如海豚和鲨鱼都有流线型身体。",
            "keywords": ["相似特征", "环境压力", "独立演化"]
        },
        "共生关系": {
            "description": "共生是两个物种之间的紧密生态关系，包括互利共生、偏利共生和寄生。",
            "keywords": ["互利", "寄生", "依赖", "合作"]
        },
    }

    def __init__(
        self,
        embedding_service: 'EmbeddingService',
        router: 'ModelRouter | None' = None
    ):
        self.embeddings = embedding_service
        self.router = router
        
        # 概念索引已初始化标记
        self._concepts_initialized = False
    
    @property
    def _species_cache(self):
        """使用全局物种缓存（避免维护冗余缓存）"""
        return get_species_cache()

    def _ensure_concepts_indexed(self) -> None:
        """确保概念已索引（延迟初始化）"""
        if self._concepts_initialized:
            return
        
        try:
            # 批量索引概念
            self.embeddings.index_concepts(self.GAME_CONCEPTS)
            self._concepts_initialized = True
            logger.info(f"[Encyclopedia] 概念索引初始化完成: {len(self.GAME_CONCEPTS)} 个")
        except Exception as e:
            logger.warning(f"[Encyclopedia] 概念索引初始化失败: {e}")

    def update_species_cache(self, species_list: Sequence['Species']) -> None:
        """通知本服务物种列表已更新
        
        【优化】物种数据由全局 SpeciesCacheManager 统一管理，
        此方法只确保概念索引已初始化。
        """
        # 确保概念索引已初始化（首次调用时）
        self._ensure_concepts_indexed()
    
    def build_species_index(self, species_list: Sequence['Species']) -> None:
        """构建物种搜索索引（完整版本，包含索引更新）
        
        注意：如果通过 EmbeddingIntegrationService 调用，
        应该使用 update_species_cache 方法以避免重复索引。
        """
        # 更新物种缓存
        self.update_species_cache(species_list)
        
        # 使用 EmbeddingService 的索引功能（支持增量更新）
        count = self.embeddings.index_species(species_list)
        if count > 0:
            logger.info(f"[Encyclopedia] 物种索引更新: {count} 个（总计 {len(species_list)} 个）")

    def add_events_to_index(self, events: list['EventRecord']) -> None:
        """添加事件到索引（批量操作）"""
        events_to_index = []
        for event in events:
            events_to_index.append({
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "metadata": {
                    "turn_index": event.turn_index,
                    "event_type": event.event_type
                }
            })
        
        if events_to_index:
            self.embeddings.index_events_batch(events_to_index)

    def search(
        self,
        query: str,
        search_types: list[str] | None = None,
        top_k: int = 10,
        threshold: float = 0.0
    ) -> list[SearchResult]:
        """语义搜索（使用向量索引）
        
        Args:
            query: 搜索查询
            search_types: 搜索类型列表 ["species", "event", "concept"]
            top_k: 返回数量
            threshold: 相似度阈值
        
        Returns:
            搜索结果列表
        """
        if search_types is None:
            search_types = ["species", "event", "concept"]
        
        results = []
        
        # 搜索物种（使用向量索引）
        if "species" in search_types:
            species_results = self.embeddings.search_species(query, top_k, threshold)
            for r in species_results:
                species = self._species_cache.get(r.id)
                results.append(SearchResult(
                    result_type="species",
                    id=r.id,
                    title=r.metadata.get("common_name", r.id),
                    description=species.description[:200] if species else "",
                    similarity=r.score,
                    metadata={
                        "latin_name": r.metadata.get("latin_name", ""),
                        "status": r.metadata.get("status", ""),
                        "trophic_level": r.metadata.get("trophic_level", 0)
                    }
                ))
        
        # 搜索事件（使用向量索引）
        if "event" in search_types:
            event_results = self.embeddings.search_events(query, top_k, threshold)
            for r in event_results:
                results.append(SearchResult(
                    result_type="event",
                    id=r.id,
                    title=r.metadata.get("title", ""),
                    description=r.metadata.get("description", "")[:200],
                    similarity=r.score,
                    metadata={
                        "turn_index": r.metadata.get("turn_index", 0),
                        "event_type": r.metadata.get("event_type", "")
                    }
                ))
        
        # 搜索概念（使用向量索引）
        if "concept" in search_types:
            self._ensure_concepts_indexed()
            concept_results = self.embeddings.search_concepts(query, top_k, threshold)
            for r in concept_results:
                results.append(SearchResult(
                    result_type="concept",
                    id=r.id,
                    title=r.id,
                    description=r.metadata.get("description", "")[:200],
                    similarity=r.score,
                    metadata={"keywords": r.metadata.get("keywords", [])}
                ))
        
        # 按相似度排序
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    async def answer_question(self, question: str) -> QAResponse:
        """智能问答 (RAG)
        
        Args:
            question: 用户问题
        
        Returns:
            问答响应
        """
        # 1. 检索相关信息
        search_results = self.search(question, top_k=5, threshold=0.3)
        
        if not search_results:
            return QAResponse(
                question=question,
                answer="抱歉，我没有找到与您问题相关的信息。请尝试更具体的问题或不同的关键词。",
                sources=[],
                confidence=0.0,
                follow_up_questions=[]
            )
        
        # 2. 构建上下文
        context_parts = []
        for result in search_results:
            if result.result_type == "species":
                species = self._species_cache.get(result.id)
                if species:
                    context_parts.append(f"【物种: {species.common_name}】\n{species.description}")
            elif result.result_type == "concept":
                context_parts.append(f"【概念: {result.title}】\n{result.description}")
            elif result.result_type == "event":
                context_parts.append(f"【事件: {result.title}】\n{result.description}")
        
        context = "\n\n".join(context_parts)
        
        # 3. 使用 LLM 生成回答
        if self.router:
            answer = await self._generate_answer_with_llm(question, context, search_results)
        else:
            answer = self._generate_answer_simple(search_results)
        
        # 4. 生成后续问题建议
        follow_ups = self._generate_follow_up_questions(question, search_results)
        
        # 5. 计算置信度
        confidence = max(r.similarity for r in search_results) if search_results else 0.0
        
        return QAResponse(
            question=question,
            answer=answer,
            sources=search_results[:3],
            confidence=confidence,
            follow_up_questions=follow_ups
        )

    def _generate_answer_simple(self, results: list[SearchResult]) -> str:
        """简单回答生成"""
        if not results:
            return "没有找到相关信息。"
        
        best = results[0]
        if best.result_type == "species":
            return f"{best.title}: {best.description}"
        elif best.result_type == "concept":
            return best.description
        else:
            return f"在第{best.metadata.get('turn_index', '?')}回合: {best.description}"

    async def _generate_answer_with_llm(
        self,
        question: str,
        context: str,
        results: list[SearchResult]
    ) -> str:
        """使用 LLM 生成回答"""
        # 使用模板化 prompt
        prompt = EMBEDDING_PROMPTS["embedding_qa"].format(
            context=context,
            question=question
        )

        try:
            return await self.router.chat(prompt, capability="turn_report")
        except Exception as e:
            logger.error(f"LLM 问答失败: {e}")
            return self._generate_answer_simple(results)

    def _generate_follow_up_questions(
        self,
        question: str,
        results: list[SearchResult]
    ) -> list[str]:
        """生成后续问题建议"""
        follow_ups = []
        
        for result in results[:3]:
            if result.result_type == "species":
                follow_ups.append(f"{result.title}是如何演化的？")
                follow_ups.append(f"{result.title}的主要天敌是什么？")
            elif result.result_type == "concept":
                follow_ups.append(f"能举个{result.title}的例子吗？")
            elif result.result_type == "event":
                follow_ups.append(f"这个事件对生态系统有什么影响？")
        
        return follow_ups[:3]

    async def explain_species_evolution(
        self,
        species: 'Species',
        related_events: list[dict] | None = None,
        taxonomy_info: dict | None = None
    ) -> EvolutionExplanation:
        """解释物种的演化原因
        
        Args:
            species: 目标物种
            related_events: 相关事件列表
            taxonomy_info: 分类学信息
        
        Returns:
            演化解释
        """
        # 收集解释材料
        key_factors = []
        trait_explanations = {}
        
        # 分析特征
        for trait, value in species.abstract_traits.items():
            if value > 7:
                key_factors.append(f"高{trait}")
                trait_explanations[trait] = f"该物种具有较高的{trait}（{value:.1f}/10）"
            elif value < 3:
                key_factors.append(f"低{trait}")
                trait_explanations[trait] = f"该物种的{trait}较低（{value:.1f}/10）"
        
        # 分析器官
        for organ_cat, organ_data in species.organs.items():
            if isinstance(organ_data, dict) and organ_data.get("is_active"):
                organ_type = organ_data.get("type", "未知")
                key_factors.append(f"发达的{organ_type}")
        
        # 生成解释
        if self.router:
            explanation = await self._generate_evolution_explanation_llm(
                species, key_factors, related_events, taxonomy_info
            )
        else:
            explanation = self._generate_evolution_explanation_simple(
                species, key_factors
            )
        
        return EvolutionExplanation(
            species_code=species.lineage_code,
            species_name=species.common_name,
            explanation=explanation,
            key_factors=key_factors,
            trait_explanations=trait_explanations,
            related_events=related_events or []
        )

    def _generate_evolution_explanation_simple(
        self,
        species: 'Species',
        key_factors: list[str]
    ) -> str:
        """简单解释生成"""
        parts = [f"{species.common_name}的演化受到以下因素影响："]
        
        for factor in key_factors[:5]:
            parts.append(f"- {factor}")
        
        if species.parent_code:
            parts.append(f"该物种从{species.parent_code}分化而来。")
        
        return "\n".join(parts)

    async def _generate_evolution_explanation_llm(
        self,
        species: 'Species',
        key_factors: list[str],
        related_events: list[dict] | None,
        taxonomy_info: dict | None
    ) -> str:
        """使用 LLM 生成演化解释"""
        # 构建事件文本
        events_text = ""
        if related_events:
            events_text = "\n".join([
                f"- {e.get('description', '')}" for e in related_events[:5]
            ])
        
        # 构建分类文本
        taxonomy_text = str(taxonomy_info) if taxonomy_info else "尚未分类"
        
        # 使用模板化 prompt
        prompt = EMBEDDING_PROMPTS["embedding_explanation"].format(
            species_name=species.common_name,
            latin_name=species.latin_name,
            description=species.description,
            parent_code=species.parent_code or "原始物种",
            habitat_type=species.habitat_type,
            trophic_level=species.trophic_level,
            key_factors=", ".join(key_factors) if key_factors else "无特殊特征",
            related_events=events_text or "无相关事件记录",
            taxonomy_info=taxonomy_text
        )

        try:
            return await self.router.chat(prompt, capability="turn_report")
        except Exception as e:
            logger.error(f"生成演化解释失败: {e}")
            return self._generate_evolution_explanation_simple(species, key_factors)

    def generate_hints(
        self,
        species: 'Species',
        ecosystem_state: dict | None = None
    ) -> list[GameHint]:
        """生成游戏提示
        
        Args:
            species: 目标物种
            ecosystem_state: 生态系统状态（可选）
        
        Returns:
            提示列表
        """
        hints = []
        
        # 1. 种群状态提示
        population = species.morphology_stats.get("population", 0)
        if population < 1000:
            hints.append(GameHint(
                hint_type="warning",
                message=f"{species.common_name}种群数量过低（{int(population)}），面临灭绝风险！",
                priority="critical",
                related_species=[species.lineage_code],
                suggested_actions=["考虑保护该物种", "减少环境压力"]
            ))
        elif population > 1000000:
            hints.append(GameHint(
                hint_type="opportunity",
                message=f"{species.common_name}种群繁盛，可能即将分化！",
                priority="medium",
                related_species=[species.lineage_code],
                suggested_actions=["观察分化趋势", "记录演化方向"]
            ))
        
        # 2. 特征极端化提示
        for trait, value in species.abstract_traits.items():
            if value >= 9:
                hints.append(GameHint(
                    hint_type="evolution",
                    message=f"{species.common_name}的{trait}已达到极限（{value:.1f}/10），可能形成新的生态策略。",
                    priority="low",
                    related_species=[species.lineage_code]
                ))
        
        # 3. 栖息地转换潜力
        if species.habitat_type in ["coastal", "amphibious"]:
            hints.append(GameHint(
                hint_type="evolution",
                message=f"{species.common_name}生活在过渡环境，可能向陆地或海洋进一步适应。",
                priority="low",
                related_species=[species.lineage_code]
            ))
        
        return hints

    def compare_species(
        self,
        species_a: 'Species',
        species_b: 'Species'
    ) -> dict[str, Any]:
        """对比两个物种"""
        # 使用 EmbeddingService 计算相似度
        similarity = self.embeddings.get_species_similarity(
            species_a.lineage_code, 
            species_b.lineage_code
        )
        
        # 对比特征
        trait_diff = {}
        for trait in species_a.abstract_traits:
            val_a = species_a.abstract_traits.get(trait, 5)
            val_b = species_b.abstract_traits.get(trait, 5)
            if abs(val_a - val_b) > 2:
                trait_diff[trait] = {
                    species_a.common_name: val_a,
                    species_b.common_name: val_b,
                    "difference": val_a - val_b
                }
        
        # 对比栖息地
        same_habitat = species_a.habitat_type == species_b.habitat_type
        
        # 对比营养级
        trophic_diff = abs(species_a.trophic_level - species_b.trophic_level)
        
        return {
            "similarity": similarity,
            "same_habitat": same_habitat,
            "habitat_a": species_a.habitat_type,
            "habitat_b": species_b.habitat_type,
            "trophic_difference": trophic_diff,
            "trait_differences": trait_diff,
            "relationship": self._infer_relationship(similarity, same_habitat, trophic_diff)
        }

    def _infer_relationship(
        self,
        similarity: float,
        same_habitat: bool,
        trophic_diff: float
    ) -> str:
        """推断物种关系"""
        if similarity > 0.8:
            if same_habitat:
                return "可能是竞争关系（高度相似且同栖息地）"
            else:
                return "可能是趋同演化（高度相似但不同栖息地）"
        elif similarity > 0.5:
            if trophic_diff > 1:
                return "可能存在捕食关系（营养级差异大）"
            else:
                return "可能是远亲（中等相似度）"
        else:
            return "关系较远（低相似度）"

    def get_index_stats(self) -> dict[str, Any]:
        """获取索引统计"""
        index_stats = self.embeddings.get_index_stats()
        return {
            "species_count": index_stats.get("species", {}).get("size", 0),
            "event_count": index_stats.get("events", {}).get("size", 0),
            "concept_count": index_stats.get("concepts", {}).get("size", 0),
            "species_cache_count": len(self._species_cache),
        }

