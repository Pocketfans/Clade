from __future__ import annotations

import logging
import random
from datetime import datetime

from ..models.genus import Genus
from ..models.species import Species
from ..repositories.genus_repository import genus_repository
from ..repositories.species_repository import species_repository
from ..services.species.trophic import TrophicLevelCalculator

logger = logging.getLogger(__name__)

A_SCENARIO = [
    {
        "lineage_code": "A1",
        "latin_name": "Algaprimordia pelagica",
        "common_name": "海洋微藻",
        "genus_code": "A",
        "habitat_type": "marine",  # 海洋生物
        "trophic_level": 1.0,  # T1: 生产者
        "diet_type": "autotroph",  # 自养
        # 【新增】植物演化系统字段
        "life_form_stage": 1,  # 单细胞真核藻类
        "growth_form": "aquatic",  # 水生
        "achieved_milestones": ["first_eukaryote"],  # 已达成：真核化
        "description": (
            "单细胞光合生物，球形，体长8微米。细胞壁透明，内含叶绿体进行光合作用。"
            "漂浮于浅海上层水域，通过二分裂快速繁殖。自养型，固定二氧化碳生产有机物。"
            "栖息于温带至热带浅海0-50米，需充足光照。作为初级生产者，是浮游动物主要食物来源。"
        ),
        "morphology_stats": {
            # 【平衡调整】从小族群开始演化
            # 初始种群较小，让物种有增长空间
            # 微藻作为生产者，初始 500万，加速前几回合形成食物网
            "population": 5000000,  # 500万
            "body_length_cm": 0.0008,
            "body_weight_g": 0.000000001,  # 1纳克
            "body_surface_area_cm2": 0.000002,
            "lifespan_days": 7,
            "generation_time_days": 1,  # 1天一代，快速繁殖
            "metabolic_rate": 5.0,
        },
        "abstract_traits": {
            # 共享特质
            "耐寒性": 1.0,
            "耐热性": 6.0,
            "耐旱性": 1.0,
            "耐盐性": 4.0,
            "光照需求": 5.0,
            "繁殖速度": 8.0,  # 提高繁殖速度，支撑食物链
            # 植物专属特质
            "光合效率": 5.0,
            "固碳能力": 5.0,
            "多细胞程度": 1.0,  # 单细胞
            "保水能力": 1.0,  # 水生不需要保水
            "散布能力": 3.0,
        },
        "organs": {
            "photosynthetic": {
                "type": "叶绿体",
                "parameters": {
                    "efficiency": 1.0,
                },
                "acquired_turn": 0,
                "is_active": True
            },
            "protection": {
                "type": "粘液层",
                "parameters": {
                    "uv_resist": 0.5,
                    "drought_resist": 0.3
                },
                "acquired_turn": 0,
                "is_active": True
            }
        },
        "capabilities": ["光合作用", "自养"],
        "hidden_traits": {
            "gene_diversity": 0.8,
            "environment_sensitivity": 0.4,
            "evolution_potential": 0.9,
            "mutation_rate": 0.6,
            "adaptation_speed": 0.7,
        },
    },
    {
        "lineage_code": "B1",
        "latin_name": "Protoflagella vorax",
        "common_name": "原始鞭毛虫",
        "genus_code": "B",
        "habitat_type": "marine",  # 海洋生物
        "trophic_level": 2.0,  # T2: 初级消费者（吃微藻的浮游动物）
        "diet_type": "herbivore",  # 【新增】草食性
        "prey_species": ["A1"],  # 捕食微藻
        "prey_preferences": {"A1": 1.0},  # 100%依赖微藻
        "description": (
            "单细胞异养生物，梨形，体长15微米。前端1-2根鞭毛用于游动和捕食。"
            "主动捕食微藻和有机碎屑，通过鞭毛将食物送入胞口。纵向二分裂繁殖。"
            "栖息浅海至中层水域，垂直迁移觅食。初级消费者，连接生产者和更高营养级。运动灵活，具趋光性和趋化性。"
        ),
        "morphology_stats": {
            # 【平衡调整】从小族群开始演化
            "population": 500000,  
            "body_length_cm": 0.0015,
            "body_weight_g": 0.000000003,  # 3纳克
            "body_surface_area_cm2": 0.000007,
            "lifespan_days": 14,
            "generation_time_days": 3,  # 3天一代
            "metabolic_rate": 3.5,
        },
        "abstract_traits": {
            "耐寒性": 2.0,
            "耐热性": 4.0,
            "耐旱性": 1.0,
            "耐盐性": 4.0,
            "光照需求": 2.0,  # 需要光照来追踪微藻
            "繁殖速度": 5.0,  # 中等繁殖速度
            "运动能力": 4.0,
            "攻击性": 3.0,  # 捕食能力
        },
        "organs": {
            "locomotion": {
                "type": "双鞭毛",
                "parameters": {
                    "count": 2,
                    "length_um": 10,
                    "efficiency": 1.0
                },
                "acquired_turn": 0,
                "is_active": True
            },
            "sensory": {
                "type": "化学感受器",
                "parameters": {
                    "sensitivity": 0.5,
                    "range_cm": 3
                },
                "acquired_turn": 0,
                "is_active": True
            }
        },
        "capabilities": ["鞭毛运动", "化学感知", "异养", "捕食微藻"],
        "hidden_traits": {
            "gene_diversity": 0.7,
            "environment_sensitivity": 0.6,
            "evolution_potential": 0.85,
            "mutation_rate": 0.5,
            "adaptation_speed": 0.6,
        },
    },
    {
        "lineage_code": "C1",
        "latin_name": "Thiobacter obstinata",
        "common_name": "硫细菌",
        "genus_code": "C",
        "habitat_type": "hydrothermal",  # 热泉生物（深海火山/热液喷口）
        "trophic_level": 1.0,  # T1: 生产者（化能自养，深海食物链基础）
        "diet_type": "autotroph",  # 自养
        # 【新增】植物演化系统字段（原核生物，尚未真核化）
        "life_form_stage": 0,  # 原核光合/化能生物
        "growth_form": "aquatic",  # 水生
        "achieved_milestones": [],  # 无里程碑（原核阶段）
        "description": (
            "单细胞化能合成细菌，杆状或球状，体长5微米。细胞壁坚固，抵抗极端环境。"
            "氧化硫化氢获取能量，合成有机物。二分裂繁殖，生长慢但生命力强。"
            "栖息深海热液喷口、火山口等极端环境。耐高温高压低氧。极端生态系统的初级生产者，支撑化能合成食物链。"
        ),
        "morphology_stats": {
            # 【平衡调整】从小族群开始演化
            # 深海生态系统的基础生产者，初始 25万
            "population": 250000,  # 25万
            "body_length_cm": 0.0005,
            "body_weight_g": 0.0000000005,  # 0.5纳克
            "body_surface_area_cm2": 0.000001,
            "lifespan_days": 30,
            "generation_time_days": 5,  # 5天一代
            "metabolic_rate": 1.5,
        },
        "abstract_traits": {
            # 共享特质
            "耐寒性": 5.0,
            "耐热性": 5.0,
            "耐旱性": 4.0,
            "耐盐性": 4.0,
            "光照需求": 0.0,  # 不需要光照（化能合成）
            "繁殖速度": 4.0,
            # 植物专属特质（化能合成版本）
            "光合效率": 0.0,  # 化能合成，无光合
            "固碳能力": 4.0,  # 仍可固碳
            "多细胞程度": 0.5,  # 原核单细胞
            "保水能力": 2.0,
        },
        "organs": {
            "photosynthetic": {
                "type": "原始色素体",
                "parameters": {
                    "efficiency": 0.0,  # 化能合成不用光
                },
                "acquired_turn": 0,
                "is_active": False  # 未激活
            },
            "protection": {
                "type": "细胞壁加厚",
                "parameters": {
                    "uv_resist": 0.8,
                    "drought_resist": 0.5
                },
                "acquired_turn": 0,
                "is_active": True
            }
        },
        "capabilities": ["化能合成", "嗜极生物", "自养"],
        "hidden_traits": {
            "gene_diversity": 0.65,
            "environment_sensitivity": 0.3,
            "evolution_potential": 0.7,
            "mutation_rate": 0.4,
            "adaptation_speed": 0.5,
        },
    },
]

# ============ 繁荣生态剧本 ============
# 模拟约150回合后的成熟生态系统
# 包含15+物种，覆盖多种栖息地类型和营养级
THRIVING_ECOSYSTEM_SCENARIO = [
    # ============ 生产者层 (T1.0-1.5) ============
    {
        "lineage_code": "A1",
        "latin_name": "Algacolonia maritima",
        "common_name": "群体海藻",
        "genus_code": "A",
        "habitat_type": "marine",
        "trophic_level": 1.0,
        "diet_type": "autotroph",
        "life_form_stage": 2,  # 多细胞群体藻类
        "growth_form": "aquatic",
        "achieved_milestones": ["first_eukaryote", "multicellular_colony"],
        "created_turn": 0,
        "description": (
            "多细胞群体藻类，由数千个细胞组成球状或带状群体，直径可达2毫米。"
            "细胞间有初步分化，外层细胞专司光合作用，内层储存营养。"
            "漂浮于温带浅海表层0-30米，是海洋生态系统的主要初级生产者。"
            "经历150万年演化，已形成稳定的群体协作机制。"
        ),
        "morphology_stats": {
            "population": 1600000,  # 160万群体
            "body_length_cm": 0.2,  # 2mm群体
            "body_weight_g": 0.00001,
            "body_surface_area_cm2": 0.12,
            "lifespan_days": 30,
            "generation_time_days": 5,
            "metabolic_rate": 4.0,
        },
        "abstract_traits": {
            "耐寒性": 3.0,
            "耐热性": 5.5,
            "耐旱性": 1.0,
            "耐盐性": 6.0,
            "光照需求": 6.0,
            "繁殖速度": 7.0,
            "光合效率": 6.5,
            "固碳能力": 6.0,
            "多细胞程度": 3.0,
            "保水能力": 2.0,
            "散布能力": 4.0,
        },
        "organs": {
            "photosynthetic": {
                "type": "增强叶绿体",
                "parameters": {"efficiency": 1.8},
                "acquired_turn": 50,
                "is_active": True
            },
            "protection": {
                "type": "胶质外膜",
                "parameters": {"uv_resist": 0.7, "drought_resist": 0.4},
                "acquired_turn": 80,
                "is_active": True
            }
        },
        "capabilities": ["光合作用", "自养", "群体协作", "浮力调节"],
        "hidden_traits": {
            "gene_diversity": 0.75,
            "environment_sensitivity": 0.35,
            "evolution_potential": 0.8,
            "mutation_rate": 0.5,
            "adaptation_speed": 0.65,
        },
    },
    {
        "lineage_code": "A2",
        "latin_name": "Bryophyta primordia",
        "common_name": "原始苔藓",
        "genus_code": "A",
        "habitat_type": "terrestrial",
        "trophic_level": 1.0,
        "diet_type": "autotroph",
        "life_form_stage": 3,  # 苔藓类
        "growth_form": "moss",
        "achieved_milestones": ["first_eukaryote", "multicellular_colony", "land_colonization"],
        "created_turn": 60,
        "parent_code": "A1",  # 从海藻演化而来
        "description": (
            "陆地先驱植物，形成致密的绿色垫状群落，高度约5毫米。"
            "没有真正的根系，依靠假根附着于岩石和土壤表面。"
            "需要潮湿环境繁殖，通过孢子散布。已成功定居温带湿润地区，"
            "为后续陆地生态系统的建立奠定了基础。"
        ),
        "morphology_stats": {
            "population": 1000000,
            "body_length_cm": 0.5,
            "body_weight_g": 0.001,
            "body_surface_area_cm2": 0.3,
            "lifespan_days": 180,
            "generation_time_days": 30,
            "metabolic_rate": 2.5,
        },
        "abstract_traits": {
            "耐寒性": 5.0,
            "耐热性": 4.0,
            "耐旱性": 3.5,
            "耐盐性": 2.0,
            "光照需求": 4.0,
            "繁殖速度": 4.0,
            "光合效率": 5.0,
            "固碳能力": 4.5,
            "多细胞程度": 4.0,
            "保水能力": 5.0,
            "散布能力": 5.5,
        },
        "organs": {
            "photosynthetic": {
                "type": "陆生叶绿体",
                "parameters": {"efficiency": 1.5},
                "acquired_turn": 70,
                "is_active": True
            },
            "protection": {
                "type": "角质层",
                "parameters": {"uv_resist": 0.8, "drought_resist": 0.6},
                "acquired_turn": 90,
                "is_active": True
            },
            "root": {
                "type": "假根",
                "parameters": {"absorption": 0.4, "anchor": 0.6},
                "acquired_turn": 65,
                "is_active": True
            }
        },
        "capabilities": ["光合作用", "自养", "陆地定居", "孢子繁殖"],
        "hidden_traits": {
            "gene_diversity": 0.7,
            "environment_sensitivity": 0.5,
            "evolution_potential": 0.85,
            "mutation_rate": 0.45,
            "adaptation_speed": 0.55,
        },
    },
    {
        "lineage_code": "A3",
        "latin_name": "Cyanobacteria lacustris",
        "common_name": "淡水蓝藻",
        "genus_code": "A",
        "habitat_type": "freshwater",
        "trophic_level": 1.0,
        "diet_type": "autotroph",
        "life_form_stage": 1,
        "growth_form": "aquatic",
        "achieved_milestones": ["first_eukaryote"],
        "created_turn": 30,
        "description": (
            "单细胞至丝状的蓝绿藻类，可进行光合作用和固氮。"
            "形成蓝绿色的藻华，覆盖湖泊和池塘表面。"
            "对环境变化适应性强，可在低营养水体中生存。"
            "是淡水生态系统的基础生产者，支撑着整个淡水食物链。"
        ),
        "morphology_stats": {
            "population": 2400000,
            "body_length_cm": 0.001,
            "body_weight_g": 0.0000001,
            "body_surface_area_cm2": 0.000003,
            "lifespan_days": 10,
            "generation_time_days": 2,
            "metabolic_rate": 5.5,
        },
        "abstract_traits": {
            "耐寒性": 4.0,
            "耐热性": 6.0,
            "耐旱性": 2.0,
            "耐盐性": 1.5,
            "光照需求": 5.5,
            "繁殖速度": 8.5,
            "光合效率": 5.5,
            "固碳能力": 5.0,
            "多细胞程度": 1.5,
            "保水能力": 1.0,
            "散布能力": 3.5,
        },
        "organs": {
            "photosynthetic": {
                "type": "蓝藻素体",
                "parameters": {"efficiency": 1.4, "nitrogen_fix": 0.6},
                "acquired_turn": 30,
                "is_active": True
            }
        },
        "capabilities": ["光合作用", "自养", "固氮"],
        "hidden_traits": {
            "gene_diversity": 0.8,
            "environment_sensitivity": 0.3,
            "evolution_potential": 0.7,
            "mutation_rate": 0.55,
            "adaptation_speed": 0.7,
        },
    },
    {
        "lineage_code": "A4",
        "latin_name": "Thermobacter abyssalis",
        "common_name": "深海热泉菌",
        "genus_code": "A",
        "habitat_type": "deep_sea",
        "trophic_level": 1.0,
        "diet_type": "autotroph",
        "life_form_stage": 0,
        "growth_form": "aquatic",
        "achieved_milestones": [],
        "created_turn": 0,
        "description": (
            "极端嗜热的化能自养细菌，生活在深海热液喷口周围。"
            "通过氧化硫化物和氢气获取能量，不依赖阳光。"
            "能在120°C高温和巨大压力下生存，形成厚实的菌席。"
            "是深海生态系统的基础，支撑着独特的深海食物链。"
        ),
        "morphology_stats": {
            "population": 600000,
            "body_length_cm": 0.0003,
            "body_weight_g": 0.0000000003,
            "body_surface_area_cm2": 0.0000005,
            "lifespan_days": 60,
            "generation_time_days": 8,
            "metabolic_rate": 2.0,
        },
        "abstract_traits": {
            "耐寒性": 2.0,
            "耐热性": 9.5,
            "耐旱性": 3.0,
            "耐盐性": 8.0,
            "光照需求": 0.0,
            "繁殖速度": 3.5,
            "光合效率": 0.0,
            "固碳能力": 5.5,
            "多细胞程度": 0.5,
            "保水能力": 3.0,
        },
        "organs": {
            "photosynthetic": {
                "type": "化能合成酶系",
                "parameters": {"efficiency": 0.0, "chemosynthesis": 1.5},
                "acquired_turn": 0,
                "is_active": True
            },
            "protection": {
                "type": "耐压细胞壁",
                "parameters": {"pressure_resist": 0.95, "heat_resist": 0.9},
                "acquired_turn": 0,
                "is_active": True
            }
        },
        "capabilities": ["化能合成", "嗜极生物", "自养", "耐高温", "耐高压"],
        "hidden_traits": {
            "gene_diversity": 0.6,
            "environment_sensitivity": 0.2,
            "evolution_potential": 0.65,
            "mutation_rate": 0.4,
            "adaptation_speed": 0.45,
        },
    },
    
    # ============ 初级消费者层 (T2.0-2.5) ============
    {
        "lineage_code": "B1",
        "latin_name": "Ciliophora pelagica",
        "common_name": "海洋纤毛虫",
        "genus_code": "B",
        "habitat_type": "marine",
        "trophic_level": 2.0,
        "diet_type": "herbivore",
        "prey_species": ["A1"],
        "prey_preferences": {"A1": 1.0},
        "created_turn": 20,
        "description": (
            "单细胞纤毛原生动物，卵形，体长约100微米。"
            "全身覆盖纤毛用于游动和捕食，具有发达的口沟。"
            "以浮游藻类为食，通过纤毛将食物颗粒送入细胞内消化。"
            "繁殖迅速，是海洋食物链中重要的次级生产者。"
        ),
        "morphology_stats": {
            "population": 800000,
            "body_length_cm": 0.01,
            "body_weight_g": 0.00000005,
            "body_surface_area_cm2": 0.0003,
            "lifespan_days": 20,
            "generation_time_days": 3,
            "metabolic_rate": 4.5,
        },
        "abstract_traits": {
            "耐寒性": 3.0,
            "耐热性": 5.0,
            "耐旱性": 1.0,
            "耐盐性": 5.5,
            "光照需求": 2.0,
            "繁殖速度": 7.0,
            "运动能力": 5.0,
            "攻击性": 2.0,
        },
        "organs": {
            "locomotion": {
                "type": "纤毛",
                "parameters": {"count": 500, "efficiency": 1.3},
                "acquired_turn": 20,
                "is_active": True
            },
            "feeding": {
                "type": "口沟",
                "parameters": {"filter_rate": 1.2},
                "acquired_turn": 40,
                "is_active": True
            },
            "sensory": {
                "type": "化学感受器",
                "parameters": {"sensitivity": 0.6, "range_cm": 5},
                "acquired_turn": 60,
                "is_active": True
            }
        },
        "capabilities": ["纤毛运动", "滤食", "化学感知", "异养"],
        "hidden_traits": {
            "gene_diversity": 0.7,
            "environment_sensitivity": 0.5,
            "evolution_potential": 0.75,
            "mutation_rate": 0.5,
            "adaptation_speed": 0.6,
        },
    },
    {
        "lineage_code": "B2",
        "latin_name": "Gastropoda primitiva",
        "common_name": "原始腹足类",
        "genus_code": "B",
        "habitat_type": "coastal",
        "trophic_level": 2.0,
        "diet_type": "herbivore",
        "prey_species": ["A1", "A2"],
        "prey_preferences": {"A1": 0.6, "A2": 0.4},
        "created_turn": 80,
        "description": (
            "早期软体动物，具有螺旋形外壳和肌肉足，体长约8毫米。"
            "用齿舌刮食岩石表面的藻类和苔藓。"
            "主要活动于潮间带，能短暂耐受退潮时的干燥环境。"
            "移动缓慢但稳定，壳体提供了良好的保护。"
        ),
        "morphology_stats": {
            "population": 300000,
            "body_length_cm": 0.8,
            "body_weight_g": 0.3,
            "body_surface_area_cm2": 1.5,
            "lifespan_days": 365,
            "generation_time_days": 60,
            "metabolic_rate": 2.0,
        },
        "abstract_traits": {
            "耐寒性": 4.0,
            "耐热性": 4.5,
            "耐旱性": 4.0,
            "耐盐性": 6.0,
            "光照需求": 1.5,
            "繁殖速度": 3.5,
            "运动能力": 2.0,
            "防御能力": 5.5,
        },
        "organs": {
            "locomotion": {
                "type": "肌肉足",
                "parameters": {"speed": 0.3, "adhesion": 0.9},
                "acquired_turn": 80,
                "is_active": True
            },
            "feeding": {
                "type": "齿舌",
                "parameters": {"scrape_rate": 1.0, "teeth_rows": 20},
                "acquired_turn": 90,
                "is_active": True
            },
            "protection": {
                "type": "螺旋壳",
                "parameters": {"hardness": 0.7, "coverage": 0.8},
                "acquired_turn": 85,
                "is_active": True
            }
        },
        "capabilities": ["刮食", "壳体保护", "潮间带适应"],
        "hidden_traits": {
            "gene_diversity": 0.65,
            "environment_sensitivity": 0.45,
            "evolution_potential": 0.8,
            "mutation_rate": 0.35,
            "adaptation_speed": 0.5,
        },
    },
    {
        "lineage_code": "B3",
        "latin_name": "Daphnia antiqua",
        "common_name": "原始水蚤",
        "genus_code": "B",
        "habitat_type": "freshwater",
        "trophic_level": 2.0,
        "diet_type": "herbivore",
        "prey_species": ["A3"],
        "prey_preferences": {"A3": 1.0},
        "created_turn": 50,
        "description": (
            "小型甲壳类浮游动物，透明的卵形身体，体长约2毫米。"
            "具有分叉的触角用于游动，体侧有透明的甲壳。"
            "以滤食蓝藻和有机碎屑为生，是淡水食物链的关键环节。"
            "对水质敏感，常被用作环境指示生物。"
        ),
        "morphology_stats": {
            "population": 1200000,
            "body_length_cm": 0.2,
            "body_weight_g": 0.0001,
            "body_surface_area_cm2": 0.1,
            "lifespan_days": 40,
            "generation_time_days": 7,
            "metabolic_rate": 4.0,
        },
        "abstract_traits": {
            "耐寒性": 4.5,
            "耐热性": 4.0,
            "耐旱性": 1.0,
            "耐盐性": 1.5,
            "光照需求": 2.5,
            "繁殖速度": 7.5,
            "运动能力": 4.0,
            "防御能力": 2.0,
        },
        "organs": {
            "locomotion": {
                "type": "触角",
                "parameters": {"thrust": 0.8, "maneuver": 0.7},
                "acquired_turn": 50,
                "is_active": True
            },
            "feeding": {
                "type": "滤食附肢",
                "parameters": {"filter_rate": 1.5, "mesh_size": 0.01},
                "acquired_turn": 60,
                "is_active": True
            },
            "sensory": {
                "type": "复眼",
                "parameters": {"resolution": 0.3, "light_sense": 0.8},
                "acquired_turn": 70,
                "is_active": True
            }
        },
        "capabilities": ["滤食", "垂直迁移", "孤雌生殖"],
        "hidden_traits": {
            "gene_diversity": 0.75,
            "environment_sensitivity": 0.6,
            "evolution_potential": 0.7,
            "mutation_rate": 0.55,
            "adaptation_speed": 0.65,
        },
    },
    {
        "lineage_code": "B4",
        "latin_name": "Arthropoda terrestris",
        "common_name": "陆地节肢动物",
        "genus_code": "B",
        "habitat_type": "terrestrial",
        "trophic_level": 2.2,
        "diet_type": "herbivore",
        "prey_species": ["A2"],
        "prey_preferences": {"A2": 1.0},
        "created_turn": 100,
        "description": (
            "早期陆生节肢动物，类似马陆，体长约15毫米。"
            "身体由多节组成，每节有两对腿，外骨骼坚硬。"
            "以腐烂的植物材料和苔藓为食，在落叶层中活动。"
            "夜间活动，白天躲避在石头或树皮下避免干燥。"
        ),
        "morphology_stats": {
            "population": 400000,
            "body_length_cm": 1.5,
            "body_weight_g": 0.5,
            "body_surface_area_cm2": 2.0,
            "lifespan_days": 730,
            "generation_time_days": 120,
            "metabolic_rate": 1.8,
        },
        "abstract_traits": {
            "耐寒性": 4.0,
            "耐热性": 3.5,
            "耐旱性": 3.0,
            "耐盐性": 2.0,
            "光照需求": 1.0,
            "繁殖速度": 3.0,
            "运动能力": 3.5,
            "防御能力": 4.5,
        },
        "organs": {
            "locomotion": {
                "type": "多节足",
                "parameters": {"legs": 30, "speed": 0.5},
                "acquired_turn": 100,
                "is_active": True
            },
            "protection": {
                "type": "几丁质外骨骼",
                "parameters": {"hardness": 0.6, "flexibility": 0.7},
                "acquired_turn": 110,
                "is_active": True
            },
            "respiratory": {
                "type": "气管系统",
                "parameters": {"efficiency": 0.7},
                "acquired_turn": 105,
                "is_active": True
            }
        },
        "capabilities": ["陆地呼吸", "蜕皮", "化学防御"],
        "hidden_traits": {
            "gene_diversity": 0.65,
            "environment_sensitivity": 0.5,
            "evolution_potential": 0.75,
            "mutation_rate": 0.4,
            "adaptation_speed": 0.5,
        },
    },
    
    # ============ 次级消费者层 (T2.5-3.2) ============
    {
        "lineage_code": "C1",
        "latin_name": "Medusozoa primitiva",
        "common_name": "原始水母",
        "genus_code": "C",
        "habitat_type": "marine",
        "trophic_level": 2.8,
        "diet_type": "carnivore",
        "prey_species": ["B1"],
        "prey_preferences": {"B1": 1.0},
        "created_turn": 70,
        "description": (
            "伞形浮游刺胞动物，伞径约3厘米，透明带淡粉色。"
            "边缘有触手，上有刺细胞用于捕捉猎物。"
            "随洋流漂浮，捕食纤毛虫等浮游动物。"
            "生活史包含水螅体和水母体两种形态的世代交替。"
        ),
        "morphology_stats": {
            "population": 200000,
            "body_length_cm": 3.0,
            "body_weight_g": 5.0,
            "body_surface_area_cm2": 30.0,
            "lifespan_days": 180,
            "generation_time_days": 45,
            "metabolic_rate": 1.5,
        },
        "abstract_traits": {
            "耐寒性": 3.5,
            "耐热性": 4.5,
            "耐旱性": 0.5,
            "耐盐性": 6.5,
            "光照需求": 1.0,
            "繁殖速度": 4.0,
            "运动能力": 2.5,
            "攻击性": 5.0,
        },
        "organs": {
            "locomotion": {
                "type": "伞缘肌",
                "parameters": {"pulse_rate": 0.5, "efficiency": 0.6},
                "acquired_turn": 70,
                "is_active": True
            },
            "attack": {
                "type": "刺细胞",
                "parameters": {"toxicity": 0.4, "reload_time": 2},
                "acquired_turn": 80,
                "is_active": True
            },
            "sensory": {
                "type": "平衡囊",
                "parameters": {"gravity_sense": 0.8},
                "acquired_turn": 75,
                "is_active": True
            }
        },
        "capabilities": ["刺细胞捕食", "世代交替", "浮游"],
        "hidden_traits": {
            "gene_diversity": 0.6,
            "environment_sensitivity": 0.55,
            "evolution_potential": 0.7,
            "mutation_rate": 0.45,
            "adaptation_speed": 0.5,
        },
    },
    {
        "lineage_code": "C2",
        "latin_name": "Nautiloidea minor",
        "common_name": "小型鹦鹉螺",
        "genus_code": "C",
        "habitat_type": "marine",
        "trophic_level": 3.0,
        "diet_type": "carnivore",
        "prey_species": ["B1", "B2"],
        "prey_preferences": {"B1": 0.6, "B2": 0.4},
        "created_turn": 110,
        "description": (
            "早期头足类软体动物，具有螺旋状外壳，壳径约4厘米。"
            "有多条触手用于捕捉猎物，具有发达的眼睛。"
            "通过气室调节浮力，在浅海中层活动。"
            "夜间上升到浅层捕食，白天下沉到深处休息。"
        ),
        "morphology_stats": {
            "population": 100000,
            "body_length_cm": 5.0,
            "body_weight_g": 30.0,
            "body_surface_area_cm2": 50.0,
            "lifespan_days": 1825,  # 约5年
            "generation_time_days": 365,
            "metabolic_rate": 2.5,
        },
        "abstract_traits": {
            "耐寒性": 4.0,
            "耐热性": 4.0,
            "耐旱性": 0.5,
            "耐盐性": 7.0,
            "光照需求": 1.5,
            "繁殖速度": 2.0,
            "运动能力": 4.5,
            "攻击性": 5.5,
            "智力": 4.0,
        },
        "organs": {
            "locomotion": {
                "type": "喷射推进",
                "parameters": {"thrust": 1.2, "maneuver": 0.8},
                "acquired_turn": 110,
                "is_active": True
            },
            "attack": {
                "type": "触手",
                "parameters": {"count": 20, "grip_strength": 0.7},
                "acquired_turn": 115,
                "is_active": True
            },
            "sensory": {
                "type": "针孔眼",
                "parameters": {"resolution": 0.5, "range_m": 10},
                "acquired_turn": 120,
                "is_active": True
            },
            "buoyancy": {
                "type": "气室",
                "parameters": {"chambers": 8, "control": 0.85},
                "acquired_turn": 115,
                "is_active": True
            }
        },
        "capabilities": ["喷射游泳", "浮力调节", "垂直迁移", "触手捕食"],
        "hidden_traits": {
            "gene_diversity": 0.6,
            "environment_sensitivity": 0.4,
            "evolution_potential": 0.85,
            "mutation_rate": 0.35,
            "adaptation_speed": 0.45,
        },
    },
    {
        "lineage_code": "C3",
        "latin_name": "Amphibiodrilus transitans",
        "common_name": "两栖蠕虫",
        "genus_code": "C",
        "habitat_type": "amphibious",
        "trophic_level": 2.8,
        "diet_type": "omnivore",
        "prey_species": ["B3", "A3"],
        "prey_preferences": {"B3": 0.7, "A3": 0.3},
        "created_turn": 90,
        "description": (
            "原始的两栖类环节动物，体长约5厘米，身体分节。"
            "具有原始的肺囊，可在水陆两栖生活。"
            "在潮湿的岸边活动，捕食小型水生动物和藻类。"
            "皮肤需保持湿润，不能远离水源。"
        ),
        "morphology_stats": {
            "population": 160000,
            "body_length_cm": 5.0,
            "body_weight_g": 2.0,
            "body_surface_area_cm2": 8.0,
            "lifespan_days": 365,
            "generation_time_days": 60,
            "metabolic_rate": 2.8,
        },
        "abstract_traits": {
            "耐寒性": 3.5,
            "耐热性": 4.0,
            "耐旱性": 2.5,
            "耐盐性": 3.0,
            "光照需求": 1.5,
            "繁殖速度": 4.5,
            "运动能力": 4.0,
            "攻击性": 3.5,
        },
        "organs": {
            "locomotion": {
                "type": "环节蠕动",
                "parameters": {"speed": 0.6, "terrain": ["水下", "泥地"]},
                "acquired_turn": 90,
                "is_active": True
            },
            "respiratory": {
                "type": "原始肺囊",
                "parameters": {"air_efficiency": 0.5, "water_efficiency": 0.7},
                "acquired_turn": 95,
                "is_active": True
            },
            "sensory": {
                "type": "化学感受器",
                "parameters": {"sensitivity": 0.7},
                "acquired_turn": 92,
                "is_active": True
            }
        },
        "capabilities": ["水陆两栖", "皮肤呼吸", "蠕动运动"],
        "hidden_traits": {
            "gene_diversity": 0.7,
            "environment_sensitivity": 0.55,
            "evolution_potential": 0.9,
            "mutation_rate": 0.5,
            "adaptation_speed": 0.6,
        },
    },
    
    # ============ 顶级消费者层 (T3.5+) ============
    {
        "lineage_code": "D1",
        "latin_name": "Anomalocaris primigenius",
        "common_name": "原始奇虾",
        "genus_code": "D",
        "habitat_type": "marine",
        "trophic_level": 3.8,
        "diet_type": "carnivore",
        "prey_species": ["C1", "C2", "B1", "B2"],
        "prey_preferences": {"C1": 0.3, "C2": 0.3, "B1": 0.2, "B2": 0.2},
        "created_turn": 130,
        "description": (
            "海洋顶级掠食者，体长可达30厘米，流线型身体。"
            "头部有一对大型复眼和两条带刺的捕食附肢。"
            "口器呈圆盘状，边缘有齿，可以咬碎猎物的外壳。"
            "游泳能力出色，是当时海洋中最危险的掠食者。"
        ),
        "morphology_stats": {
            "population": 30000,
            "body_length_cm": 30.0,
            "body_weight_g": 500.0,
            "body_surface_area_cm2": 400.0,
            "lifespan_days": 1095,  # 约3年
            "generation_time_days": 180,
            "metabolic_rate": 3.5,
        },
        "abstract_traits": {
            "耐寒性": 4.0,
            "耐热性": 5.0,
            "耐旱性": 0.5,
            "耐盐性": 7.0,
            "光照需求": 2.0,
            "繁殖速度": 2.0,
            "运动能力": 7.0,
            "攻击性": 8.0,
            "智力": 3.5,
        },
        "organs": {
            "locomotion": {
                "type": "侧叶",
                "parameters": {"pairs": 11, "thrust": 2.0, "maneuver": 1.5},
                "acquired_turn": 130,
                "is_active": True
            },
            "attack": {
                "type": "捕食附肢",
                "parameters": {"reach_cm": 8, "grip_force": 2.5, "spines": 14},
                "acquired_turn": 135,
                "is_active": True
            },
            "feeding": {
                "type": "圆盘口器",
                "parameters": {"diameter_cm": 3, "teeth": 32, "bite_force": 2.0},
                "acquired_turn": 140,
                "is_active": True
            },
            "sensory": {
                "type": "复眼",
                "parameters": {"ommatidia": 16000, "resolution": 0.9, "range_m": 30},
                "acquired_turn": 132,
                "is_active": True
            }
        },
        "capabilities": ["高速游泳", "精准捕食", "咬碎外壳", "复眼视觉"],
        "hidden_traits": {
            "gene_diversity": 0.55,
            "environment_sensitivity": 0.35,
            "evolution_potential": 0.7,
            "mutation_rate": 0.3,
            "adaptation_speed": 0.4,
        },
    },
    {
        "lineage_code": "D2",
        "latin_name": "Chilopoda gigantea",
        "common_name": "巨型蜈蚣",
        "genus_code": "D",
        "habitat_type": "terrestrial",
        "trophic_level": 3.5,
        "diet_type": "carnivore",
        "prey_species": ["B4", "C3"],
        "prey_preferences": {"B4": 0.6, "C3": 0.4},
        "created_turn": 140,
        "parent_code": "B4",  # 从陆地节肢动物演化而来
        "description": (
            "陆地顶级节肢掠食者，体长可达20厘米。"
            "身体扁平，多节，每节一对腿，第一对腿特化为毒爪。"
            "主要在夜间活动，捕食其他节肢动物和两栖动物。"
            "具有毒腺，毒液可麻痹猎物。敏捷的捕食者。"
        ),
        "morphology_stats": {
            "population": 50000,
            "body_length_cm": 20.0,
            "body_weight_g": 15.0,
            "body_surface_area_cm2": 80.0,
            "lifespan_days": 1460,  # 约4年
            "generation_time_days": 200,
            "metabolic_rate": 2.8,
        },
        "abstract_traits": {
            "耐寒性": 3.5,
            "耐热性": 4.5,
            "耐旱性": 4.0,
            "耐盐性": 2.0,
            "光照需求": 0.5,
            "繁殖速度": 2.5,
            "运动能力": 6.5,
            "攻击性": 7.5,
        },
        "organs": {
            "locomotion": {
                "type": "步行足",
                "parameters": {"pairs": 21, "speed": 1.5},
                "acquired_turn": 140,
                "is_active": True
            },
            "attack": {
                "type": "毒爪",
                "parameters": {"toxicity": 0.7, "inject_speed": 0.9},
                "acquired_turn": 145,
                "is_active": True
            },
            "sensory": {
                "type": "触角",
                "parameters": {"length_cm": 3, "sensitivity": 0.85},
                "acquired_turn": 142,
                "is_active": True
            },
            "protection": {
                "type": "强化外骨骼",
                "parameters": {"hardness": 0.75, "flexibility": 0.8},
                "acquired_turn": 143,
                "is_active": True
            }
        },
        "capabilities": ["毒液注射", "快速奔跑", "夜视", "触角感知"],
        "hidden_traits": {
            "gene_diversity": 0.6,
            "environment_sensitivity": 0.4,
            "evolution_potential": 0.75,
            "mutation_rate": 0.35,
            "adaptation_speed": 0.45,
        },
    },
    
    # ============ 特殊生态位 ============
    {
        "lineage_code": "E1",
        "latin_name": "Decomposia universalis",
        "common_name": "分解细菌群",
        "genus_code": "E",
        "habitat_type": "terrestrial",
        "trophic_level": 1.5,
        "diet_type": "detritivore",
        "created_turn": 40,
        "description": (
            "多种腐生细菌的共生群落，分解有机物质。"
            "存在于土壤、落叶层和动物尸体中。"
            "将复杂有机物分解为简单的无机物，供植物重新利用。"
            "是生态系统物质循环的关键环节，默默维持着生态平衡。"
        ),
        "morphology_stats": {
            "population": 10000000,  # 以群落计
            "body_length_cm": 0.0002,
            "body_weight_g": 0.0000000001,
            "body_surface_area_cm2": 0.0000001,
            "lifespan_days": 2,
            "generation_time_days": 0.5,
            "metabolic_rate": 8.0,
        },
        "abstract_traits": {
            "耐寒性": 5.0,
            "耐热性": 5.0,
            "耐旱性": 4.0,
            "耐盐性": 3.0,
            "光照需求": 0.0,
            "繁殖速度": 9.5,
        },
        "organs": {
            "digestion": {
                "type": "胞外酶系统",
                "parameters": {"enzyme_types": 50, "efficiency": 1.5},
                "acquired_turn": 40,
                "is_active": True
            }
        },
        "capabilities": ["分解有机物", "矿化", "固氮", "群落协作"],
        "hidden_traits": {
            "gene_diversity": 0.9,
            "environment_sensitivity": 0.25,
            "evolution_potential": 0.6,
            "mutation_rate": 0.7,
            "adaptation_speed": 0.8,
        },
    },
    {
        "lineage_code": "F1",
        "latin_name": "Riftia symbiotica",
        "common_name": "深海管虫",
        "genus_code": "F",
        "habitat_type": "deep_sea",
        "trophic_level": 2.0,
        "diet_type": "herbivore",  # 通过共生细菌获取营养
        "prey_species": ["A4"],
        "prey_preferences": {"A4": 1.0},
        "symbiotic_dependencies": ["A4"],
        "dependency_strength": 0.9,
        "symbiosis_type": "mutualism",
        "created_turn": 120,
        "description": (
            "生活在深海热泉口的管状蠕虫，体长可达40厘米。"
            "没有消化系统，完全依赖体内共生的化能细菌获取营养。"
            "红色的羽状鳃用于交换气体和吸收化学物质。"
            "与化能细菌形成紧密的互利共生关系。"
        ),
        "morphology_stats": {
            "population": 60000,
            "body_length_cm": 40.0,
            "body_weight_g": 80.0,
            "body_surface_area_cm2": 200.0,
            "lifespan_days": 7300,  # 约20年
            "generation_time_days": 730,
            "metabolic_rate": 1.0,
        },
        "abstract_traits": {
            "耐寒性": 2.0,
            "耐热性": 8.0,
            "耐旱性": 0.5,
            "耐盐性": 8.5,
            "光照需求": 0.0,
            "繁殖速度": 1.5,
            "运动能力": 0.5,
        },
        "organs": {
            "respiratory": {
                "type": "羽状鳃",
                "parameters": {"surface_area": 50, "chemical_uptake": 1.5},
                "acquired_turn": 120,
                "is_active": True
            },
            "symbiotic": {
                "type": "营养体",
                "parameters": {"bacteria_density": 3000000000, "efficiency": 0.95},
                "acquired_turn": 125,
                "is_active": True
            },
            "protection": {
                "type": "几丁质管",
                "parameters": {"hardness": 0.8, "heat_resist": 0.9},
                "acquired_turn": 122,
                "is_active": True
            }
        },
        "capabilities": ["化能共生", "深海适应", "固着生活"],
        "hidden_traits": {
            "gene_diversity": 0.5,
            "environment_sensitivity": 0.3,
            "evolution_potential": 0.6,
            "mutation_rate": 0.25,
            "adaptation_speed": 0.35,
        },
    },
]


def _generate_initial_dormant_genes(species: Species) -> None:
    """为物种生成初始休眠基因 v3.0（快速进化版本）
    
    根据物种的生态特性（栖息地、食性、营养级）生成符合其特质的休眠基因。
    
    【v3.0 快速进化增强】
    - 显隐性遗传：每个基因有显隐性类型
    - 有害突变：25%概率生成有害基因（提供自然选择原料）
    - 细化压力类型：使用新的压力-基因映射系统
    - 器官发育阶段：器官初始为未发育状态
    - 更多基因：大幅提升各类基因生成概率
    """
    # 导入新的基因常量
    from ..services.species.gene_constants import (
        PRESSURE_GENE_MAPPING,
        DominanceType,
        MutationEffect,
        HARMFUL_MUTATIONS,
        roll_dominance,
        roll_mutation_effect,
    )
    
    if species.dormant_genes is None:
        species.dormant_genes = {"traits": {}, "organs": {}}
    
    species.dormant_genes.setdefault("traits", {})
    species.dormant_genes.setdefault("organs", {})
    
    # 使用物种信息作为种子确保可重复性
    seed = abs(hash(f"{species.lineage_code}-dormant-v2")) % 1_000_000_007
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
    is_microbe = trophic <= 1.5  # 微生物（可进行HGT）
    
    # ========== 压力类型映射（使用新系统） ==========
    pressure_mapping = {
        "耐寒性": ["cold", "temperature_fluctuation"],
        "耐热性": ["heat", "temperature_fluctuation"],
        "耐旱性": ["drought"],
        "耐盐性": ["salinity"],
        "免疫力": ["disease", "parasitism"],
        "运动能力": ["predation", "hunting"],
        "繁殖速度": ["starvation", "competition"],
        "社会性": ["competition"],
        "光合效率": ["light_limitation"],
        "固碳能力": ["light_limitation", "nutrient_poor"],
        "攻击性": ["hunting", "competition"],
        "防御能力": ["predation"],
        "代谢效率": ["starvation"],
    }
    
    # ========== 1. 基于现有特质生成强化版休眠基因（85%概率）==========
    for trait_name, trait_value in (species.abstract_traits or {}).items():
        # 85% 概率为每个特质生成一个增强版休眠基因
        if rng.random() < 0.85:
            enhanced_name = f"强化{trait_name}" if not trait_name.startswith("强化") else trait_name
            if enhanced_name not in species.dormant_genes["traits"]:
                pressure_types = pressure_mapping.get(trait_name, ["competition", "starvation"])
                dominance = roll_dominance("trait")
                
                species.dormant_genes["traits"][enhanced_name] = {
                    "potential_value": min(15.0, float(trait_value) * 1.35),  # 提升潜力值
                    "activation_threshold": 0.18,  # 降低激活门槛
                    "pressure_types": pressure_types,
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": "initial",
                    "dominance": dominance.value,
                    "mutation_effect": MutationEffect.BENEFICIAL.value,
                }
    
    # ========== 2. 根据生态位生成特化休眠特质 ==========
    ecological_traits = []
    
    if is_producer:
        # 生产者特化特质（使用新压力类型）
        ecological_traits.extend([
            ("光合效率提升", ["light_limitation"], 6.0),
            ("固碳强化", ["nutrient_poor", "competition"], 5.5),
            ("营养吸收", ["nutrient_poor"], 5.0),
        ])
    
    if is_consumer:
        # 消费者特化特质
        ecological_traits.extend([
            ("消化效率", ["starvation", "competition"], 5.5),
            ("感知敏锐", ["predation", "hunting"], 5.0),
        ])
    
    if is_predator:
        # 捕食者特化特质
        ecological_traits.extend([
            ("捕猎本能", ["hunting"], 6.0),
            ("追踪能力", ["hunting", "competition"], 5.5),
        ])
    
    if is_aquatic:
        # 水生特化特质
        ecological_traits.extend([
            ("流线型优化", ["predation"], 5.0),
            ("渗透调节", ["salinity"], 5.5),
        ])
    
    if is_terrestrial:
        # 陆生特化特质
        ecological_traits.extend([
            ("保水强化", ["drought"], 6.0),
            ("陆地适应", ["drought", "abrasion"], 5.5),
        ])
    
    if is_deep_sea:
        # 深海特化特质
        ecological_traits.extend([
            ("耐压强化", ["pressure_deep"], 7.0),
            ("化能利用", ["oxygen_low"], 6.0),
        ])
    
    if is_amphibious:
        # 两栖特化特质
        ecological_traits.extend([
            ("双栖适应", ["drought", "flooding"], 6.0),
            ("皮肤呼吸", ["oxygen_low"], 5.5),
        ])
    
    # 添加通用适应性特质
    ecological_traits.extend([
        ("环境适应性", ["competition", "temperature_fluctuation"], rng.uniform(4.5, 6.5)),
        ("恢复力", ["disease", "abrasion"], rng.uniform(4.0, 6.0)),
    ])
    
    for trait_name, pressure_types, base_value in ecological_traits:
        if trait_name not in (species.abstract_traits or {}) and trait_name not in species.dormant_genes["traits"]:
            if rng.random() < 0.75:  # 75% 概率生成生态位特化基因
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
        harmful_mutations = [m for m in HARMFUL_MUTATIONS 
                           if m["effect"] in (MutationEffect.MILDLY_HARMFUL, MutationEffect.HARMFUL)]
        if harmful_mutations:
            harmful = rng.choice(harmful_mutations)
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
                    "dominance": DominanceType.RECESSIVE.value,  # 有害突变通常是隐性
                    "mutation_effect": harmful["effect"].value if hasattr(harmful["effect"], 'value') else harmful["effect"],
                    "description": harmful.get("description", ""),
                }
                logger.debug(f"[Seed] {species.lineage_code} 生成有害突变: {harm_name}")
    
    # ========== 3. 根据生态位生成符合物种特性的休眠器官 ==========
    potential_organs = []
    
    # --- 生产者器官（概率提升）---
    if is_producer:
        potential_organs.extend([
            {"name": "增强叶绿体", "category": "photosynthetic", "type": "enhanced_chloroplast", 
             "parameters": {"efficiency": 1.5}, "pressure_types": ["light", "resource"], "prob": 0.75},
            {"name": "光合色素", "category": "photosynthetic", "type": "pigment", 
             "parameters": {"spectrum_range": 0.8}, "pressure_types": ["light", "competition"], "prob": 0.60},
            {"name": "UV防护层", "category": "protection", "type": "uv_shield", 
             "parameters": {"uv_resist": 0.7}, "pressure_types": ["radiation", "damage"], "prob": 0.55},
            {"name": "储能细胞", "category": "storage", "type": "energy_storage", 
             "parameters": {"capacity": 0.6}, "pressure_types": ["resource", "stress"], "prob": 0.50},
        ])
    
    # --- 消费者感知器官（概率提升）---
    if is_consumer:
        if not is_deep_sea:  # 深海物种不需要感光器官
            potential_organs.append(
                {"name": "原始眼点", "category": "sensory", "type": "eyespot", 
                 "parameters": {"sensitivity": 0.5}, "pressure_types": ["predation", "hunting"], "prob": 0.65}
            )
        potential_organs.extend([
            {"name": "化学感受器", "category": "sensory", "type": "chemoreceptor", 
             "parameters": {"range": 0.4}, "pressure_types": ["predation", "foraging"], "prob": 0.70},
            {"name": "触觉感受器", "category": "sensory", "type": "mechanoreceptor", 
             "parameters": {"sensitivity": 0.5}, "pressure_types": ["predation", "navigation"], "prob": 0.55},
            {"name": "原始消化腔", "category": "digestive", "type": "primitive_gut", 
             "parameters": {"efficiency": 0.4}, "pressure_types": ["starvation"], "prob": 0.55},
        ])
    
    # --- 捕食者攻击器官（概率提升）---
    if is_predator:
        potential_organs.extend([
            {"name": "捕食附肢", "category": "attack", "type": "grasping_appendage", 
             "parameters": {"grip_strength": 0.6}, "pressure_types": ["predation", "hunting"], "prob": 0.70},
            {"name": "毒腺原基", "category": "attack", "type": "venom_gland", 
             "parameters": {"toxicity": 0.3}, "pressure_types": ["predation", "defense"], "prob": 0.45},
        ])
    
    # --- 水生运动器官（概率提升）---
    if is_aquatic:
        potential_organs.extend([
            {"name": "纤毛", "category": "locomotion", "type": "cilia", 
             "parameters": {"efficiency": 0.5}, "pressure_types": ["predation", "locomotion"], "prob": 0.65},
            {"name": "鞭毛强化", "category": "locomotion", "type": "flagellum", 
             "parameters": {"thrust": 0.6}, "pressure_types": ["predation", "locomotion"], "prob": 0.55},
            {"name": "浮力调节囊", "category": "buoyancy", "type": "swim_bladder", 
             "parameters": {"control": 0.5}, "pressure_types": ["locomotion", "depth"], "prob": 0.50},
            {"name": "侧线原基", "category": "sensory", "type": "lateral_line", 
             "parameters": {"sensitivity": 0.4}, "pressure_types": ["predation", "hunting"], "prob": 0.45},
        ])
    
    # --- 陆生呼吸/运动器官（概率提升）---
    if is_terrestrial:
        potential_organs.extend([
            {"name": "原始气管", "category": "respiratory", "type": "trachea", 
             "parameters": {"efficiency": 0.4}, "pressure_types": ["oxygen", "respiration"], "prob": 0.55},
            {"name": "角质层强化", "category": "protection", "type": "cuticle", 
             "parameters": {"drought_resist": 0.6}, "pressure_types": ["drought", "protection"], "prob": 0.65},
            {"name": "运动肌群", "category": "locomotion", "type": "muscle", 
             "parameters": {"strength": 0.5}, "pressure_types": ["predation", "locomotion"], "prob": 0.55},
        ])
    
    # --- 深海特化器官（概率提升）---
    if is_deep_sea:
        potential_organs.extend([
            {"name": "耐压细胞壁", "category": "protection", "type": "pressure_resistant", 
             "parameters": {"pressure_resist": 0.8}, "pressure_types": ["pressure", "deep_sea"], "prob": 0.75},
            {"name": "化能合成体", "category": "metabolism", "type": "chemosynthesis", 
             "parameters": {"efficiency": 0.6}, "pressure_types": ["resource", "chemosynthesis"], "prob": 0.65},
            {"name": "热感受器", "category": "sensory", "type": "thermoreceptor", 
             "parameters": {"range": 0.5}, "pressure_types": ["temperature", "navigation"], "prob": 0.55},
            {"name": "发光器原基", "category": "bioluminescence", "type": "photophore", 
             "parameters": {"intensity": 0.3}, "pressure_types": ["predation", "hunting"], "prob": 0.40},
        ])
    
    # --- 两栖特化器官（概率提升）---
    if is_amphibious:
        potential_organs.extend([
            {"name": "原始肺囊", "category": "respiratory", "type": "primitive_lung", 
             "parameters": {"air_efficiency": 0.5}, "pressure_types": ["oxygen", "amphibious"], "prob": 0.65},
            {"name": "皮肤腺", "category": "protection", "type": "mucous_gland", 
             "parameters": {"moisture": 0.6}, "pressure_types": ["drought", "amphibious"], "prob": 0.60},
        ])
    
    # --- 通用防御器官 ---
    potential_organs.extend([
        {"name": "防护外壳", "category": "defense", "type": "shell", 
         "parameters": {"hardness": 0.4}, "pressure_types": ["predation", "defense"], "prob": 0.25},
        {"name": "再生组织", "category": "regeneration", "type": "regenerative_tissue", 
         "parameters": {"rate": 0.3}, "pressure_types": ["damage", "stress"], "prob": 0.20},
    ])
    
    # 根据概率生成休眠器官（使用新的发育阶段系统）
    for organ in potential_organs:
        prob = organ.get("prob", 0.30)
        if rng.random() < prob:
            organ_name = organ["name"]
            if organ_name not in species.dormant_genes["organs"]:
                # 检查物种是否已有类似器官
                existing_organs = species.organs or {}
                has_similar = any(
                    organ["type"] in str(existing_organs.get(cat, {}))
                    for cat in existing_organs
                )
                if not has_similar:
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
                        "development_stage": None,  # 未开始发育（渐进发育系统）
                        "stage_start_turn": None,
                    }
    
    # ========== 统计生成结果 ==========
    total_traits = len(species.dormant_genes.get("traits", {}))
    total_organs = len(species.dormant_genes.get("organs", {}))
    harmful_count = sum(1 for t in species.dormant_genes.get("traits", {}).values() 
                       if t.get("mutation_effect") in (MutationEffect.HARMFUL.value, 
                                                       MutationEffect.MILDLY_HARMFUL.value,
                                                       "harmful", "mildly_harmful"))
    total_dormant = total_traits + total_organs
    if total_dormant > 0:
        logger.debug(
            f"[Seed] {species.lineage_code}({species.common_name}) 生成了 "
            f"{total_traits} 个休眠特质 (含 {harmful_count} 个有害), {total_organs} 个休眠器官"
        )


def seed_defaults() -> None:
    """Ensure core starter species exist (原初大陆剧本)."""

    existing = {sp.lineage_code for sp in species_repository.list_species()}
    trophic_calc = TrophicLevelCalculator()
    
    created_species = []
    for payload in A_SCENARIO:
        if payload["lineage_code"] in existing:
            continue
        sp = Species(**payload)
        # 【新增】为物种生成初始休眠基因
        _generate_initial_dormant_genes(sp)
        created_species.append(sp)
    
    for sp in created_species:
        species_repository.upsert(sp)
    
    if created_species:
        all_species = species_repository.list_species()
        for sp in all_species:
            if sp.trophic_level == 0.0 or sp.trophic_level == 1.0:
                calculated_trophic = trophic_calc.calculate_trophic_level(sp, all_species)
                sp.trophic_level = calculated_trophic
                print(f"[Seed] 计算营养级: {sp.common_name} ({sp.lineage_code}) -> {calculated_trophic:.2f}")
                species_repository.upsert(sp)


def seed_thriving_ecosystem() -> None:
    """加载繁荣生态剧本 - 模拟约150回合后的成熟生态系统。
    
    包含15个物种，覆盖：
    - 4种生产者（海洋群体藻、陆地苔藓、淡水蓝藻、深海热泉菌）
    - 4种初级消费者（海洋纤毛虫、原始腹足类、原始水蚤、陆地节肢动物）
    - 3种次级消费者（原始水母、小型鹦鹉螺、两栖蠕虫）
    - 2种顶级消费者（原始奇虾、巨型蜈蚣）
    - 2种特殊生态位（分解细菌、深海管虫）
    """
    existing = {sp.lineage_code for sp in species_repository.list_species()}
    trophic_calc = TrophicLevelCalculator()
    
    created_species = []
    for payload in THRIVING_ECOSYSTEM_SCENARIO:
        if payload["lineage_code"] in existing:
            continue
        sp = Species(**payload)
        # 【新增】为物种生成初始休眠基因
        _generate_initial_dormant_genes(sp)
        created_species.append(sp)
        print(f"[Seed·繁荣生态] 创建物种: {sp.common_name} ({sp.lineage_code}) - T{sp.trophic_level:.1f}")
    
    # 批量保存
    for sp in created_species:
        species_repository.upsert(sp)
    
    # 计算并更新营养级
    if created_species:
        all_species = species_repository.list_species()
        for sp in all_species:
            calculated_trophic = trophic_calc.calculate_trophic_level(sp, all_species)
            if abs(calculated_trophic - sp.trophic_level) > 0.1:
                sp.trophic_level = calculated_trophic
                print(f"[Seed·繁荣生态] 更新营养级: {sp.common_name} ({sp.lineage_code}) -> {calculated_trophic:.2f}")
                species_repository.upsert(sp)
    
    print(f"[Seed·繁荣生态] 剧本加载完成，共 {len(created_species)} 个物种")


def _seed_genera():
    """创建初始属"""
    genera_data = [
        {"code": "A", "name_latin": "Algaprimordia", "name_common": "原藻属"},
        {"code": "B", "name_latin": "Protoflagella", "name_common": "原鞭毛属"},
        {"code": "C", "name_latin": "Thiobacter", "name_common": "硫菌属"},
    ]
    
    for data in genera_data:
        existing = genus_repository.get_by_code(data["code"])
        if not existing:
            genus = Genus(
                code=data["code"],
                name_latin=data["name_latin"],
                name_common=data["name_common"],
                genetic_distances={},
                gene_library={"traits": {}, "organs": {}},
                created_turn=0,
                updated_turn=0
            )
            genus_repository.upsert(genus)
            print(f"[Seed] 创建属: {genus.name_common} ({genus.code})")
