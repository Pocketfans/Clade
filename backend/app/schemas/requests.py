from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, Field


PressureType = Literal[
    # 气候相关
    "glacial_period",           # 冰河时期
    "greenhouse_earth",         # 温室地球
    "pluvial_period",          # 洪积期
    "drought_period",          # 干旱期
    "monsoon_shift",           # 季风变动
    "fog_period",              # 浓雾时期
    # 地质相关
    "volcanic_eruption",       # 火山喷发期
    "orogeny",                 # 造山期
    "subsidence",              # 陆架沉降
    "land_degradation",        # 土地退化
    "ocean_current_shift",     # 洋流变迁
    # 生态相关
    "resource_abundance",      # 资源繁盛期
    "productivity_decline",    # 生产力衰退
    "predator_rise",          # 捕食者兴起
    "species_invasion",       # 物种入侵
    # 化学相关
    "ocean_acidification",    # 海洋酸化
    "oxygen_increase",        # 氧气增多
    "anoxic_event",          # 缺氧事件
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
