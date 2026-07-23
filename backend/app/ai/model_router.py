from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, AsyncGenerator, AsyncIterator, Callable
from urllib.parse import quote, urlencode

from ..security import (
    AI_JSON_MAX_BYTES,
    DeadlineBudget,
    DeadlineExpired,
    RETRYABLE_OUTBOUND_CODES,
    STREAM_EVENT_MAX_BYTES,
    STREAM_MAX_BYTES,
    OutboundRequestError,
    SafeRuntimeClient,
)
from ..security.deadline import StreamBudget

logger = logging.getLogger(__name__)

# 服务商类型定义
PROVIDER_TYPE_OPENAI = "openai"      # OpenAI 兼容格式
PROVIDER_TYPE_ANTHROPIC = "anthropic"  # Claude 原生 API
PROVIDER_TYPE_GOOGLE = "google"       # Gemini 原生 API

# 负载均衡策略
LB_ROUND_ROBIN = "round_robin"       # 轮询
LB_RANDOM = "random"                 # 随机
LB_LEAST_LATENCY = "least_latency"   # 最低延迟

_STREAM_RESPONSE_ERROR = "AI stream response error"
_PRIMARY_RESPONSE_ERROR = "AI response error"
_PUBLIC_OUTBOUND_TIMEOUT = "The upstream request timed out"


def _ensure_deadline(
    supplied: DeadlineBudget | None,
    *,
    timeout: float,
    started_at: float,
) -> DeadlineBudget:
    if supplied is not None:
        return supplied
    try:
        return DeadlineBudget.from_timeout(timeout, started_at=started_at)
    except ValueError:
        raise OutboundRequestError(
            "outbound_url_invalid", 400, "外部服务地址无效"
        ) from None


def _budget_phase_timeout(budget: DeadlineBudget | StreamBudget) -> float:
    try:
        return budget.phase_timeout()
    except DeadlineExpired:
        raise OutboundRequestError(
            "outbound_timeout", 504, _PUBLIC_OUTBOUND_TIMEOUT
        ) from None


def _ensure_stream_budget(
    supplied: StreamBudget | None,
    *,
    idle_timeout: float,
    started_at: float,
) -> StreamBudget:
    if supplied is not None:
        return supplied
    try:
        return StreamBudget.from_timeouts(
            idle_timeout,
            hard_timeout=600.0,
            started_at=started_at,
        )
    except ValueError:
        raise OutboundRequestError(
            "outbound_url_invalid", 400, "外部服务地址无效"
        ) from None


class _PrimaryResponseError(Exception):
    pass


@dataclass
class ProviderPoolConfig:
    """服务商池配置（用于负载均衡）"""
    provider_id: str
    base_url: str
    api_key: str
    provider_type: str = PROVIDER_TYPE_OPENAI
    model: str | None = None  # 该服务商使用的模型（可覆盖默认）
    weight: int = 1  # 权重（用于加权轮询）


@dataclass(frozen=True)
class _RuntimeCredentialSnapshot:
    base_url: str | None
    api_key: str | None
    provider_type: str | None


@dataclass
class ModelConfig:
    provider: str
    model: str
    endpoint: str | None = None
    extra_body: dict[str, Any] | None = None
    provider_type: str = PROVIDER_TYPE_OPENAI  # 新增：服务商类型


@dataclass
class _AsyncRequestLifecycle:
    router: "ModelRouter"
    capability: str
    started_at: float
    request_id: int = field(init=False)
    queued: bool = field(init=False, default=True)
    active: bool = field(init=False, default=False)
    acquired_semaphore: asyncio.Semaphore | None = field(
        init=False, default=None
    )
    stats_finished: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.request_id = self.router._begin_request_stats(self.capability)
        self.router._queued_requests += 1

    async def acquire(self, budget: DeadlineBudget | StreamBudget) -> None:
        self.acquired_semaphore = await self.router._acquire_with_budget(budget)
        if self.queued:
            self.router._queued_requests -= 1
            self.queued = False
        self.router._active_requests += 1
        self.active = True

    @asynccontextmanager
    async def slot(
        self, budget: DeadlineBudget | StreamBudget
    ) -> AsyncIterator[None]:
        await self.acquire(budget)
        try:
            yield
        finally:
            self.release_attempt()

    def release_attempt(self) -> None:
        if self.active:
            self.router._active_requests -= 1
            self.active = False
        if self.acquired_semaphore is not None:
            self.acquired_semaphore.release()
            self.acquired_semaphore = None

    def queue_for_retry(self) -> None:
        if not self.queued:
            self.router._queued_requests += 1
            self.queued = True

    def finish(self, outcome: str) -> None:
        self.stats_finished = self.router._finish_request_stats(
            self.capability,
            outcome,
            time.monotonic() - self.started_at,
            finished=self.stats_finished,
        )

    def close(self) -> None:
        self.release_attempt()
        if self.queued:
            self.router._queued_requests -= 1
            self.queued = False


class ModelRouter:
    """Keeps routing between providers/models configurable per capability."""

    def __init__(
        self,
        defaults: dict[str, ModelConfig] | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 60,
        concurrency_limit: int = 50,
        max_retries: int = 2,
        use_keepalive: bool = False,  # 是否启用连接复用（高效并发模式）
        runtime_client: SafeRuntimeClient | None = None,
        allow_local_ai_endpoints: bool = False,
    ) -> None:
        self.routes = defaults or {}
        self.prompts: dict[str, str] = {}
        self._runtime_credential_snapshot = _RuntimeCredentialSnapshot(
            base_url=base_url.rstrip("/") if base_url else None,
            api_key=api_key,
            provider_type=None,
        )
        self.timeout = timeout
        self.overrides: dict[str, dict[str, Any]] = {}
        self.max_retries = max(1, max_retries)
        self.use_keepalive = use_keepalive  # 连接复用开关
        self._runtime_client = runtime_client or SafeRuntimeClient()
        self.allow_local_ai_endpoints = allow_local_ai_endpoints
        
        # 并发控制
        self.concurrency_limit = concurrency_limit
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        # 【诊断日志】并发追踪
        self._active_requests = 0  # 当前活跃请求数
        self._queued_requests = 0  # 当前排队请求数
        self._total_requests = 0   # 总请求数
        self._total_timeouts = 0   # 总超时数
        self._total_cancellations = 0
        self._request_stats: dict[str, dict] = {}  # 每个 capability 的统计
        self._last_summary_time = 0  # 上次输出摘要的时间
        self._summary_interval = 10  # 摘要输出间隔（秒）
        
        # 【负载均衡】服务商池配置
        self._provider_pools: dict[str, list[ProviderPoolConfig]] = {}  # capability -> 服务商池
        self._lb_counters: dict[str, int] = {}  # 轮询计数器
        self._lb_strategy: str = LB_ROUND_ROBIN  # 默认策略
        self._lb_enabled: bool = False  # 是否启用负载均衡
        self._provider_latencies: dict[str, float] = {}  # 服务商延迟记录（用于最低延迟策略）

    def set_concurrency_limit(self, limit: int) -> None:
        """Update concurrency limit (requires recreating semaphore)"""
        self.concurrency_limit = limit
        # Semaphore cannot be resized, so we replace it.
        # Note: This is safe enough for this app's usage pattern.
        self._semaphore = asyncio.Semaphore(limit)
        logger.info(f"[ModelRouter] Concurrency limit set to {limit}")
    
    # ========== 负载均衡相关方法 ==========
    
    def configure_load_balance(self, enabled: bool, strategy: str = LB_ROUND_ROBIN) -> None:
        """配置负载均衡
        
        Args:
            enabled: 是否启用负载均衡
            strategy: 负载均衡策略 (round_robin, random, least_latency)
        """
        self._lb_enabled = enabled
        self._lb_strategy = strategy
        logger.info(f"[ModelRouter] 负载均衡: {'启用' if enabled else '禁用'}, 策略: {strategy}")
    
    def set_provider_pool(self, capability: str, providers: list[ProviderPoolConfig]) -> None:
        """为指定capability设置服务商池
        
        Args:
            capability: 能力名称
            providers: 服务商配置列表
        """
        if providers:
            self._provider_pools[capability] = providers
            self._lb_counters[capability] = 0
            # 【诊断】打印每个服务商的详细配置
            for p in providers:
                logger.info(f"[ModelRouter] 设置 {capability} 服务商池: {p.provider_id}, model={p.model}, type={p.provider_type}")
        elif capability in self._provider_pools:
            del self._provider_pools[capability]
            if capability in self._lb_counters:
                del self._lb_counters[capability]

    def clear_provider_pools(self) -> None:
        """Clear all runtime load-balancing provider state."""
        self._provider_pools.clear()
        self._lb_counters.clear()
        self._provider_latencies.clear()
    
    def get_provider_pools_info(self) -> dict[str, list[str]]:
        """获取所有capability的服务商池信息"""
        return {
            cap: [p.provider_id for p in pool] 
            for cap, pool in self._provider_pools.items()
        }
    
    def _select_provider_from_pool(self, capability: str) -> ProviderPoolConfig | None:
        """从服务商池中选择一个服务商（根据负载均衡策略）
        
        Args:
            capability: 能力名称
            
        Returns:
            选中的服务商配置，如果没有配置池则返回None
        """
        pool = self._provider_pools.get(capability)
        if not pool:
            return None
        
        if len(pool) == 1:
            return pool[0]
        
        if self._lb_strategy == LB_RANDOM:
            return random.choice(pool)
        
        elif self._lb_strategy == LB_LEAST_LATENCY:
            # 选择延迟最低的服务商
            min_latency = float('inf')
            best_provider = pool[0]
            for p in pool:
                latency = self._provider_latencies.get(p.provider_id, 0)
                if latency < min_latency:
                    min_latency = latency
                    best_provider = p
            return best_provider
        
        else:  # LB_ROUND_ROBIN (默认)
            idx = self._lb_counters.get(capability, 0)
            selected = pool[idx % len(pool)]
            self._lb_counters[capability] = idx + 1
            return selected
    
    def _record_provider_latency(self, provider_id: str, latency: float) -> None:
        """记录服务商的响应延迟（用于最低延迟策略）
        
        使用指数移动平均来平滑延迟数据
        """
        alpha = 0.3  # 平滑系数
        old_latency = self._provider_latencies.get(provider_id, latency)
        self._provider_latencies[provider_id] = alpha * latency + (1 - alpha) * old_latency
    
    async def set_keepalive_mode(self, enabled: bool) -> None:
        """切换连接复用模式（需要重置客户端）
        
        Args:
            enabled: True=高效并发模式（keep-alive），False=安全模式（每次新连接）
        """
        if self.use_keepalive != enabled:
            self.use_keepalive = enabled
            await self.reset_client()  # 重置客户端以应用新设置
            mode_name = "高效并发" if enabled else "安全"
            logger.info(f"[ModelRouter] 已切换到{mode_name}模式")
    
    def get_diagnostics(self) -> dict[str, Any]:
        """获取诊断信息，用于调试并发和超时问题"""
        return {
            "concurrency_limit": self.concurrency_limit,
            "active_requests": self._active_requests,
            "queued_requests": self._queued_requests,
            "total_requests": self._total_requests,
            "total_timeouts": self._total_timeouts,
            "total_cancellations": self._total_cancellations,
            "timeout_rate": f"{(self._total_timeouts / max(self._total_requests, 1)) * 100:.1f}%",
            "request_stats": dict(self._request_stats),
        }

    def _begin_request_stats(self, capability: str) -> int:
        self._total_requests += 1
        stats = self._request_stats.setdefault(
            capability,
            {
                "total": 0,
                "success": 0,
                "timeout": 0,
                "error": 0,
                "cancelled": 0,
                "avg_time": 0,
            },
        )
        stats.setdefault("cancelled", 0)
        stats["total"] += 1
        return self._total_requests

    def _finish_request_stats(
        self,
        capability: str,
        outcome: str,
        elapsed: float,
        *,
        finished: bool,
    ) -> bool:
        if finished:
            return True
        stats = self._request_stats[capability]
        stats[outcome] += 1
        if outcome == "timeout":
            self._total_timeouts += 1
        elif outcome == "cancelled":
            self._total_cancellations += 1
        elif outcome == "success":
            stats["avg_time"] = (
                stats["avg_time"] * (stats["success"] - 1) + elapsed
            ) / stats["success"]
        return True

    async def _acquire_with_budget(
        self, budget: DeadlineBudget | StreamBudget
    ) -> asyncio.Semaphore:
        semaphore = self._semaphore
        try:
            queue_timeout = _budget_phase_timeout(budget)
            await asyncio.wait_for(
                semaphore.acquire(), timeout=queue_timeout
            )
        except OutboundRequestError:
            raise
        except (TimeoutError, asyncio.TimeoutError):
            raise OutboundRequestError(
                "outbound_timeout", 504, _PUBLIC_OUTBOUND_TIMEOUT
            ) from None
        return semaphore
    
    def _log_diagnostics(self, event: str, capability: str, extra: str = ""):
        """输出诊断日志到终端（更清晰的格式）"""
        # 计算使用率
        usage_pct = (self._active_requests / max(self.concurrency_limit, 1)) * 100
        timeout_pct = (self._total_timeouts / max(self._total_requests, 1)) * 100
        success_count = self._total_requests - self._total_timeouts
        
        # 构建状态栏（固定宽度，更易读）
        status_bar = f"[{self._active_requests:2d}/{self.concurrency_limit:2d}并发] [排队:{self._queued_requests:2d}] [成功:{success_count:3d}] [超时:{self._total_timeouts:2d}|{timeout_pct:4.1f}%]"
        
        # 根据事件类型使用不同的前缀
        if "超时" in event:
            prefix = "⏱️  TIMEOUT"
        elif "成功" in event:
            prefix = "✅ SUCCESS"
        elif "错误" in event or "异常" in event:
            prefix = "❌   ERROR"
        elif "排队" in event:
            prefix = "⏳   QUEUE"
        elif "开始" in event:
            prefix = "🚀   START"
        else:
            prefix = "ℹ️    INFO"
        
        # 输出格式：前缀 | 能力名(固定宽度) | 状态栏 | 额外信息
        cap_display = f"{capability:20s}"
        log_line = f"{prefix} | {cap_display} | {status_bar}"
        if extra:
            log_line += f" | {extra}"
        
        logger.info(log_line)
        
        # 如果使用率超过80%或有大量排队，输出警告
        if usage_pct >= 80 and self._queued_requests > 3:
            logger.warning(f"⚠️  高负载警告: 并发使用率 {usage_pct:.0f}%, 排队 {self._queued_requests} 个请求")
        
        # 定期输出状态摘要（每10秒）
        current_time = time.time()
        if current_time - self._last_summary_time >= self._summary_interval and self._active_requests > 0:
            self._last_summary_time = current_time
            self._print_status_summary()
    
    def _print_status_summary(self):
        """输出当前状态摘要（用于长时间等待时查看进度）"""
        logger.info("=" * 80)
        logger.info("📊 AI 调用状态摘要")
        logger.info("-" * 80)
        logger.info(f"   并发限制: {self.concurrency_limit} | 活跃请求: {self._active_requests} | 排队请求: {self._queued_requests}")
        logger.info(f"   总请求数: {self._total_requests} | 超时次数: {self._total_timeouts} | 超时率: {(self._total_timeouts / max(self._total_requests, 1)) * 100:.1f}%")
        
        if self._request_stats:
            logger.info("-" * 80)
            logger.info("   各能力统计:")
            for cap, stats in self._request_stats.items():
                in_progress = stats["total"] - stats["success"] - stats["timeout"] - stats["error"]
                if in_progress > 0 or stats["total"] > 0:
                    status = f"进行中:{in_progress}" if in_progress > 0 else f"完成:{stats['success']}"
                    logger.info(f"   - {cap:20s}: 总计:{stats['total']:3d} | {status:12s} | 超时:{stats['timeout']} | 平均:{stats['avg_time']:.1f}s")
        logger.info("=" * 80)

    def register(self, capability: str, config: ModelConfig) -> None:
        self.routes[capability] = config

    def resolve(self, capability: str) -> ModelConfig:
        if capability not in self.routes:
            raise KeyError(f"Missing model configuration for {capability}")
        return self.routes[capability]

    def set_prompt(self, capability: str, prompt: str) -> None:
        self.prompts[capability] = prompt

    def get_prompt(self, capability: str) -> str | None:
        return self.prompts.get(capability)

    def configure_overrides(self, overrides: dict[str, dict[str, Any]]) -> None:
        self.overrides = overrides or {}

    @property
    def api_base_url(self) -> str | None:
        return self._runtime_credential_snapshot.base_url

    @api_base_url.setter
    def api_base_url(self, value: str | None) -> None:
        self._runtime_credential_snapshot = replace(
            self._runtime_credential_snapshot,
            base_url=value,
        )

    @property
    def api_key(self) -> str | None:
        return self._runtime_credential_snapshot.api_key

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        self._runtime_credential_snapshot = replace(
            self._runtime_credential_snapshot,
            api_key=value,
        )

    def configure_runtime_credentials(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        provider_type: str | None,
    ) -> None:
        """Atomically publish one complete runtime credential tuple."""
        self._runtime_credential_snapshot = _RuntimeCredentialSnapshot(
            base_url=base_url,
            api_key=api_key,
            provider_type=provider_type,
        )

    def _select_runtime_credentials(
        self,
        override: dict[str, Any],
        fallback_provider_type: str,
    ) -> _RuntimeCredentialSnapshot:
        if any(
            field_name in override
            for field_name in ("base_url", "api_key", "provider_type")
        ):
            return _RuntimeCredentialSnapshot(
                base_url=override.get("base_url"),
                api_key=override.get("api_key"),
                provider_type=override.get("provider_type"),
            )

        snapshot = self._runtime_credential_snapshot
        if snapshot.provider_type is None:
            return replace(snapshot, provider_type=fallback_provider_type)
        return snapshot

    def capabilities(self) -> list[str]:
        return list(self.routes.keys())

    async def reset_client(self):
        """Compatibility no-op; safe requests own and close their clients."""
        return None

    def _prepare_request(
        self, capability: str, payload: dict[str, Any], use_format_placeholder: bool = True
    ) -> dict[str, Any]:
        """Prepare request data, shared by sync and async invoke"""
        config = self.resolve(capability)
        prompt_template = self.prompts.get(capability)
        override = self.overrides.get(capability, {})
        
        # 【负载均衡】如果启用且有服务商池，从池中选择服务商
        lb_provider: ProviderPoolConfig | None = None
        if self._lb_enabled and capability in self._provider_pools:
            lb_provider = self._select_provider_from_pool(capability)
            if lb_provider:
                logger.debug(f"[ModelRouter] 负载均衡: {capability} -> {lb_provider.provider_id}")
        
        # 优先级: 负载均衡选择 > override配置 > 全局配置
        if lb_provider:
            base_url = lb_provider.base_url
            api_key = lb_provider.api_key
            provider_type = lb_provider.provider_type
            model_name = lb_provider.model or override.get("model") or config.model
        else:
            credentials = self._select_runtime_credentials(
                override,
                getattr(config, "provider_type", PROVIDER_TYPE_OPENAI),
            )
            base_url = credentials.base_url
            api_key = credentials.api_key
            provider_type = credentials.provider_type
            model_name = override.get("model") or config.model
        
        timeout = override.get("timeout") or self.timeout
        extra_body = override.get("extra_body") or config.extra_body
        
        # 判断是否有有效的 API 凭据（来自 override 或全局配置）
        has_valid_credentials = bool(base_url and api_key and provider_type)
        
        # 如果 override 中有有效凭据，即使初始 provider 是 "local" 也应该使用 AI
        # 这允许用户通过设置默认服务商来覆盖 local 模式
        is_local_mode = (config.provider == "local" and not has_valid_credentials) or not has_valid_credentials

        # Format prompt
        formatted_prompt = prompt_template
        if prompt_template and use_format_placeholder:
            try:
                formatted_prompt = prompt_template.format(**payload)
            except (KeyError, ValueError) as e:
                logger.warning(f"[ModelRouter] Prompt format failed ({capability}): {e}")
                logger.warning(f"[ModelRouter] Available payload keys: {list(payload.keys())}")
                formatted_prompt = prompt_template
        
        if is_local_mode:
            return {
                "is_local": True,
                "result": {
                    "provider": config.provider,
                    "model": model_name,
                    "prompt": formatted_prompt,
                    "payload": payload,
                }
            }
        
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # 根据服务商类型构建请求
        if provider_type == PROVIDER_TYPE_ANTHROPIC:
            # Claude 原生 API
            body = {
                "model": model_name,
                "max_tokens": extra_body.get("max_tokens", 4096) if extra_body else 4096,
                "messages": [
                    {"role": "user", "content": user_content},
                ],
            }
            if formatted_prompt:
                body["system"] = formatted_prompt
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        elif provider_type == PROVIDER_TYPE_GOOGLE:
            # Gemini 原生 API
            contents = [{"role": "user", "parts": [{"text": user_content}]}]
            body: dict[str, Any] = {"contents": contents}
            
            # 使用 systemInstruction 设置系统提示（Gemini 原生支持）
            if formatted_prompt:
                body["systemInstruction"] = {"parts": [{"text": formatted_prompt}]}
            
            # 处理 generationConfig
            generation_config: dict[str, Any] = {}
            if extra_body:
                if "generationConfig" in extra_body:
                    generation_config.update(extra_body["generationConfig"])
                # 转换 OpenAI 的 response_format 为 Gemini 的 responseMimeType
                if "response_format" in extra_body:
                    response_format = extra_body["response_format"]
                    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                        generation_config["responseMimeType"] = "application/json"
            
            if generation_config:
                body["generationConfig"] = generation_config
            
            headers = {"Content-Type": "application/json"}
        else:
            # OpenAI 兼容格式（默认）
            body = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": formatted_prompt or "You are an AI assistant."},
                    {"role": "user", "content": user_content},
                ],
            }
            if extra_body:
                body.update(extra_body)
            headers = {"Authorization": f"Bearer {api_key}"}

        request_base_url, request_target = self._provider_request_location(
            provider_type,
            base_url,
            model_name,
            config.endpoint,
            api_key=api_key,
            stream=False,
        )

        return {
            "is_local": False,
            "base_url": request_base_url,
            "request_target": request_target,
            "api_key": api_key,
            "endpoint": config.endpoint,
            "body": body,
            "headers": headers,
            "timeout": timeout,
            "provider_type": provider_type,
            "lb_provider_id": lb_provider.provider_id if lb_provider else None,  # 负载均衡选中的服务商ID
            "meta": {
                "provider": config.provider,
                "model": model_name,
                "prompt": formatted_prompt,
                "payload": payload,
            }
        }

    def _provider_request_location(
        self, provider_type, base_url, model_name, endpoint, *, api_key: str, stream
    ) -> tuple[str, str]:
        base_url_stripped = base_url.rstrip("/")

        if provider_type == PROVIDER_TYPE_ANTHROPIC:
            return base_url_stripped, "/messages"

        if provider_type == PROVIDER_TYPE_GOOGLE:
            action = "streamGenerateContent" if stream else "generateContent"
            request_target = (
                f"/models/{quote(str(model_name), safe='')}:{action}?"
                f"{urlencode({'key': api_key})}"
            )
            return base_url_stripped, request_target

        request_target = endpoint or "/chat/completions"
        if (
            request_target == "/chat/completions"
            and not self._has_api_version_suffix(base_url_stripped)
        ):
            request_target = "/v1/chat/completions"
        return base_url_stripped, request_target

    def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        budget: DeadlineBudget | None = None,
    ) -> dict[str, Any]:
        """Sync invocation (blocking)"""
        started_at = time.monotonic()
        allow_local = self.allow_local_ai_endpoints
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            logger.debug(f"[ModelRouter] Local mode: {req['result']}")
            return req["result"]

        self._begin_request_stats(capability)
        stats_finished = False
        try:
            effective_budget = _ensure_deadline(
                budget, timeout=req["timeout"], started_at=started_at
            )
            _budget_phase_timeout(effective_budget)
            logger.debug(f"[ModelRouter] Sync invoke {capability} (provider={req['meta']['provider']})")
            data = self._runtime_client.post_json(
                req["base_url"],
                request_target=req["request_target"],
                headers=req["headers"],
                json_body=req["body"],
                allow_local=allow_local,
                budget=effective_budget,
                max_bytes=AI_JSON_MAX_BYTES,
            )
            content = self._extract_primary_content(
                data, req.get("provider_type", PROVIDER_TYPE_OPENAI)
            )
            parsed_content = self._parse_content(content)
            _budget_phase_timeout(effective_budget)
        except _PrimaryResponseError:
            stats_finished = self._finish_request_stats(
                capability,
                "error",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            logger.warning(
                "[ModelRouter] Sync invoke invalid response %s code=invalid_response_shape",
                capability,
            )
            return {
                **req["meta"],
                "error": _PRIMARY_RESPONSE_ERROR,
            }
        except OutboundRequestError as exc:
            stats_finished = self._finish_request_stats(
                capability,
                "timeout" if exc.code == "outbound_timeout" else "error",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            logger.warning(
                "[ModelRouter] Sync invoke failed %s code=%s",
                capability,
                exc.code,
            )
            return {
                **req["meta"],
                "error": exc.public_message,
            }
        else:
            self._finish_request_stats(
                capability,
                "success",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            return {
                **req["meta"],
                "content": parsed_content,
                "raw": data,
            }

    async def ainvoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        budget: DeadlineBudget | None = None,
    ) -> dict[str, Any]:
        """Async invocation (non-blocking) with semaphore."""
        started_at = time.monotonic()
        allow_local = self.allow_local_ai_endpoints
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            return req["result"]

        try:
            effective_budget = _ensure_deadline(
                budget, timeout=req["timeout"], started_at=started_at
            )
        except OutboundRequestError as exc:
            return {**req["meta"], "error": exc.public_message}

        lifecycle = _AsyncRequestLifecycle(self, capability, started_at)
        request_id = lifecycle.request_id
        queue_start = time.monotonic()
        self._log_diagnostics("排队", capability, f"请求#{request_id}")

        last_error = "AI request failed"
        final_outcome = "error"
        try:
            for attempt in range(self.max_retries):
                process_start = time.monotonic()
                try:
                    await lifecycle.acquire(effective_budget)
                    queue_time = time.monotonic() - queue_start

                    self._log_diagnostics(
                        "开始处理",
                        capability,
                        (
                            f"请求#{request_id} 排队耗时:{queue_time:.2f}s "
                            f"尝试:{attempt + 1}/{self.max_retries}"
                        ),
                    )
                    timeout = req.get("timeout") or self.timeout
                    headers = {**req["headers"], "Connection": "close"}
                    provider_type = req.get(
                        "provider_type", PROVIDER_TYPE_OPENAI
                    )
                    _budget_phase_timeout(effective_budget)
                    provider_call_start = time.monotonic()
                    data = await self._runtime_client.apost_json(
                        req["base_url"],
                        request_target=req["request_target"],
                        headers=headers,
                        json_body=req["body"],
                        allow_local=allow_local,
                        budget=effective_budget,
                        max_bytes=AI_JSON_MAX_BYTES,
                    )
                    provider_latency = time.monotonic() - provider_call_start
                    content = self._extract_primary_content(data, provider_type)
                    parsed_content = self._parse_content(content)
                    _budget_phase_timeout(effective_budget)
                except _PrimaryResponseError:
                    lifecycle.finish("error")
                    logger.warning(
                        "[ModelRouter] Async invoke invalid response %s code=invalid_response_shape",
                        capability,
                    )
                    return {**req["meta"], "error": _PRIMARY_RESPONSE_ERROR}
                except OutboundRequestError as exc:
                    last_error = exc.public_message
                    final_outcome = (
                        "timeout" if exc.code == "outbound_timeout" else "error"
                    )
                    process_time = time.monotonic() - process_start
                    logger.warning(
                        "[ModelRouter] Async invoke failed %s attempt=%s/%s code=%s duration=%.2fs",
                        capability,
                        attempt + 1,
                        self.max_retries,
                        exc.code,
                        process_time,
                    )
                    if exc.code not in RETRYABLE_OUTBOUND_CODES:
                        lifecycle.finish(final_outcome)
                        return {**req["meta"], "error": exc.public_message}
                except asyncio.CancelledError:
                    lifecycle.finish("cancelled")
                    raise
                except Exception as exc:
                    lifecycle.finish("error")
                    self._log_diagnostics(
                        "❌ 异常",
                        capability,
                        f"请求#{request_id} type={type(exc).__name__}",
                    )
                    return {**req["meta"], "error": "AI request failed"}
                else:
                    process_time = time.monotonic() - process_start
                    lifecycle.finish("success")
                    lb_provider_id = req.get("lb_provider_id")
                    if lb_provider_id:
                        self._record_provider_latency(
                            lb_provider_id, provider_latency
                        )
                    self._log_diagnostics(
                        "✅ 成功",
                        capability,
                        f"请求#{request_id} 处理耗时:{process_time:.2f}s",
                    )
                    return {
                        **req["meta"],
                        "content": parsed_content,
                        "raw": data,
                    }
                finally:
                    lifecycle.release_attempt()

                if attempt < self.max_retries - 1:
                    lifecycle.queue_for_retry()
                    sleep_time = min(2.0, 0.5 * (attempt + 1))
                    try:
                        backoff_timeout = effective_budget.phase_timeout()
                        await asyncio.wait_for(
                            asyncio.sleep(sleep_time), timeout=backoff_timeout
                        )
                    except asyncio.CancelledError:
                        lifecycle.finish("cancelled")
                        raise
                    except (DeadlineExpired, TimeoutError, asyncio.TimeoutError):
                        last_error = _PUBLIC_OUTBOUND_TIMEOUT
                        final_outcome = "timeout"
                        break

            lifecycle.finish(final_outcome)
            if effective_budget.remaining() <= 0:
                return {**req["meta"], "error": last_error}
            return {
                **req["meta"],
                "error": f"{last_error} (after {self.max_retries} attempts)",
            }
        except asyncio.CancelledError:
            lifecycle.finish("cancelled")
            raise
        finally:
            lifecycle.close()

    def _stream_status_event(self, capability: str, state: str, **extra) -> dict[str, Any]:
        event = {
            "type": "status",
            "state": state,
            "capability": capability,
            "timestamp": time.time(),
        }
        event.update(extra)
        return event

    def _stream_error_event(
        self, capability: str, message: str, **extra: Any
    ) -> dict[str, Any]:
        event = {
            "type": "error",
            "message": message,
            "capability": capability,
            "timestamp": time.time(),
        }
        event.update(extra)
        return event

    @staticmethod
    def _finish_stream_event(
        lifecycle: _AsyncRequestLifecycle, event: Any
    ) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") == "status":
            state = event.get("state")
            if state == "completed":
                lifecycle.finish("success")
            elif state == "interrupted":
                lifecycle.finish("timeout")
        elif event.get("type") == "error":
            lifecycle.finish(
                "timeout" if event.get("code") == "outbound_timeout" else "error"
            )

    async def _publish_stream_events(
        self,
        capability: str,
        source: AsyncIterator[Any],
        *,
        budget: StreamBudget,
        lifecycle: _AsyncRequestLifecycle,
    ) -> AsyncGenerator[Any, None]:
        iterator = source.__aiter__()
        primary_cancel: asyncio.CancelledError | None = None
        generator_closing = False
        try:
            while True:
                try:
                    event = await iterator.__anext__()
                except StopAsyncIteration:
                    return
                self._finish_stream_event(lifecycle, event)
                yield event
        except asyncio.CancelledError as exc:
            primary_cancel = exc
            lifecycle.finish("cancelled")
            raise
        except GeneratorExit:
            generator_closing = True
            lifecycle.finish("cancelled")
            raise
        except OutboundRequestError as exc:
            lifecycle.finish(
                "timeout" if exc.code == "outbound_timeout" else "error"
            )
            if exc.code == "outbound_timeout" and budget.content_started:
                yield self._stream_status_event(
                    capability,
                    "interrupted",
                    reason=exc.code,
                    partial=True,
                )
            else:
                yield self._stream_error_event(
                    capability, exc.public_message, code=exc.code
                )
            return
        except Exception:
            lifecycle.finish("error")
            yield self._stream_error_event(capability, _STREAM_RESPONSE_ERROR)
            return
        finally:
            if not lifecycle.stats_finished:
                lifecycle.finish("cancelled")
            try:
                await iterator.aclose()
            except asyncio.CancelledError:
                if primary_cancel is None and not generator_closing:
                    raise
            except OutboundRequestError as exc:
                logger.warning(
                    "[ModelRouter] Stream source close failed %s code=%s",
                    capability,
                    exc.code,
                )
            except Exception as exc:
                logger.warning(
                    "[ModelRouter] Stream source close failed %s type=%s",
                    capability,
                    type(exc).__name__,
                )
            finally:
                lifecycle.close()

    async def astream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        budget: StreamBudget | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Async streaming invocation with one logical budget and outcome."""
        started_at = time.monotonic()
        override = self.overrides.get(capability, {})
        effective_budget = _ensure_stream_budget(
            budget,
            idle_timeout=override.get("timeout") or self.timeout,
            started_at=started_at,
        )
        lifecycle = _AsyncRequestLifecycle(self, capability, started_at)
        source = self._astream_impl(
            capability,
            payload,
            budget=effective_budget,
            lifecycle=lifecycle,
        )
        publisher = self._publish_stream_events(
            capability,
            source,
            budget=effective_budget,
            lifecycle=lifecycle,
        )
        try:
            async for event in publisher:
                yield event
        finally:
            await publisher.aclose()

    async def _astream_impl(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        budget: StreamBudget,
        lifecycle: _AsyncRequestLifecycle,
    ) -> AsyncGenerator[Any, None]:
        """Async streaming invocation. Yields status/error dicts and plain chunks."""
        allow_local = self.allow_local_ai_endpoints
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            yield self._stream_error_event(capability, "Streaming not supported for local provider")
            return

        provider_type = req.get("provider_type", PROVIDER_TYPE_OPENAI)
        stream_base_url, stream_request_target = self._provider_request_location(
            provider_type,
            req["base_url"],
            req["meta"]["model"],
            req["endpoint"],
            api_key=req["api_key"],
            stream=True,
        )
        if provider_type != PROVIDER_TYPE_GOOGLE:
            req["body"]["stream"] = True

        yield self._stream_status_event(capability, "connecting")

        async with lifecycle.slot(budget):
            logger.info(
                "[ModelRouter] Async stream %s start (type=%s)",
                capability,
                provider_type,
            )
            headers = {**req["headers"], "Connection": "close"}
            iterator: Any = None
            primary_cancel: asyncio.CancelledError | None = None

            try:
                lines = self._runtime_client.astream_lines(
                    stream_base_url,
                    request_target=stream_request_target,
                    headers=headers,
                    json_body=req["body"],
                    allow_local=allow_local,
                    budget=budget,
                    max_bytes=STREAM_MAX_BYTES,
                    max_event_bytes=STREAM_EVENT_MAX_BYTES,
                )
                iterator = lines.__aiter__()
                try:
                    first_line = await iterator.__anext__()
                except StopAsyncIteration:
                    yield self._stream_status_event(capability, "connected")
                    _budget_phase_timeout(budget)
                    yield self._stream_status_event(capability, "completed")
                    return

                yield self._stream_status_event(capability, "connected")
                first_chunk = True

                async def incoming_lines() -> AsyncGenerator[str, None]:
                    yield first_line
                    async for next_line in iterator:
                        yield next_line

                def protocol_error(code: str, value: Any = None) -> None:
                    logger.warning(
                        "[ModelRouter] Stream protocol error %s provider=%s code=%s value_type=%s",
                        capability,
                        provider_type,
                        code,
                        type(value).__name__ if value is not None else "none",
                    )

                if provider_type == PROVIDER_TYPE_GOOGLE:
                    decoder = json.JSONDecoder()
                    buffer = ""
                    async for line in incoming_lines():
                        if not line:
                            continue
                        buffer += line
                        while True:
                            buffer = buffer.lstrip()
                            while buffer.startswith("[") or buffer.startswith(","):
                                buffer = buffer[1:].lstrip()
                            if buffer.startswith("]"):
                                buffer = buffer[1:].lstrip()
                                continue
                            if not buffer:
                                break
                            try:
                                chunk, consumed = decoder.raw_decode(buffer)
                            except json.JSONDecodeError:
                                break
                            buffer = buffer[consumed:]
                            if not isinstance(chunk, dict):
                                protocol_error("invalid_chunk_type", chunk)
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            if "error" in chunk:
                                protocol_error("upstream_error", chunk["error"])
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            try:
                                candidates = chunk.get("candidates", [])
                                if not isinstance(candidates, list):
                                    raise TypeError
                                for candidate in candidates:
                                    content_obj = candidate.get("content", {})
                                    content_parts = content_obj.get("parts", [])
                                    for part in content_parts:
                                        text = part.get("text", "")
                                        if not isinstance(text, str):
                                            raise TypeError
                                        if text:
                                            _budget_phase_timeout(budget)
                                            budget.mark_content()
                                            if first_chunk:
                                                yield self._stream_status_event(
                                                    capability, "receiving"
                                                )
                                                first_chunk = False
                                            yield text
                            except (AttributeError, TypeError):
                                protocol_error("invalid_chunk_shape", chunk)
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return

                    remaining = buffer.strip()
                    while remaining.startswith("[") or remaining.startswith(","):
                        remaining = remaining[1:].lstrip()
                    while remaining.endswith("]"):
                        remaining = remaining[:-1].rstrip()
                    if remaining:
                        protocol_error("malformed_json")
                        yield self._stream_error_event(
                            capability, _STREAM_RESPONSE_ERROR
                        )
                        return

                elif provider_type == PROVIDER_TYPE_ANTHROPIC:
                    async for line in incoming_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            protocol_error("malformed_json")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if not isinstance(event, dict):
                            protocol_error("invalid_event_type", event)
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if event.get("type") == "error":
                            protocol_error("upstream_error", event.get("error"))
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if not isinstance(delta, dict):
                                protocol_error("invalid_delta_type", delta)
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            text = delta.get("text", "")
                            if not isinstance(text, str):
                                protocol_error("invalid_delta_text", text)
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            if text:
                                _budget_phase_timeout(budget)
                                budget.mark_content()
                                if first_chunk:
                                    yield self._stream_status_event(
                                        capability, "receiving"
                                    )
                                    first_chunk = False
                                yield text

                else:
                    async for line in incoming_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            protocol_error("malformed_json")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if not isinstance(chunk, dict):
                            protocol_error("invalid_chunk_type", chunk)
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if "error" in chunk:
                            protocol_error("upstream_error", chunk["error"])
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        try:
                            choices = chunk.get("choices", [])
                            if not isinstance(choices, list):
                                raise TypeError
                            delta = choices[0].get("delta", {}) if choices else {}
                            if not isinstance(delta, dict):
                                raise TypeError
                            content = delta.get("content", "")
                            if not isinstance(content, str):
                                raise TypeError
                        except (AttributeError, TypeError):
                            protocol_error("invalid_chunk_shape", chunk)
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if content:
                            _budget_phase_timeout(budget)
                            budget.mark_content()
                            if first_chunk:
                                yield self._stream_status_event(
                                    capability, "receiving"
                                )
                                first_chunk = False
                            yield content

                _budget_phase_timeout(budget)
                yield self._stream_status_event(capability, "completed")
            except asyncio.CancelledError as exc:
                primary_cancel = exc
                raise
            except OutboundRequestError as exc:
                logger.warning(
                    "[ModelRouter] Async stream failed %s code=%s",
                    capability,
                    exc.code,
                )
                if exc.code == "outbound_timeout" and budget.content_started:
                    yield self._stream_status_event(
                        capability,
                        "interrupted",
                        reason=exc.code,
                        partial=True,
                    )
                else:
                    yield self._stream_error_event(
                        capability, exc.public_message, code=exc.code
                    )
                return
            except Exception as exc:
                logger.error(
                    "[ModelRouter] Async stream failed %s type=%s",
                    capability,
                    type(exc).__name__,
                )
                yield self._stream_error_event(capability, _STREAM_RESPONSE_ERROR)
                return
            finally:
                if iterator is not None:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        try:
                            await close()
                        except asyncio.CancelledError:
                            if primary_cancel is None:
                                raise
                        except OutboundRequestError as exc:
                            logger.warning(
                                "[ModelRouter] Stream close failed %s code=%s",
                                capability,
                                exc.code,
                            )
                        except Exception as exc:
                            logger.warning(
                                "[ModelRouter] Stream close failed %s type=%s",
                                capability,
                                type(exc).__name__,
                            )

    def _has_api_version_suffix(self, url: str) -> bool:
        """检查 URL 是否已包含 API 版本路径（如 /v1, /v1beta, /v2, /api/v1 等）
        
        Args:
            url: 已经 strip 掉尾部斜杠的 URL
            
        Returns:
            True 如果 URL 已经包含版本路径
        """
        # 匹配常见的 API 版本路径模式
        # 例如: /v1, /v1beta, /v2, /api/v1, /api/v3 等
        version_pattern = r'/v\d+[a-z]*$|/api/v\d+[a-z]*$'
        return bool(re.search(version_pattern, url))

    def call_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        *,
        budget: DeadlineBudget | None = None,
    ) -> str:
        """Sync direct call"""
        started_at = time.monotonic()
        allow_local = self.allow_local_ai_endpoints
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        
        # 【负载均衡】如果启用且有服务商池，从池中选择服务商
        lb_provider: ProviderPoolConfig | None = None
        if self._lb_enabled and capability in self._provider_pools:
            lb_provider = self._select_provider_from_pool(capability)
            if lb_provider:
                logger.debug(f"[call_capability] 负载均衡: {capability} -> {lb_provider.provider_id}")
        
        # 优先级: 负载均衡选择 > override配置 > 全局配置
        if lb_provider:
            base_url = lb_provider.base_url
            api_key = lb_provider.api_key
            provider_type = lb_provider.provider_type
            model_name = lb_provider.model or override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
        else:
            credentials = self._select_runtime_credentials(
                override,
                getattr(config, "provider_type", PROVIDER_TYPE_OPENAI),
            )
            base_url = credentials.base_url
            api_key = credentials.api_key
            model_name = override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
            provider_type = credentials.provider_type
        
        timeout = override.get("timeout") or self.timeout
        
        if (
            config.provider == "local"
            or not base_url
            or not api_key
            or not provider_type
        ):
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        # 根据 provider_type 处理不同的 API 格式
        if provider_type == PROVIDER_TYPE_GOOGLE:
            # Google Gemini 原生 API
            # 分离 system 和 user 消息
            system_parts = []
            user_contents = []
            for msg in messages:
                if msg["role"] == "system":
                    system_parts.append({"text": msg["content"]})
                else:
                    role = "user" if msg["role"] == "user" else "model"
                    user_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            
            body: dict[str, Any] = {"contents": user_contents if user_contents else [{"role": "user", "parts": [{"text": ""}]}]}
            
            # 使用 systemInstruction 设置系统提示
            if system_parts:
                body["systemInstruction"] = {"parts": system_parts}
            
            # 处理 generationConfig
            generation_config: dict[str, Any] = {}
            if extra_body:
                if "generationConfig" in extra_body:
                    generation_config.update(extra_body["generationConfig"])
                if "response_format" in extra_body:
                    response_format = extra_body["response_format"]
                    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                        generation_config["responseMimeType"] = "application/json"
            if response_format:
                if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                    generation_config["responseMimeType"] = "application/json"
            if generation_config:
                body["generationConfig"] = generation_config
            
            headers = {"Content-Type": "application/json", "Connection": "close"}
        elif provider_type == PROVIDER_TYPE_ANTHROPIC:
            # Claude 原生 API
            system_content = None
            filtered_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    filtered_messages.append(msg)
            body = {
                "model": model_name,
                "max_tokens": extra_body.get("max_tokens", 4096) if extra_body else 4096,
                "messages": filtered_messages,
            }
            if system_content:
                body["system"] = system_content
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Connection": "close",
            }
        else:
            # OpenAI 兼容格式（默认）
            body = {
                "model": model_name,
                "messages": messages,
            }
            if response_format:
                body["response_format"] = response_format
            if extra_body:
                body.update(extra_body)
            headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        request_base_url, request_target = self._provider_request_location(
            provider_type,
            base_url,
            model_name,
            config.endpoint,
            api_key=api_key,
            stream=False,
        )
        self._begin_request_stats(capability)
        stats_finished = False
        try:
            effective_budget = _ensure_deadline(
                budget, timeout=timeout, started_at=started_at
            )
            _budget_phase_timeout(effective_budget)
            data = self._runtime_client.post_json(
                request_base_url,
                request_target=request_target,
                headers=headers,
                json_body=body,
                allow_local=allow_local,
                budget=effective_budget,
                max_bytes=AI_JSON_MAX_BYTES,
            )
            result = self._extract_capability_content(
                data, provider_type, capability
            )
            _budget_phase_timeout(effective_budget)
        except OutboundRequestError as exc:
            stats_finished = self._finish_request_stats(
                capability,
                "timeout" if exc.code == "outbound_timeout" else "error",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            logger.warning(
                "[ModelRouter] Capability call failed %s code=%s",
                capability,
                exc.code,
            )
            raise RuntimeError(exc.public_message) from None
        except Exception:
            self._finish_request_stats(
                capability,
                "error",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            raise
        else:
            self._finish_request_stats(
                capability,
                "success",
                time.monotonic() - started_at,
                finished=stats_finished,
            )
            return result

    async def acall_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        *,
        budget: DeadlineBudget | None = None,
    ) -> str:
        """Async direct call"""
        started_at = time.monotonic()
        allow_local = self.allow_local_ai_endpoints
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        
        # 【负载均衡】如果启用且有服务商池，从池中选择服务商
        lb_provider: ProviderPoolConfig | None = None
        if self._lb_enabled and capability in self._provider_pools:
            lb_provider = self._select_provider_from_pool(capability)
            if lb_provider:
                logger.debug(f"[acall_capability] 负载均衡: {capability} -> {lb_provider.provider_id}")
        
        # 优先级: 负载均衡选择 > override配置 > 全局配置
        if lb_provider:
            base_url = lb_provider.base_url
            api_key = lb_provider.api_key
            provider_type = lb_provider.provider_type
            model_name = lb_provider.model
            extra_body = override.get("extra_body") or config.extra_body
            
            # 【关键修复】如果 lb_provider.model 为空，回退到 override 或 config
            if not model_name:
                model_name = override.get("model")
            if not model_name:
                model_name = config.model
            
            logger.info(f"[acall_capability] 负载均衡选择: {capability} -> {lb_provider.provider_id}, model={model_name}")
        else:
            credentials = self._select_runtime_credentials(
                override,
                getattr(config, "provider_type", PROVIDER_TYPE_OPENAI),
            )
            base_url = credentials.base_url
            api_key = credentials.api_key
            model_name = override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
            provider_type = credentials.provider_type
        
        timeout_value = override.get("timeout") or self.timeout or 60  # 确保有默认值
        
        # 【关键修复】model 为空时直接报错，不要发送无效请求
        if not model_name:
            raise RuntimeError(
                f"Cannot call AI for capability {capability}: model name is empty. "
                f"请检查服务商配置的 selected_models 是否为空，或者 capability_routes 中的 model 配置。"
            )
        
        if (
            config.provider == "local"
            or not base_url
            or not api_key
            or not provider_type
        ):
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        # 根据 provider_type 处理不同的 API 格式
        if provider_type == PROVIDER_TYPE_GOOGLE:
            # Google Gemini 原生 API
            # 分离 system 和 user 消息
            system_parts = []
            user_contents = []
            for msg in messages:
                if msg["role"] == "system":
                    system_parts.append({"text": msg["content"]})
                else:
                    role = "user" if msg["role"] == "user" else "model"
                    user_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            
            body: dict[str, Any] = {"contents": user_contents if user_contents else [{"role": "user", "parts": [{"text": ""}]}]}
            
            # 使用 systemInstruction 设置系统提示
            if system_parts:
                body["systemInstruction"] = {"parts": system_parts}
            
            # 处理 generationConfig
            generation_config: dict[str, Any] = {}
            if extra_body:
                if "generationConfig" in extra_body:
                    generation_config.update(extra_body["generationConfig"])
                if "response_format" in extra_body:
                    rf = extra_body["response_format"]
                    if isinstance(rf, dict) and rf.get("type") == "json_object":
                        generation_config["responseMimeType"] = "application/json"
            if response_format:
                if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                    generation_config["responseMimeType"] = "application/json"
            if generation_config:
                body["generationConfig"] = generation_config
            
            headers = {"Content-Type": "application/json", "Connection": "close"}
        elif provider_type == PROVIDER_TYPE_ANTHROPIC:
            # Claude 原生 API
            system_content = None
            filtered_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    filtered_messages.append(msg)
            body = {
                "model": model_name,
                "max_tokens": extra_body.get("max_tokens", 4096) if extra_body else 4096,
                "messages": filtered_messages,
            }
            if system_content:
                body["system"] = system_content
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Connection": "close",
            }
        else:
            # OpenAI 兼容格式（默认）
            body = {
                "model": model_name,
                "messages": messages,
            }
            if response_format:
                body["response_format"] = response_format
            if extra_body:
                body.update(extra_body)
            headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        request_base_url, request_target = self._provider_request_location(
            provider_type,
            base_url,
            model_name,
            config.endpoint,
            api_key=api_key,
            stream=False,
        )
        
        try:
            effective_budget = _ensure_deadline(
                budget, timeout=timeout_value, started_at=started_at
            )
        except OutboundRequestError as exc:
            raise RuntimeError(exc.public_message) from None

        lifecycle = _AsyncRequestLifecycle(self, capability, started_at)
        try:
            await lifecycle.acquire(effective_budget)
            _budget_phase_timeout(effective_budget)
            data = await self._runtime_client.apost_json(
                request_base_url,
                request_target=request_target,
                headers=headers,
                json_body=body,
                allow_local=allow_local,
                budget=effective_budget,
                max_bytes=AI_JSON_MAX_BYTES,
            )
            result = self._extract_capability_content(
                data, provider_type, capability
            )
            _budget_phase_timeout(effective_budget)
        except OutboundRequestError as exc:
            outcome = "timeout" if exc.code == "outbound_timeout" else "error"
            lifecycle.finish(outcome)
            logger.warning(
                "[ModelRouter] Async capability call failed %s code=%s",
                capability,
                exc.code,
            )
            raise RuntimeError(exc.public_message) from None
        except asyncio.CancelledError:
            lifecycle.finish("cancelled")
            raise
        except Exception:
            lifecycle.finish("error")
            if lifecycle.active:
                raise
            raise RuntimeError("AI request failed") from None
        else:
            lifecycle.finish("success")
            return result
        finally:
            lifecycle.close()

    async def chat(
        self,
        prompt: str,
        capability: str = "turn_report",
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        *,
        budget: DeadlineBudget | None = None,
    ) -> str:
        """通用聊天接口 - 直接传入完整 prompt 文本进行对话
        
        此方法用于不需要预定义 prompt 模板的场景，如动态生成的叙事、解释等。
        
        Args:
            prompt: 完整的用户提示文本
            capability: 使用的模型配置（决定使用哪个模型、超时等设置）
            system_prompt: 可选的系统提示
            max_tokens: 可选的最大输出 token 数
            
        Returns:
            LLM 的响应文本
            
        Raises:
            RuntimeError: 当配置缺失或调用失败时
        """
        started_at = time.monotonic()
        allow_local = self.allow_local_ai_endpoints
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        
        # 【负载均衡】如果启用且有服务商池，从池中选择服务商
        lb_provider: ProviderPoolConfig | None = None
        if self._lb_enabled and capability in self._provider_pools:
            lb_provider = self._select_provider_from_pool(capability)
            if lb_provider:
                logger.debug(f"[chat] 负载均衡: {capability} -> {lb_provider.provider_id}")
        
        # 优先级: 负载均衡选择 > override配置 > 全局配置
        if lb_provider:
            base_url = lb_provider.base_url
            api_key = lb_provider.api_key
            provider_type = lb_provider.provider_type
            model_name = lb_provider.model or override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
        else:
            credentials = self._select_runtime_credentials(
                override,
                getattr(config, "provider_type", PROVIDER_TYPE_OPENAI),
            )
            base_url = credentials.base_url
            api_key = credentials.api_key
            model_name = override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
            provider_type = credentials.provider_type
        
        timeout_value = override.get("timeout") or self.timeout or 60
        
        # 检查是否为本地模式（无 API 配置）
        if (
            config.provider == "local"
            or not base_url
            or not api_key
            or not provider_type
        ):
            logger.warning(f"[chat] {capability} 无 API 配置，返回占位符响应")
            return f"[本地模式] 无法生成响应: {prompt[:100]}..."
        
        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # 根据 provider_type 处理不同的 API 格式
        if provider_type == PROVIDER_TYPE_GOOGLE:
            # Google Gemini 原生 API
            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            body: dict[str, Any] = {"contents": contents}
            
            # 使用 systemInstruction 设置系统提示
            if system_prompt:
                body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            
            # 处理 generationConfig
            generation_config: dict[str, Any] = {}
            if max_tokens:
                generation_config["maxOutputTokens"] = max_tokens
            if extra_body:
                if "generationConfig" in extra_body:
                    generation_config.update(extra_body["generationConfig"])
                if "response_format" in extra_body:
                    rf = extra_body["response_format"]
                    if isinstance(rf, dict) and rf.get("type") == "json_object":
                        generation_config["responseMimeType"] = "application/json"
            if generation_config:
                body["generationConfig"] = generation_config
            
            headers = {"Content-Type": "application/json", "Connection": "close"}
        elif provider_type == PROVIDER_TYPE_ANTHROPIC:
            # Claude 原生 API
            system_content = system_prompt
            filtered_messages = [{"role": "user", "content": prompt}]
            body = {
                "model": model_name,
                "max_tokens": max_tokens or (extra_body.get("max_tokens", 4096) if extra_body else 4096),
                "messages": filtered_messages,
            }
            if system_content:
                body["system"] = system_content
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Connection": "close",
            }
        else:
            # OpenAI 兼容格式（默认）
            body = {
                "model": model_name,
                "messages": messages,
            }
            if max_tokens:
                body["max_tokens"] = max_tokens
            if extra_body:
                body.update(extra_body)
            headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        request_base_url, request_target = self._provider_request_location(
            provider_type,
            base_url,
            model_name,
            config.endpoint,
            api_key=api_key,
            stream=False,
        )
        
        try:
            effective_budget = _ensure_deadline(
                budget, timeout=timeout_value, started_at=started_at
            )
        except OutboundRequestError as exc:
            raise RuntimeError(exc.public_message) from None

        lifecycle = _AsyncRequestLifecycle(self, capability, started_at)
        try:
            await lifecycle.acquire(effective_budget)
            _budget_phase_timeout(effective_budget)
            data = await self._runtime_client.apost_json(
                request_base_url,
                request_target=request_target,
                headers=headers,
                json_body=body,
                allow_local=allow_local,
                budget=effective_budget,
                max_bytes=AI_JSON_MAX_BYTES,
            )
            result = self._extract_capability_content(
                data, provider_type, capability
            )
            _budget_phase_timeout(effective_budget)
        except OutboundRequestError as exc:
            outcome = "timeout" if exc.code == "outbound_timeout" else "error"
            lifecycle.finish(outcome)
            logger.warning(
                "[ModelRouter] Chat failed %s code=%s",
                capability,
                exc.code,
            )
            raise RuntimeError(exc.public_message) from None
        except asyncio.CancelledError:
            lifecycle.finish("cancelled")
            raise
        except Exception:
            lifecycle.finish("error")
            if lifecycle.active:
                raise
            raise RuntimeError("AI request failed") from None
        else:
            lifecycle.finish("success")
            return result
        finally:
            lifecycle.close()

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        *,
        budget: StreamBudget | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Async direct stream call with one logical budget and outcome."""
        started_at = time.monotonic()
        override = self.overrides.get(capability, {})
        effective_budget = _ensure_stream_budget(
            budget,
            idle_timeout=override.get("timeout") or self.timeout,
            started_at=started_at,
        )
        lifecycle = _AsyncRequestLifecycle(self, capability, started_at)
        source = self._astream_capability_impl(
            capability,
            messages,
            response_format,
            budget=effective_budget,
            lifecycle=lifecycle,
        )
        publisher = self._publish_stream_events(
            capability,
            source,
            budget=effective_budget,
            lifecycle=lifecycle,
        )
        try:
            async for event in publisher:
                yield event
        finally:
            await publisher.aclose()

    async def _astream_capability_impl(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        *,
        budget: StreamBudget,
        lifecycle: _AsyncRequestLifecycle,
    ) -> AsyncGenerator[Any, None]:
        """Async direct stream call yielding status events and chunks."""
        allow_local = self.allow_local_ai_endpoints
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})

        lb_provider: ProviderPoolConfig | None = None
        if self._lb_enabled and capability in self._provider_pools:
            lb_provider = self._select_provider_from_pool(capability)
            if lb_provider:
                logger.debug(
                    "[ModelRouter] Stream capability pool selected %s provider=%s",
                    capability,
                    lb_provider.provider_id,
                )

        if lb_provider:
            base_url = lb_provider.base_url
            api_key = lb_provider.api_key
            provider_type = lb_provider.provider_type
            model_name = lb_provider.model or override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
        else:
            credentials = self._select_runtime_credentials(
                override,
                getattr(config, "provider_type", PROVIDER_TYPE_OPENAI),
            )
            base_url = credentials.base_url
            api_key = credentials.api_key
            model_name = override.get("model") or config.model
            extra_body = override.get("extra_body") or config.extra_body
            provider_type = credentials.provider_type

        if (
            config.provider == "local"
            or not base_url
            or not api_key
            or not provider_type
        ):
            yield self._stream_error_event(
                capability, "Missing configuration for streaming"
            )
            return

        request_base_url, request_target = self._provider_request_location(
            provider_type,
            base_url,
            model_name,
            config.endpoint,
            api_key=api_key,
            stream=True,
        )

        if provider_type == PROVIDER_TYPE_GOOGLE:
            system_parts = []
            user_contents = []
            for message in messages:
                if message["role"] == "system":
                    system_parts.append({"text": message["content"]})
                else:
                    role = "user" if message["role"] == "user" else "model"
                    user_contents.append(
                        {
                            "role": role,
                            "parts": [{"text": message["content"]}],
                        }
                    )
            body: dict[str, Any] = {
                "contents": user_contents
                or [{"role": "user", "parts": [{"text": ""}]}]
            }
            if system_parts:
                body["systemInstruction"] = {"parts": system_parts}
            generation_config: dict[str, Any] = {}
            if extra_body:
                if "generationConfig" in extra_body:
                    generation_config.update(extra_body["generationConfig"])
                extra_format = extra_body.get("response_format")
                if (
                    isinstance(extra_format, dict)
                    and extra_format.get("type") == "json_object"
                ):
                    generation_config["responseMimeType"] = "application/json"
            if (
                isinstance(response_format, dict)
                and response_format.get("type") == "json_object"
            ):
                generation_config["responseMimeType"] = "application/json"
            if generation_config:
                body["generationConfig"] = generation_config
            headers = {
                "Content-Type": "application/json",
                "Connection": "close",
            }
        elif provider_type == PROVIDER_TYPE_ANTHROPIC:
            system_content = None
            filtered_messages = []
            for message in messages:
                if message["role"] == "system":
                    system_content = message["content"]
                else:
                    filtered_messages.append(message)
            body = {
                "model": model_name,
                "max_tokens": (
                    extra_body.get("max_tokens", 4096) if extra_body else 4096
                ),
                "messages": filtered_messages,
                "stream": True,
            }
            if system_content:
                body["system"] = system_content
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Connection": "close",
            }
        else:
            body = {
                "model": model_name,
                "messages": messages,
                "stream": True,
            }
            if response_format:
                body["response_format"] = response_format
            if extra_body:
                body.update(extra_body)
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Connection": "close",
            }

        yield self._stream_status_event(capability, "connecting")

        async with lifecycle.slot(budget):
            iterator: Any = None
            primary_cancel: asyncio.CancelledError | None = None
            try:
                lines = self._runtime_client.astream_lines(
                    request_base_url,
                    request_target=request_target,
                    headers=headers,
                    json_body=body,
                    allow_local=allow_local,
                    budget=budget,
                    max_bytes=STREAM_MAX_BYTES,
                    max_event_bytes=STREAM_EVENT_MAX_BYTES,
                )
                iterator = lines.__aiter__()
                try:
                    first_line = await iterator.__anext__()
                except StopAsyncIteration:
                    yield self._stream_status_event(capability, "connected")
                    _budget_phase_timeout(budget)
                    yield self._stream_status_event(capability, "completed")
                    return

                yield self._stream_status_event(capability, "connected")
                first_chunk = True

                async def incoming_lines() -> AsyncGenerator[str, None]:
                    yield first_line
                    while True:
                        try:
                            yield await iterator.__anext__()
                        except StopAsyncIteration:
                            return

                def protocol_error(code: str) -> None:
                    logger.warning(
                        "[ModelRouter] Stream capability protocol error %s "
                        "provider=%s code=%s",
                        capability,
                        provider_type,
                        code,
                    )

                if provider_type == PROVIDER_TYPE_GOOGLE:
                    decoder = json.JSONDecoder()
                    buffer = ""
                    async for line in incoming_lines():
                        if not line or line.startswith(":"):
                            continue
                        buffer += line
                        while True:
                            buffer = buffer.lstrip()
                            while buffer.startswith("[") or buffer.startswith(","):
                                buffer = buffer[1:].lstrip()
                            if buffer.startswith("]"):
                                buffer = buffer[1:].lstrip()
                                continue
                            if not buffer:
                                break
                            try:
                                chunk, consumed = decoder.raw_decode(buffer)
                            except json.JSONDecodeError:
                                break
                            buffer = buffer[consumed:]
                            if not isinstance(chunk, dict):
                                protocol_error("invalid_chunk_type")
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            if "error" in chunk:
                                protocol_error("upstream_error")
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            try:
                                candidates = chunk.get("candidates", [])
                                if not isinstance(candidates, list):
                                    raise TypeError
                                for candidate in candidates:
                                    if not isinstance(candidate, dict):
                                        raise TypeError
                                    content_obj = candidate.get("content", {})
                                    if not isinstance(content_obj, dict):
                                        raise TypeError
                                    parts = content_obj.get("parts", [])
                                    if not isinstance(parts, list):
                                        raise TypeError
                                    for part in parts:
                                        if not isinstance(part, dict):
                                            raise TypeError
                                        text = part.get("text", "")
                                        if not isinstance(text, str):
                                            raise TypeError
                                        if text:
                                            _budget_phase_timeout(budget)
                                            budget.mark_content()
                                            if first_chunk:
                                                yield self._stream_status_event(
                                                    capability, "receiving"
                                                )
                                                first_chunk = False
                                            yield text
                            except (AttributeError, TypeError):
                                protocol_error("invalid_chunk_shape")
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return

                    remaining = buffer.strip()
                    while remaining.startswith("[") or remaining.startswith(","):
                        remaining = remaining[1:].lstrip()
                    while remaining.endswith("]"):
                        remaining = remaining[:-1].rstrip()
                    if remaining:
                        protocol_error("malformed_json")
                        yield self._stream_error_event(
                            capability, _STREAM_RESPONSE_ERROR
                        )
                        return
                elif provider_type == PROVIDER_TYPE_ANTHROPIC:
                    async for line in incoming_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            protocol_error("malformed_json")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if not isinstance(event, dict):
                            protocol_error("invalid_event_type")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if event.get("type") == "error":
                            protocol_error("upstream_error")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if not isinstance(delta, dict):
                                protocol_error("invalid_delta_type")
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            text = delta.get("text", "")
                            if not isinstance(text, str):
                                protocol_error("invalid_delta_text")
                                yield self._stream_error_event(
                                    capability, _STREAM_RESPONSE_ERROR
                                )
                                return
                            if text:
                                _budget_phase_timeout(budget)
                                budget.mark_content()
                                if first_chunk:
                                    yield self._stream_status_event(
                                        capability, "receiving"
                                    )
                                    first_chunk = False
                                yield text
                else:
                    async for line in incoming_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            protocol_error("malformed_json")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if not isinstance(chunk, dict):
                            protocol_error("invalid_chunk_type")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if "error" in chunk:
                            protocol_error("upstream_error")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        try:
                            choices = chunk.get("choices", [])
                            if not isinstance(choices, list):
                                raise TypeError
                            delta = choices[0].get("delta", {}) if choices else {}
                            if not isinstance(delta, dict):
                                raise TypeError
                            content = delta.get("content", "")
                            if not isinstance(content, str):
                                raise TypeError
                        except (AttributeError, TypeError):
                            protocol_error("invalid_chunk_shape")
                            yield self._stream_error_event(
                                capability, _STREAM_RESPONSE_ERROR
                            )
                            return
                        if content:
                            _budget_phase_timeout(budget)
                            budget.mark_content()
                            if first_chunk:
                                yield self._stream_status_event(
                                    capability, "receiving"
                                )
                                first_chunk = False
                            yield content

                _budget_phase_timeout(budget)
                yield self._stream_status_event(capability, "completed")
            except asyncio.CancelledError as exc:
                primary_cancel = exc
                raise
            except OutboundRequestError as exc:
                logger.warning(
                    "[ModelRouter] Async capability stream failed %s code=%s",
                    capability,
                    exc.code,
                )
                if exc.code == "outbound_timeout" and budget.content_started:
                    yield self._stream_status_event(
                        capability,
                        "interrupted",
                        reason=exc.code,
                        partial=True,
                    )
                else:
                    yield self._stream_error_event(
                        capability, exc.public_message, code=exc.code
                    )
                return
            except Exception as exc:
                logger.error(
                    "[ModelRouter] Async capability stream failed %s type=%s",
                    capability,
                    type(exc).__name__,
                )
                yield self._stream_error_event(capability, _STREAM_RESPONSE_ERROR)
                return
            finally:
                if iterator is not None:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        try:
                            await close()
                        except asyncio.CancelledError:
                            if primary_cancel is None:
                                raise
                        except OutboundRequestError as exc:
                            logger.warning(
                                "[ModelRouter] Capability stream close failed "
                                "%s code=%s",
                                capability,
                                exc.code,
                            )
                        except Exception as exc:
                            logger.warning(
                                "[ModelRouter] Capability stream close failed "
                                "%s type=%s",
                                capability,
                                type(exc).__name__,
                            )
    def _extract_capability_content(
        self,
        data: dict[str, Any],
        provider_type: str,
        capability: str,
    ) -> str:
        try:
            return self._extract_primary_content(data, provider_type)
        except _PrimaryResponseError:
            logger.warning(
                "[ModelRouter] Capability response invalid %s code=invalid_response_shape",
                capability,
            )
            raise RuntimeError(_PRIMARY_RESPONSE_ERROR) from None

    def _extract_primary_content(
        self, data: dict[str, Any], provider_type: str
    ) -> str:
        """Extract content from a validated primary-invocation response shape."""
        if not isinstance(data, dict) or "error" in data:
            raise _PrimaryResponseError

        if provider_type == PROVIDER_TYPE_ANTHROPIC:
            blocks = data.get("content")
            if not isinstance(blocks, list) or not blocks:
                raise _PrimaryResponseError
            texts: list[str] = []
            for block in blocks:
                if not isinstance(block, dict):
                    raise _PrimaryResponseError
                if block.get("type") != "text":
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    raise _PrimaryResponseError
                texts.append(text)
            if not texts:
                raise _PrimaryResponseError
            return "\n".join(texts)

        if provider_type == PROVIDER_TYPE_GOOGLE:
            candidates = data.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise _PrimaryResponseError
            candidate = candidates[0]
            if not isinstance(candidate, dict):
                raise _PrimaryResponseError
            content = candidate.get("content")
            if not isinstance(content, dict):
                raise _PrimaryResponseError
            parts = content.get("parts")
            if not isinstance(parts, list) or not parts:
                raise _PrimaryResponseError
            texts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    raise _PrimaryResponseError
                if "text" not in part:
                    continue
                text = part["text"]
                if not isinstance(text, str):
                    raise _PrimaryResponseError
                texts.append(text)
            if not texts:
                raise _PrimaryResponseError
            return "\n".join(texts)

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise _PrimaryResponseError
        choice = choices[0]
        if not isinstance(choice, dict):
            raise _PrimaryResponseError
        message = choice.get("message")
        if not isinstance(message, dict):
            raise _PrimaryResponseError
        content = message.get("content")
        if not isinstance(content, str):
            raise _PrimaryResponseError
        return content

    def _extract_content(self, data: dict, provider_type: str) -> str:
        """从不同API类型的响应中提取内容"""
        try:
            if provider_type == PROVIDER_TYPE_ANTHROPIC:
                # Claude API 响应格式
                content_blocks = data.get("content", [])
                if content_blocks:
                    texts = []
                    for block in content_blocks:
                        if block.get("type") == "text":
                            texts.append(block.get("text", ""))
                    return "\n".join(texts)
                logger.warning("[ModelRouter] Anthropic response has no content")
                return ""
            elif provider_type == PROVIDER_TYPE_GOOGLE:
                # Gemini API 响应格式
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        # 合并所有 parts 的文本
                        texts = [p.get("text", "") for p in parts if p.get("text")]
                        if texts:
                            return "\n".join(texts)
                # 如果没有 candidates，检查是否有错误
                error = data.get("error", {})
                if error:
                    logger.error("[ModelRouter] Google response reported an upstream error")
                else:
                    logger.warning("[ModelRouter] Google response has no content")
                return ""
            else:
                # OpenAI 兼容格式（默认）
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
        except Exception as exc:
            logger.warning(
                "[ModelRouter] Response parsing failed provider=%s type=%s",
                provider_type,
                type(exc).__name__,
            )
            return str(data)

    def _parse_content(self, content: str) -> Any:
        """解析AI返回的内容，尝试提取JSON或返回原始文本"""
        # 如果内容为空，直接返回空字符串
        if not content or not content.strip():
            logger.debug("[ModelRouter] AI返回内容为空")
            return ""
            
        try:
            # 尝试清理常见的JSON格式问题
            cleaned = content.strip()
            
            # 移除markdown代码块标记
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # 如果清理后为空，返回原始内容
            if not cleaned:
                return content
            
            # 如果是markdown格式的文本（以#或##开头），这可能是纯文本响应
            if cleaned.startswith("#"):
                # 查找JSON代码块
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(1)
                else:
                    # 尝试查找任何JSON对象
                    json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', content, re.DOTALL)
                    if json_match:
                        cleaned = json_match.group(1)
                    else:
                        # 这是纯Markdown文本，直接返回
                        logger.info(f"[ModelRouter] 识别为Markdown格式，直接返回文本内容")
                        return content
            
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[ModelRouter] JSON parsing failed type=%s",
                type(exc).__name__,
            )
            
            # 最后尝试：查找任何可能的JSON对象
            import re
            json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
            matches = re.finditer(json_pattern, content, re.DOTALL)
            for match in matches:
                try:
                    potential_json = match.group(0)
                    parsed = json.loads(potential_json)
                    logger.info(f"[ModelRouter] 成功从文本中提取JSON")
                    return parsed
                except json.JSONDecodeError:
                    continue
            
            # 完全失败，返回原始文本（用于非JSON响应的情况）
            logger.info(f"[ModelRouter] 无法解析为JSON，返回原始文本内容")
            return content


async def staggered_gather(
    coroutines: list,
    interval: float = 2.0,
    max_concurrent: int = 10,  # 【提升】默认并发从 3 提升到 10
    task_name: str = "任务",
    event_callback: Callable[[str, str, str], None] | None = None,  # 【新增】心跳回调
) -> list:
    """
    间隔并行执行协程，避免同时发送过多请求。
    
    Args:
        coroutines: 协程列表
        interval: 每个任务启动的间隔秒数
        max_concurrent: 最大同时执行的任务数
        task_name: 任务名称（用于日志）
        event_callback: 事件回调函数，签名 (event_type, message, category)
    
    Returns:
        所有任务的结果列表（保持原始顺序）
    """
    if not coroutines:
        return []
    
    def emit_event(event_type: str, message: str, category: str = "AI"):
        if event_callback:
            try:
                # 尝试以3参数方式调用 (event_type, message, category)
                try:
                    event_callback(event_type, message, category)
                except TypeError:
                    # 如果失败，回退到1参数方式
                    event_callback(message)
            except Exception:
                pass
    
    results = [None] * len(coroutines)
    completed_count = 0
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_with_delay(idx: int, coro):
        nonlocal completed_count
        # 间隔延迟：每个任务按索引递增延迟
        delay = idx * interval
        if delay > 0:
            await asyncio.sleep(delay)
        
        async with semaphore:
            start_time = time.time()
            logger.debug(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 开始执行")
            emit_event("ai_parallel_task_start", f"🚀 {task_name} {idx + 1}/{len(coroutines)} 开始", "AI")
            try:
                result = await coro
                results[idx] = result
                completed_count += 1
                elapsed = time.time() - start_time
                logger.debug(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 完成 (耗时{elapsed:.1f}s)")
                emit_event("ai_parallel_task_complete", f"✅ {task_name} {idx + 1}/{len(coroutines)} 完成 ({completed_count}/{len(coroutines)})", "AI")
            except Exception as e:
                elapsed = time.time() - start_time
                logger.warning(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 失败 (耗时{elapsed:.1f}s): {e}")
                results[idx] = e
                completed_count += 1
                emit_event("ai_parallel_task_error", f"❌ {task_name} {idx + 1}/{len(coroutines)} 失败 ({completed_count}/{len(coroutines)})", "AI")
    
    # 创建所有任务
    tasks = [
        asyncio.create_task(run_with_delay(idx, coro))
        for idx, coro in enumerate(coroutines)
    ]
    
    # 发送开始事件
    emit_event("ai_parallel_batch_start", f"🔄 开始 {len(coroutines)} 个{task_name}（并发{max_concurrent}）", "AI")
    logger.info(f"[间隔并行] 开始执行 {len(coroutines)} 个{task_name}（间隔{interval}s，最大并发{max_concurrent}）")
    
    # 【新增】心跳任务：定期发送进度
    heartbeat_task = None
    if event_callback:
        async def heartbeat_loop():
            while completed_count < len(coroutines):
                await asyncio.sleep(3.0)  # 每3秒发送一次心跳
                if completed_count < len(coroutines):
                    emit_event("ai_parallel_heartbeat", f"💓 {task_name} 进度: {completed_count}/{len(coroutines)}", "AI")
        heartbeat_task = asyncio.create_task(heartbeat_loop())
    
    await asyncio.gather(*tasks)
    
    # 停止心跳
    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    
    # 统计结果
    success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    timeout_count = sum(1 for r in results if isinstance(r, TimeoutError))
    error_count = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, TimeoutError))
    logger.info(f"[间隔并行] 全部 {len(coroutines)} 个{task_name}执行完成 (成功:{success_count} 超时:{timeout_count} 错误:{error_count})")
    emit_event("ai_parallel_batch_complete", f"✅ 全部 {len(coroutines)} 个{task_name}完成 (成功:{success_count})", "AI")
    
    return results
