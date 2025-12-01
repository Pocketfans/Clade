"""物种杂交服务

【平衡优化v2】调整杂交参数：
- 杂交遗传距离上限从0.5降到0.45，更严格但更快达到
- 可育性计算更平滑
- 支持自动杂交检测

【命名规范修复v2】
- 杂交物种使用主亲本的lineage_code作为前缀（主亲本 + h + 数字）
- parent_code设为主亲本，使杂交物种在族谱中挂在主亲本下
- 主亲本选择规则：营养级低者优先 → 创建时间早者优先

【AI集成】
- 使用LLM生成杂交物种的名称、描述和属性
- 复用分化模块的AI调用逻辑
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Sequence, TYPE_CHECKING

from ...core.config import get_settings
from ...models.species import Species
from .genetic_distance import GeneticDistanceCalculator

if TYPE_CHECKING:
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


class HybridizationService:
    """处理物种杂交"""
    
    def __init__(
        self, 
        genetic_calculator: GeneticDistanceCalculator,
        router: "ModelRouter | None" = None
    ):
        self.genetic_calculator = genetic_calculator
        self.router = router
    
    def _select_primary_parent(self, parent1: Species, parent2: Species) -> tuple[Species, Species]:
        """选择主亲本和次要亲本
        
        主亲本选择规则（按优先级）：
        1. 营养级较低的亲本优先（生产者更基础）
        2. 营养级相同时，选择创建时间更早的亲本
        3. 都相同时，按lineage_code字母顺序选择
        
        Returns:
            (主亲本, 次要亲本)
        """
        t1 = getattr(parent1, 'trophic_level', 2.0) or 2.0
        t2 = getattr(parent2, 'trophic_level', 2.0) or 2.0
        
        # 规则1：营养级较低者优先
        if t1 < t2:
            return parent1, parent2
        elif t2 < t1:
            return parent2, parent1
        
        # 规则2：创建时间更早者优先
        c1 = getattr(parent1, 'created_turn', 0) or 0
        c2 = getattr(parent2, 'created_turn', 0) or 0
        
        if c1 < c2:
            return parent1, parent2
        elif c2 < c1:
            return parent2, parent1
        
        # 规则3：按lineage_code字母顺序
        if parent1.lineage_code <= parent2.lineage_code:
            return parent1, parent2
        else:
            return parent2, parent1
    
    def can_hybridize(self, sp1: Species, sp2: Species, genetic_distance: float = None) -> tuple[bool, float]:
        """判断两个物种能否杂交
        
        【平衡优化v3】放宽杂交条件：
        - 杂交距离上限从配置读取（默认0.50）
        - 可育性计算更平滑，且基础值更高
        - 允许不同属但同科的物种进行杂交（低可育性）
        
        生物学依据：
        - 属间杂交在植物中很常见（如小麦属×黑麦属）
        - 某些动物也存在属间杂交（如狮虎兽、骡子）
        
        Args:
            sp1, sp2: 待杂交的物种
            genetic_distance: 预计算的遗传距离（可选）
            
        Returns:
            (是否可杂交, 预期可育性)
        """
        _settings = get_settings()
        max_distance = _settings.hybridization_distance_max  # 默认0.50
        
        if sp1.lineage_code == sp2.lineage_code:
            return False, 0.0
        
        if genetic_distance is None:
            genetic_distance = self.genetic_calculator.calculate_distance(sp1, sp2)
        
        # 同属杂交：正常判断
        if sp1.genus_code == sp2.genus_code and sp1.genus_code:
            if genetic_distance >= max_distance:
                return False, 0.0
            # 可育性计算：距离越近可育性越高，使用更平滑的曲线
            # 使用0.7次幂让中等距离的可育性更高
            fertility = max(0.0, 1.0 - (genetic_distance / max_distance) ** 0.7)
            return True, fertility
        
        # 【新增】不同属的杂交：需要更近的遗传距离，且可育性大幅降低
        # 这模拟了属间杂交（如骡子、狮虎兽等）
        cross_genus_max_distance = max_distance * 0.6  # 更严格的距离限制
        if genetic_distance < cross_genus_max_distance:
            # 属间杂交可育性很低（最高30%）
            fertility = max(0.0, 0.30 * (1.0 - (genetic_distance / cross_genus_max_distance) ** 0.5))
            return True, fertility
        
        return False, 0.0
    
    def create_hybrid(
        self, 
        parent1: Species, 
        parent2: Species, 
        turn_index: int,
        genetic_distance: float = None,
        existing_codes: set[str] = None
    ) -> Species | None:
        """创建杂交种
        
        Args:
            parent1, parent2: 杂交亲本
            turn_index: 当前回合
            genetic_distance: 预计算的遗传距离（可选）
            existing_codes: 已存在的谱系编码集合（用于生成唯一编码）
            
        Returns:
            杂交种，如果杂交失败则返回None
        """
        can_hybrid, fertility = self.can_hybridize(parent1, parent2, genetic_distance)
        if not can_hybrid:
            return None
        
        # 【v2】选择主亲本：营养级低优先 → 创建时间早优先
        primary_parent, secondary_parent = self._select_primary_parent(parent1, parent2)
        
        # 【v2】使用主亲本编码作为杂交种编码前缀
        hybrid_code = self._generate_hybrid_code(
            primary_parent.lineage_code, existing_codes or set()
        )
        
        hybrid_traits = self._mix_traits(parent1, parent2)
        hybrid_organs = self._merge_organs(parent1, parent2)
        hybrid_morphology = self._mix_morphology(parent1, parent2)
        hybrid_trophic = self._mix_trophic_level(parent1, parent2)
        hybrid_capabilities = list(set(parent1.capabilities + parent2.capabilities))
        
        # 继承食性和猎物偏好
        diet_type, prey_species, prey_preferences = self._merge_diet(parent1, parent2)
        
        # 继承栖息地类型
        habitat_type = self._merge_habitat(parent1, parent2)
        
        # 【命名规范】生成规范的拉丁名和俗名
        latin_name = self._generate_hybrid_latin_name(parent1, parent2)
        common_name = self._generate_hybrid_common_name(parent1, parent2)
        
        # 【v2】parent_code设为主亲本，杂交物种挂在主亲本下
        parent_code = primary_parent.lineage_code
        
        # 【v2】hybrid_parent_codes：主亲本在前，次要亲本在后
        hybrid_parent_codes = [primary_parent.lineage_code, secondary_parent.lineage_code]
        
        return Species(
            lineage_code=hybrid_code,
            latin_name=latin_name,
            common_name=common_name,
            description=self._generate_hybrid_description(parent1, parent2),
            morphology_stats=hybrid_morphology,
            abstract_traits=hybrid_traits,
            hidden_traits=self._mix_hidden_traits(parent1, parent2),
            ecological_vector=None,
            parent_code=parent_code,
            status="alive",
            created_turn=turn_index,
            trophic_level=hybrid_trophic,
            organs=hybrid_organs,
            capabilities=hybrid_capabilities,
            genus_code=primary_parent.genus_code,
            taxonomic_rank="hybrid",
            hybrid_parent_codes=hybrid_parent_codes,
            hybrid_fertility=fertility,
            diet_type=diet_type,
            prey_species=prey_species,
            prey_preferences=prey_preferences,
            habitat_type=habitat_type,
        )
    
    async def create_hybrid_async(
        self, 
        parent1: Species, 
        parent2: Species, 
        turn_index: int,
        genetic_distance: float = None,
        existing_codes: set[str] = None
    ) -> Species | None:
        """异步创建杂交种（使用AI生成名称和属性）
        
        Args:
            parent1, parent2: 杂交亲本
            turn_index: 当前回合
            genetic_distance: 预计算的遗传距离（可选）
            existing_codes: 已存在的谱系编码集合（用于生成唯一编码）
            
        Returns:
            杂交种，如果杂交失败则返回None
        """
        can_hybrid, fertility = self.can_hybridize(parent1, parent2, genetic_distance)
        if not can_hybrid:
            return None
        
        if genetic_distance is None:
            genetic_distance = self.genetic_calculator.calculate_distance(parent1, parent2)
        
        # 【v2】选择主亲本：营养级低优先 → 创建时间早优先
        primary_parent, secondary_parent = self._select_primary_parent(parent1, parent2)
        
        # 【v2】使用主亲本编码作为杂交种编码前缀
        hybrid_code = self._generate_hybrid_code(
            primary_parent.lineage_code, existing_codes or set()
        )
        
        # 尝试使用AI生成杂交物种信息
        ai_content = None
        if self.router:
            ai_content = await self._call_hybridization_ai(
                parent1, parent2, hybrid_code, genetic_distance, fertility
            )
        
        # 混合基础属性（体现杂交特点）
        hybrid_traits = self._mix_traits(parent1, parent2)
        hybrid_organs = self._merge_organs(parent1, parent2)
        hybrid_morphology = self._mix_morphology(parent1, parent2)
        hybrid_trophic = self._mix_trophic_level(parent1, parent2)
        hybrid_capabilities = list(set(parent1.capabilities + parent2.capabilities))
        
        # 继承食性和猎物偏好
        diet_type, prey_species, prey_preferences = self._merge_diet(parent1, parent2)
        
        # 继承栖息地类型（默认值）
        habitat_type = self._merge_habitat(parent1, parent2)
        
        # 应用AI生成的内容（如果有）
        if ai_content and isinstance(ai_content, dict):
            latin_name = ai_content.get("latin_name") or self._generate_hybrid_latin_name(parent1, parent2)
            common_name = ai_content.get("common_name") or self._generate_hybrid_common_name(parent1, parent2)
            description = ai_content.get("description") or self._generate_hybrid_description(parent1, parent2)
            
            # 应用AI建议的属性变化
            trait_balance = ai_content.get("trait_balance", {})
            if isinstance(trait_balance, dict):
                for trait_name, change in trait_balance.items():
                    try:
                        if isinstance(change, str):
                            change_value = float(change.replace("+", ""))
                        else:
                            change_value = float(change)
                        if trait_name in hybrid_traits:
                            hybrid_traits[trait_name] = max(0.0, min(15.0, 
                                hybrid_traits[trait_name] + change_value
                            ))
                    except (ValueError, TypeError):
                        pass
            
            # 应用AI建议的营养级
            ai_trophic = ai_content.get("trophic_level")
            if ai_trophic is not None:
                try:
                    hybrid_trophic = max(1.0, min(6.0, float(ai_trophic)))
                except (ValueError, TypeError):
                    pass
            
            # 应用AI建议的栖息地（覆盖规则计算的值）
            ai_habitat = ai_content.get("habitat_type")
            if ai_habitat:
                habitat_type = ai_habitat
            
            logger.info(
                f"[杂交AI] {primary_parent.common_name} × {secondary_parent.common_name} → "
                f"{common_name} ({latin_name})"
            )
        else:
            # 回退到规则生成
            latin_name = self._generate_hybrid_latin_name(parent1, parent2)
            common_name = self._generate_hybrid_common_name(parent1, parent2)
            description = self._generate_hybrid_description(parent1, parent2)
            
            logger.info(
                f"[杂交规则] {primary_parent.common_name} × {secondary_parent.common_name} → "
                f"{common_name} (AI未返回有效数据)"
            )
        
        # 【v2】parent_code设为主亲本，杂交物种挂在主亲本下
        parent_code = primary_parent.lineage_code
        
        # 【v2】hybrid_parent_codes：主亲本在前，次要亲本在后
        hybrid_parent_codes = [primary_parent.lineage_code, secondary_parent.lineage_code]
        
        return Species(
            lineage_code=hybrid_code,
            latin_name=latin_name,
            common_name=common_name,
            description=description,
            morphology_stats=hybrid_morphology,
            abstract_traits=hybrid_traits,
            hidden_traits=self._mix_hidden_traits(parent1, parent2),
            ecological_vector=None,
            parent_code=parent_code,
            status="alive",
            created_turn=turn_index,
            trophic_level=hybrid_trophic,
            organs=hybrid_organs,
            capabilities=hybrid_capabilities,
            genus_code=primary_parent.genus_code,
            taxonomic_rank="hybrid",
            hybrid_parent_codes=hybrid_parent_codes,
            hybrid_fertility=fertility,
            diet_type=diet_type,
            prey_species=prey_species,
            prey_preferences=prey_preferences,
            habitat_type=habitat_type,
        )
    
    async def _call_hybridization_ai(
        self,
        parent1: Species,
        parent2: Species,
        hybrid_code: str,
        genetic_distance: float,
        fertility: float
    ) -> dict | None:
        """调用AI生成杂交物种信息"""
        if not self.router:
            return None
        
        payload = {
            "parent1_lineage": parent1.lineage_code,
            "parent1_latin_name": parent1.latin_name or "Species unknown",
            "parent1_common_name": parent1.common_name or "未知物种",
            "parent1_habitat": parent1.habitat_type or "unknown",
            "parent1_trophic": parent1.trophic_level,
            "parent1_description": parent1.description or "",
            "parent2_lineage": parent2.lineage_code,
            "parent2_latin_name": parent2.latin_name or "Species unknown",
            "parent2_common_name": parent2.common_name or "未知物种",
            "parent2_habitat": parent2.habitat_type or "unknown",
            "parent2_trophic": parent2.trophic_level,
            "parent2_description": parent2.description or "",
            "genetic_distance": genetic_distance,
            "fertility": fertility,
            "hybrid_code": hybrid_code,
        }
        
        from ...ai.streaming_helper import invoke_with_heartbeat
        
        try:
            response = await invoke_with_heartbeat(
                router=self.router,
                capability="hybridization",
                payload=payload,
                task_name=f"杂交[{sp1.common_name[:6]}×{sp2.common_name[:6]}]",
                timeout=30,
                heartbeat_interval=2.0,
            )
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                return content
            logger.warning(f"[杂交AI] 响应格式不正确: {type(content)}")
            return None
        except asyncio.TimeoutError:
            logger.warning("[杂交AI] 请求超时（30秒）")
            return None
        except Exception as e:
            logger.warning(f"[杂交AI] 请求失败: {e}")
            return None
    
    def _find_common_ancestor_code(self, code1: str, code2: str) -> str:
        """找到两个谱系编码的最近公共祖先编码
        
        例如：
        - B1a, B1b -> B1（最近公共祖先）
        - A1a1, A1b -> A1（公共祖先）
        - A1, B1 -> ""（无公共祖先，不同属）
        """
        # 解析谱系路径
        path1 = self._get_lineage_path(code1)
        path2 = self._get_lineage_path(code2)
        
        # 找到最长公共前缀
        common = ""
        for p1, p2 in zip(path1, path2):
            if p1 == p2:
                common = p1
            else:
                break
        
        return common
    
    def _get_lineage_path(self, lineage_code: str) -> list[str]:
        """获取谱系路径
        
        例如: "A1a1b" -> ["A", "A1", "A1a", "A1a1", "A1a1b"]
        """
        path = []
        current = ""
        
        for char in lineage_code:
            current += char
            if char.isalpha() and len(current) == 1:
                path.append(current)
            elif char.isdigit():
                path.append(current)
            elif char.isalpha() and len(current) > 1:
                path.append(current)
        
        return path
    
    def _generate_hybrid_code(self, parent_code: str, existing_codes: set[str]) -> str:
        """生成杂交种的编码
        
        【v2】使用格式: 主亲本编码 + h + 数字
        例如: A1h1, A1h2, B1h1（挂在主亲本下）
        
        Args:
            parent_code: 主亲本的lineage_code
            existing_codes: 已存在的编码集合
        """
        if not parent_code:
            # 无主亲本时（理论上不应发生），使用H作为基础
            parent_code = "H"
        
        # 尝试生成唯一编码
        idx = 1
        while True:
            hybrid_code = f"{parent_code}h{idx}"
            if hybrid_code not in existing_codes:
                return hybrid_code
            idx += 1
    
    def _generate_hybrid_latin_name(self, p1: Species, p2: Species) -> str:
        """生成杂交种的拉丁学名
        
        格式: Genus × epithet（符合杂交种命名规范）
        """
        p1_parts = (p1.latin_name or "").split()
        p2_parts = (p2.latin_name or "").split()
        
        genus = p1_parts[0] if p1_parts else "Genus"
        # 从两个亲本的种加词中取字符组合
        epithet1 = p1_parts[1][:3] if len(p1_parts) > 1 else "hyb"
        epithet2 = p2_parts[1][:3] if len(p2_parts) > 1 else "rid"
        
        return f"{genus} × {epithet1}{epithet2}"
    
    def _generate_hybrid_common_name(self, p1: Species, p2: Species) -> str:
        """生成杂交种的中文俗名
        
        格式: 简化的亲本名称组合
        例如: 鞭毛亚种×鞭毛变种 -> 鞭毛杂交种
        """
        # 提取亲本俗名的核心部分（去掉后缀如亚种、变种等）
        suffixes = ["亚种", "变种", "适应型", "进化型", "新型", "原始"]
        
        def extract_core_name(name: str) -> str:
            for suffix in suffixes:
                if name.endswith(suffix):
                    return name[:-len(suffix)]
            # 如果没有后缀，取前4个字符
            return name[:4] if len(name) > 4 else name
        
        core1 = extract_core_name(p1.common_name or "物种1")
        core2 = extract_core_name(p2.common_name or "物种2")
        
        # 如果核心名称相同，只用一个
        if core1 == core2:
            return f"{core1}杂交种"
        else:
            # 取较短的名称组合
            return f"{core1[:3]}×{core2[:3]}杂交种"
    
    def _mix_traits(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合属性：模拟杂交遗传特性
        
        杂交遗传模式：
        1. 杂交优势（20%概率）：某些特质超过双亲最大值（+10-20%）
        2. 显性遗传（40%概率）：继承双亲中的较高值
        3. 中间型（30%概率）：取双亲平均值
        4. 隐性表达（10%概率）：继承双亲中的较低值
        
        还会体现：
        - 双亲差异大时更可能出现杂交优势
        - 随机变异幅度与遗传距离正相关
        """
        mixed = {}
        
        # 合并双亲的所有特质（不只是p1的）
        all_traits = set(p1.abstract_traits.keys()) | set(p2.abstract_traits.keys())
        
        for trait_name in all_traits:
            val1 = p1.abstract_traits.get(trait_name, 5.0)  # 默认中等值
            val2 = p2.abstract_traits.get(trait_name, 5.0)
            
            # 计算双亲差异（差异越大，杂交效应越明显）
            difference = abs(val1 - val2)
            heterosis_bonus = difference * 0.15  # 差异越大，杂交优势越明显
            
            rand = random.random()
            if rand < 0.20:
                # 杂交优势：超过双亲最大值
                max_val = max(val1, val2)
                bonus = random.uniform(0.1, 0.2) * max_val + heterosis_bonus
                mixed[trait_name] = max_val + bonus
            elif rand < 0.60:
                # 显性遗传：取较高值
                mixed[trait_name] = max(val1, val2)
            elif rand < 0.90:
                # 中间型：加权平均（略偏向较高值）
                weight = random.uniform(0.4, 0.6)
                mixed[trait_name] = val1 * weight + val2 * (1 - weight)
            else:
                # 隐性表达：取较低值
                mixed[trait_name] = min(val1, val2)
            
            # 随机变异（与差异正相关）
            mutation = random.uniform(-0.3, 0.3) * (1 + difference * 0.1)
            mixed[trait_name] += mutation
            mixed[trait_name] = max(0.0, min(15.0, round(mixed[trait_name], 2)))
        
        return mixed
    
    def _merge_organs(self, p1: Species, p2: Species) -> dict:
        """合并器官：杂交种获得双亲器官的融合版本
        
        器官合并规则：
        1. 继承双亲所有器官类别（生态位扩展）
        2. 同类器官取阶段更高者，但参数融合
        3. 有概率产生器官增强效应（杂交优势）
        """
        merged = {}
        all_categories = set(p1.organs.keys()) | set(p2.organs.keys())
        
        for category in all_categories:
            organ1 = p1.organs.get(category)
            organ2 = p2.organs.get(category)
            
            if organ1 and organ2:
                # 双亲都有该器官：融合
                stage1 = organ1.get("stage", 0)
                stage2 = organ2.get("stage", 0)
                
                # 选择阶段更高的作为基础
                if stage1 >= stage2:
                    base_organ = dict(organ1)
                    other_organ = organ2
                else:
                    base_organ = dict(organ2)
                    other_organ = organ1
                
                # 融合参数：取双方参数的平均值或最大值
                base_params = base_organ.get("parameters", {})
                other_params = other_organ.get("parameters", {})
                merged_params = dict(base_params)
                
                for param_key, param_val in other_params.items():
                    if param_key in merged_params:
                        # 参数融合：60%概率取最大值，40%取平均值
                        if random.random() < 0.6:
                            merged_params[param_key] = max(merged_params[param_key], param_val)
                        else:
                            merged_params[param_key] = (merged_params[param_key] + param_val) / 2
                    else:
                        merged_params[param_key] = param_val
                
                # 杂交优势：15%概率器官参数额外提升
                if random.random() < 0.15:
                    for param_key in merged_params:
                        if isinstance(merged_params[param_key], (int, float)):
                            merged_params[param_key] *= random.uniform(1.05, 1.15)
                
                base_organ["parameters"] = merged_params
                merged[category] = base_organ
                
            elif organ1:
                # 只有p1有该器官
                merged[category] = dict(organ1)
            elif organ2:
                # 只有p2有该器官
                merged[category] = dict(organ2)
        
        return merged
    
    def _mix_morphology(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合形态学参数
        
        形态学混合规则：
        1. 体型参数取双亲中间值（±10%变异）
        2. 代谢率可能因杂交优势提升
        3. 种群初始较小（杂交种建群困难）
        4. 寿命取平均值或略高（杂交优势）
        """
        mixed = {}
        
        # 合并双亲的所有形态学参数
        all_keys = set(p1.morphology_stats.keys()) | set(p2.morphology_stats.keys())
        
        for key in all_keys:
            val1 = p1.morphology_stats.get(key)
            val2 = p2.morphology_stats.get(key)
            
            if val1 is None:
                mixed[key] = val2
                continue
            if val2 is None:
                mixed[key] = val1
                continue
            
            if key == "population":
                # 杂交种初始种群较小（建群困难）
                mixed[key] = int(min(val1, val2) * 0.3)
            elif key in ("body_length_cm", "body_weight_g", "body_surface_area_cm2"):
                # 体型参数取中间值
                mixed[key] = (val1 + val2) / 2 * random.uniform(0.95, 1.05)
            elif key == "metabolic_rate":
                # 代谢率：杂交优势可能提升
                avg = (val1 + val2) / 2
                if random.random() < 0.3:
                    mixed[key] = avg * random.uniform(1.05, 1.15)  # 杂交优势
                else:
                    mixed[key] = avg * random.uniform(0.95, 1.05)
            elif key in ("lifespan_days", "generation_time_days"):
                # 寿命和世代时间：可能略有优势
                avg = (val1 + val2) / 2
                if random.random() < 0.25:
                    mixed[key] = avg * random.uniform(1.0, 1.1)  # 寿命优势
                else:
                    mixed[key] = avg
            else:
                # 其他参数取平均值
                mixed[key] = (val1 + val2) / 2 * random.uniform(0.9, 1.1)
        
        return mixed
    
    def _mix_hidden_traits(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合隐藏属性
        
        杂交种隐藏属性特点：
        1. 基因多样性显著提升（杂交带来新基因组合）
        2. 演化潜力可能增加（新的遗传变异）
        3. 突变率略微提升（基因重组效应）
        4. 环境敏感度可能改变
        """
        mixed = {}
        
        # 合并双亲的所有隐藏属性
        all_keys = set(p1.hidden_traits.keys()) | set(p2.hidden_traits.keys())
        
        for key in all_keys:
            val1 = p1.hidden_traits.get(key, 0.5)
            val2 = p2.hidden_traits.get(key, 0.5)
            
            if key == "gene_diversity":
                # 杂交显著提升基因多样性（核心杂交优势）
                base = (val1 + val2) / 2
                boost = random.uniform(1.15, 1.30)  # 15-30%提升
                mixed[key] = min(1.0, base * boost)
                
            elif key == "evolution_potential":
                # 演化潜力可能增加（新的遗传组合）
                base = (val1 + val2) / 2
                if random.random() < 0.4:
                    mixed[key] = min(1.0, base * random.uniform(1.05, 1.15))
                else:
                    mixed[key] = base
                    
            elif key == "mutation_rate":
                # 突变率略微提升（基因重组带来的不稳定性）
                base = (val1 + val2) / 2
                mixed[key] = min(1.0, base * random.uniform(1.0, 1.1))
                
            elif key == "adaptation_speed":
                # 适应速度取平均值或略高
                base = (val1 + val2) / 2
                if random.random() < 0.3:
                    mixed[key] = min(1.0, base * 1.08)
                else:
                    mixed[key] = base
                    
            elif key == "environment_sensitivity":
                # 环境敏感度：可能增加或减少
                base = (val1 + val2) / 2
                mixed[key] = base * random.uniform(0.9, 1.1)
                mixed[key] = max(0.0, min(1.0, mixed[key]))
                
            else:
                # 其他隐藏属性取平均值
                mixed[key] = (val1 + val2) / 2
        
        return mixed
    
    def _generate_hybrid_description(self, p1: Species, p2: Species) -> str:
        """生成杂交种描述"""
        return (
            f"{p1.common_name}与{p2.common_name}的杂交后代。"
            f"继承了双亲的部分特征，形态介于两者之间。"
            f"杂交种通常表现出杂交优势或某些特征的中间型。"
        )
    
    def _mix_trophic_level(self, p1: Species, p2: Species) -> float:
        """计算杂交种的营养级
        
        营养级混合规则：
        1. 基础取双亲平均值
        2. 偏向较高营养级（杂交可能扩展生态位）
        3. 小幅随机变异
        """
        t1 = p1.trophic_level
        t2 = p2.trophic_level
        
        # 基础：取平均值，略偏向较高者
        avg = (t1 + t2) / 2
        max_t = max(t1, t2)
        
        # 70%权重给平均值，30%权重给较高值
        base = avg * 0.7 + max_t * 0.3
        
        # 小幅变异
        result = base + random.uniform(-0.2, 0.2)
        
        # 范围限制
        return max(1.0, min(6.0, round(result, 1)))
    
    def _merge_diet(self, p1: Species, p2: Species) -> tuple[str, list, dict]:
        """合并双亲的食性和猎物偏好
        
        食性合并规则：
        1. 如果双亲食性相同，继承该食性
        2. 如果不同，倾向于更广泛的食性（如omnivore）
        3. 猎物列表合并双亲的猎物
        4. 偏好值取加权平均
        
        Returns:
            (diet_type, prey_species, prey_preferences)
        """
        diet1 = getattr(p1, 'diet_type', None) or "omnivore"
        diet2 = getattr(p2, 'diet_type', None) or "omnivore"
        
        # 食性优先级（越广泛越高）
        diet_priority = {
            "autotroph": 1,
            "detritivore": 2,
            "herbivore": 3,
            "carnivore": 4,
            "omnivore": 5,
        }
        
        # 如果双亲食性相同
        if diet1 == diet2:
            result_diet = diet1
        else:
            # 倾向于更广泛的食性
            p1_priority = diet_priority.get(diet1, 3)
            p2_priority = diet_priority.get(diet2, 3)
            
            # 如果一方是杂食，杂交种也倾向杂食
            if diet1 == "omnivore" or diet2 == "omnivore":
                result_diet = "omnivore"
            elif p1_priority > p2_priority:
                result_diet = diet1
            else:
                result_diet = diet2
        
        # 合并猎物列表
        prey1 = set(getattr(p1, 'prey_species', None) or [])
        prey2 = set(getattr(p2, 'prey_species', None) or [])
        combined_prey = list(prey1 | prey2)
        
        # 合并猎物偏好
        pref1 = dict(getattr(p1, 'prey_preferences', None) or {})
        pref2 = dict(getattr(p2, 'prey_preferences', None) or {})
        combined_pref = {}
        
        all_prey_codes = set(pref1.keys()) | set(pref2.keys())
        for code in all_prey_codes:
            v1 = pref1.get(code, 0)
            v2 = pref2.get(code, 0)
            # 取平均或取非零值
            if v1 > 0 and v2 > 0:
                combined_pref[code] = (v1 + v2) / 2
            else:
                combined_pref[code] = v1 or v2
        
        # 归一化偏好（确保总和接近1）
        total = sum(combined_pref.values())
        if total > 0:
            combined_pref = {k: round(v / total, 2) for k, v in combined_pref.items()}
        
        return result_diet, combined_prey, combined_pref
    
    def _merge_habitat(self, p1: Species, p2: Species) -> str:
        """合并双亲的栖息地类型
        
        栖息地合并规则：
        1. 如果双亲栖息地相同，继承该栖息地
        2. 如果不同，选择更广泛或介于两者之间的类型
        """
        h1 = getattr(p1, 'habitat_type', None) or "terrestrial"
        h2 = getattr(p2, 'habitat_type', None) or "terrestrial"
        
        if h1 == h2:
            return h1
        
        # 栖息地兼容性映射
        # 如果一方水生一方陆生，杂交种可能是两栖的
        aquatic = {"marine", "freshwater", "deep_sea"}
        land = {"terrestrial", "aerial"}
        transitional = {"coastal", "amphibious"}
        
        if h1 in aquatic and h2 in land:
            return "amphibious"
        if h2 in aquatic and h1 in land:
            return "amphibious"
        
        if h1 in aquatic and h2 in transitional:
            return h2  # 选择过渡型
        if h2 in aquatic and h1 in transitional:
            return h1
        
        if h1 in land and h2 in transitional:
            return h2
        if h2 in land and h1 in transitional:
            return h1
        
        # 同为水生或同为陆生，随机选择
        return random.choice([h1, h2])
    
    # ==================== 强行杂交（跨属/幻想杂交）====================
    
    def can_force_hybridize(self, sp1: Species, sp2: Species) -> tuple[bool, str]:
        """检查是否可以进行强行杂交
        
        强行杂交允许跨越正常杂交限制，但有条件：
        1. 两个物种都必须存活
        2. 两个物种不能是同一个
        3. 消耗更多能量（由调用方处理）
        
        Returns:
            (是否可以强行杂交, 原因说明)
        """
        if sp1.lineage_code == sp2.lineage_code:
            return False, "不能与自身杂交"
        
        if sp1.status != "alive":
            return False, f"{sp1.common_name}已灭绝"
        
        if sp2.status != "alive":
            return False, f"{sp2.common_name}已灭绝"
        
        # 检查是否已经可以正常杂交（如果可以，建议使用普通杂交）
        can_normal, _ = self.can_hybridize(sp1, sp2)
        if can_normal:
            return True, "这两个物种可以正常杂交，建议使用普通杂交（消耗更少能量）"
        
        return True, "可以进行强行杂交实验"
    
    async def force_hybridize_async(
        self,
        parent1: Species,
        parent2: Species,
        turn_index: int,
        existing_codes: set[str] = None
    ) -> Species | None:
        """强行杂交：跨越自然界限创造嵌合体
        
        这是一个疯狂的基因工程实验，可以将任意两个物种强行融合！
        
        特点：
        1. 无视遗传距离和属的限制
        2. 产生的是"嵌合体"（Chimera）
        3. 通常不育或极低可育性
        4. 可能有基因不稳定性
        5. 消耗大量能量（由调用方处理）
        
        Args:
            parent1, parent2: 要融合的两个物种
            turn_index: 当前回合
            existing_codes: 已存在的编码集合
            
        Returns:
            嵌合体物种，如果失败则返回None
        """
        # 生成嵌合体编码：使用X前缀表示跨属杂交
        chimera_code = self._generate_chimera_code(
            parent1.lineage_code, 
            parent2.lineage_code, 
            existing_codes or set()
        )
        
        # 调用AI生成嵌合体信息
        ai_content = None
        if self.router:
            ai_content = await self._call_forced_hybridization_ai(
                parent1, parent2, chimera_code
            )
        
        # 基础属性混合（使用更激进的混合策略）
        chimera_traits = self._mix_chimera_traits(parent1, parent2)
        chimera_organs = self._merge_chimera_organs(parent1, parent2)
        chimera_morphology = self._mix_chimera_morphology(parent1, parent2)
        chimera_capabilities = list(set(parent1.capabilities + parent2.capabilities))
        
        # 计算嵌合体的可育性（通常极低或不育）
        # 基于两个物种的差异程度
        trophic_diff = abs(parent1.trophic_level - parent2.trophic_level)
        base_fertility = max(0.0, 0.15 - trophic_diff * 0.03)  # 最高15%可育性
        
        # 如果是完全不同的属，可育性更低
        if parent1.genus_code != parent2.genus_code:
            base_fertility *= 0.3
        
        fertility = max(0.0, min(0.15, base_fertility))
        
        # 应用AI生成的内容
        if ai_content and isinstance(ai_content, dict):
            latin_name = ai_content.get("latin_name") or self._generate_chimera_latin_name(parent1, parent2)
            common_name = ai_content.get("common_name") or self._generate_chimera_common_name(parent1, parent2)
            description = ai_content.get("description") or self._generate_chimera_description(parent1, parent2)
            appearance = ai_content.get("appearance", "")
            
            # 将外形描述添加到描述中
            if appearance and appearance not in description:
                description = f"{appearance} {description}"
            
            # 应用AI建议的属性加成
            trait_bonuses = ai_content.get("trait_bonuses", {})
            if isinstance(trait_bonuses, dict):
                for trait_name, bonus in trait_bonuses.items():
                    try:
                        bonus_value = float(str(bonus).replace("+", ""))
                        if trait_name in chimera_traits:
                            chimera_traits[trait_name] = max(0.0, min(15.0, 
                                chimera_traits[trait_name] + bonus_value
                            ))
                        else:
                            chimera_traits[trait_name] = max(0.0, min(15.0, 5.0 + bonus_value))
                    except (ValueError, TypeError):
                        pass
            
            # 应用AI建议的属性惩罚
            trait_penalties = ai_content.get("trait_penalties", {})
            if isinstance(trait_penalties, dict):
                for trait_name, penalty in trait_penalties.items():
                    try:
                        penalty_value = float(str(penalty).replace("-", "").replace("+", ""))
                        if trait_name in chimera_traits:
                            chimera_traits[trait_name] = max(0.0, min(15.0, 
                                chimera_traits[trait_name] - penalty_value
                            ))
                    except (ValueError, TypeError):
                        pass
            
            # 应用稳定性和可育性
            stability = ai_content.get("stability", "unstable")
            ai_fertility = ai_content.get("fertility", "very_low")
            
            # 根据AI判断调整可育性
            if ai_fertility == "sterile":
                fertility = 0.0
            elif ai_fertility == "very_low":
                fertility = min(fertility, 0.05)
            elif ai_fertility == "low":
                fertility = min(fertility, 0.10)
            
            # 营养级
            trophic_level = parent1.trophic_level
            ai_trophic = ai_content.get("trophic_level")
            if ai_trophic is not None:
                try:
                    trophic_level = max(1.0, min(6.0, float(ai_trophic)))
                except (ValueError, TypeError):
                    pass
            
            # 栖息地
            habitat_type = ai_content.get("habitat_type") or self._merge_habitat(parent1, parent2)
            
            # 特殊能力和弱点（存储在描述或隐藏属性中）
            abilities = ai_content.get("abilities", [])
            weaknesses = ai_content.get("weaknesses", [])
            personality = ai_content.get("personality", "")
            
            logger.info(
                f"[强行杂交] {parent1.common_name} × {parent2.common_name} → "
                f"{common_name} ({latin_name}) [稳定性:{stability}, 可育:{fertility:.0%}]"
            )
        else:
            # 回退到规则生成
            latin_name = self._generate_chimera_latin_name(parent1, parent2)
            common_name = self._generate_chimera_common_name(parent1, parent2)
            description = self._generate_chimera_description(parent1, parent2)
            habitat_type = self._merge_habitat(parent1, parent2)
            trophic_level = (parent1.trophic_level + parent2.trophic_level) / 2
            stability = "unstable"
            abilities = []
            weaknesses = ["基因不稳定"]
            personality = ""
            
            logger.info(
                f"[强行杂交规则] {parent1.common_name} × {parent2.common_name} → "
                f"{common_name} (AI未返回有效数据)"
            )
        
        # 混合隐藏属性（嵌合体特殊处理）
        hidden_traits = self._mix_chimera_hidden_traits(parent1, parent2, stability)
        
        # 合并食性（嵌合体可能有更广泛的食性）
        diet_type, prey_species, prey_preferences = self._merge_chimera_diet(parent1, parent2)
        
        # 创建嵌合体物种
        chimera = Species(
            lineage_code=chimera_code,
            latin_name=latin_name,
            common_name=common_name,
            description=description,
            morphology_stats=chimera_morphology,
            abstract_traits=chimera_traits,
            hidden_traits=hidden_traits,
            ecological_vector=None,
            parent_code=None,  # 嵌合体没有单一父系
            status="alive",
            created_turn=turn_index,
            trophic_level=trophic_level,
            organs=chimera_organs,
            capabilities=chimera_capabilities,
            genus_code=None,  # 嵌合体没有明确的属
            taxonomic_rank="chimera",  # 特殊分类等级
            hybrid_parent_codes=[parent1.lineage_code, parent2.lineage_code],
            hybrid_fertility=fertility,
            diet_type=diet_type,
            prey_species=prey_species,
            prey_preferences=prey_preferences,
            habitat_type=habitat_type,
        )
        
        return chimera
    
    def _generate_chimera_code(
        self, 
        code1: str, 
        code2: str, 
        existing_codes: set[str]
    ) -> str:
        """生成嵌合体的编码
        
        使用格式: X + 数字（X表示跨属嵌合体）
        """
        idx = 1
        while True:
            chimera_code = f"X{idx}"
            if chimera_code not in existing_codes:
                return chimera_code
            idx += 1
    
    def _generate_chimera_latin_name(self, p1: Species, p2: Species) -> str:
        """生成嵌合体的拉丁学名"""
        # 取两个物种名称的部分组合
        p1_parts = (p1.latin_name or "Species").split()
        p2_parts = (p2.latin_name or "Species").split()
        
        name1 = p1_parts[0][:4] if p1_parts else "Spec"
        name2 = p2_parts[0][:4] if p2_parts else "imen"
        
        return f"× Chimera {name1.lower()}{name2.lower()}"
    
    def _generate_chimera_common_name(self, p1: Species, p2: Species) -> str:
        """生成嵌合体的中文俗名"""
        name1 = (p1.common_name or "物种1")[:2]
        name2 = (p2.common_name or "物种2")[:2]
        return f"{name1}{name2}兽"
    
    def _generate_chimera_description(self, p1: Species, p2: Species) -> str:
        """生成嵌合体的描述"""
        return (
            f"由{p1.common_name}和{p2.common_name}强行融合产生的嵌合体生物。"
            f"这是违背自然规律的基因工程产物，融合了双方的特征。"
            f"由于基因不稳定性，这种生物的寿命和繁殖能力都受到严重影响。"
            f"然而，它也可能展现出双亲都不具备的独特能力。"
        )
    
    async def _call_forced_hybridization_ai(
        self,
        parent1: Species,
        parent2: Species,
        chimera_code: str
    ) -> dict | None:
        """调用AI生成嵌合体信息"""
        if not self.router:
            return None
        
        # 提取双亲的特征关键词
        def extract_traits(sp: Species) -> str:
            traits = []
            for name, value in sp.abstract_traits.items():
                if value >= 7:
                    traits.append(f"{name}(高)")
                elif value <= 3:
                    traits.append(f"{name}(低)")
            return ", ".join(traits[:5]) or "无明显特征"
        
        payload = {
            "parent1_lineage": parent1.lineage_code,
            "parent1_latin_name": parent1.latin_name or "Species unknown",
            "parent1_common_name": parent1.common_name or "未知物种",
            "parent1_description": parent1.description or "",
            "parent1_traits": extract_traits(parent1),
            "parent2_lineage": parent2.lineage_code,
            "parent2_latin_name": parent2.latin_name or "Species unknown",
            "parent2_common_name": parent2.common_name or "未知物种",
            "parent2_description": parent2.description or "",
            "parent2_traits": extract_traits(parent2),
            "chimera_code": chimera_code,
        }
        
        from ...ai.streaming_helper import invoke_with_heartbeat
        
        try:
            response = await invoke_with_heartbeat(
                router=self.router,
                capability="forced_hybridization",
                payload=payload,
                task_name=f"嵌合体[{parent1.common_name[:5]}+{parent2.common_name[:5]}]",
                timeout=45,
                heartbeat_interval=2.0,
            )
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                return content
            logger.warning(f"[强行杂交AI] 响应格式不正确: {type(content)}")
            return None
        except asyncio.TimeoutError:
            logger.warning("[强行杂交AI] 请求超时（45秒）")
            return None
        except Exception as e:
            logger.warning(f"[强行杂交AI] 请求失败: {e}")
            return None
    
    def _mix_chimera_traits(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合嵌合体的特质
        
        嵌合体特质混合更加极端：
        - 更高概率出现极端值
        - 可能有双亲都不具备的新特质
        """
        mixed = {}
        
        # 合并双亲的所有特质
        all_traits = set(p1.abstract_traits.keys()) | set(p2.abstract_traits.keys())
        
        for trait_name in all_traits:
            val1 = p1.abstract_traits.get(trait_name, 5.0)
            val2 = p2.abstract_traits.get(trait_name, 5.0)
            
            rand = random.random()
            if rand < 0.25:
                # 极端增强：取最大值再加成
                mixed[trait_name] = max(val1, val2) * random.uniform(1.1, 1.3)
            elif rand < 0.45:
                # 极端削弱：取最小值再减少
                mixed[trait_name] = min(val1, val2) * random.uniform(0.6, 0.9)
            elif rand < 0.75:
                # 随机偏向一方
                if random.random() < 0.5:
                    mixed[trait_name] = val1 * random.uniform(0.9, 1.1)
                else:
                    mixed[trait_name] = val2 * random.uniform(0.9, 1.1)
            else:
                # 完全随机
                mixed[trait_name] = random.uniform(
                    min(val1, val2) * 0.5,
                    max(val1, val2) * 1.3
                )
            
            mixed[trait_name] = max(0.0, min(15.0, round(mixed[trait_name], 2)))
        
        return mixed
    
    def _merge_chimera_organs(self, p1: Species, p2: Species) -> dict:
        """合并嵌合体的器官
        
        嵌合体可能有双亲的器官混合，甚至产生新器官
        """
        merged = {}
        all_categories = set(p1.organs.keys()) | set(p2.organs.keys())
        
        for category in all_categories:
            organ1 = p1.organs.get(category)
            organ2 = p2.organs.get(category)
            
            if organ1 and organ2:
                # 双亲都有：随机选择或融合
                if random.random() < 0.3:
                    # 融合增强
                    base_organ = dict(organ1) if organ1.get("stage", 0) >= organ2.get("stage", 0) else dict(organ2)
                    base_organ["stage"] = min(5, base_organ.get("stage", 0) + 1)
                    merged[category] = base_organ
                else:
                    merged[category] = dict(organ1 if random.random() < 0.5 else organ2)
            elif organ1:
                merged[category] = dict(organ1)
            elif organ2:
                merged[category] = dict(organ2)
        
        return merged
    
    def _mix_chimera_morphology(self, p1: Species, p2: Species) -> dict[str, float]:
        """混合嵌合体的形态学参数"""
        mixed = {}
        
        all_keys = set(p1.morphology_stats.keys()) | set(p2.morphology_stats.keys())
        
        for key in all_keys:
            val1 = p1.morphology_stats.get(key)
            val2 = p2.morphology_stats.get(key)
            
            if val1 is None:
                mixed[key] = val2
                continue
            if val2 is None:
                mixed[key] = val1
                continue
            
            if key == "population":
                # 嵌合体初始数量极少
                mixed[key] = max(10, int(min(val1, val2) * 0.1))
            elif key in ("body_length_cm", "body_weight_g"):
                # 体型可能有较大变化
                mixed[key] = (val1 + val2) / 2 * random.uniform(0.7, 1.5)
            elif key == "lifespan_days":
                # 寿命通常缩短
                mixed[key] = min(val1, val2) * random.uniform(0.4, 0.8)
            else:
                mixed[key] = (val1 + val2) / 2 * random.uniform(0.8, 1.2)
        
        return mixed
    
    def _mix_chimera_hidden_traits(
        self, 
        p1: Species, 
        p2: Species, 
        stability: str
    ) -> dict[str, float]:
        """混合嵌合体的隐藏属性"""
        mixed = {}
        
        all_keys = set(p1.hidden_traits.keys()) | set(p2.hidden_traits.keys())
        
        for key in all_keys:
            val1 = p1.hidden_traits.get(key, 0.5)
            val2 = p2.hidden_traits.get(key, 0.5)
            
            if key == "gene_diversity":
                # 嵌合体基因多样性极高
                mixed[key] = min(1.0, (val1 + val2) / 2 * 1.5)
                
            elif key == "evolution_potential":
                # 演化潜力取决于稳定性
                base = (val1 + val2) / 2
                if stability == "stable":
                    mixed[key] = base * 1.2
                elif stability == "volatile":
                    mixed[key] = base * 0.6
                else:
                    mixed[key] = base
                    
            elif key == "mutation_rate":
                # 突变率显著提高
                mixed[key] = min(1.0, (val1 + val2) / 2 * 1.5)
                
            elif key == "environment_sensitivity":
                # 环境敏感度通常增加
                mixed[key] = min(1.0, (val1 + val2) / 2 * 1.3)
                
            else:
                mixed[key] = (val1 + val2) / 2
        
        # 添加嵌合体特有的隐藏属性
        mixed["genetic_stability"] = {
            "stable": 0.8,
            "unstable": 0.5,
            "volatile": 0.2
        }.get(stability, 0.5)
        
        return mixed
    
    def _merge_chimera_diet(self, p1: Species, p2: Species) -> tuple[str, list, dict]:
        """合并嵌合体的食性
        
        嵌合体通常是杂食性，能吃双亲能吃的所有食物
        """
        diet1 = getattr(p1, 'diet_type', None) or "omnivore"
        diet2 = getattr(p2, 'diet_type', None) or "omnivore"
        
        # 嵌合体倾向于杂食
        if diet1 != diet2:
            result_diet = "omnivore"
        else:
            result_diet = diet1
        
        # 合并猎物
        prey1 = set(getattr(p1, 'prey_species', None) or [])
        prey2 = set(getattr(p2, 'prey_species', None) or [])
        combined_prey = list(prey1 | prey2)
        
        # 合并偏好
        pref1 = dict(getattr(p1, 'prey_preferences', None) or {})
        pref2 = dict(getattr(p2, 'prey_preferences', None) or {})
        combined_pref = {}
        
        for code in set(pref1.keys()) | set(pref2.keys()):
            v1 = pref1.get(code, 0)
            v2 = pref2.get(code, 0)
            combined_pref[code] = (v1 + v2) / 2 if v1 and v2 else (v1 or v2)
        
        # 归一化
        total = sum(combined_pref.values())
        if total > 0:
            combined_pref = {k: round(v / total, 2) for k, v in combined_pref.items()}
        
        return result_diet, combined_prey, combined_pref

