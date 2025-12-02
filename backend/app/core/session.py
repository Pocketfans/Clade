"""
模拟会话管理器 - 运行时状态管理

此模块负责管理模拟运行时的状态：
- simulation_running: 模拟是否正在运行
- current_save_name: 当前存档名称
- autosave_counter: 自动保存计数器
- pressure_queue: 压力队列
- simulation_events: 事件队列（用于 SSE 推送）
- backend_session_id: 后端会话 ID

架构：
- 会话在 app lifespan 中实例化并存储到 app.state
- 路由通过 Depends(get_session) 从 api.dependencies 访问
- 使用进程内 Queue/RLock 进行状态同步

约束：
- 仅支持单 Worker：状态是进程本地的，不会持久化
- 多 Worker 部署需要外部状态存储（Redis、数据库）
- 进程重启后会话状态丢失

使用方式（通过依赖注入）：
    from fastapi import Depends
    from app.api.dependencies import get_session
    
    @router.get("/status")
    def get_status(session: SimulationSessionManager = Depends(get_session)):
        return {"running": session.is_running}
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from queue import Queue
from threading import RLock
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from ..schemas.requests import PressureConfig

logger = logging.getLogger(__name__)


class SimulationSessionManager:
    """模拟会话管理器
    
    集中管理模拟运行时的状态，提供线程安全的状态访问和修改。
    
    集中管理模拟运行时的全局状态，提供线程安全的状态访问和修改。
    
    Attributes:
        _running: 模拟是否正在运行
        _current_save_name: 当前存档名称
        _autosave_counter: 自动保存回合计数
        _pressure_queue: 压力配置队列
        _events: 事件队列（用于 SSE）
        _session_id: 后端会话 ID
        _lock: 状态锁
    """
    
    def __init__(self) -> None:
        self._running: bool = False
        self._current_save_name: str | None = None
        self._autosave_counter: int = 0
        self._pressure_queue: list[list[Any]] = []
        self._events: Queue = Queue()
        self._session_id: str = ""
        self._lock = RLock()
        
        # AI 任务状态
        self._abort_requested: bool = False
        self._skip_ai_step: bool = False
        self._current_ai_step: str = ""
    
    # ========== 会话 ID ==========
    
    @property
    def session_id(self) -> str:
        """获取后端会话 ID"""
        return self._session_id
    
    def generate_session_id(self) -> str:
        """生成新的会话 ID（启动时调用）"""
        self._session_id = str(uuid.uuid4())
        logger.info(f"[会话] 生成会话ID: {self._session_id[:8]}...")
        return self._session_id
    
    # ========== 模拟运行状态 ==========
    
    @property
    def is_running(self) -> bool:
        """模拟是否正在运行"""
        with self._lock:
            return self._running
    
    def set_running(self, running: bool) -> None:
        """设置模拟运行状态"""
        with self._lock:
            self._running = running
            if running:
                logger.info("[会话] 模拟开始运行")
            else:
                logger.info("[会话] 模拟停止运行")
    
    @contextmanager
    def simulation_lock(self) -> Generator[None, None, None]:
        """模拟锁上下文管理器
        
        用于确保模拟互斥执行。
        
        Raises:
            RuntimeError: 如果模拟已在运行
        """
        with self._lock:
            if self._running:
                raise RuntimeError("模拟已在运行中")
            self._running = True
        
        try:
            yield
        finally:
            with self._lock:
                self._running = False
    
    # ========== 存档状态 ==========
    
    @property
    def current_save_name(self) -> str | None:
        """当前存档名称"""
        with self._lock:
            return self._current_save_name
    
    def set_save_name(self, name: str | None) -> None:
        """设置当前存档名称"""
        with self._lock:
            self._current_save_name = name
            if name:
                logger.info(f"[会话] 当前存档: {name}")
    
    @property
    def autosave_counter(self) -> int:
        """自动保存计数器"""
        with self._lock:
            return self._autosave_counter
    
    def increment_autosave_counter(self) -> int:
        """递增自动保存计数器并返回新值"""
        with self._lock:
            self._autosave_counter += 1
            return self._autosave_counter
    
    def reset_autosave_counter(self) -> None:
        """重置自动保存计数器"""
        with self._lock:
            self._autosave_counter = 0
    
    # ========== 压力队列 ==========
    
    @property
    def pressure_queue(self) -> list[list[Any]]:
        """获取压力队列（返回副本）"""
        with self._lock:
            return list(self._pressure_queue)
    
    def add_pressure(self, pressures: list[Any]) -> None:
        """添加压力配置到队列"""
        with self._lock:
            self._pressure_queue.append(pressures)
    
    def pop_pressure(self) -> list[Any] | None:
        """弹出队列头部的压力配置"""
        with self._lock:
            if self._pressure_queue:
                return self._pressure_queue.pop(0)
            return None
    
    def clear_pressure_queue(self) -> None:
        """清空压力队列"""
        with self._lock:
            self._pressure_queue.clear()
    
    def get_queue_preview(self, max_items: int = 3) -> list[str]:
        """获取队列预览"""
        with self._lock:
            preview = []
            for i, pressures in enumerate(self._pressure_queue[:max_items]):
                if pressures:
                    labels = [p.kind if hasattr(p, 'kind') else str(p) for p in pressures]
                    preview.append(f"回合 {i+1}: {', '.join(labels)}")
            return preview
    
    # ========== 事件队列 ==========
    
    @property
    def events(self) -> Queue:
        """获取事件队列"""
        return self._events
    
    def push_event(
        self, 
        event_type: str, 
        message: str, 
        category: str = "其他",
        force: bool = False,
        **extra
    ) -> None:
        """推送演化事件
        
        Args:
            event_type: 事件类型 (info/warn/error/success/speciation/extinction等)
            message: 事件消息
            category: 事件分类
            force: 是否强制推送（绕过队列满检查）
            **extra: 额外数据
        """
        import time
        
        # 防止队列无限膨胀
        if not force and self._events.qsize() > 1000:
            return
        
        event = {
            "type": event_type,
            "message": message,
            "category": category,
            "timestamp": time.time(),
            **extra
        }
        
        self._events.put(event)
    
    def get_pending_events(self, max_count: int = 100) -> list[dict]:
        """获取待处理的事件（非阻塞）"""
        events = []
        while not self._events.empty() and len(events) < max_count:
            try:
                events.append(self._events.get_nowait())
            except:
                break
        return events
    
    # ========== AI 任务状态 ==========
    
    @property
    def abort_requested(self) -> bool:
        """是否请求中止"""
        with self._lock:
            return self._abort_requested
    
    def request_abort(self) -> None:
        """请求中止当前任务"""
        with self._lock:
            self._abort_requested = True
            logger.info("[会话] 请求中止当前任务")
    
    def clear_abort(self) -> None:
        """清除中止请求"""
        with self._lock:
            self._abort_requested = False
    
    @property
    def skip_ai_step(self) -> bool:
        """是否跳过当前 AI 步骤"""
        with self._lock:
            return self._skip_ai_step
    
    def request_skip_ai(self) -> None:
        """请求跳过当前 AI 步骤"""
        with self._lock:
            self._skip_ai_step = True
    
    def clear_skip_ai(self) -> None:
        """清除跳过请求"""
        with self._lock:
            self._skip_ai_step = False
    
    @property
    def current_ai_step(self) -> str:
        """当前 AI 步骤名称"""
        with self._lock:
            return self._current_ai_step
    
    def set_ai_step(self, step: str) -> None:
        """设置当前 AI 步骤"""
        with self._lock:
            self._current_ai_step = step
    
    # ========== 状态重置 ==========
    
    def reset_for_new_game(self) -> None:
        """为新游戏重置状态"""
        with self._lock:
            self._current_save_name = None
            self._autosave_counter = 0
            self._pressure_queue.clear()
            self._abort_requested = False
            self._skip_ai_step = False
            self._current_ai_step = ""
            
            # 清空事件队列
            while not self._events.empty():
                try:
                    self._events.get_nowait()
                except:
                    break
            
            logger.info("[会话] 状态已重置")
    
    def get_state_snapshot(self) -> dict:
        """获取状态快照（用于调试）"""
        with self._lock:
            return {
                "session_id": self._session_id[:8] + "..." if self._session_id else "",
                "running": self._running,
                "current_save": self._current_save_name,
                "autosave_counter": self._autosave_counter,
                "queue_size": len(self._pressure_queue),
                "events_pending": self._events.qsize(),
                "abort_requested": self._abort_requested,
                "skip_ai_step": self._skip_ai_step,
                "current_ai_step": self._current_ai_step,
            }
    
    # ========== 只读查询接口 ==========
    
    def get_queue_status(self) -> dict:
        """获取队列状态（只读）"""
        with self._lock:
            return {
                "queued_rounds": len(self._pressure_queue),
                "running": self._running,
                "preview": self.get_queue_preview(),
            }
    
    def get_events_count(self) -> int:
        """获取待处理事件数量（只读）"""
        return self._events.qsize()
    
    def peek_events(self, max_count: int = 10) -> list[dict]:
        """查看事件但不移除（只读）
        
        注意：由于 Queue 不支持 peek，这里返回的是近似值
        """
        # Queue 不支持 peek，返回空列表
        # 实际实现中可以考虑使用 deque 替代
        return []
    
    def can_start_simulation(self) -> tuple[bool, str]:
        """检查是否可以开始模拟
        
        Returns:
            (can_start, reason) 元组
        """
        with self._lock:
            if self._running:
                return False, "模拟已在运行中"
            return True, ""
    
    def can_modify_save(self) -> tuple[bool, str]:
        """检查是否可以修改存档（加载/创建/删除）
        
        Returns:
            (can_modify, reason) 元组
        """
        with self._lock:
            if self._running:
                return False, "模拟正在运行，无法修改存档"
            return True, ""


# ========== DEPRECATED: Global Instance ==========
# These functions are DEPRECATED and will be removed in a future version.
# Use app.state.session via Depends() for all new code.

import warnings

_session_manager: SimulationSessionManager | None = None
_global_access_warned: bool = False


def get_session_manager() -> SimulationSessionManager:
    """获取全局会话管理器实例
    
    .. deprecated::
        请使用 ``Depends(get_session)`` 从 ``request.app.state.session`` 获取。
        全局单例会在多 Worker 部署时导致状态隔离问题。
        
    Warning:
        调用此函数会记录废弃警告。当所有代码路径迁移到
        基于 lifespan 的注入后，此函数将被移除。
    """
    global _session_manager, _global_access_warned
    
    if not _global_access_warned:
        warnings.warn(
            "get_session_manager() 已废弃。请使用 api.dependencies 中的 Depends(get_session)，"
            "它会访问 app.state.session。此全局单例将被移除。",
            DeprecationWarning,
            stacklevel=2
        )
        logger.warning(
            "[已废弃] get_session_manager() 被调用。请迁移到 api.dependencies 中的 "
            "Depends(get_session) 以获得正确的生命周期管理。"
        )
        _global_access_warned = True
    
    if _session_manager is None:
        _session_manager = SimulationSessionManager()
    return _session_manager


def reset_session_manager() -> None:
    """重置会话管理器（仅用于测试）
    
    .. deprecated::
        请直接创建新的 SimulationSessionManager 实例。
    """
    global _session_manager, _global_access_warned
    _session_manager = None
    _global_access_warned = False

