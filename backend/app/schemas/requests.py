from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, Field


PressureType = Literal[
    # ========== 气候相关 ==========
    "glacial_period",           # 冰河时期：全球降温，冰川扩张
    "greenhouse_earth",         # 温室地球：全球升温，极端高温
    "pluvial_period",          # 洪积期：降水增加，洪水频发
    "drought_period",          # 干旱期：持续缺水
    "monsoon_shift",           # 季风变动：降水模式改变
    "fog_period",              # 浓雾时期：光照减少，湿度增加
    "extreme_weather",         # 极端天气：风暴/飓风频发
    
    # ========== 地质相关 ==========
    "volcanic_eruption",       # 火山喷发期：火山灰、有毒气体、火山冬天
    "orogeny",                 # 造山期：山脉隆起，地形变化
    "subsidence",              # 陆架沉降：低地淹没
    "land_degradation",        # 土地退化：土壤贫瘠化
    "ocean_current_shift",     # 洋流变迁：温度/营养盐分布改变
    "sea_level_rise",          # 海平面上升：沿海栖息地淹没
    "sea_level_fall",          # 海平面下降：大陆架暴露
    "earthquake_period",       # 地震活跃期：地形破碎，栖息地分割
    
    # ========== 生态相关 ==========
    "resource_abundance",      # 资源繁盛期：食物充足，竞争降低
    "productivity_decline",    # 生产力衰退：初级生产力下降
    "predator_rise",          # 捕食者兴起：顶级捕食者数量激增
    "species_invasion",       # 物种入侵：外来竞争者入侵
    "disease_outbreak",        # 疾病爆发：传染病流行
    "wildfire_period",         # 野火肆虐期：火灾频发
    "algal_bloom",             # 藻华爆发：水体富营养化
    
    # ========== 化学/大气相关 ==========
    "ocean_acidification",    # 海洋酸化：碳酸钙壳体溶解
    "oxygen_increase",        # 氧气增多：有利于需氧生物
    "anoxic_event",           # 缺氧事件：大规模窒息
    "sulfide_event",          # 硫化事件：硫化氢毒害
    "uv_radiation_increase",  # 紫外辐射增强：臭氧层变薄
    "salinity_change",        # 盐度变化：淡咸水变化
    "methane_release",        # 甲烷释放：温室效应+缺氧
]


class PressureConfig(BaseModel):
    kind: PressureType
    intensity: int = Field(ge=1, le=10)
    target_region: tuple[int, int] | None = None  # (x, y) grid coordinate for local events
    radius: int | None = Field(default=None, ge=1)
    label: str | None = None  # Display label for the UI and logs
    narrative_note: str | None = None


class TurnCommand(BaseModel):
    rounds: int = Field(gt=0, le=100)
    pressures: Sequence[PressureConfig] = Field(default_factory=list)
    auto_reports: bool = True


class SpeciesEditRequest(BaseModel):
    lineage_code: str
    description: str | None = None
    trait_overrides: dict[str, float] | None = None
    abstract_overrides: dict[str, float] | None = None  # 修复：与Species模型一致，使用float
    open_new_lineage: bool = False


class WatchlistRequest(BaseModel):
    lineage_codes: list[str]


class QueueRequest(BaseModel):
    pressures: list[PressureConfig] = Field(default_factory=list)
    rounds: int = Field(ge=1, le=20, default=1)


class CreateSaveRequest(BaseModel):
    save_name: str = Field(min_length=1, max_length=50)
    scenario: str = Field(default="原初大陆")
    species_prompts: list[str] | None = None  # 用于空白剧本的物种描述
    map_seed: int | None = None  # 可选的地图种子


class SaveGameRequest(BaseModel):
    save_name: str


class LoadGameRequest(BaseModel):
    save_name: str


class GenerateSpeciesRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    lineage_code: str = Field(default="A1")


class NicheCompareRequest(BaseModel):
    species_a: str = Field(description="第一个物种的lineage_code")
    species_b: str = Field(description="第二个物种的lineage_code")


# ========== 玩家干预系统请求 ==========

class ProtectSpeciesRequest(BaseModel):
    """保护物种请求"""
    lineage_code: str = Field(description="要保护的物种代码")
    turns: int = Field(ge=1, le=50, default=10, description="保护回合数")


class SuppressSpeciesRequest(BaseModel):
    """压制物种请求"""
    lineage_code: str = Field(description="要压制的物种代码")
    turns: int = Field(ge=1, le=50, default=10, description="压制回合数")


class IntroduceSpeciesRequest(BaseModel):
    """引入新物种请求"""
    prompt: str = Field(min_length=1, max_length=500, description="物种描述")
    target_region: tuple[int, int] | None = Field(default=None, description="目标区域坐标(x,y)")
    initial_population: int = Field(ge=100, le=10_000_000, default=100_000, description="初始种群数量")


class SetSymbiosisRequest(BaseModel):
    """设置共生关系请求"""
    species_code: str = Field(description="要设置的物种代码")
    depends_on: list[str] = Field(default_factory=list, description="依赖的物种代码列表")
    strength: float = Field(ge=0.0, le=1.0, default=0.5, description="依赖强度")
    symbiosis_type: Literal["mutualism", "commensalism", "parasitism", "none"] = Field(
        default="mutualism", description="共生类型"
    )
