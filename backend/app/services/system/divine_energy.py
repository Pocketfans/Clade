"""神力能量点系统

管理玩家的"神力"资源，用于各种干预操作。

能量机制：
- 每回合开始自动回复一定能量
- 不同操作消耗不同能量
- 能量有上限，不会无限积累

消耗规则：
- 环境压力：强度 × 基础消耗
- 创建物种：固定高消耗
- 杂交：中等消耗
- 保护/压制：低消耗
- 推进回合：免费
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)


@dataclass
class EnergyCost:
    """能量消耗定义"""
    base_cost: int
    name: str
    description: str
    icon: str
    # 可变消耗的系数（如压力强度）
    multiplier_field: str | None = None


# 操作能量消耗定义
ENERGY_COSTS: dict[str, EnergyCost] = {
    # 环境压力（基础消耗 × 强度）
    "pressure": EnergyCost(
        base_cost=3,
        name="环境压力",
        description="释放环境压力，强度越高消耗越多",
        icon="⚡",
        multiplier_field="intensity",
    ),
    # 创建物种（高消耗）
    "create_species": EnergyCost(
        base_cost=50,
        name="创造物种",
        description="以神力创造全新生命",
        icon="✨",
    ),
    # 杂交（中等消耗）
    "hybridize": EnergyCost(
        base_cost=30,
        name="诱导杂交",
        description="引导两个物种进行杂交",
        icon="🧬",
    ),
    # 保护物种（低消耗）
    "protect": EnergyCost(
        base_cost=15,
        name="神庇护",
        description="保护物种免受伤害",
        icon="🛡️",
    ),
    # 压制物种（低消耗）
    "suppress": EnergyCost(
        base_cost=15,
        name="神罚",
        description="削弱目标物种",
        icon="⚔️",
    ),
    # 引入物种（中等消耗）
    "introduce": EnergyCost(
        base_cost=35,
        name="物种引入",
        description="将AI生成的物种引入生态系统",
        icon="🌱",
    ),
    # 设置共生（低消耗）
    "symbiosis": EnergyCost(
        base_cost=10,
        name="共生契约",
        description="建立物种间的共生关系",
        icon="🤝",
    ),
    # 强行杂交/嵌合体（高消耗）
    "forced_hybridize": EnergyCost(
        base_cost=50,
        name="强行杂交",
        description="强行融合两个物种创造嵌合体",
        icon="🧬",
    ),
}


@dataclass
class EnergyState:
    """能量状态"""
    current: int = 100
    maximum: int = 100
    regen_per_turn: int = 15
    
    # 历史记录
    total_spent: int = 0
    total_regenerated: int = 0
    
    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "maximum": self.maximum,
            "regen_per_turn": self.regen_per_turn,
            "total_spent": self.total_spent,
            "total_regenerated": self.total_regenerated,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EnergyState":
        return cls(
            current=data.get("current", 100),
            maximum=data.get("maximum", 100),
            regen_per_turn=data.get("regen_per_turn", 15),
            total_spent=data.get("total_spent", 0),
            total_regenerated=data.get("total_regenerated", 0),
        )


@dataclass
class EnergyTransaction:
    """能量交易记录"""
    action: str
    cost: int
    turn: int
    details: str = ""
    success: bool = True


class DivineEnergyService:
    """神力能量服务
    
    管理玩家的能量点资源。
    
    【重要】能量状态完全由存档系统管理，不再使用全局文件持久化。
    - 服务启动时使用默认状态
    - 存档加载时由 SaveManager 恢复状态
    - 存档保存时由 SaveManager 导出状态
    """
    
    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self._state = EnergyState()
        self._history: list[EnergyTransaction] = []
        self._enabled = True  # 可以禁用能量系统（测试模式）
        
        # 【移除】不再从全局文件加载状态，等待存档系统恢复
        logger.info(f"[能量] 服务初始化，使用默认状态: {self._state.current}/{self._state.maximum}")
    
    @property
    def enabled(self) -> bool:
        """能量系统是否启用"""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        # 【移除】不再自动保存到全局文件
    
    def get_state(self) -> EnergyState:
        """获取当前能量状态"""
        return self._state
    
    def get_cost(self, action: str, **kwargs) -> int:
        """计算操作的能量消耗
        
        Args:
            action: 操作类型
            **kwargs: 额外参数（如intensity用于压力）
        
        Returns:
            能量消耗值
        """
        if action not in ENERGY_COSTS:
            return 0
        
        cost_def = ENERGY_COSTS[action]
        base = cost_def.base_cost
        
        # 应用乘数
        if cost_def.multiplier_field and cost_def.multiplier_field in kwargs:
            multiplier = kwargs[cost_def.multiplier_field]
            return int(base * multiplier)
        
        return base
    
    def get_pressure_cost(self, pressures: list[dict]) -> int:
        """计算压力组合的总消耗
        
        Args:
            pressures: 压力列表，每个包含 kind 和 intensity
        
        Returns:
            总能量消耗
        """
        # 零消耗的压力类型（自然演化）
        FREE_PRESSURE_KINDS = {"natural_evolution"}
        
        total = 0
        for p in pressures:
            kind = p.get("kind", "")
            # 自然演化不消耗能量
            if kind in FREE_PRESSURE_KINDS:
                continue
            intensity = p.get("intensity", 5)
            total += self.get_cost("pressure", intensity=intensity)
        return total
    
    def can_afford(self, action: str, **kwargs) -> tuple[bool, int]:
        """检查是否有足够能量
        
        Returns:
            (是否足够, 需要消耗的能量)
        """
        if not self._enabled:
            return True, 0
        
        cost = self.get_cost(action, **kwargs)
        return self._state.current >= cost, cost
    
    def spend(self, action: str, turn: int, details: str = "", **kwargs) -> tuple[bool, str]:
        """消耗能量
        
        Args:
            action: 操作类型
            turn: 当前回合
            details: 操作详情
            **kwargs: 额外参数
        
        Returns:
            (是否成功, 消息)
        """
        if not self._enabled:
            return True, "能量系统已禁用"
        
        cost = self.get_cost(action, **kwargs)
        
        if self._state.current < cost:
            # 记录失败
            self._history.append(EnergyTransaction(
                action=action,
                cost=cost,
                turn=turn,
                details=f"能量不足: {details}",
                success=False,
            ))
            # 【移除】不再自动保存到全局文件
            
            return False, f"能量不足！需要 {cost}，当前 {self._state.current}"
        
        # 扣除能量
        self._state.current -= cost
        self._state.total_spent += cost
        
        # 记录交易
        self._history.append(EnergyTransaction(
            action=action,
            cost=cost,
            turn=turn,
            details=details,
            success=True,
        ))
        
        # 【移除】不再自动保存到全局文件
        
        action_name = ENERGY_COSTS.get(action, EnergyCost(0, action, "", "")).name
        logger.info(f"[能量] 消耗 {cost} ({action_name}): {self._state.current}/{self._state.maximum}")
        
        return True, f"消耗 {cost} 能量"
    
    def regenerate(self, turn: int) -> int:
        """回合开始时回复能量
        
        Returns:
            实际回复的能量
        """
        if not self._enabled:
            return 0
        
        old_value = self._state.current
        regen = self._state.regen_per_turn
        
        self._state.current = min(self._state.maximum, self._state.current + regen)
        actual_regen = self._state.current - old_value
        self._state.total_regenerated += actual_regen
        
        if actual_regen > 0:
            self._history.append(EnergyTransaction(
                action="regenerate",
                cost=-actual_regen,  # 负数表示获得
                turn=turn,
                details=f"回合开始恢复",
                success=True,
            ))
            # 【移除】不再自动保存到全局文件
            logger.info(f"[能量] 回复 {actual_regen}: {self._state.current}/{self._state.maximum}")
        
        return actual_regen
    
    def set_energy(self, current: int | None = None, maximum: int | None = None, regen: int | None = None) -> None:
        """设置能量参数（GM模式或存档恢复）"""
        if current is not None:
            self._state.current = max(0, min(current, self._state.maximum if maximum is None else maximum))
        if maximum is not None:
            self._state.maximum = max(1, maximum)
            self._state.current = min(self._state.current, self._state.maximum)
        if regen is not None:
            self._state.regen_per_turn = max(0, regen)
        # 【移除】不再自动保存到全局文件
    
    def spend_fixed(self, amount: int, turn: int, details: str = "") -> tuple[bool, str]:
        """直接消耗指定数量的能量
        
        Args:
            amount: 消耗数量
            turn: 当前回合
            details: 操作详情
        
        Returns:
            (是否成功, 消息)
        """
        if not self._enabled:
            return True, "能量系统已禁用"
        
        if self._state.current < amount:
            return False, f"能量不足！需要 {amount}，当前 {self._state.current}"
        
        self._state.current -= amount
        self._state.total_spent += amount
        
        self._history.append(EnergyTransaction(
            action="divine_action",
            cost=amount,
            turn=turn,
            details=details,
            success=True,
        ))
        
        logger.info(f"[能量] 消耗 {amount} ({details}), 剩余: {self._state.current}")
        return True, f"消耗 {amount} 能量"
    
    def add_energy(self, amount: int, reason: str = "") -> None:
        """添加能量（奖励等）"""
        old_value = self._state.current
        self._state.current = min(self._state.maximum, self._state.current + amount)
        actual = self._state.current - old_value
        
        if actual > 0:
            self._history.append(EnergyTransaction(
                action="bonus",
                cost=-actual,
                turn=0,
                details=reason,
                success=True,
            ))
            # 【移除】不再自动保存到全局文件
    
    def reset(self) -> None:
        """重置能量状态（新存档时调用）"""
        self._state = EnergyState()
        self._history.clear()
        
        # 【移除】不再操作全局文件，状态完全由内存管理
        
        logger.info("[能量] 状态已重置")
    
    def get_history(self, limit: int = 20) -> list[dict]:
        """获取历史记录"""
        return [
            {
                "action": h.action,
                "action_name": ENERGY_COSTS.get(h.action, EnergyCost(0, h.action, "", "")).name or h.action,
                "cost": h.cost,
                "turn": h.turn,
                "details": h.details,
                "success": h.success,
            }
            for h in self._history[-limit:]
        ]
    
    def get_all_costs(self) -> list[dict]:
        """获取所有操作的消耗定义"""
        return [
            {
                "action": action,
                "name": cost.name,
                "description": cost.description,
                "icon": cost.icon,
                "base_cost": cost.base_cost,
                "has_multiplier": cost.multiplier_field is not None,
            }
            for action, cost in ENERGY_COSTS.items()
        ]
    
    def get_status(self) -> dict:
        """获取完整状态"""
        return {
            "enabled": self._enabled,
            "current": self._state.current,
            "maximum": self._state.maximum,
            "regen_per_turn": self._state.regen_per_turn,
            "total_spent": self._state.total_spent,
            "total_regenerated": self._state.total_regenerated,
            "percentage": round(self._state.current / self._state.maximum * 100, 1),
        }


# 模块级单例
energy_service = DivineEnergyService()
