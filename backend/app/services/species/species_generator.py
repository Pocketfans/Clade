from __future__ import annotations

from ...models.species import Species
from ...ai.model_router import ModelRouter
from .population_calculator import PopulationCalculator
from .trait_config import TraitConfig


class SpeciesGenerator:
    """使用AI生成新物种"""

    def __init__(self, router: ModelRouter) -> None:
        self.router = router
        self.pop_calc = PopulationCalculator()

    def generate_from_prompt(self, prompt: str, lineage_code: str = "A1") -> Species:
        """根据自然语言描述生成物种
        
        Args:
            prompt: 用户的自然语言描述
            lineage_code: 谱系代码，默认A1
            
        Returns:
            Species对象
        """
        print(f"[物种生成器] 生成物种: {lineage_code}")
        print(f"[物种生成器] 用户描述: {prompt}")
        
        # 构建AI请求
        payload = {
            "user_prompt": prompt,
            "lineage_code": lineage_code,
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
        
        try:
            # 调用AI生成
            response = self.router.invoke("species_generation", payload)
            
            # 解析响应：ModelRouter 返回 {"content": {...}, ...}
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                # content 可能直接就是物种数据，或者包含 "species" 字段
                if "species" in content:
                    species_data = content["species"]
                else:
                    species_data = content
            else:
                # AI返回格式不正确，使用默认值
                print(f"[物种生成器] AI响应格式不正确，使用模板生成")
                print(f"[物种生成器] 响应内容: {response}")
                species_data = self._generate_fallback(prompt, lineage_code)
            
            # 确保必需字段存在
            species_data = self._ensure_required_fields(species_data, lineage_code, prompt)
            
            # 直接从species_data中获取名称和栖息地类型
            description = species_data.get("description", prompt)
            latin_name = species_data.get("latin_name", f"Species {lineage_code.lower()}")
            common_name = species_data.get("common_name", f"物种{lineage_code}")
            habitat_type = species_data.get("habitat_type", "terrestrial")
            
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
            )
            
            print(f"[物种生成器] 物种生成成功: {species.latin_name} / {species.common_name}")
            return species
            
        except Exception as e:
            print(f"[物种生成器] AI生成失败，使用模板: {e}")
            return self._create_fallback_species(prompt, lineage_code)

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
        
        # 根据体型计算合理的种群数量
        if "population" not in data["morphology_stats"]:
            body_length = data["morphology_stats"].get("body_length_cm", 1.0)
            body_weight = data["morphology_stats"].get("body_weight_g")
            data["morphology_stats"]["population"] = self.pop_calc.get_initial_population(
                body_length, body_weight
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
        """生成备用数据（当AI失败时）"""
        # 根据提示词推测物种类型
        prompt_lower = prompt.lower()
        
        if any(kw in prompt_lower for kw in ["植物", "藻类", "光合", "plant", "algae"]):
            return {
                "latin_name": f"Plantae {lineage_code.lower()}",
                "common_name": "原始植物",
                "description": (
                    f"基于用户描述生成的植物物种：{prompt}。"
                    "具有光合能力，通过叶绿体进行光合作用，从阳光中获取能量，固定二氧化碳生产有机物。"
                    "细胞壁由纤维素构成，提供结构支撑。繁殖方式包括无性繁殖和有性生殖。"
                    "作为初级生产者，在生态系统中处于食物链基础位置。"
                    "对光照有较高需求，耐旱性中等，适应温带至热带环境。"
                ),
                "morphology_stats": {
                    "body_length_cm": 5,
                    "body_weight_g": 0.5,
                    "metabolic_rate": 2.0,
                    "lifespan_days": 180,
                },
                "abstract_traits": {
                    "耐寒性": 6,
                    "耐热性": 6,
                    "耐旱性": 4,
                    "耐盐性": 5,
                    "耐酸碱性": 5,
                    "光照需求": 9,
                    "氧气需求": 8,
                    "繁殖速度": 6,
                    "运动能力": 3,
                    "社会性": 2,
                },
                "hidden_traits": {"gene_diversity": 0.8, "environment_sensitivity": 0.3, "evolution_potential": 0.85},
            }
        elif any(kw in prompt_lower for kw in ["肉食", "捕食", "carnivore", "predator"]):
            return {
                "latin_name": f"Predator {lineage_code.lower()}",
                "common_name": "原始捕食者",
                "description": (
                    f"基于用户描述生成的捕食性物种：{prompt}。"
                    "异养生物，通过主动捕食其他生物获取能量和营养。"
                    "具有发达的感觉器官用于探测猎物，强健的肌肉系统用于追逐，"
                    "锐利的牙齿或其他捕食结构用于捕获和撕咬猎物。"
                    "繁殖速度较慢，但个体生存能力强。"
                    "在生态系统中处于较高营养级，对种群数量有调控作用。"
                    "对环境变化较为敏感，需要稳定的猎物来源。"
                ),
                "morphology_stats": {
                    "body_length_cm": 20,
                    "body_weight_g": 150,
                    "metabolic_rate": 1.5,
                    "lifespan_days": 365,
                },
                "abstract_traits": {
                    "耐寒性": 5,
                    "耐热性": 5,
                    "耐旱性": 6,
                    "耐盐性": 4,
                    "耐酸碱性": 5,
                    "光照需求": 3,
                    "氧气需求": 8,
                    "繁殖速度": 4,
                    "运动能力": 8,
                    "社会性": 5,
                },
                "hidden_traits": {"gene_diversity": 0.7, "environment_sensitivity": 0.6, "evolution_potential": 0.8},
            }
        else:
            return {
                "latin_name": f"Organism {lineage_code.lower()}",
                "common_name": "原始生物",
                "description": (
                    f"基于用户描述生成的生物物种：{prompt}。"
                    "具有基本的生命活动能力，包括新陈代谢、生长、繁殖等。"
                    "形态结构相对简单，但能够适应特定环境。"
                    "食性可能为杂食性，能够利用多种食物来源。"
                    "繁殖方式灵活，适应能力较强。"
                    "在生态系统中扮演中间角色，连接不同营养级。"
                ),
                "morphology_stats": {
                    "body_length_cm": 10,
                    "body_weight_g": 10,
                    "metabolic_rate": 2.0,
                    "lifespan_days": 270,
                },
                "abstract_traits": {
                    "耐寒性": 5,
                    "耐热性": 5,
                    "耐旱性": 5,
                    "耐盐性": 5,
                    "耐酸碱性": 5,
                    "光照需求": 5,
                    "氧气需求": 7,
                    "繁殖速度": 6,
                    "运动能力": 5,
                    "社会性": 3,
                },
                "hidden_traits": {"gene_diversity": 0.75, "environment_sensitivity": 0.5, "evolution_potential": 0.8},
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
        
        return Species(
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
        )

