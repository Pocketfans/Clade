from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from collections import Counter

from ..schemas.requests import PressureConfig
from ..schemas.responses import MajorPressureEvent


@dataclass(slots=True)
class PressureRecord:
    turn_index: int
    intensity: int
    kinds: list[str]


class PressureEscalationService:
    """基于规则的压力累积与升级系统。
    
    跟踪滑动窗口内的压力历史，当累计强度超过阈值时触发重大事件。
    """

    def __init__(
        self,
        window: int,
        threshold: int,
        cooldown: int,
    ) -> None:
        self.window = max(1, window)
        self.threshold = max(1, threshold)
        self.cooldown_default = max(0, cooldown)
        self.history: list[PressureRecord] = []
        self.cooldown = 0

    def register(self, pressures: Sequence[PressureConfig], turn_index: int) -> list[MajorPressureEvent]:
        """注册当前回合的压力并检查是否触发重大事件。"""
        total_intensity = sum(p.intensity for p in pressures)
        kinds = [p.kind for p in pressures]
        self.history.append(
            PressureRecord(turn_index=turn_index, intensity=total_intensity, kinds=kinds)
        )
        self.history = self.history[-self.window :]
        events: list[MajorPressureEvent] = []
        
        # 冷却期检查
        if self.cooldown > 0:
            self.cooldown -= 1
            return events
        
        # 累计压力检查
        cumulative = sum(record.intensity for record in self.history)
        if cumulative >= self.threshold:
            # 分析压力类型
            description, severity = self._analyze_pressure_pattern(self.history)
            
            events.append(
                MajorPressureEvent(
                    severity=severity,
                    description=description,
                    affected_tiles=[],  # 全局事件
                )
            )
            self.cooldown = self.cooldown_default
            self.history.clear()
        
        return events
    
    def _analyze_pressure_pattern(self, history: list[PressureRecord]) -> tuple[str, str]:
        """分析压力历史模式，生成描述和严重度。"""
        # 统计压力类型
        all_kinds: list[str] = []
        for record in history:
            all_kinds.extend(record.kinds)
        kind_counts = Counter(all_kinds)
        
        # 计算平均强度
        avg_intensity = sum(r.intensity for r in history) / len(history) if history else 0
        
        # 确定严重度
        if avg_intensity >= 8:
            severity = "extreme"
        elif avg_intensity >= 6:
            severity = "high"
        elif avg_intensity >= 4:
            severity = "medium"
        else:
            severity = "low"
        
        # 生成描述
        if not kind_counts:
            return "累计压力触发环境剧变", severity
        
        dominant_kind = kind_counts.most_common(1)[0][0]
        count = kind_counts[dominant_kind]
        
        # 根据主导压力类型生成描述
        kind_descriptions = {
            "temperature": "极端温度波动引发大规模气候异常",
            "humidity": "湿度剧变导致水循环失衡",
            "drought": "持续干旱引发大陆级缺水危机",
            "flood": "频繁洪水泛滥，低地栖息地大面积淹没",
            "volcano": "火山活动频发，火山灰遮蔽阳光",
            "predator": "顶级捕食者爆发，食物链严重失衡",
            "competitor": "物种间竞争白热化，资源枯竭",
        }
        
        base_desc = kind_descriptions.get(dominant_kind, "环境压力持续累积")
        
        if len(kind_counts) > 3:
            description = f"{base_desc}，叠加多重压力形成连锁灾难"
        elif count >= self.window * 0.6:
            description = f"连续{count}次{base_desc}，生态系统濒临崩溃"
        else:
            description = f"{base_desc}，多种压力交织引发生态危机"
        
        return description, severity
