from __future__ import annotations

from datetime import datetime

from ..models.genus import Genus
from ..models.species import Species
from ..repositories.genus_repository import genus_repository
from ..repositories.species_repository import species_repository
from ..services.species.trophic import TrophicLevelCalculator

A_SCENARIO = [
    {
        "lineage_code": "A1",
        "latin_name": "Algaprimordia pelagica",
        "common_name": "海洋微藻",
        "genus_code": "A",
        "habitat_type": "marine",  # 海洋生物
        "trophic_level": 1.0,  # T1: 生产者
        "description": (
            "单细胞光合生物，球形，体长8微米。细胞壁透明，内含叶绿体进行光合作用。"
            "漂浮于浅海上层水域，通过二分裂快速繁殖。自养型，固定二氧化碳生产有机物。"
            "栖息于温带至热带浅海0-50米，需充足光照。作为初级生产者，是浮游动物主要食物来源。"
        ),
        "morphology_stats": {
            # 生物量平衡：微藻作为食物链基础，需要大量生物量支撑上层
            # 鞭毛虫生物量约 3e6 * 3e-9 = 0.009g，按15%生态效率需要 0.06g 微藻
            # 设置 100e6 * 1e-9 = 0.1g，留有余量支持生态系统发展
            "population": 100000000,  # 1亿（生产者应为消费者的10-100倍）
            "body_length_cm": 0.0008,
            "body_weight_g": 0.000000001,  # 1纳克
            "body_surface_area_cm2": 0.000002,
            "lifespan_days": 7,
            "generation_time_days": 1,  # 1天一代，快速繁殖
            "metabolic_rate": 5.0,
        },
        "abstract_traits": {
            "耐寒性": 1.0,
            "耐热性": 6.0,
            "耐旱性": 1.0,
            "耐盐性": 4.0,
            "耐酸碱性": 1.0,
            "光照需求": 5.0,
            "氧气需求": 4.0,
            "繁殖速度": 8.0,  # 提高繁殖速度，支撑食物链
            "运动能力": 1.0,
            "社会性": 1.0,
        },
        "organs": {
            "metabolic": {
                "type": "叶绿体",
                "parameters": {
                    "count": 1,
                    "efficiency": 1.0,
                    "photosynthetic_rate": 1.0
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
        "description": (
            "单细胞异养生物，梨形，体长15微米。前端1-2根鞭毛用于游动和捕食。"
            "主动捕食微藻和有机碎屑，通过鞭毛将食物送入胞口。纵向二分裂繁殖。"
            "栖息浅海至中层水域，垂直迁移觅食。初级消费者，连接生产者和更高营养级。运动灵活，具趋光性和趋化性。"
        ),
        "morphology_stats": {
            # 生物量约为微藻的1/10-1/20（符合生态金字塔）
            "population": 5000000,  # 500万
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
            "耐酸碱性": 3.0,
            "光照需求": 2.0,
            "氧气需求": 4.0,
            "繁殖速度": 5.0,  # 中等繁殖速度
            "运动能力": 4.0,
            "社会性": 1.0,
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
        "habitat_type": "deep_sea",  # 深海生物
        "trophic_level": 1.0,  # T1: 生产者（化能自养，深海食物链基础）
        "description": (
            "单细胞化能合成细菌，杆状或球状，体长5微米。细胞壁坚固，抵抗极端环境。"
            "氧化硫化氢获取能量，合成有机物。二分裂繁殖，生长慢但生命力强。"
            "栖息深海热液喷口、火山口等极端环境。耐高温高压低氧。极端生态系统的初级生产者，支撑化能合成食物链。"
        ),
        "morphology_stats": {
            # 深海生态系统的基础生产者
            "population": 50000000,  # 5000万（深海环境相对有限）
            "body_length_cm": 0.0005,
            "body_weight_g": 0.0000000005,  # 0.5纳克
            "body_surface_area_cm2": 0.000001,
            "lifespan_days": 30,
            "generation_time_days": 5,  # 5天一代
            "metabolic_rate": 1.5,
        },
        "abstract_traits": {
            "耐寒性": 5.0,
            "耐热性": 5.0,
            "耐旱性": 4.0,
            "耐盐性": 4.0,
            "耐酸碱性": 5.0,
            "光照需求": 0.0,  # 不需要光照
            "氧气需求": 1.0,
            "繁殖速度": 4.0,  # 提高繁殖速度
            "运动能力": 1.0,
            "社会性": 1.0
        },
        "organs": {
            "metabolic": {
                "type": "化能合成系统",
                "parameters": {
                    "efficiency": 1.0,
                    "substrate": "H2S",
                    "energy_yield": 0.8
                },
                "acquired_turn": 0,
                "is_active": True
            }
        },
        "capabilities": ["化能合成", "嗜极生物"],
        "hidden_traits": {
            "gene_diversity": 0.65,
            "environment_sensitivity": 0.3,
            "evolution_potential": 0.7,
            "mutation_rate": 0.4,
            "adaptation_speed": 0.5,
        },
    },
]


def seed_defaults() -> None:
    """Ensure core starter species exist."""

    existing = {sp.lineage_code for sp in species_repository.list_species()}
    trophic_calc = TrophicLevelCalculator()
    
    created_species = []
    for payload in A_SCENARIO:
        if payload["lineage_code"] in existing:
            continue
        sp = Species(**payload)
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
