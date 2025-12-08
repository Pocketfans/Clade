from __future__ import annotations

import logging
import random
from typing import Sequence

from ...models.species import Species
from ...ai.model_router import ModelRouter
from .population_calculator import PopulationCalculator
from .trait_config import TraitConfig
from .predation import PredationService
from .gene_diversity import GeneDiversityService
from .naming_hints import NamingHintGenerator, get_habitat_naming_hint

logger = logging.getLogger(__name__)


class SpeciesGenerator:
    """使用AI生成新物种"""

    def __init__(self, router: ModelRouter) -> None:
        self.router = router
        self.pop_calc = PopulationCalculator()
        self.predation_service = PredationService()
        self.gene_diversity_service = GeneDiversityService()
        self.naming_hint_generator = NamingHintGenerator()

    def _should_generate_name(self, name: str | None, min_len: int = 4) -> bool:
        """判断名称是否需要替换"""
        if not name:
            return True
        if len(name) < min_len:
            return True
        lowered = name.lower()
        if lowered.startswith("species "):
            return True
        if name.startswith("物种"):
            return True
        return False

    def _generate_names(self, data: dict, lineage_code: str) -> dict[str, str]:
        """基于特征生成更生动的学名和俗名"""
        habitat = data.get("habitat_type", "")
        diet = data.get("diet_type", "")
        seed = abs(hash(f"{lineage_code}-{habitat}-{diet}")) % 1_000_000_007
        rng = random.Random(seed)

        # 俗名：环境意象 + 形态/行为 + 类群后缀
        env_prefixes = [
            "风崖", "暮林", "霜岭", "碧潭", "玄渊", "焰原",
            "云脊", "雾沼", "潮湾", "石林", "幽谷", "寒潭",
        ]
        feature_tokens = [
            "长鳍", "厚甲", "尖吻", "羽鳍", "裂唇", "刺背",
            "盘尾", "滑翔", "潜沙", "逐雾", "攀枝", "钻泥",
        ]
        suffix_tokens = ["鱼", "兽", "蟹", "螈", "蜥", "鳗", "鸟", "蛾", "虫", "龙"]

        common_name = None
        for _ in range(6):
            candidate = (
                rng.choice(env_prefixes)
                + rng.choice(feature_tokens)
                + rng.choice(suffix_tokens)
            )
            if 4 <= len(candidate) <= 8:
                common_name = candidate
                break
        if not common_name:
            common_name = rng.choice(env_prefixes) + rng.choice(suffix_tokens)

        # 学名：根据栖息地/食性选择属名前缀 + 特征词根
        genus_roots = {
            "marine": ["Pelago", "Thalasso", "Aqua"],
            "deep_sea": ["Abysso", "Bathyo"],
            "coastal": ["Littoro", "Rupio"],
            "freshwater": ["Lacusto", "Fluvio"],
            "amphibious": ["Amphio", "Paludo"],
            "terrestrial": ["Silvestro", "Terrano"],
            "aerial": ["Aero", "Volu"],
        }
        trait_roots = {
            "autotroph": ["viridis", "luminis", "photos"],
            "herbivore": ["herbidus", "folivora"],
            "carnivore": ["raptor", "vorax", "venator"],
            "omnivore": ["omnivora", "versicolor"],
            "detritivore": ["detritus", "humilis"],
        }
        genus_choices = genus_roots.get(habitat, ["Neo", "Proto"])
        genus = f"{rng.choice(genus_choices)}{rng.choice(['sa', 'ta', 'ra', 'nia'])}"
        genus = genus.capitalize()

        species_roots = [
            "longus", "brevis", "pinnatus", "gracilis", "spinosus", "barbatus",
            "maculatus", "aureus", "caeruleus", "glacialis", "errans", "natans",
            "littoralis", "montanus", "orientalis", "noctis", "abyssalis", "volans",
        ]
        diet_suffixes = trait_roots.get(diet, [])
        epithet_pool = species_roots + diet_suffixes
        epithet = rng.choice(epithet_pool) if epithet_pool else rng.choice(species_roots)

        latin_name = f"{genus} {epithet}"

        return {"latin_name": latin_name, "common_name": common_name}

    def generate_from_prompt(
        self, 
        prompt: str, 
        lineage_code: str = "A1",
        existing_species: Sequence[Species] | None = None
    ) -> Species:
        """根据自然语言描述生成物种
        
        Args:
            prompt: 用户的自然语言描述
            lineage_code: 谱系代码，默认A1
            existing_species: 可选的现有物种列表（用于推断捕食关系）
            
        Returns:
            Species对象
        """
        logger.info(f"[物种生成器] 生成物种: {lineage_code}")
        logger.debug(f"[物种生成器] 用户描述: {prompt}")
        
        # 【优化】生成简洁的现有物种列表（不传全部物种给LLM）
        existing_species_context = ""
        if existing_species:
            # 根据prompt推测营养级范围
            prompt_lower = prompt.lower()
            if any(kw in prompt_lower for kw in ["植物", "藻类", "光合", "plant", "algae", "自养"]):
                target_trophic = (1.0, 1.5)  # 生产者
            elif any(kw in prompt_lower for kw in ["草食", "herbivore", "滤食"]):
                target_trophic = (1.0, 2.5)  # 显示生产者作为猎物
            elif any(kw in prompt_lower for kw in ["肉食", "捕食", "carnivore", "predator"]):
                target_trophic = (2.0, 4.0)  # 显示消费者作为猎物
            else:
                target_trophic = None  # 不筛选
            
            # 根据prompt推测栖息地
            target_habitat = None
            if any(kw in prompt_lower for kw in ["海洋", "海水", "ocean", "marine"]):
                target_habitat = "marine"
            elif any(kw in prompt_lower for kw in ["淡水", "湖泊", "河流"]):
                target_habitat = "freshwater"
            elif any(kw in prompt_lower for kw in ["陆地", "terrestrial"]):
                target_habitat = "terrestrial"
            
            existing_species_context = self.predation_service.generate_existing_species_context(
                existing_species,
                target_trophic_range=target_trophic,
                target_habitat=target_habitat,
                max_species=15  # 只显示15个最相关的物种
            )
        else:
            existing_species_context = "暂无现有物种"
        
        # 生成命名提示（基于lineage_code作为种子，确保可复现性）
        naming_seed = abs(hash(f"{lineage_code}-{prompt[:50]}")) % 1_000_000_007
        self.naming_hint_generator.set_seed(naming_seed)
        naming_hints = self.naming_hint_generator.generate_compact_hint()
        
        # 构建AI请求
        payload = {
            "user_prompt": prompt,
            "lineage_code": lineage_code,
            "existing_species_context": existing_species_context,
            "naming_hints": naming_hints,
            "requirements": {
                "latin_name": "拉丁学名（Genus species格式）",
                "common_name": "中文俗名",
                "description": "详细的生物学描述，必须包含：形态特征（体型、颜色、结构）、器官系统、运动方式、繁殖方式、食性（自养/异养/混合营养等）、栖息地环境、生态位角色、对环境因子的耐受性等。描述应足够详细以便后续的生态位分析。",
                "morphology_stats": {
                    "population": "初始种群数量（整数，建议100000-1000000）",
                    "body_length_cm": "体长（厘米，统一使用厘米作为单位）",
                    "body_weight_g": "体重（克，可选）",
                    "lifespan_days": "寿命（天，可选）",
                },
                "abstract_traits": {
                    "耐寒性": "0-10的整数，表示对低温的耐受性",
                    "耐旱性": "0-10的整数，表示对干旱的耐受性",
                    "耐盐性": "0-10的整数，表示对盐度的耐受性（可选）",
                    "光照需求": "0-10的整数，0表示不需要光照，10表示强光需求（可选）",
                    "繁殖速度": "0-10的整数，表示繁殖能力（可选）",
                },
                "hidden_traits": {
                    "gene_diversity": "基因多样性 0.0-1.0",
                    "environment_sensitivity": "环境敏感度 0.0-1.0",
                    "evolution_potential": "演化潜力 0.0-1.0",
                },
            }
        }
        
        # 调用AI生成（强制要求 LLM，不再使用本地规则）
        response = self.router.invoke("species_generation", payload)

        # 处理错误和本地模式
        if isinstance(response, dict) and response.get("provider") == "local":
            raise RuntimeError("LLM 未配置：species_generation 使用了 local provider")
        if isinstance(response, dict) and response.get("error"):
            raise RuntimeError(f"LLM 调用失败: {response.get('error')}")

        # 解析响应：ModelRouter 返回 {"content": {...}, ...}
        content = response.get("content") if isinstance(response, dict) else None
        if not isinstance(content, dict):
            raise RuntimeError(f"LLM 响应为空或格式错误: {response}")

        # content 可能直接是物种数据，或包含 "species"
        if "species" in content and isinstance(content["species"], dict):
            species_data = content["species"]
        else:
            species_data = content

        # 确保必需字段存在
        species_data = self._ensure_required_fields(species_data, lineage_code, prompt)

        # 如果缺少名称或名称过短，用规则生成更丰富的命名
        generated_names = self._generate_names(species_data, lineage_code)
        if self._should_generate_name(species_data.get("latin_name"), min_len=6):
            species_data["latin_name"] = generated_names["latin_name"]
        if self._should_generate_name(species_data.get("common_name"), min_len=4):
            species_data["common_name"] = generated_names["common_name"]

        # 直接从species_data中获取名称和栖息地类型
        description = species_data.get("description", prompt)
        latin_name = species_data.get("latin_name", f"Species {lineage_code.lower()}")
        common_name = species_data.get("common_name", f"物种{lineage_code}")
        habitat_type = species_data.get("habitat_type", "terrestrial")

        # 提取捕食关系字段
        diet_type = species_data.get("diet_type", "omnivore")
        prey_species = species_data.get("prey_species", [])
        prey_preferences = species_data.get("prey_preferences", {})

        # 验证食性类型
        valid_diet_types = ["autotroph", "herbivore", "carnivore", "omnivore", "detritivore"]
        if diet_type not in valid_diet_types:
            diet_type = "omnivore"

        # 【修复】根据食性设置合理的营养级
        trophic_mapping = {
            "autotroph": 1.0,
            "herbivore": 2.0,
            "carnivore": 3.5,
            "omnivore": 2.5,
            "detritivore": 1.5
        }
        trophic_level = trophic_mapping.get(diet_type, 2.0)

        # 创建物种对象
        # 注意：不再使用 ecological_vector，系统会基于 description 自动计算 embedding
        species = Species(
            lineage_code=lineage_code,
            parent_code=None,
            latin_name=latin_name,
            common_name=common_name,
            description=description,
            habitat_type=habitat_type,
            morphology_stats=species_data.get("morphology_stats", {}),
            abstract_traits=species_data.get("abstract_traits", {}),
            hidden_traits=species_data.get("hidden_traits", {}),
            ecological_vector=None,  # 不再手动设置，让系统自动计算
            status="alive",
            is_background=False,
            created_turn=0,
            trophic_level=trophic_level,  # 【修复】设置营养级
            # 捕食关系
            diet_type=diet_type,
            prey_species=prey_species if isinstance(prey_species, list) else [],
            prey_preferences=prey_preferences if isinstance(prey_preferences, dict) else {},
        )

        # 初始化基因多样性字段（默认按时代/兼容旧值）
        try:
            self.gene_diversity_service.ensure_initialized(species, turn_index=0)
        except Exception:
            pass

        # 【新增】为新物种生成初始休眠基因
        try:
            self._generate_initial_dormant_genes(species)
        except Exception as e:
            logger.warning(f"[物种生成器] 生成初始休眠基因失败: {e}")

        # 【新增】如果是消费者但没有猎物，自动分配
        if trophic_level >= 2.0 and not species.prey_species and existing_species:
            auto_prey, auto_prefs = self.predation_service.auto_assign_prey(
                species, existing_species
            )
            if auto_prey:
                species.prey_species = auto_prey
                species.prey_preferences = auto_prefs
                logger.debug(f"[物种生成器] 自动分配猎物: {auto_prey}")

        logger.info(f"[物种生成器] 物种生成成功: {species.latin_name} / {species.common_name}")
        return species

    def _ensure_required_fields(self, data: dict, lineage_code: str, prompt: str) -> dict:
        """确保必需字段存在"""
        if "latin_name" not in data:
            data["latin_name"] = f"Species {lineage_code.lower()}"
        
        if "common_name" not in data:
            data["common_name"] = f"物种{lineage_code}"
        
        if "description" not in data:
            data["description"] = prompt
        
        if "morphology_stats" not in data:
            data["morphology_stats"] = {}
        
        # 根据体型和营养级计算合理的种群数量
        # 【修复】检查 population 是否存在且为正数，否则重新计算
        current_pop = data["morphology_stats"].get("population")
        if current_pop is None or (isinstance(current_pop, (int, float)) and current_pop <= 0):
            body_length = data["morphology_stats"].get("body_length_cm", 1.0)
            body_weight = data["morphology_stats"].get("body_weight_g")
            trophic_level = data.get("trophic_level", 1.0)
            data["morphology_stats"]["population"] = self.pop_calc.get_initial_population(
                body_length, body_weight, trophic_level=trophic_level
            )
        
        if "abstract_traits" not in data:
            data["abstract_traits"] = TraitConfig.get_default_traits()
        else:
            data["abstract_traits"] = TraitConfig.merge_traits({}, data["abstract_traits"])
        
        if "hidden_traits" not in data:
            data["hidden_traits"] = {
                "gene_diversity": 0.75,
                "environment_sensitivity": 0.5,
                "evolution_potential": 0.8,
            }
        
        # 不再设置 ecological_vector，让系统基于 description 自动计算
        
        return data

    def _generate_fallback(self, prompt: str, lineage_code: str) -> dict:
        """生成备用数据（当AI失败时），尽量利用用户描述做差异化"""
        prompt = (prompt or "").strip()
        prompt_lower = prompt.lower()
        seed = abs(hash(prompt + lineage_code)) % 1_000_000_007
        rng = random.Random(seed)

        # 基于关键词推测类别与习性
        is_plant = any(kw in prompt_lower for kw in ["植物", "藻类", "光合", "plant", "algae"])
        is_carnivore = any(kw in prompt_lower for kw in ["肉食", "捕食", "carnivore", "predator"])
        is_herbivore = any(kw in prompt_lower for kw in ["草食", "herbivore", "滤食"])

        # 生成少量可见差异的名称
        base_adjectives = ["早期", "原生", "适应性强", "特化", "耐寒", "耐热", "灵活", "稳健"]
        nouns = ["生物", "物种", "演化支系", "栖居者", "形态型"]
        adj = rng.choice(base_adjectives)
        noun = rng.choice(nouns)

        # 栖息地描述
        if any(kw in prompt_lower for kw in ["海", "marine", "ocean"]):
            habitat_desc = "海洋/沿海环境"
            habitat_type = "marine"
        elif any(kw in prompt_lower for kw in ["河", "湖", "freshwater"]):
            habitat_desc = "淡水环境"
            habitat_type = "freshwater"
        elif any(kw in prompt_lower for kw in ["空中", "飞行", "aerial"]):
            habitat_desc = "空中/树冠层"
            habitat_type = "aerial"
        else:
            habitat_desc = "陆地或混合栖息地"
            habitat_type = "terrestrial"

        # 食性与营养级
        if is_plant:
            diet_desc = "自养型，以光合作用获取能量"
            diet_type = "autotroph"
            trophic_level = 1.0
        elif is_carnivore:
            diet_desc = "肉食性，主动捕猎其他生物"
            diet_type = "carnivore"
            trophic_level = 3.5
        elif is_herbivore:
            diet_desc = "草食/滤食型，依赖植物或微生物群"
            diet_type = "herbivore"
            trophic_level = 2.0
        else:
            diet_desc = "杂食性，可灵活利用多种食物来源"
            diet_type = "omnivore"
            trophic_level = 2.5

        # 体型与代谢：从提示长度做轻量扰动
        length_cm = 5 + (len(prompt) % 20) + rng.uniform(-2, 2)
        weight_g = max(0.5, (length_cm ** 2) * rng.uniform(0.3, 0.8))
        lifespan_days = max(90, int(150 + rng.uniform(-40, 80)))

        # 抽象特征做轻微差异化
        def jitter(base: float, spread: float = 1.2) -> int:
            return int(max(1, min(10, round(base + rng.uniform(-spread, spread)))))

        cold = jitter(5 + (len(prompt) % 3))
        heat = jitter(5 + rng.uniform(-1, 1))
        drought = jitter(5 + rng.uniform(-1, 1))
        salt = jitter(5 + rng.uniform(-1, 1))
        light_need = jitter(8 if is_plant else 5, spread=1.5)
        reproduction = jitter(6 + rng.uniform(-2, 2))
        locomotion = jitter(3 if is_plant else 6, spread=2.0)
        social = jitter(2 if is_plant else 4, spread=2.5)

        # 简要描述：保留用户描述片段
        prompt_snippet = prompt[:120] if prompt else "（用户未提供额外描述）"
        description = (
            f"{adj}的{noun}（推断栖息地：{habitat_desc}，食性：{diet_desc}）。"
            f"输入描述片段：{prompt_snippet}。"
            "具备基础形态与代谢系统，可在当前环境中维持稳定种群。"
        )

        latin_prefix = "Plantae" if is_plant else ("Predator" if is_carnivore else "Organism")
        common_prefix = "先锋植物" if is_plant else ("原始捕食者" if is_carnivore else "原始生物")

        return {
            "latin_name": f"{latin_prefix} {lineage_code.lower()}",
            "common_name": f"{common_prefix}-{lineage_code}",
            "description": description,
            "habitat_type": habitat_type,
            "diet_type": diet_type,
            "trophic_level": trophic_level,
            "morphology_stats": {
                "body_length_cm": round(length_cm, 2),
                "body_weight_g": round(weight_g, 2),
                "metabolic_rate": round(rng.uniform(1.2, 2.5), 2),
                "lifespan_days": lifespan_days,
            },
            "abstract_traits": {
                "耐寒性": cold,
                "耐热性": heat,
                "耐旱性": drought,
                "耐盐性": salt,
                "耐酸碱性": jitter(5),
                "光照需求": light_need,
                "氧气需求": jitter(7),
                "繁殖速度": reproduction,
                "运动能力": locomotion,
                "社会性": social,
            },
            "hidden_traits": {
                "gene_diversity": round(0.6 + rng.random() * 0.3, 3),
                "environment_sensitivity": round(0.3 + rng.random() * 0.4, 3),
                "evolution_potential": round(0.6 + rng.random() * 0.25, 3),
            },
        }

    def _create_fallback_species(self, prompt: str, lineage_code: str) -> Species:
        """创建备用物种对象"""
        data = self._generate_fallback(prompt, lineage_code)
        
        # 根据prompt推测habitat_type
        prompt_lower = prompt.lower()
        habitat_type = "terrestrial"  # 默认陆生
        if any(kw in prompt_lower for kw in ["海洋", "海水", "ocean", "marine", "海"]):
            habitat_type = "marine"
        elif any(kw in prompt_lower for kw in ["深海", "deep sea", "热液", "hydrothermal"]):
            habitat_type = "deep_sea"
        elif any(kw in prompt_lower for kw in ["湖泊", "河流", "淡水", "lake", "river", "freshwater"]):
            habitat_type = "freshwater"
        elif any(kw in prompt_lower for kw in ["两栖", "amphibious"]):
            habitat_type = "amphibious"
        elif any(kw in prompt_lower for kw in ["飞行", "空中", "aerial", "flying"]):
            habitat_type = "aerial"
        elif any(kw in prompt_lower for kw in ["海岸", "潮间带", "coastal", "intertidal"]):
            habitat_type = "coastal"
        
        # 【修复】根据prompt推测食性和营养级
        diet_type = "omnivore"  # 默认杂食
        trophic_level = 2.5
        if any(kw in prompt_lower for kw in ["植物", "藻类", "光合", "plant", "algae", "自养"]):
            diet_type = "autotroph"
            trophic_level = 1.0
        elif any(kw in prompt_lower for kw in ["肉食", "捕食", "carnivore", "predator"]):
            diet_type = "carnivore"
            trophic_level = 3.5
        elif any(kw in prompt_lower for kw in ["草食", "herbivore", "滤食"]):
            diet_type = "herbivore"
            trophic_level = 2.0
        elif any(kw in prompt_lower for kw in ["腐食", "分解", "detritivore", "decomposer"]):
            diet_type = "detritivore"
            trophic_level = 1.5
        
        species = Species(
            lineage_code=lineage_code,
            parent_code=None,
            latin_name=data["latin_name"],
            common_name=data["common_name"],
            description=data["description"],
            habitat_type=habitat_type,
            morphology_stats=data["morphology_stats"],
            abstract_traits=data["abstract_traits"],
            hidden_traits=data["hidden_traits"],
            ecological_vector=None,  # 不再手动设置，让系统自动计算
            status="alive",
            is_background=False,
            created_turn=0,
            trophic_level=trophic_level,  # 【修复】设置营养级
            diet_type=diet_type,  # 【修复】设置食性类型
        )
        
        # 【新增】为备用物种也生成初始休眠基因
        try:
            self._generate_initial_dormant_genes(species)
        except Exception as e:
            logger.warning(f"[物种生成器] 备用物种生成休眠基因失败: {e}")
        
        return species

    def generate_advanced(
        self,
        prompt: str,
        lineage_code: str,
        existing_species: Sequence[Species] | None = None,
        habitat_type: str | None = None,
        diet_type: str | None = None,
        prey_species: list[str] | None = None,
        parent_code: str | None = None,
        is_plant: bool = False,
        plant_stage: int | None = None,
    ) -> Species:
        """增强版物种生成 - 支持完整的物种创建参数
        
        Args:
            prompt: 用户的自然语言描述
            lineage_code: 谱系代码
            existing_species: 现有物种列表
            habitat_type: 预设的栖息地类型
            diet_type: 预设的食性类型
            prey_species: 预设的猎物列表
            parent_code: 父代物种代码（神启分化模式）
            is_plant: 是否为植物
            plant_stage: 植物演化阶段
            
        Returns:
            Species对象
        """
        logger.info(f"[物种生成器(增强版)] 生成物种: {lineage_code}")
        logger.debug(f"[物种生成器(增强版)] 用户描述: {prompt}")
        if parent_code:
            logger.debug(f"[物种生成器(增强版)] 父代物种: {parent_code}")
        
        # 构建增强的prompt
        enhanced_prompt = prompt
        hints = []
        
        # 栖息地提示
        habitat_names = {
            "marine": "海洋",
            "deep_sea": "深海",
            "coastal": "海岸/潮间带",
            "freshwater": "淡水",
            "amphibious": "两栖",
            "terrestrial": "陆地",
            "aerial": "空中/飞行"
        }
        if habitat_type:
            hints.append(f"栖息环境：{habitat_names.get(habitat_type, habitat_type)}")
        
        # 食性提示
        diet_names = {
            "autotroph": "自养生物（光合/化能合成，无需捕食）",
            "herbivore": "草食动物（以植物为食）",
            "carnivore": "肉食动物（以其他动物为食）",
            "omnivore": "杂食动物（植物和动物都吃）",
            "detritivore": "腐食/分解者"
        }
        if diet_type:
            hints.append(f"食性类型：{diet_names.get(diet_type, diet_type)}")
        
        # 猎物提示
        if prey_species and len(prey_species) > 0:
            prey_info = []
            if existing_species:
                for prey_code in prey_species:
                    prey_sp = next((s for s in existing_species if s.lineage_code == prey_code), None)
                    if prey_sp:
                        prey_info.append(f"{prey_code}({prey_sp.common_name})")
                    else:
                        prey_info.append(prey_code)
            else:
                prey_info = prey_species
            hints.append(f"主要猎物：{', '.join(prey_info)}")
        
        # 植物特化提示
        if is_plant:
            hints.append("这是一种植物/生产者类生物")
            if plant_stage is not None:
                stage_names = {
                    0: "原核光合生物（蓝藻、光合细菌）",
                    1: "单细胞真核藻类（绿藻、硅藻）",
                    2: "多细胞群体藻类",
                    3: "苔藓类（首批登陆植物）",
                    4: "蕨类（维管植物先驱）",
                    5: "裸子植物（种子植物）",
                    6: "被子植物（开花植物）"
                }
                hints.append(f"演化阶段：{stage_names.get(plant_stage, f'阶段{plant_stage}')}")
        
        # 父代物种提示（神启分化模式）
        parent_species = None
        if parent_code and existing_species:
            parent_species = next((s for s in existing_species if s.lineage_code == parent_code), None)
            if parent_species:
                hints.append(f"这是从物种{parent_code}({parent_species.common_name})分化而来的新物种")
                hints.append(f"父代特征参考：{parent_species.description[:100]}...")
        
        # 组合增强提示
        if hints:
            enhanced_prompt = f"{prompt}\n\n【用户预设参数】\n" + "\n".join(f"- {h}" for h in hints)
        
        # 使用基础生成方法
        species = self.generate_from_prompt(enhanced_prompt, lineage_code, existing_species)
        
        # 覆盖用户预设的参数
        if habitat_type:
            species.habitat_type = habitat_type
        
        if diet_type:
            species.diet_type = diet_type
            # 根据食性设置合理的营养级
            trophic_mapping = {
                "autotroph": 1.0,
                "herbivore": 2.0,
                "carnivore": 3.5,
                "omnivore": 2.5,
                "detritivore": 1.5
            }
            species.trophic_level = trophic_mapping.get(diet_type, 2.0)
        
        if prey_species:
            species.prey_species = prey_species
            # 均分猎物偏好
            if len(prey_species) > 0:
                pref = 1.0 / len(prey_species)
                species.prey_preferences = {p: pref for p in prey_species}
        elif species.trophic_level >= 2.0 and not species.prey_species and existing_species:
            # 【新增】如果是消费者但没有猎物，自动分配
            auto_prey, auto_prefs = self.predation_service.auto_assign_prey(
                species, existing_species
            )
            if auto_prey:
                species.prey_species = auto_prey
                species.prey_preferences = auto_prefs
                logger.debug(f"[物种生成器(增强版)] 自动分配猎物: {auto_prey}")
        
        if parent_code:
            species.parent_code = parent_code
            # 如果有父代，继承部分特征
            if parent_species:
                # 继承一些隐性特征（基因多样性略低）
                if hasattr(parent_species, 'hidden_traits') and parent_species.hidden_traits:
                    species.hidden_traits = {
                        **species.hidden_traits,
                        "gene_diversity": max(0.3, parent_species.hidden_traits.get("gene_diversity", 0.7) * 0.9),
                    }
        
        # 植物特化设置
        if is_plant:
            species.trophic_level = 1.0
            species.diet_type = "autotroph"
            species.prey_species = []
            species.prey_preferences = {}
            
            if plant_stage is not None:
                species.life_form_stage = plant_stage
                # 设置生长形式
                form_mapping = {0: "aquatic", 1: "aquatic", 2: "aquatic", 3: "moss", 4: "herb", 5: "shrub", 6: "tree"}
                species.growth_form = form_mapping.get(plant_stage, "aquatic")
        
        logger.info(f"[物种生成器(增强版)] 物种生成成功: {species.latin_name} / {species.common_name}")
        return species

    def _generate_initial_dormant_genes(self, species) -> None:
        """为新物种生成初始休眠基因 v3.0（快速进化版本）
        
        根据物种的生态特性（栖息地、食性、营养级）生成符合其特质的休眠基因。
        
        【v3.0 快速进化增强】
        - 显隐性遗传：每个基因有显隐性类型
        - 有害突变：25%概率生成有害基因（提供自然选择原料）
        - 细化压力类型：使用新的压力-基因映射系统
        - 器官发育阶段：器官初始为未发育状态
        - 更多基因：大幅提升各类基因生成概率，为演化预埋丰富种子
        """
        from .gene_constants import (
            DominanceType,
            MutationEffect,
            HARMFUL_MUTATIONS,
            roll_dominance,
        )
        
        if species.dormant_genes is None:
            species.dormant_genes = {"traits": {}, "organs": {}}
        
        species.dormant_genes.setdefault("traits", {})
        species.dormant_genes.setdefault("organs", {})
        
        # 使用物种信息作为种子确保可重复性
        seed = abs(hash(f"{species.lineage_code}-dormant-gen-v2")) % 1_000_000_007
        rng = random.Random(seed)
        
        # 获取物种生态位信息
        habitat = getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial'
        diet = getattr(species, 'diet_type', 'omnivore') or 'omnivore'
        trophic = getattr(species, 'trophic_level', 2.0) or 2.0
        
        is_producer = diet == "autotroph" or trophic < 1.5
        is_consumer = diet in ("herbivore", "carnivore", "omnivore") or trophic >= 2.0
        is_predator = diet == "carnivore" or trophic >= 3.0
        is_aquatic = habitat in ("marine", "freshwater", "deep_sea", "coastal", "hydrothermal")
        is_terrestrial = habitat in ("terrestrial", "aerial")
        is_deep_sea = habitat in ("deep_sea", "hydrothermal")
        is_amphibious = habitat == "amphibious"
        
        # ========== 1. 基于现有特质生成强化版休眠基因（概率提升到85%）==========
        for trait_name, trait_value in (species.abstract_traits or {}).items():
            if rng.random() < 0.85:  # 85%概率生成强化版
                enhanced_name = f"强化{trait_name}" if not trait_name.startswith("强化") else trait_name
                if enhanced_name not in species.dormant_genes["traits"]:
                    dominance = roll_dominance("trait")
                    species.dormant_genes["traits"][enhanced_name] = {
                        "potential_value": min(15.0, float(trait_value) * 1.35),  # 提升潜力值
                        "activation_threshold": 0.18,  # 降低激活门槛
                        "pressure_types": self._infer_pressure_types_for_trait(trait_name),
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": "initial",
                        "dominance": dominance.value,
                        "mutation_effect": MutationEffect.BENEFICIAL.value,
                    }
        
        # ========== 2. 根据生态位生成特化休眠特质 ==========
        ecological_traits = []
        
        if is_producer:
            ecological_traits.extend([
                ("光合效率提升", ["light_limitation"], 6.0),
                ("固碳强化", ["nutrient_poor", "competition"], 5.5),
            ])
        
        if is_consumer:
            ecological_traits.extend([
                ("消化效率", ["starvation", "competition"], 5.5),
                ("感知敏锐", ["predation", "hunting"], 5.0),
            ])
        
        if is_predator:
            ecological_traits.extend([
                ("捕猎本能", ["hunting"], 6.0),
            ])
        
        if is_aquatic:
            ecological_traits.extend([
                ("流线型优化", ["predation"], 5.0),
            ])
        
        if is_terrestrial:
            ecological_traits.extend([
                ("保水强化", ["drought"], 6.0),
            ])
        
        if is_deep_sea:
            ecological_traits.extend([
                ("耐压强化", ["pressure_deep"], 7.0),
            ])
        
        # 通用特质
        ecological_traits.extend([
            ("环境适应性", ["competition", "temperature_fluctuation"], rng.uniform(4.5, 6.5)),
            ("恢复力", ["disease", "abrasion"], rng.uniform(4.0, 6.0)),
        ])
        
        for trait_name, pressure_types, base_value in ecological_traits:
            if trait_name not in (species.abstract_traits or {}) and trait_name not in species.dormant_genes["traits"]:
                if rng.random() < 0.75:  # 75%概率生成生态位特化基因
                    dominance = roll_dominance("trait")
                    species.dormant_genes["traits"][trait_name] = {
                        "potential_value": base_value + rng.uniform(0.5, 2.0),  # 提升潜力值范围
                        "activation_threshold": 0.15,  # 降低激活门槛
                        "pressure_types": pressure_types,
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": "ecological",
                        "dominance": dominance.value,
                        "mutation_effect": MutationEffect.BENEFICIAL.value,
                    }
        
        # ========== 2.5 添加有害突变（25%概率，提供自然选择原料） ==========
        if rng.random() < 0.25:
            harmful_list = [m for m in HARMFUL_MUTATIONS 
                          if m["effect"] in (MutationEffect.MILDLY_HARMFUL, MutationEffect.HARMFUL)]
            if harmful_list:
                harmful = rng.choice(harmful_list)
                harm_name = harmful["name"]
                if harm_name not in species.dormant_genes["traits"]:
                    species.dormant_genes["traits"][harm_name] = {
                        "potential_value": 0,
                        "target_trait": harmful.get("target_trait"),
                        "value_modifier": harmful.get("value_modifier", -1.0),
                        "activation_threshold": 0.35,
                        "pressure_types": ["disease", "starvation"],
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": "mutation",
                        "dominance": DominanceType.RECESSIVE.value,
                        "mutation_effect": harmful["effect"].value if hasattr(harmful["effect"], 'value') else str(harmful["effect"]),
                        "description": harmful.get("description", ""),
                    }
                    logger.debug(f"[物种生成器] {species.lineage_code} 生成有害突变: {harm_name}")
        
        # ========== 3. 根据生态位生成符合物种特性的休眠器官 ==========
        potential_organs = []
        
        if is_producer:
            potential_organs.extend([
                {"name": "增强叶绿体", "category": "photosynthetic", "type": "enhanced_chloroplast", 
                 "parameters": {"efficiency": 1.5}, "pressure_types": ["light_limitation"], "prob": 0.75},
                {"name": "UV防护层", "category": "protection", "type": "uv_shield", 
                 "parameters": {"uv_resist": 0.7}, "pressure_types": ["uv_radiation", "abrasion"], "prob": 0.55},
                {"name": "储能体", "category": "storage", "type": "energy_storage", 
                 "parameters": {"capacity": 0.6}, "pressure_types": ["starvation"], "prob": 0.50},
            ])
        
        if is_consumer:
            if not is_deep_sea:
                potential_organs.append(
                    {"name": "原始眼点", "category": "sensory", "type": "eyespot", 
                     "parameters": {"sensitivity": 0.5}, "pressure_types": ["predation", "hunting"], "prob": 0.65}
                )
            potential_organs.extend([
                {"name": "化学感受器", "category": "sensory", "type": "chemoreceptor", 
                 "parameters": {"range": 0.4}, "pressure_types": ["predation", "starvation"], "prob": 0.70},
                {"name": "原始消化腔", "category": "digestive", "type": "primitive_gut", 
                 "parameters": {"efficiency": 0.4}, "pressure_types": ["starvation"], "prob": 0.55},
            ])
        
        if is_predator:
            potential_organs.extend([
                {"name": "捕食附肢", "category": "attack", "type": "grasping_appendage", 
                 "parameters": {"grip_strength": 0.6}, "pressure_types": ["hunting"], "prob": 0.70},
                {"name": "毒腺原基", "category": "attack", "type": "venom_gland", 
                 "parameters": {"toxicity": 0.3}, "pressure_types": ["hunting", "defense"], "prob": 0.40},
            ])
        
        if is_aquatic:
            potential_organs.extend([
                {"name": "纤毛", "category": "locomotion", "type": "cilia", 
                 "parameters": {"efficiency": 0.5}, "pressure_types": ["predation"], "prob": 0.65},
                {"name": "浮力调节囊", "category": "buoyancy", "type": "swim_bladder", 
                 "parameters": {"control": 0.5}, "pressure_types": ["pressure_deep"], "prob": 0.50},
                {"name": "侧线原基", "category": "sensory", "type": "lateral_line", 
                 "parameters": {"sensitivity": 0.4}, "pressure_types": ["predation", "hunting"], "prob": 0.45},
            ])
        
        if is_terrestrial:
            potential_organs.extend([
                {"name": "角质层强化", "category": "protection", "type": "cuticle", 
                 "parameters": {"drought_resist": 0.6}, "pressure_types": ["drought"], "prob": 0.65},
                {"name": "气孔原基", "category": "respiratory", "type": "stomata", 
                 "parameters": {"gas_exchange": 0.4}, "pressure_types": ["oxygen_low"], "prob": 0.50},
            ])
        
        if is_deep_sea:
            potential_organs.extend([
                {"name": "耐压细胞壁", "category": "protection", "type": "pressure_resistant", 
                 "parameters": {"pressure_resist": 0.8}, "pressure_types": ["pressure_deep"], "prob": 0.75},
                {"name": "热感受器", "category": "sensory", "type": "thermoreceptor", 
                 "parameters": {"range": 0.5}, "pressure_types": ["heat"], "prob": 0.55},
                {"name": "发光器原基", "category": "bioluminescence", "type": "photophore", 
                 "parameters": {"intensity": 0.3}, "pressure_types": ["predation", "hunting"], "prob": 0.40},
            ])
        
        # 通用器官（所有物种都可能生成）
        potential_organs.extend([
            {"name": "防护外壳", "category": "defense", "type": "shell", 
             "parameters": {"hardness": 0.4}, "pressure_types": ["predation"], "prob": 0.45},
            {"name": "再生组织", "category": "regeneration", "type": "regenerative_tissue", 
             "parameters": {"rate": 0.3}, "pressure_types": ["abrasion", "predation"], "prob": 0.35},
            {"name": "原始神经索", "category": "nervous", "type": "nerve_cord", 
             "parameters": {"coordination": 0.3}, "pressure_types": ["predation", "hunting"], "prob": 0.30},
        ])
        
        for organ in potential_organs:
            prob = organ.get("prob", 0.30)
            if rng.random() < prob:
                organ_name = organ["name"]
                if organ_name not in species.dormant_genes["organs"]:
                    dominance = roll_dominance("organ")
                    species.dormant_genes["organs"][organ_name] = {
                        "organ_data": {
                            "category": organ["category"],
                            "type": organ["type"],
                            "parameters": organ["parameters"]
                        },
                        "activation_threshold": 0.18,
                        "pressure_types": organ.get("pressure_types", ["competition", "predation"]),
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": "ecological",
                        "dominance": dominance.value,
                        "development_stage": None,  # 渐进发育系统
                        "stage_start_turn": None,
                    }
        
        # 统计生成结果
        total_traits = len(species.dormant_genes.get("traits", {}))
        total_organs = len(species.dormant_genes.get("organs", {}))
        harmful_count = sum(1 for t in species.dormant_genes.get("traits", {}).values() 
                          if t.get("mutation_effect") in (MutationEffect.HARMFUL.value, 
                                                          MutationEffect.MILDLY_HARMFUL.value,
                                                          "harmful", "mildly_harmful"))
        if total_traits + total_organs > 0:
            logger.info(
                f"[物种生成器] {species.lineage_code} 生成了 "
                f"{total_traits} 个休眠特质 (含 {harmful_count} 个有害), {total_organs} 个休眠器官"
            )

    def _infer_pressure_types_for_trait(self, trait_name: str) -> list[str]:
        """根据特质名推断触发压力类型（使用新系统）"""
        mapping = {
            "耐寒性": ["cold", "temperature_fluctuation"],
            "耐热性": ["heat", "temperature_fluctuation"],
            "耐旱性": ["drought"],
            "耐盐性": ["salinity"],
            "免疫力": ["disease", "parasitism"],
            "运动能力": ["predation", "hunting"],
            "繁殖速度": ["starvation", "competition"],
            "社会性": ["competition"],
            "光合效率": ["light_limitation"],
            "固碳能力": ["nutrient_poor", "competition"],
            "攻击性": ["hunting", "competition"],
            "防御能力": ["predation"],
            "代谢效率": ["starvation"],
            "感知敏锐": ["predation", "hunting"],
        }
        for key, types in mapping.items():
            if key in trait_name:
                return types
        return ["competition", "starvation"]

