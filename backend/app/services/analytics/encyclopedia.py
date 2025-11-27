"""智能百科系统 - 基于 Embedding 的语义搜索和问答

【核心功能】
1. 语义搜索 - 用自然语言搜索物种、事件、概念
2. 智能问答 (RAG) - 检索相关信息后用 LLM 回答问题
3. 演化解释 - 解释物种为什么这样演化
4. 智能提示 - 为玩家提供游戏建议

【用途】
- 百科搜索：用户输入"会飞的捕食者"找到相关物种
- 问答：用户问"为什么这个物种有毒刺？"获得解释
- 对比分析：对比两个物种的差异
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ...ai.prompts.embedding import EMBEDDING_PROMPTS

if TYPE_CHECKING:
    from ...models.species import Species
    from ..system.embedding import EmbeddingService
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
        
        # 索引
        self._species_index: dict[str, tuple[np.ndarray, 'Species']] = {}
        self._concept_index: dict[str, tuple[np.ndarray, dict]] = {}
        self._event_index: dict[int, tuple[np.ndarray, dict]] = {}
        
        # 初始化概念索引
        self._init_concept_index()

    def _init_concept_index(self) -> None:
        """初始化游戏概念索引"""
        for name, info in self.GAME_CONCEPTS.items():
            text = f"{name}. {info['description']}"
            try:
                vec = np.array(self.embeddings.embed_single(text))
                self._concept_index[name] = (vec, {"name": name, **info})
            except Exception as e:
                logger.warning(f"初始化概念 {name} 失败: {e}")

    def build_species_index(self, species_list: Sequence['Species']) -> None:
        """构建物种搜索索引"""
        self._species_index.clear()
        
        for sp in species_list:
            # 构建丰富的搜索文本
            search_text = f"{sp.common_name} {sp.latin_name}. {sp.description}"
            
            # 添加特征信息
            traits = []
            for trait, value in sp.abstract_traits.items():
                if value > 7:
                    traits.append(f"高{trait}")
                elif value < 3:
                    traits.append(f"低{trait}")
            if traits:
                search_text += f" 特征: {', '.join(traits)}"
            
            try:
                vec = np.array(self.embeddings.embed_single(search_text))
                self._species_index[sp.lineage_code] = (vec, sp)
            except Exception as e:
                logger.warning(f"索引物种 {sp.lineage_code} 失败: {e}")
        
        logger.info(f"物种索引构建完成: {len(self._species_index)} 个物种")

    def add_events_to_index(self, events: list['EventRecord']) -> None:
        """添加事件到索引"""
        for event in events:
            if event.embedding is not None:
                self._event_index[event.id] = (
                    event.embedding,
                    {
                        "id": event.id,
                        "title": event.title,
                        "description": event.description,
                        "turn_index": event.turn_index,
                        "event_type": event.event_type
                    }
                )

    def search(
        self,
        query: str,
        search_types: list[str] | None = None,
        top_k: int = 10,
        threshold: float = 0.0
    ) -> list[SearchResult]:
        """语义搜索
        
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
        
        query_vec = np.array(self.embeddings.embed_single(query))
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        
        results = []
        
        # 搜索物种
        if "species" in search_types:
            for code, (vec, species) in self._species_index.items():
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                similarity = float(np.dot(query_norm, vec_norm))
                
                if similarity >= threshold:
                    results.append(SearchResult(
                        result_type="species",
                        id=code,
                        title=species.common_name,
                        description=species.description[:200],
                        similarity=similarity,
                        metadata={
                            "latin_name": species.latin_name,
                            "status": species.status,
                            "trophic_level": species.trophic_level
                        }
                    ))
        
        # 搜索事件
        if "event" in search_types:
            for event_id, (vec, event_info) in self._event_index.items():
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                similarity = float(np.dot(query_norm, vec_norm))
                
                if similarity >= threshold:
                    results.append(SearchResult(
                        result_type="event",
                        id=event_id,
                        title=event_info["title"],
                        description=event_info["description"][:200],
                        similarity=similarity,
                        metadata={
                            "turn_index": event_info["turn_index"],
                            "event_type": event_info["event_type"]
                        }
                    ))
        
        # 搜索概念
        if "concept" in search_types:
            for name, (vec, concept_info) in self._concept_index.items():
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                similarity = float(np.dot(query_norm, vec_norm))
                
                if similarity >= threshold:
                    results.append(SearchResult(
                        result_type="concept",
                        id=name,
                        title=name,
                        description=concept_info["description"][:200],
                        similarity=similarity,
                        metadata={"keywords": concept_info.get("keywords", [])}
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
                species = self._species_index.get(result.id, (None, None))[1]
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
        # 获取 embedding
        vec_a = self._species_index.get(species_a.lineage_code, (None, None))[0]
        vec_b = self._species_index.get(species_b.lineage_code, (None, None))[0]
        
        # 计算相似度
        similarity = 0.0
        if vec_a is not None and vec_b is not None:
            norm_a = vec_a / (np.linalg.norm(vec_a) + 1e-8)
            norm_b = vec_b / (np.linalg.norm(vec_b) + 1e-8)
            similarity = float(np.dot(norm_a, norm_b))
        
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
        return {
            "species_count": len(self._species_index),
            "event_count": len(self._event_index),
            "concept_count": len(self._concept_index),
        }

