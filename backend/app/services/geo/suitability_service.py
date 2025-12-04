"""混合 Embedding 宜居度服务

结合语义向量和特征向量计算物种-地块宜居度。

架构:
1. 语义相似度 (50%): 使用在线 Embedding API 获取语义理解
2. 特征相似度 (50%): 使用 12 维数值向量计算精确匹配

优化:
- 矩阵计算: 一次性计算 N物种 × M地块
- 缓存机制: 向量缓存 + 矩阵缓存
- 增量更新: 只重算变化的部分
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ...core.config import get_settings
from ...core.config_service import ConfigService

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import MapTile
    from ..system.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_SETTINGS = get_settings()
_TILE_CACHE_DIR = Path(_SETTINGS.cache_dir) / "embeddings"
_SUITABILITY_CONFIG_SERVICE: ConfigService | None = None


def _get_config_service() -> ConfigService:
    global _SUITABILITY_CONFIG_SERVICE
    if _SUITABILITY_CONFIG_SERVICE is None:
        _SUITABILITY_CONFIG_SERVICE = ConfigService(_SETTINGS)
    return _SUITABILITY_CONFIG_SERVICE


# ============ 12 维特征空间定义 ============

DIMENSION_NAMES = [
    "thermal",      # 热量偏好
    "moisture",     # 水分偏好
    "altitude",     # 海拔偏好
    "salinity",     # 盐度偏好
    "resources",    # 资源需求
    "aquatic",      # 水域性
    "depth",        # 深度偏好
    "light",        # 光照需求
    "volcanic",     # 地热偏好
    "stability",    # 稳定性偏好
    "vegetation",   # 植被偏好
    "river",        # 河流偏好
]

# 各维度权重 (总和 = 1.0)
DIMENSION_WEIGHTS = np.array([
    0.10,   # thermal - 温度重要
    0.08,   # moisture - 湿度中等
    0.08,   # altitude - 海拔中等
    0.10,   # salinity - 盐度重要(区分淡水/海水)
    0.08,   # resources - 资源中等
    0.22,   # aquatic - 水域性最重要！(水生上岸必死)
    0.08,   # depth - 深度中等
    0.06,   # light - 光照次要
    0.04,   # volcanic - 地热次要
    0.04,   # stability - 稳定性次要
    0.06,   # vegetation - 植被次要
    0.06,   # river - 河流次要
])

# 语义 vs 特征的权重
SEMANTIC_WEIGHT = 0.4
FEATURE_WEIGHT = 0.6


@dataclass
class SuitabilityResult:
    """宜居度计算结果"""
    total: float
    semantic_score: float
    feature_score: float
    feature_breakdown: dict[str, float] = field(default_factory=dict)
    species_text: str = ""
    tile_text: str = ""


class SuitabilityService:
    """混合 Embedding 宜居度服务
    
    结合语义向量(在线API)和特征向量(12D)计算宜居度。
    """
    
    def __init__(
        self, 
        embedding_service: "EmbeddingService | None" = None,
        use_semantic: bool = True,
        semantic_weight: float = SEMANTIC_WEIGHT,
        feature_weight: float = FEATURE_WEIGHT,
        semantic_hotspot_only: bool = False,
        semantic_hotspot_limit: int = 512,
        tile_cache_path: Path | None = None,
    ):
        self.embeddings = embedding_service
        self.use_semantic = use_semantic and embedding_service is not None
        self.semantic_weight = semantic_weight
        self.feature_weight = feature_weight
        self.semantic_hotspot_only = semantic_hotspot_only
        self.semantic_hotspot_limit = max(1, semantic_hotspot_limit)
        self._recent_hotspot_ids: set[int] = set()
        self._hotspot_resource_threshold: float = 0.0
        
        # 向量缓存
        self._species_semantic_cache: dict[str, np.ndarray] = {}  # lineage_code -> vector
        self._species_feature_cache: dict[str, np.ndarray] = {}
        self._tile_semantic_cache: dict[int, np.ndarray] = {}     # tile_id -> vector
        self._tile_semantic_signatures: dict[int, str] = {}
        self._tile_feature_cache: dict[int, np.ndarray] = {}
        
        # 文本缓存 (用于显示)
        self._species_text_cache: dict[str, str] = {}
        self._tile_text_cache: dict[int, str] = {}
        
        # 矩阵缓存
        self._matrix_cache: np.ndarray | None = None
        self._cache_species_codes: list[str] = []
        self._cache_tile_ids: list[int] = []
        self._cache_turn: int = -1
        
        # 统计
        self._stats = {
            "compute_calls": 0,
            "cache_hits": 0,
            "semantic_calls": 0,
            "matrix_computes": 0,
        }
        
        # 持久化语义存储
        self._tile_semantic_store_path = tile_cache_path or (_TILE_CACHE_DIR / "tile_semantics.json")
        self._tile_semantic_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._semantic_store_dirty = False
        self._load_tile_semantic_store()

    # ============ 配置与缓存管理 ============

    def update_semantic_settings(
        self,
        *,
        use_semantic: bool | None = None,
        semantic_hotspot_only: bool | None = None,
        semantic_hotspot_limit: int | None = None,
        embedding_service: "EmbeddingService | None" = None,
    ) -> None:
        if embedding_service is not None:
            self.embeddings = embedding_service
        if use_semantic is not None:
            self.use_semantic = use_semantic and self.embeddings is not None
        if semantic_hotspot_only is not None:
            self.semantic_hotspot_only = semantic_hotspot_only
        if semantic_hotspot_limit is not None:
            self.semantic_hotspot_limit = max(1, semantic_hotspot_limit)

    def _load_tile_semantic_store(self) -> None:
        path = self._tile_semantic_store_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[SuitabilityService] 无法加载地块语义缓存: {exc}")
            return
        loaded = 0
        for key, payload in data.items():
            try:
                tile_id = int(key)
            except ValueError:
                continue
            vector = payload.get("vector")
            signature = payload.get("signature")
            if not isinstance(vector, list) or signature is None:
                continue
            self._tile_semantic_cache[tile_id] = np.array(vector, dtype=np.float32)
            self._tile_semantic_signatures[tile_id] = signature
            loaded += 1
        if loaded:
            logger.info(f"[SuitabilityService] 已加载 {loaded} 个地块语义向量缓存")

    def _save_tile_semantic_store(self) -> None:
        if not self._semantic_store_dirty:
            return
        data = {}
        for tile_id, vector in self._tile_semantic_cache.items():
            signature = self._tile_semantic_signatures.get(tile_id)
            if signature is None:
                continue
            data[str(tile_id)] = {
                "vector": vector.tolist(),
                "signature": signature,
            }
        try:
            self._tile_semantic_store_path.write_text(json.dumps(data), encoding="utf-8")
            self._semantic_store_dirty = False
        except Exception as exc:
            logger.warning(f"[SuitabilityService] 保存地块语义缓存失败: {exc}")

    def _cache_tile_semantic_vector(self, tile_id: int, vector: np.ndarray, signature: str) -> None:
        self._tile_semantic_cache[tile_id] = vector
        self._tile_semantic_signatures[tile_id] = signature
        self._semantic_store_dirty = True
        self._save_tile_semantic_store()
    
    # ============ 语义描述生成 ============
    
    def _build_species_text(self, species: "Species") -> str:
        """生成物种的语义描述文本"""
        traits = getattr(species, 'abstract_traits', {}) or {}
        habitat = getattr(species, 'habitat_type', 'terrestrial') or 'terrestrial'
        caps = getattr(species, 'capabilities', []) or []
        diet = getattr(species, 'diet_type', 'omnivore') or 'omnivore'
        trophic = getattr(species, 'trophic_level', 1.0) or 1.0
        growth = getattr(species, 'growth_form', 'aquatic') or 'aquatic'
        
        habitat_cn = {
            "marine": "海洋生物，生活在海水中",
            "deep_sea": "深海生物，适应高压低温黑暗环境",
            "freshwater": "淡水生物，生活在湖泊河流中",
            "coastal": "海岸潮间带生物，适应潮汐变化",
            "terrestrial": "陆地生物",
            "amphibious": "两栖生物，可在水陆间活动",
            "aerial": "空中生物，主要在空中活动",
        }.get(habitat, habitat)
        
        diet_cn = {
            "autotroph": "自养型，通过光合作用或化能合成获取能量",
            "herbivore": "草食性，以植物或藻类为食",
            "carnivore": "肉食性，捕食其他动物",
            "omnivore": "杂食性，食物来源多样",
            "detritivore": "腐食性，分解有机物",
        }.get(diet, "")
        
        growth_cn = {
            "aquatic": "水生形态",
            "moss": "苔藓形态",
            "herb": "草本形态",
            "shrub": "灌木形态",
            "tree": "乔木形态",
        }.get(growth, "")
        
        cap_str = "、".join(caps[:5]) if caps else "无特殊能力"
        
        # 温度偏好描述
        heat = traits.get('耐热性', 5)
        cold = traits.get('耐寒性', 5)
        if heat > 7:
            temp_pref = "喜高温环境"
        elif cold > 7:
            temp_pref = "喜低温环境"
        else:
            temp_pref = "适应温和气候"
        
        # 湿度偏好描述
        drought = traits.get('耐旱性', 5)
        if drought > 7:
            humid_pref = "耐干旱"
        elif drought < 3:
            humid_pref = "需要高湿度"
        else:
            humid_pref = "适应中等湿度"
        
        desc = getattr(species, 'description', '') or ''
        common_name = getattr(species, 'common_name', '') or '未知物种'
        latin_name = getattr(species, 'latin_name', '') or ''
        
        text = f"""{common_name} ({latin_name})
栖息环境: {habitat_cn}
营养级: {trophic:.1f} ({diet_cn})
{f'生长形态: {growth_cn}' if trophic < 2.0 else ''}
温度适应: {temp_pref} (耐热{heat}/10, 耐寒{cold}/10)
湿度适应: {humid_pref} (耐旱{drought}/10)
特殊能力: {cap_str}
{desc[:150] if desc else ''}"""
        
        return text.strip()
    
    def _classify_water_type(self, tile: "MapTile") -> tuple[str, bool]:
        biome = (getattr(tile, 'biome', '') or '').lower()
        salinity = getattr(tile, 'salinity', 0.0) or 0.0
        is_lake = getattr(tile, 'is_lake', False)
        if "海" in biome or is_lake:
            if salinity > 30:
                return "高盐度深海水域", True
            if salinity > 10:
                return "半咸水海域", True
            if is_lake:
                return "淡水湖泊", True
            return "浅海/近海水域", True
        return "陆地环境", False

    def _quantize_temperature(self, temp: float) -> tuple[str, str]:
        buckets = [
            (-100, -50, "致命极寒", "低于 -50°C 的地带几乎没有生命"),
            (-50, -35, "极地冰封", "极寒冻原，偶尔出现耐寒微生物"),
            (-35, -25, "严冬冻原", "长期 -30°C 的深冬大陆性气候"),
            (-25, -20, "深冬酷寒", "-25~-20°C，稀有生命勉强存活"),
            (-20, -15, "寒冷凛冽", "-20~-15°C，稍有升温即可触发生命反应"),
            (-15, -10, "刺骨寒潮", "-15~-10°C 的冷锋地带"),
            (-10, -6, "寒凉初春", "-10~-6°C，融雪期刚开始"),
            (-6, -2, "低温临界", "-6~-2°C，许多生物的绝对临界点"),
            (-2, 2, "冰线附近", "-2~2°C，冰水交错的敏感区"),
            (2, 6, "冷凉温带", "2~6°C，适合冷水生物"),
            (6, 10, "清爽微凉", "6~10°C，温带海洋气候"),
            (10, 14, "温和宜居", "10~14°C，越来越多物种适应"),
            (14, 18, "暖润舒适", "14~18°C，适宜大多数温带生命"),
            (18, 22, "黄金暖温", "18~22°C，生理最优区"),
            (22, 26, "温热繁盛", "22~26°C，热带雨林惯常温度"),
            (26, 30, "炎热湿润", "26~30°C，热带浅海/雨林"),
            (30, 36, "酷热闷湿", "30~36°C，热应激明显"),
            (36, 42, "炽热危险", "36~42°C，仅耐热物种可长期生存"),
            (42, 100, "致命酷热", "高于 42°C 的极端环境"),
        ]
        for low, high, label, desc in buckets:
            if temp >= low and temp < high:
                return label, desc
        return ("未知", "气温数据缺失")

    def _quantize_humidity(self, humidity: float) -> tuple[str, str]:
        value = max(0.0, min(1.0, humidity))
        buckets = [
            (0.0, 0.05, "极端干裂", "接近真空的干燥，生命难以维系"),
            (0.05, 0.12, "极度干燥", "沙漠中心的干燥空气"),
            (0.12, 0.2, "荒漠干燥", "蒸发量远大于降水"),
            (0.2, 0.3, "半干草原", "略有降水，植被稀疏"),
            (0.3, 0.4, "干燥温带", "低湿度的温带大陆性气候"),
            (0.4, 0.5, "适中偏干", "轻微干燥，仍可支持大部分植物"),
            (0.5, 0.6, "温润宜居", "湿度 50% 左右的人居舒适区"),
            (0.6, 0.7, "微潮湿润", "持续潮湿，适合雨林边缘"),
            (0.7, 0.8, "潮湿丰沛", "降水丰富，易形成密林"),
            (0.8, 0.9, "湿热闷沌", "90% 左右的闷热环境"),
            (0.9, 1.01, "饱和湿润", "接近饱和的沼泽/南海空气"),
        ]
        for low, high, label, desc in buckets:
            if value >= low and value < high:
                return label, desc
        return ("未知", "湿度数据缺失")

    def _quantize_resources(self, resources: float) -> tuple[str, str]:
        value = max(0.0, resources or 0.0)
        buckets = [
            (0, 20, "枯竭荒寂", "几乎没有可利用能量"),
            (20, 40, "极度贫瘠", "只能支持零星微生物"),
            (40, 70, "贫瘠", "资源稀少，需依靠突发事件"),
            (70, 110, "偏低", "勉强能维持零散生产者"),
            (110, 150, "稍低", "中小型群落可以稳定存在"),
            (150, 190, "适中偏低", "早期生态系统的常见水平"),
            (190, 230, "适中", "大多数陆地/浅海会出现的生产力"),
            (230, 270, "适中偏高", "较肥沃，能支撑多层食物网"),
            (270, 310, "充沛", "营养盐丰富，群落密度高"),
            (310, 380, "富饶", "河口/潮滩等高 NPP 区域"),
            (380, 480, "极富", "泛滥平原或藻华高发区"),
            (480, 650, "爆发丰盈", "短期事件导致的资源暴涨"),
            (650, 1000, "异常充沛", "火山灰/洪水/化能热泉等极端供给"),
        ]
        for low, high, label, desc in buckets:
            if value >= low and value < high:
                return label, desc
        return ("未知", "资源数据缺失")

    def _quantize_elevation(self, elevation: float) -> tuple[str, str]:
        buckets = [
            (-12000, -8000, "超深海沟", "最深的海沟，完全黑暗"),
            (-8000, -6000, "深海沟", "6000m 以上的极深海区"),
            (-6000, -4000, "深海盆地", "典型的深海平原"),
            (-4000, -2500, "深海山脊", "深海山脊和海山"),
            (-2500, -1500, "中层海域", "部分微光可达的水层"),
            (-1500, -700, "次深海", "深中层，营养盐较多"),
            (-700, -200, "浅海大陆架", "光照与营养最为充足"),
            (-200, -20, "潮间带", "潮汐上下波动的浅水区"),
            (-20, 0, "海岸/潟湖", "近岸或潟湖水体"),
            (0, 80, "沿海低地", "海拔 0~80m 的平原"),
            (80, 200, "内陆平原", "广阔的冲积平原"),
            (200, 500, "丘陵台地", "缓丘和台地"),
            (500, 1000, "低山", "低矮山地"),
            (1000, 1800, "中山", "森林覆盖的山地"),
            (1800, 2600, "高山", "空气稀薄的高原边缘"),
            (2600, 3500, "极高山", "接近雪线的山体"),
            (3500, 5000, "雪顶山脉", "全年积雪的山峰"),
            (5000, 9000, "巅峰地带", "极端高山，如喜马拉雅"),
        ]
        for low, high, label, desc in buckets:
            if elevation >= low and elevation < high:
                return label, desc
        return ("未知", "地势数据缺失")

    def _compute_tile_signature(self, tile: "MapTile") -> str:
        biome = getattr(tile, 'biome', 'unknown') or 'unknown'
        cover = getattr(tile, 'cover', 'none') or 'none'
        water_label, _ = self._classify_water_type(tile)
        temp_bucket = self._quantize_temperature(getattr(tile, 'temperature', 20))[0]
        humidity_bucket = self._quantize_humidity(getattr(tile, 'humidity', 0.5))[0]
        resource_bucket = self._quantize_resources(getattr(tile, 'resources', 0))[0]
        elevation_bucket = self._quantize_elevation(getattr(tile, 'elevation', 0))[0]
        river_flag = "river" if getattr(tile, 'has_river', False) else "no_river"
        lake_flag = "lake" if getattr(tile, 'is_lake', False) else "no_lake"
        volcanic = getattr(tile, 'volcanic_potential', 0.0) or 0.0
        earthquake = getattr(tile, 'earthquake_risk', 0.0) or 0.0
        volcanic_bucket = "volcanic_hot" if volcanic > 0.6 else ("volcanic_active" if volcanic > 0.3 else "stable")
        earthquake_bucket = "quake_high" if earthquake > 0.6 else ("quake_mid" if earthquake > 0.3 else "quake_low")
        return "|".join([
            biome,
            cover,
            water_label,
            temp_bucket,
            humidity_bucket,
            resource_bucket,
            elevation_bucket,
            river_flag,
            lake_flag,
            volcanic_bucket,
            earthquake_bucket,
        ])

    def _build_tile_text(self, tile: "MapTile") -> str:
        """生成地块的语义描述文本，使用量化后的描述避免频繁变动"""
        tile_id = getattr(tile, 'id', 0)
        x = getattr(tile, 'x', 0)
        y = getattr(tile, 'y', 0)
        biome = getattr(tile, 'biome', '未知') or '未知'
        cover = getattr(tile, 'cover', '无植被') or '无植被'
        temp_label, temp_desc = self._quantize_temperature(getattr(tile, 'temperature', 20))
        humid_label, humid_desc = self._quantize_humidity(getattr(tile, 'humidity', 0.5))
        resource_label, resource_desc = self._quantize_resources(getattr(tile, 'resources', 0))
        elevation_label, elevation_desc = self._quantize_elevation(getattr(tile, 'elevation', 0))
        water_label, is_water = self._classify_water_type(tile)
        has_river = getattr(tile, 'has_river', False)
        volcanic = getattr(tile, 'volcanic_potential', 0.0) or 0.0
        earthquake = getattr(tile, 'earthquake_risk', 0.0) or 0.0
        
        lines = [
            f"地块 #{tile_id} 坐标({x}, {y})",
            f"地形: {biome}",
            f"植被: {cover}",
            f"环境类型: {water_label}",
            f"温度等级: {temp_label}（{temp_desc}）",
            f"湿度等级: {humid_label}（{humid_desc}）",
            f"资源等级: {resource_label}（{resource_desc}）",
            f"地势: {elevation_label}（{elevation_desc}）",
        ]
        if has_river:
            lines.append("存在河流网络")
        if volcanic > 0.6:
            lines.append("处于火山强活跃区")
        elif volcanic > 0.3:
            lines.append("火山活动频繁")
        if earthquake > 0.6:
            lines.append("地震风险极高")
        elif earthquake > 0.3:
            lines.append("地震活动中等")
        if not is_water and getattr(tile, 'is_lake', False):
            lines.append("包含大型淡水湖泊")
        return "\n".join(lines).strip()

    def _should_use_semantic_for_tile(self, tile: "MapTile", signature: str) -> bool:
        if not self.use_semantic or self.embeddings is None:
            return False
        if not self.semantic_hotspot_only:
            return True
        tile_id = getattr(tile, 'id', None)
        if tile_id is None:
            return False
        if tile_id in self._recent_hotspot_ids:
            return True
        if not self._recent_hotspot_ids:
            resources = getattr(tile, 'resources', 0.0) or 0.0
            return resources >= self._hotspot_resource_threshold
        # 如果签名发生变化（例如环境突变），允许重新计算一次
        cached_signature = self._tile_semantic_signatures.get(tile_id)
        return cached_signature != signature

    def _select_hotspot_tiles(self, tiles: Sequence["MapTile"]) -> list["MapTile"]:
        valid_tiles = [t for t in tiles if getattr(t, 'id', None) is not None]
        if not self.semantic_hotspot_only:
            self._recent_hotspot_ids = {t.id for t in valid_tiles if t.id is not None}
            self._hotspot_resource_threshold = 0.0
            return valid_tiles
        
        sorted_tiles = sorted(
            valid_tiles,
            key=lambda t: getattr(t, 'resources', 0.0) or 0.0,
            reverse=True,
        )
        subset = sorted_tiles[: self.semantic_hotspot_limit]
        self._recent_hotspot_ids = {t.id for t in subset if t.id is not None}
        if subset:
            self._hotspot_resource_threshold = getattr(subset[-1], 'resources', 0.0) or 0.0
        else:
            self._hotspot_resource_threshold = 0.0
        return subset
    
    # ============ 特征向量提取 ============
    
    def _extract_species_features(self, species: "Species") -> np.ndarray:
        """从物种属性提取 12 维特征向量
        
        【改进】综合多个属性判断水生/陆生，而不仅仅依赖 habitat_type
        """
        traits = getattr(species, 'abstract_traits', {}) or {}
        habitat = (getattr(species, 'habitat_type', '') or '').lower()
        trophic = getattr(species, 'trophic_level', 1.0) or 1.0
        caps = getattr(species, 'capabilities', []) or []
        growth = (getattr(species, 'growth_form', '') or '').lower()
        common_name = (getattr(species, 'common_name', '') or '').lower()
        desc = (getattr(species, 'description', '') or '').lower()
        
        # 【智能判断】物种是否为水生
        # 综合考虑: habitat_type, growth_form, common_name, description, capabilities
        is_aquatic_species = False
        is_deep_sea = False
        is_freshwater = False
        is_hydrothermal = False  # 热泉生物
        
        # 1. 从 habitat_type 判断
        # 【修复】添加 hydrothermal（热泉）类型的识别
        if habitat in ("marine", "deep_sea", "freshwater", "coastal", "hydrothermal"):
            is_aquatic_species = True
            is_deep_sea = habitat in ("deep_sea", "hydrothermal")  # 热泉也是深海环境
            is_freshwater = habitat == "freshwater"
            is_hydrothermal = habitat == "hydrothermal"
        
        # 2. 从 growth_form 判断 (水生植物)
        if growth == "aquatic" and trophic < 2.0:
            is_aquatic_species = True
        
        # 3. 从名称/描述判断
        aquatic_keywords = ["藻", "浮游", "海洋", "深海", "水生", "海", "鱼", "虾", "蟹", "贝", 
                          "珊瑚", "水母", "海星", "海胆", "鲸", "鲨", "细菌"]
        freshwater_keywords = ["淡水", "河", "湖", "溪"]
        deep_keywords = ["深海", "热泉", "硫", "化能", "热液", "喷口"]
        
        for kw in aquatic_keywords:
            if kw in common_name or kw in desc:
                is_aquatic_species = True
                break
        
        for kw in freshwater_keywords:
            if kw in common_name or kw in desc:
                is_freshwater = True
                is_aquatic_species = True
                break
        
        for kw in deep_keywords:
            if kw in common_name or kw in desc:
                is_deep_sea = True
                is_aquatic_species = True
                break
        
        # 4. 从能力判断（同时检查中英文）
        caps_lower = [c.lower() for c in caps] if caps else []
        caps_set = set(caps_lower + list(caps if caps else []))
        if "chemosynthesis" in caps_set or "化能合成" in caps_set:
            is_deep_sea = True
            is_aquatic_species = True
            is_hydrothermal = True
        
        # 5. 【新增】从 diet_type 判断
        diet_type = (getattr(species, 'diet_type', '') or '').lower()
        if diet_type == "autotroph" and is_deep_sea:
            # 深海自养生物 = 化能自养
            is_hydrothermal = True
        
        # D0: 热量偏好 (0=极寒, 0.5=温和, 1=极热)
        heat = traits.get('耐热性', 5)
        cold = traits.get('耐寒性', 5)
        thermal = (heat - cold + 10) / 20  # [-10, 10] -> [0, 1]
        thermal = np.clip(thermal, 0, 1)
        
        # D1: 水分偏好 (0=干旱, 1=湿润)
        drought = traits.get('耐旱性', 5)
        moisture = 1 - drought / 10
        if is_aquatic_species:
            moisture = max(moisture, 0.8)  # 水生物种偏好高湿度
        
        # D2: 海拔偏好 (0=深海, 0.5=海平面, 1=高山)
        if is_deep_sea:
            altitude = 0.1
        elif is_aquatic_species and not is_freshwater:
            altitude = 0.3  # 海洋
        elif is_freshwater:
            altitude = 0.5  # 淡水
        elif habitat == "aerial":
            altitude = 0.75
        elif habitat == "terrestrial" or not is_aquatic_species:
            altitude = 0.6
        else:
            altitude = 0.5
        
        # D3: 盐度偏好 (0=淡水, 1=高盐)
        if is_freshwater:
            salinity_pref = 0.1
        elif is_aquatic_species:
            salinity_pref = 0.85  # 海洋生物偏好高盐
        else:
            salinity_pref = 0.3  # 陆生不太在意
        
        # D4: 资源偏好 (生产者需要高资源，水生消费者也需要)
        if trophic < 2.0:
            resources_pref = 0.8
        elif is_aquatic_species:
            resources_pref = 0.5  # 水生消费者需要猎物，间接需要资源
        else:
            resources_pref = 0.4
        
        # D5: 水域性 (0=纯陆地, 1=纯水域) - 最重要！
        if is_aquatic_species:
            aquatic = 1.0
        elif habitat == "amphibious":
            aquatic = 0.5
        else:
            aquatic = 0.0
        
        # D6: 深度偏好 (0=浅/陆, 1=深海)
        if is_deep_sea:
            depth_pref = 0.9
        elif is_aquatic_species:
            depth_pref = 0.4  # 一般水生物种偏好中等深度
        else:
            depth_pref = 0.0
        
        # D7: 光照需求 (0=喜暗, 1=需光)
        if "photosynthesis" in caps_set or "光合作用" in caps_set:
            light_pref = 0.95  # 光合作用必须有光
        elif is_hydrothermal or "chemosynthesis" in caps_set or "化能合成" in caps_set or "bioluminescence" in caps_set:
            light_pref = 0.1   # 热泉/化能生物适应黑暗
        elif is_deep_sea:
            light_pref = 0.15
        elif is_aquatic_species:
            light_pref = 0.5  # 一般水生物种
        else:
            light_pref = 0.6
        
        # D8: 地热偏好
        if is_hydrothermal or "chemosynthesis" in caps_set or "化能合成" in caps_set:
            volcanic_pref = 0.95  # 热泉/化能合成物种非常依赖地热
        elif is_deep_sea:
            volcanic_pref = 0.7  # 深海物种偏好地热
        else:
            volcanic_pref = 0.3
        
        # D9: 稳定性偏好 (大多数生物喜欢稳定)
        stability_pref = 0.6
        
        # D10: 植被偏好
        if is_aquatic_species:
            vegetation_pref = 0.2  # 水生物种不关心陆地植被
        elif growth in ("moss", "herb", "shrub", "tree"):
            vegetation_map = {"moss": 0.3, "herb": 0.5, "shrub": 0.7, "tree": 0.9}
            vegetation_pref = vegetation_map.get(growth, 0.5)
        else:
            vegetation_pref = 0.4
        
        # D11: 河流偏好
        # 【改进】海洋生物不关心河流，用中性值
        if is_freshwater:
            river_pref = 0.9  # 淡水物种非常需要河流
        elif is_aquatic_species:
            river_pref = 0.3  # 海洋物种不需要河流，给低值使其与无河流地块匹配
        else:
            river_pref = 0.4  # 陆生物种中等偏好
        
        return np.array([
            thermal, moisture, altitude, salinity_pref,
            resources_pref, aquatic, depth_pref, light_pref,
            volcanic_pref, stability_pref, vegetation_pref, river_pref
        ])
    
    def _extract_tile_features(self, tile: "MapTile") -> np.ndarray:
        """从地块属性提取 12 维特征向量
        
        【改进】更智能地检测水域地块
        """
        biome = (getattr(tile, 'biome', '') or '').lower()
        temp = getattr(tile, 'temperature', 20)
        humidity = getattr(tile, 'humidity', 0.5)
        elevation = getattr(tile, 'elevation', 0)
        salinity = getattr(tile, 'salinity', 0)
        resources = getattr(tile, 'resources', 100)
        cover = (getattr(tile, 'cover', '') or '').lower()
        has_river = getattr(tile, 'has_river', False)
        is_lake = getattr(tile, 'is_lake', False)
        volcanic = getattr(tile, 'volcanic_potential', 0)
        earthquake = getattr(tile, 'earthquake_risk', 0)
        
        # 【智能判断】地块是否为水域
        # 综合考虑: biome名称, elevation, is_lake, salinity
        water_keywords = ["海", "洋", "水", "湖", "河", "溪", "浅海", "深海", "大陆架", "大陆坡", "海沟"]
        is_water = False
        is_deep_water = False
        is_freshwater_tile = False
        
        # 1. 从 biome 名称判断
        for kw in water_keywords:
            if kw in biome:
                is_water = True
                break
        
        # 2. 从海拔判断 (海拔<0 通常是水下)
        if elevation < 0:
            is_water = True
        
        # 3. 湖泊判断
        if is_lake:
            is_water = True
            is_freshwater_tile = salinity < 10
        
        # 4. 从盐度判断
        if salinity > 20:
            is_water = True
        elif salinity < 5 and is_water:
            is_freshwater_tile = True
        
        # 5. 深海判断
        if elevation < -1000 or "深海" in biome or "海沟" in biome:
            is_deep_water = True
            is_water = True
        
        # D0: 热量 (归一化温度)
        thermal = (temp + 30) / 70  # [-30, 40] -> [0, 1]
        thermal = np.clip(thermal, 0, 1)
        
        # D1: 水分
        moisture = humidity
        if is_water:
            moisture = 1.0  # 水域湿度为最高
        
        # D2: 海拔 (sigmoid 归一化)
        # -5000m -> 0.0, 0m -> 0.5, 5000m -> 1.0
        altitude = 1 / (1 + np.exp(-elevation / 1500))
        
        # D3: 盐度
        if is_water:
            salinity_norm = min(1.0, salinity / 40)
        else:
            salinity_norm = 0.3  # 陆地盐度中性
        
        # D4: 资源
        resources_norm = min(1.0, math.log(resources + 1) / math.log(1001))
        
        # D5: 水域性 - 最重要！
        aquatic = 1.0 if is_water else 0.0
        
        # D6: 深度
        if is_deep_water or elevation < -3000:
            depth = 1.0  # 深海
        elif elevation < -1000:
            depth = 0.7  # 中层
        elif elevation < 0:
            depth = 0.4  # 浅海
        elif is_lake:
            depth = 0.3  # 湖泊
        else:
            depth = 0.0  # 陆地
        
        # D7: 光照 (与深度相关)
        if elevation < -1000:
            light = 0.1  # 深海无光
        elif elevation < -200:
            light = 0.4  # 弱光层
        elif is_water:
            light = 0.7  # 浅水有光但弱于陆地
        else:
            light = 0.9  # 陆地有光
        
        # D8: 地热
        volcanic_val = volcanic
        
        # D9: 稳定性
        stability = 1.0 - earthquake
        
        # D10: 植被密度
        if is_water:
            vegetation = 0.2  # 水域无陆地植被
        elif "森林" in cover or "林" in cover or "雨林" in cover:
            vegetation = 0.9
        elif "草" in cover or "灌" in cover:
            vegetation = 0.6
        elif "苔" in cover:
            vegetation = 0.4
        elif "沙" in cover or "岩" in cover or "冰" in cover:
            vegetation = 0.1
        else:
            vegetation = 0.3
        
        # D11: 河流
        # 【改进】对于海洋地块，河流值应该是低的（与海洋物种匹配）
        if is_freshwater_tile or has_river:
            river = 0.9
        elif is_water:
            river = 0.3  # 海洋无河流，给低值与海洋物种匹配
        else:
            river = 0.4  # 陆地无河流
        
        return np.array([
            thermal, moisture, altitude, salinity_norm,
            resources_norm, aquatic, depth, light,
            volcanic_val, stability, vegetation, river
        ])
    
    # ============ 硬约束检查 ============
    
    def _check_habitat_compatibility(
        self, 
        species: "Species", 
        tile: "MapTile"
    ) -> tuple[float, str]:
        """检查物种与地块的栖息地兼容性（硬约束）
        
        【改进】使用特征向量中的水域性维度作为主要判断依据，不依赖关键词
        
        返回: (惩罚系数, 原因说明)
        - 惩罚系数 1.0 = 无惩罚
        - 惩罚系数 0.0 = 完全不兼容（致命）
        - 惩罚系数 0.0-1.0 = 部分惩罚
        """
        lineage_code = getattr(species, 'lineage_code', '')
        tile_id = getattr(tile, 'id', 0)
        
        # ========== 使用特征向量判断（最可靠的方式）==========
        # 获取或计算物种特征向量
        if lineage_code and lineage_code in self._species_feature_cache:
            sp_features = self._species_feature_cache[lineage_code]
        else:
            sp_features = self._extract_species_features(species)
        
        # 获取或计算地块特征向量
        if tile_id and tile_id in self._tile_feature_cache:
            tile_features = self._tile_feature_cache[tile_id]
        else:
            tile_features = self._extract_tile_features(tile)
        
        # 提取水域性维度 (D5: aquatic, index=5)
        # 物种水域性: 0=纯陆生, 0.5=两栖, 1=纯水生
        # 地块水域性: 0=陆地, 1=水域
        species_aquatic = sp_features[5]  # 物种的水域性偏好
        tile_aquatic = tile_features[5]    # 地块是否为水域
        
        # 提取深度维度 (D6: depth, index=6)
        species_depth = sp_features[6]     # 物种的深度偏好 (0=浅/陆, 1=深海)
        tile_depth = tile_features[6]      # 地块深度 (0=陆地, 0.3-1=水深)
        
        # 提取地热维度 (D8: volcanic, index=8)
        species_volcanic = sp_features[8]  # 物种的地热偏好
        tile_volcanic = tile_features[8]   # 地块地热程度
        
        # ========== 定义阈值 ==========
        AQUATIC_THRESHOLD = 0.6       # 物种水域性 > 此值 = 水生物种
        TERRESTRIAL_THRESHOLD = 0.3   # 物种水域性 < 此值 = 陆生物种
        DEEP_SEA_THRESHOLD = 0.7      # 物种深度偏好 > 此值 = 深海物种
        HYDROTHERMAL_THRESHOLD = 0.8  # 物种地热偏好 > 此值 = 热泉物种
        
        WATER_TILE_THRESHOLD = 0.5    # 地块水域性 > 此值 = 水域地块
        DEEP_WATER_THRESHOLD = 0.6    # 地块深度 > 此值 = 深水区
        VOLCANIC_THRESHOLD = 0.5      # 地块地热 > 此值 = 地热区
        
        # ========== 判断物种和地块类型 ==========
        is_aquatic_species = species_aquatic > AQUATIC_THRESHOLD
        is_terrestrial_species = species_aquatic < TERRESTRIAL_THRESHOLD
        is_amphibious = TERRESTRIAL_THRESHOLD <= species_aquatic <= AQUATIC_THRESHOLD
        is_deep_sea_species = species_depth > DEEP_SEA_THRESHOLD
        is_hydrothermal_species = species_volcanic > HYDROTHERMAL_THRESHOLD
        
        is_water_tile = tile_aquatic > WATER_TILE_THRESHOLD
        is_land_tile = tile_aquatic < WATER_TILE_THRESHOLD
        is_deep_water_tile = tile_depth > DEEP_WATER_THRESHOLD
        is_volcanic_area = tile_volcanic > VOLCANIC_THRESHOLD
        
        # ========== 应用硬约束 ==========
        
        # 规则1: 水生物种（水域性 > 0.6）不能在陆地生存
        if is_aquatic_species and is_land_tile:
            # 两栖物种（0.3-0.6）有一定适应性
            if is_amphibious:
                return (0.4, "两栖物种在陆地受限")
            # 深海/热泉物种在陆地完全无法生存
            if is_deep_sea_species or is_hydrothermal_species:
                return (0.0, "深海/热泉物种无法在陆地生存")
            # 一般水生物种
            # 水域性越高，惩罚越重
            penalty = max(0.02, 0.15 * (1 - species_aquatic))
            return (penalty, "水生物种无法在陆地生存")
        
        # 规则2: 陆生物种（水域性 < 0.3）不能在水中生存
        if is_terrestrial_species and is_water_tile:
            # 如果是浅水区（深度 < 0.4），给一点点机会
            if tile_depth < 0.4:
                # 水域性越低，惩罚越重
                penalty = max(0.1, 0.3 * species_aquatic)
                return (penalty, "陆生物种在浅水区受限")
            # 深水区完全无法生存
            return (0.0, "陆生物种无法在水中生存")
        
        # 规则3: 深海物种（深度偏好 > 0.7）需要深水环境
        if is_deep_sea_species and is_water_tile and not is_deep_water_tile:
            # 热泉物种需要火山活动区
            if is_hydrothermal_species and not is_volcanic_area:
                return (0.1, "热泉物种需要地热环境")
            # 深海物种在浅水也受限，但不是完全无法生存
            penalty = max(0.2, 0.5 * (1 - species_depth))
            return (penalty, "深海物种在浅水区受限")
        
        # 规则4: 热泉物种在非地热的陆地上无法生存
        if is_hydrothermal_species and is_land_tile:
            return (0.0, "热泉物种无法在陆地生存")
        
        # 规则5: 使用额外属性进行细化判断（可选）
        habitat = (getattr(species, 'habitat_type', '') or '').lower()
        salinity = getattr(tile, 'salinity', 35)
        is_lake = getattr(tile, 'is_lake', False)
        
        # 淡水物种不能在高盐度环境
        if habitat == "freshwater" and is_water_tile and salinity > 20:
            return (0.1, "淡水物种无法适应高盐度")
        
        # 海洋物种不能在淡水环境
        if habitat == "marine" and is_water_tile and (is_lake or salinity < 10):
            return (0.15, "海洋物种无法适应淡水")
        
        # 无硬约束，正常计算
        return (1.0, "")
    
    # ============ 核心计算 ============
    
    def compute_suitability(
        self, 
        species: "Species", 
        tile: "MapTile"
    ) -> SuitabilityResult:
        """计算单个物种-地块的宜居度"""
        self._stats["compute_calls"] += 1
        
        lineage_code = getattr(species, 'lineage_code', '')
        tile_id = getattr(tile, 'id', 0)
        
        # 【新增】首先检查硬约束
        penalty, penalty_reason = self._check_habitat_compatibility(species, tile)
        
        # 获取/生成特征向量
        if lineage_code not in self._species_feature_cache:
            self._species_feature_cache[lineage_code] = self._extract_species_features(species)
        if tile_id not in self._tile_feature_cache:
            self._tile_feature_cache[tile_id] = self._extract_tile_features(tile)
        
        sp_features = self._species_feature_cache[lineage_code]
        tile_features = self._tile_feature_cache[tile_id]
        
        # 计算特征相似度 (高斯距离)
        diff = sp_features - tile_features
        weighted_sq_diff = DIMENSION_WEIGHTS * (diff ** 2)
        distance = np.sqrt(np.sum(weighted_sq_diff))
        feature_score = float(np.exp(-distance ** 2 / (2 * 0.4 ** 2)))
        
        # 特征分解
        feature_breakdown = {}
        for i, name in enumerate(DIMENSION_NAMES):
            # 单维度相似度
            single_diff = abs(sp_features[i] - tile_features[i])
            single_score = float(np.exp(-single_diff ** 2 / (2 * 0.3 ** 2)))
            feature_breakdown[name] = round(single_score, 3)
        
        # 语义相似度 (如果启用)
        semantic_score = 0.5  # 默认中等
        species_text = ""
        tile_text = ""
        tile_signature = self._compute_tile_signature(tile)
        allow_semantic = self._should_use_semantic_for_tile(tile, tile_signature)
        
        if self.use_semantic and self.embeddings is not None and allow_semantic:
            try:
                # 物种文本/向量
                if lineage_code not in self._species_semantic_cache:
                    species_text = self._build_species_text(species)
                    self._species_text_cache[lineage_code] = species_text
                    vec = self.embeddings.embed_single(species_text)
                    self._species_semantic_cache[lineage_code] = np.array(vec, dtype=np.float32)
                    self._stats["semantic_calls"] += 1
                else:
                    species_text = self._species_text_cache.get(lineage_code, "")
                
                # 地块文本/向量（带签名校验）
                cached_signature = self._tile_semantic_signatures.get(tile_id)
                if tile_id not in self._tile_text_cache:
                    self._tile_text_cache[tile_id] = self._build_tile_text(tile)
                tile_text = self._tile_text_cache.get(tile_id, "")
                
                if (
                    tile_id not in self._tile_semantic_cache or
                    cached_signature != tile_signature
                ):
                    vec = self.embeddings.embed_single(tile_text)
                    np_vec = np.array(vec, dtype=np.float32)
                    self._cache_tile_semantic_vector(tile_id, np_vec, tile_signature)
                    self._stats["semantic_calls"] += 1
                else:
                    np_vec = self._tile_semantic_cache[tile_id]
                
                sp_vec = self._species_semantic_cache[lineage_code]
                sp_norm = sp_vec / (np.linalg.norm(sp_vec) + 1e-8)
                tile_norm = np_vec / (np.linalg.norm(np_vec) + 1e-8)
                semantic_score = float(np.dot(sp_norm, tile_norm))
                semantic_score = (semantic_score + 1) / 2  # [-1, 1] -> [0, 1]
                
            except Exception as e:
                logger.warning(f"[SuitabilityService] 语义计算失败: {e}")
                semantic_score = 0.5
                tile_text = ""
        
        # 融合得分
        if self.use_semantic:
            total = self.semantic_weight * semantic_score + self.feature_weight * feature_score
        else:
            total = feature_score
        
        # 【新增】应用硬约束惩罚
        if penalty < 1.0:
            total = total * penalty
            if penalty_reason:
                logger.debug(f"[SuitabilityService] 硬约束惩罚: {lineage_code} 在地块 {tile_id}: {penalty_reason} (系数={penalty:.2f})")
        
        # 确保范围（允许极低值，用于硬约束）
        total = max(0.01, min(1.0, total))
        
        return SuitabilityResult(
            total=round(total, 3),
            semantic_score=round(semantic_score, 3),
            feature_score=round(feature_score, 3),
            feature_breakdown=feature_breakdown,
            species_text=species_text,
            tile_text=tile_text,
        )
    
    def compute_matrix(
        self,
        species_list: Sequence["Species"],
        tiles: Sequence["MapTile"],
        turn_index: int = -1,
    ) -> np.ndarray:
        """批量计算 N物种 × M地块 的宜居度矩阵"""
        self._stats["matrix_computes"] += 1
        
        species_list = list(species_list)
        tiles = list(tiles)
        N, M = len(species_list), len(tiles)
        
        if N == 0 or M == 0:
            return np.array([])
        
        # 检查缓存
        current_codes = [sp.lineage_code for sp in species_list]
        current_tile_ids = [t.id for t in tiles]
        
        if (self._matrix_cache is not None and 
            self._cache_turn == turn_index and
            self._cache_species_codes == current_codes and
            self._cache_tile_ids == current_tile_ids):
            self._stats["cache_hits"] += 1
            return self._matrix_cache
        
        logger.info(f"[SuitabilityService] 计算 {N}×{M} 宜居度矩阵...")
        
        # 提取所有特征向量
        species_features = np.array([
            self._extract_species_features(sp) for sp in species_list
        ])  # (N, 12)
        
        tile_features = np.array([
            self._extract_tile_features(t) for t in tiles
        ])  # (M, 12)
        
        # 缓存特征向量
        for sp in species_list:
            if sp.lineage_code not in self._species_feature_cache:
                self._species_feature_cache[sp.lineage_code] = self._extract_species_features(sp)
        for t in tiles:
            if t.id not in self._tile_feature_cache:
                self._tile_feature_cache[t.id] = self._extract_tile_features(t)
        
        # 矩阵计算: (N, 1, 12) - (1, M, 12) = (N, M, 12)
        diff = species_features[:, np.newaxis, :] - tile_features[np.newaxis, :, :]
        
        # 加权距离
        weighted_sq_diff = DIMENSION_WEIGHTS * (diff ** 2)  # (N, M, 12)
        distances = np.sqrt(weighted_sq_diff.sum(axis=2))  # (N, M)
        
        # 高斯核转换
        feature_similarity = np.exp(-distances ** 2 / (2 * 0.4 ** 2))  # (N, M)
        
        tile_index_map = {t.id: idx for idx, t in enumerate(tiles) if getattr(t, 'id', None) is not None}
        if self.use_semantic and self.embeddings is not None:
            try:
                # 物种语义缓存
                missing_species = []
                species_texts = []
                for sp in species_list:
                    code = sp.lineage_code
                    if code not in self._species_semantic_cache:
                        text = self._species_text_cache.get(code)
                        if not text:
                            text = self._build_species_text(sp)
                            self._species_text_cache[code] = text
                        missing_species.append(code)
                        species_texts.append(text)
                if species_texts:
                    new_vectors = self.embeddings.embed(species_texts)
                    for code, vec in zip(missing_species, new_vectors):
                        self._species_semantic_cache[code] = np.array(vec, dtype=np.float32)
                    self._stats["semantic_calls"] += len(missing_species)
                species_semantic = np.array(
                    [self._species_semantic_cache[sp.lineage_code] for sp in species_list],
                    dtype=np.float32,
                )
                
                # 地块语义缓存（仅热点）
                hotspot_tiles = self._select_hotspot_tiles(tiles)
                missing_tiles: list[tuple[int, str]] = []
                missing_tile_texts: list[str] = []
                subset_vectors: list[np.ndarray] = []
                subset_indices: list[int] = []
                for tile in hotspot_tiles:
                    tile_id = getattr(tile, 'id', None)
                    if tile_id is None or tile_id not in tile_index_map:
                        continue
                    signature = self._compute_tile_signature(tile)
                    if tile_id not in self._tile_text_cache:
                        self._tile_text_cache[tile_id] = self._build_tile_text(tile)
                    cached_vec = self._tile_semantic_cache.get(tile_id)
                    cached_signature = self._tile_semantic_signatures.get(tile_id)
                    if cached_vec is not None and cached_signature == signature:
                        subset_vectors.append(cached_vec)
                        subset_indices.append(tile_index_map[tile_id])
                    else:
                        missing_tiles.append((tile_id, signature))
                        missing_tile_texts.append(self._tile_text_cache[tile_id])
                if missing_tile_texts:
                    new_tile_vecs = self.embeddings.embed(missing_tile_texts)
                    for (tile_id, signature), vec in zip(missing_tiles, new_tile_vecs):
                        np_vec = np.array(vec, dtype=np.float32)
                        self._cache_tile_semantic_vector(tile_id, np_vec, signature)
                        if tile_id in tile_index_map:
                            subset_vectors.append(np_vec)
                            subset_indices.append(tile_index_map[tile_id])
                    self._stats["semantic_calls"] += len(missing_tiles)
                
                if subset_vectors:
                    sp_norm = species_semantic / (np.linalg.norm(species_semantic, axis=1, keepdims=True) + 1e-8)
                    tile_subset = np.stack(subset_vectors, axis=0)
                    tile_norm = tile_subset / (np.linalg.norm(tile_subset, axis=1, keepdims=True) + 1e-8)
                    semantic_subset = sp_norm @ tile_norm.T  # (N, K)
                    fusion = feature_similarity.copy()
                    semantic_subset = (semantic_subset + 1) / 2
                    for col_pos, subset_idx in enumerate(subset_indices):
                        fusion[:, subset_idx] = (
                            self.semantic_weight * semantic_subset[:, col_pos]
                            + self.feature_weight * feature_similarity[:, subset_idx]
                        )
                    if len(subset_indices) == len(tiles):
                        suitability_matrix = fusion
                    else:
                        suitability_matrix = fusion
                else:
                    suitability_matrix = feature_similarity
                
            except Exception as e:
                logger.warning(f"[SuitabilityService] 语义矩阵计算失败: {e}")
                suitability_matrix = feature_similarity
        else:
            suitability_matrix = feature_similarity
        
        # 【新增】应用硬约束惩罚矩阵
        penalty_matrix = np.ones((N, M), dtype=np.float32)
        for i, sp in enumerate(species_list):
            for j, t in enumerate(tiles):
                penalty, _ = self._check_habitat_compatibility(sp, t)
                if penalty < 1.0:
                    penalty_matrix[i, j] = penalty
        
        suitability_matrix = suitability_matrix * penalty_matrix
        
        # 确保范围（允许极低值）
        suitability_matrix = np.clip(suitability_matrix, 0.01, 1.0)
        
        # 更新缓存
        self._matrix_cache = suitability_matrix
        self._cache_species_codes = current_codes
        self._cache_tile_ids = current_tile_ids
        self._cache_turn = turn_index
        
        logger.info(f"[SuitabilityService] 矩阵计算完成，平均宜居度: {suitability_matrix.mean():.3f}")
        
        return suitability_matrix
    
    def get_suitability_from_matrix(
        self,
        species_index: int,
        tile_index: int,
    ) -> float:
        """从缓存矩阵获取宜居度"""
        if self._matrix_cache is None:
            return 0.5
        
        if 0 <= species_index < self._matrix_cache.shape[0] and \
           0 <= tile_index < self._matrix_cache.shape[1]:
            return float(self._matrix_cache[species_index, tile_index])
        
        return 0.5
    
    def clear_cache(self):
        """清除所有缓存"""
        self._species_semantic_cache.clear()
        self._species_feature_cache.clear()
        self._tile_semantic_cache.clear()
        self._tile_semantic_signatures.clear()
        self._tile_feature_cache.clear()
        self._species_text_cache.clear()
        self._tile_text_cache.clear()
        self._matrix_cache = None
        self._cache_species_codes = []
        self._cache_tile_ids = []
        self._cache_turn = -1
        self._recent_hotspot_ids.clear()
        self._semantic_store_dirty = False
    
    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "species_cached": len(self._species_feature_cache),
            "tiles_cached": len(self._tile_feature_cache),
            "semantic_species_cached": len(self._species_semantic_cache),
            "semantic_tiles_cached": len(self._tile_semantic_cache),
            "matrix_cached": self._matrix_cache is not None,
        }


# 全局实例
_global_suitability_service: SuitabilityService | None = None


def get_suitability_service(
    embedding_service: "EmbeddingService | None" = None
) -> SuitabilityService:
    """获取全局宜居度服务实例"""
    global _global_suitability_service
    
    ui_config = _get_config_service().get_ui_config()
    hotspot_only = getattr(ui_config, "embedding_semantic_hotspot_only", False)
    hotspot_limit = getattr(ui_config, "embedding_semantic_hotspot_limit", 512)
    tile_cache_path = _TILE_CACHE_DIR / "tile_semantics.json"
    use_semantic = embedding_service is not None
    
    if _global_suitability_service is None:
        _global_suitability_service = SuitabilityService(
            embedding_service=embedding_service,
            use_semantic=use_semantic,
            semantic_hotspot_only=hotspot_only,
            semantic_hotspot_limit=hotspot_limit,
            tile_cache_path=tile_cache_path,
        )
    else:
        _global_suitability_service.update_semantic_settings(
            use_semantic=use_semantic,
            semantic_hotspot_only=hotspot_only,
            semantic_hotspot_limit=hotspot_limit,
            embedding_service=embedding_service,
        )
    
    return _global_suitability_service

