from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    provider: str
    model: str
    endpoint: str | None = None
    extra_body: dict[str, Any] | None = None


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
    ) -> None:
        self.routes = defaults or {}
        self.prompts: dict[str, str] = {}
        self.api_base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.overrides: dict[str, dict[str, Any]] = {}
        self.max_retries = max(1, max_retries)
        self.use_keepalive = use_keepalive  # 连接复用开关
        
        # 并发控制
        self.concurrency_limit = concurrency_limit
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self._client_session: httpx.AsyncClient | None = None
        
        # 【诊断日志】并发追踪
        self._active_requests = 0  # 当前活跃请求数
        self._queued_requests = 0  # 当前排队请求数
        self._total_requests = 0   # 总请求数
        self._total_timeouts = 0   # 总超时数
        self._request_stats: dict[str, dict] = {}  # 每个 capability 的统计
        self._last_summary_time = 0  # 上次输出摘要的时间
        self._summary_interval = 10  # 摘要输出间隔（秒）

    def set_concurrency_limit(self, limit: int) -> None:
        """Update concurrency limit (requires recreating semaphore)"""
        self.concurrency_limit = limit
        # Semaphore cannot be resized, so we replace it.
        # Note: This is safe enough for this app's usage pattern.
        self._semaphore = asyncio.Semaphore(limit)
        logger.info(f"[ModelRouter] Concurrency limit set to {limit}")
    
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
            "timeout_rate": f"{(self._total_timeouts / max(self._total_requests, 1)) * 100:.1f}%",
            "request_stats": dict(self._request_stats),
        }
    
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

    def capabilities(self) -> list[str]:
        return list(self.routes.keys())

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy init async client"""
        if self._client_session is None or self._client_session.is_closed:
            if self.use_keepalive:
                # 高效并发模式：启用连接复用
                # 适用于稳定的 API 服务（如 OpenAI 官方）
                limits = httpx.Limits(
                    max_keepalive_connections=self.concurrency_limit,
                    max_connections=self.concurrency_limit + 10
                )
                self._client_session = httpx.AsyncClient(
                    timeout=self.timeout, 
                    limits=limits,
                )
                logger.info("[ModelRouter] 客户端使用高效并发模式（keep-alive 启用）")
            else:
                # 安全模式：禁用连接复用，避免某些 API 服务的连接卡住问题
                # 适用于硅基流动等第三方 API
                limits = httpx.Limits(
                    max_keepalive_connections=0,  # 禁用 keep-alive
                    max_connections=self.concurrency_limit + 10
                )
                self._client_session = httpx.AsyncClient(
                    timeout=self.timeout, 
                    limits=limits,
                    http2=False,  # 禁用 HTTP/2
                )
                logger.debug("[ModelRouter] 客户端使用安全模式（keep-alive 禁用）")
        return self._client_session

    async def reset_client(self):
        """强制重置客户端会话"""
        old_client = self._client_session
        self._client_session = None  # 先置空，防止其他协程使用
        
        if old_client and not old_client.is_closed:
            try:
                await old_client.aclose()
                logger.info("[ModelRouter] Client session closed successfully")
            except Exception as e:
                logger.warning(f"[ModelRouter] Error closing client: {e}")
        
        # 重置计数器，防止卡住
        self._active_requests = 0
        self._queued_requests = 0
        logger.info("[ModelRouter] Client session reset, counters cleared")

    def _prepare_request(
        self, capability: str, payload: dict[str, Any], use_format_placeholder: bool = True
    ) -> dict[str, Any]:
        """Prepare request data, shared by sync and async invoke"""
        config = self.resolve(capability)
        prompt_template = self.prompts.get(capability)
        override = self.overrides.get(capability, {})
        
        # 优先使用 override 中的配置（来自 UI 设置的默认服务商）
        base_url = (override.get("base_url") or self.api_base_url)
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        # 判断是否有有效的 API 凭据（来自 override 或全局配置）
        has_valid_credentials = bool(base_url and api_key)
        
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
        
        endpoint = config.endpoint or "/chat/completions"
        # 【修复】智能处理 endpoint 路径
        # 大多数本地 LLM 服务（LMStudio、Ollama 等）需要 /v1/chat/completions
        # 而云端服务的 base_url 通常已经包含 /v1（如 https://api.deepseek.com/v1）
        base_url_stripped = base_url.rstrip('/')
        if not base_url_stripped.endswith('/v1') and endpoint == "/chat/completions":
            # base_url 不以 /v1 结尾，自动添加 /v1 前缀
            endpoint = "/v1/chat/completions"
        url = f"{base_url_stripped}{endpoint}"
        
        user_content = json.dumps(payload, ensure_ascii=False, indent=2)
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": formatted_prompt or "You are an AI assistant."},
                {"role": "user", "content": user_content},
            ],
        }
        
        if extra_body:
            body.update(extra_body)
            
        return {
            "is_local": False,
            "url": url,
            "body": body,
            "headers": {"Authorization": f"Bearer {api_key}"},
            "timeout": timeout,
            "meta": {
                "provider": config.provider,
                "model": model_name,
                "prompt": formatted_prompt,
                "payload": payload,
            }
        }

    def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Sync invocation (blocking)"""
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            logger.debug(f"[ModelRouter] Local mode: {req['result']}")
            return req["result"]
            
        try:
            logger.debug(f"[ModelRouter] Sync invoke {capability} (provider={req['meta']['provider']})")
            response = httpx.post(
                req["url"],
                json=req["body"],
                headers=req["headers"],
                timeout=req["timeout"],
            )
            response.raise_for_status()
            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            parsed_content = self._parse_content(content)
            
            return {
                **req["meta"],
                "content": parsed_content,
                "raw": data,
            }
        except httpx.HTTPError as exc:
            return {
                **req["meta"],
                "error": str(exc),
            }

    async def ainvoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Async invocation (non-blocking) with semaphore"""
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            return req["result"]

        # 【诊断】记录请求开始
        self._total_requests += 1
        self._queued_requests += 1
        request_id = self._total_requests
        queue_start = time.time()
        
        # 初始化 capability 统计
        if capability not in self._request_stats:
            self._request_stats[capability] = {"total": 0, "success": 0, "timeout": 0, "error": 0, "avg_time": 0}
        self._request_stats[capability]["total"] += 1
        
        self._log_diagnostics("排队", capability, f"请求#{request_id}")

        last_error = "unknown error"
        for attempt in range(self.max_retries):
            async with self._semaphore:
                # 【诊断】获取到信号量，开始处理
                queue_time = time.time() - queue_start
                self._queued_requests -= 1
                self._active_requests += 1
                process_start = time.time()
                
                self._log_diagnostics("开始处理", capability, f"请求#{request_id} 排队耗时:{queue_time:.2f}s 尝试:{attempt + 1}/{self.max_retries}")
                
                try:
                    timeout = req.get("timeout") or self.timeout
                    headers = {**req["headers"], "Connection": "close"}
                    
                    # 【核心修复】每次请求使用独立的临时客户端
                    # 避免共享连接池导致的各种卡住问题
                    async with httpx.AsyncClient(timeout=timeout, http2=False) as client:
                        response = await client.post(
                            req["url"],
                            json=req["body"],
                            headers=headers,
                        )
                        response.raise_for_status()
                        data = response.json()
                    
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    parsed_content = self._parse_content(content)
                    
                    # 【诊断】请求成功
                    process_time = time.time() - process_start
                    self._active_requests -= 1
                    self._request_stats[capability]["success"] += 1
                    # 更新平均时间
                    stats = self._request_stats[capability]
                    stats["avg_time"] = (stats["avg_time"] * (stats["success"] - 1) + process_time) / stats["success"]
                    
                    self._log_diagnostics("✅ 成功", capability, f"请求#{request_id} 处理耗时:{process_time:.2f}s")
                    
                    return {
                        **req["meta"],
                        "content": parsed_content,
                        "raw": data,
                    }
                except httpx.TimeoutException as te:
                    # 超时处理 - httpx原生超时会正确释放连接
                    last_error = f"timeout after {timeout}s"
                    self._total_timeouts += 1
                    self._request_stats[capability]["timeout"] += 1
                    process_time = time.time() - process_start
                    total_wait = time.time() - queue_start
                    
                    # 详细的超时日志
                    logger.error("=" * 60)
                    logger.error(f"⏱️  请求超时详情 - {capability}")
                    logger.error(f"   请求ID: #{request_id} | 尝试: {attempt + 1}/{self.max_retries}")
                    logger.error(f"   超时设置: {timeout}s | 实际等待: {process_time:.1f}s | 总耗时: {total_wait:.1f}s")
                    logger.error(f"   超时类型: {type(te).__name__}")
                    logger.error(f"   当前状态: 活跃={self._active_requests} 排队={self._queued_requests} 超时率={self._total_timeouts}/{self._total_requests}")
                    if self._active_requests >= self.concurrency_limit:
                        logger.error(f"   ⚠️ 并发已满！可能是请求太多或API响应太慢")
                    logger.error("=" * 60)
                    
                    self._active_requests -= 1
                    self._log_diagnostics("⏱️ 超时", capability, f"请求#{request_id}")
                    
                    # 【修复】连续多次超时后重置客户端，清理可能的问题连接
                    if attempt == self.max_retries - 1 and self._total_timeouts > 3:
                        logger.warning(f"[ModelRouter] 连续超时次数过多({self._total_timeouts})，重置客户端连接")
                        asyncio.create_task(self.reset_client())
                        
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    self._active_requests -= 1
                    self._request_stats[capability]["error"] += 1
                    self._log_diagnostics("❌ HTTP错误", capability, f"请求#{request_id} {exc}")
                except Exception as e:
                    last_error = str(e)
                    self._active_requests -= 1
                    self._request_stats[capability]["error"] += 1
                    self._log_diagnostics("❌ 异常", capability, f"请求#{request_id} {e}")
                    
            if attempt < self.max_retries - 1:
                self._queued_requests += 1  # 重试时重新排队
                # 【优化】429 Rate Limit 需要更长的退避时间
                sleep_time = min(2.0, 0.5 * (attempt + 1))
                if "429" in last_error:
                    sleep_time = 2.0 * (attempt + 1) # 2s, 4s, 6s...
                    logger.warning(f"[ModelRouter] 触发429限流，等待 {sleep_time}s 后重试...")
                
                await asyncio.sleep(sleep_time)
        
        return {
            **req["meta"],
            "error": f"{last_error} (after {self.max_retries} attempts)",
        }

    def _stream_status_event(self, capability: str, state: str, **extra) -> dict[str, Any]:
        event = {
            "type": "status",
            "state": state,
            "capability": capability,
            "timestamp": time.time(),
        }
        event.update(extra)
        return event

    def _stream_error_event(self, capability: str, message: str) -> dict[str, Any]:
        return {
            "type": "error",
            "message": message,
            "capability": capability,
            "timestamp": time.time(),
        }

    async def astream(self, capability: str, payload: dict[str, Any]) -> AsyncGenerator[Any, None]:
        """Async streaming invocation. Yields status/error dicts and plain chunks."""
        req = self._prepare_request(capability, payload)
        if req["is_local"]:
            yield self._stream_error_event(capability, "Streaming not supported for local provider")
            return

        req["body"]["stream"] = True
        yield self._stream_status_event(capability, "connecting")

        async with self._semaphore:
            logger.info(f"[ModelRouter] Async stream {capability} start")
            timeout = req.get("timeout") or self.timeout
            headers = {**req["headers"], "Connection": "close"}
            
            try:
                # 【核心修复】使用临时客户端，避免共享连接池卡住
                async with httpx.AsyncClient(timeout=timeout + 30, http2=False) as client:
                    async with client.stream(
                        "POST",
                        req["url"],
                        json=req["body"],
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        yield self._stream_status_event(capability, "connected")
                        first_chunk = True
                        
                        # 逐行读取，带超时保护
                        iterator = response.aiter_lines()
                        while True:
                            try:
                                line = await asyncio.wait_for(iterator.__anext__(), timeout=60.0)
                            except StopAsyncIteration:
                                break
                            except asyncio.TimeoutError:
                                logger.error(f"[ModelRouter] Stream read timeout for {capability}")
                                yield self._stream_error_event(capability, "Read timeout")
                                break
                                
                            if line.startswith("data: "):
                                data = line[6:]
                                if data.strip() == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        if first_chunk:
                                            yield self._stream_status_event(capability, "receiving")
                                            first_chunk = False
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                        yield self._stream_status_event(capability, "completed")
            except Exception as e:
                logger.error(f"[ModelRouter] Async stream error {capability}: {e}")
                yield self._stream_error_event(capability, str(e))

    def call_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Sync direct call"""
        # Simplified logic reusing parts of invoke would be better, but keeping specific call_capability logic
        # similar to original for compatibility
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        base_url = override.get("base_url") or self.api_base_url
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        if config.provider == "local" or not base_url or not api_key:
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        endpoint = config.endpoint or "/chat/completions"
        # 【修复】智能处理 endpoint 路径
        base_url_stripped = base_url.rstrip('/')
        if not base_url_stripped.endswith('/v1') and endpoint == "/chat/completions":
            endpoint = "/v1/chat/completions"
        url = f"{base_url_stripped}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
        
        # 【修复】添加 Connection: close 头
        headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def acall_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Async direct call"""
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        base_url = override.get("base_url") or self.api_base_url
        api_key = override.get("api_key") or self.api_key
        timeout_value = override.get("timeout") or self.timeout or 60  # 确保有默认值
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        if config.provider == "local" or not base_url or not api_key:
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        endpoint = config.endpoint or "/chat/completions"
        # 【修复】智能处理 endpoint 路径
        base_url_stripped = base_url.rstrip('/')
        if not base_url_stripped.endswith('/v1') and endpoint == "/chat/completions":
            endpoint = "/v1/chat/completions"
        url = f"{base_url_stripped}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
            
        # 安全模式下添加 Connection: close 头
        headers = {"Authorization": f"Bearer {api_key}"}
        if not self.use_keepalive:
            headers["Connection"] = "close"
        
        logger.debug(f"[acall_capability] {capability} -> {url} (timeout={timeout_value}s)")
        
        async with self._semaphore:
            # 【核心修复】每次请求使用独立的临时客户端
            headers["Connection"] = "close"
            try:
                async with httpx.AsyncClient(timeout=timeout_value, http2=False) as client:
                    response = await client.post(url, json=body, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except httpx.TimeoutException:
                logger.error(f"[acall_capability] {capability} timeout after {timeout_value}s")
                raise RuntimeError(
                    f"Async capability {capability} timed out after {timeout_value}s"
                ) from None
            
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def chat(
        self,
        prompt: str,
        capability: str = "turn_report",
        system_prompt: str | None = None,
        max_tokens: int | None = None,
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
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        base_url = override.get("base_url") or self.api_base_url
        api_key = override.get("api_key") or self.api_key
        timeout_value = override.get("timeout") or self.timeout or 60
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        # 检查是否为本地模式（无 API 配置）
        if config.provider == "local" or not base_url or not api_key:
            logger.warning(f"[chat] {capability} 无 API 配置，返回占位符响应")
            return f"[本地模式] 无法生成响应: {prompt[:100]}..."
        
        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # 构建请求
        endpoint = config.endpoint or "/chat/completions"
        base_url_stripped = base_url.rstrip('/')
        if not base_url_stripped.endswith('/v1') and endpoint == "/chat/completions":
            endpoint = "/v1/chat/completions"
        url = f"{base_url_stripped}{endpoint}"
        
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if extra_body:
            body.update(extra_body)
        
        headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        logger.debug(f"[chat] {capability} -> {url} (timeout={timeout_value}s)")
        
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=timeout_value, http2=False) as client:
                    response = await client.post(url, json=body, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except httpx.TimeoutException:
                logger.error(f"[chat] {capability} timeout after {timeout_value}s")
                raise RuntimeError(f"Chat request timed out after {timeout_value}s") from None
            except httpx.HTTPError as e:
                logger.error(f"[chat] {capability} HTTP error: {e}")
                raise RuntimeError(f"Chat request failed: {e}") from None
            
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Async direct stream call yielding status events and chunks."""
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        base_url = override.get("base_url") or self.api_base_url
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        if config.provider == "local" or not base_url or not api_key:
            yield self._stream_error_event(capability, "Missing configuration for streaming")
            return
        
        endpoint = config.endpoint or "/chat/completions"
        # 【修复】智能处理 endpoint 路径
        base_url_stripped = base_url.rstrip('/')
        if not base_url_stripped.endswith('/v1') and endpoint == "/chat/completions":
            endpoint = "/v1/chat/completions"
        url = f"{base_url_stripped}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
            
        headers = {"Authorization": f"Bearer {api_key}", "Connection": "close"}
        
        async with self._semaphore:
            try:
                # 【核心修复】使用临时客户端，避免共享连接池卡住
                async with httpx.AsyncClient(timeout=timeout + 30, http2=False) as client:
                    async with client.stream(
                        "POST", 
                        url, 
                        json=body, 
                        headers=headers, 
                    ) as response:
                        response.raise_for_status()
                        yield self._stream_status_event(capability, "connected")
                        first_chunk = True
                        
                        iterator = response.aiter_lines()
                        while True:
                            try:
                                line = await asyncio.wait_for(iterator.__anext__(), timeout=60.0)
                            except StopAsyncIteration:
                                break
                            except asyncio.TimeoutError:
                                logger.error(f"[ModelRouter] Stream capability read timeout for {capability}")
                                yield self._stream_error_event(capability, "Read timeout")
                                break
                            
                            if line.startswith("data: "):
                                data = line[6:]
                                if data.strip() == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        if first_chunk:
                                            yield self._stream_status_event(capability, "receiving")
                                            first_chunk = False
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                        yield self._stream_status_event(capability, "completed")
            except Exception as e:
                logger.error(f"[ModelRouter] Async capability stream error {capability}: {e}")
                yield self._stream_error_event(capability, str(e))

    def _parse_content(self, content: str) -> Any:
        """解析AI返回的内容，尝试提取JSON或返回原始文本"""
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
            
            # 如果是markdown格式的文本（以#或##开头），这可能是纯文本响应
            if cleaned.startswith("#"):
                # 查找JSON代码块
                import re
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
        except json.JSONDecodeError as e:
            logger.warning(f"[ModelRouter] JSON解析失败: {e}, 内容前200字符: {content[:200]}")
            
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
    max_concurrent: int = 3,
    task_name: str = "任务",
    task_timeout: float = 90.0,  # 【新增】单任务超时
) -> list:
    """
    间隔并行执行协程，避免同时发送过多请求。
    
    Args:
        coroutines: 协程列表
        interval: 每个任务启动的间隔秒数
        max_concurrent: 最大同时执行的任务数
        task_name: 任务名称（用于日志）
        task_timeout: 单个任务的超时时间（秒）
    
    Returns:
        所有任务的结果列表（保持原始顺序）
    """
    if not coroutines:
        return []
    
    results = [None] * len(coroutines)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_with_delay(idx: int, coro):
        # 间隔延迟：每个任务按索引递增延迟
        delay = idx * interval
        if delay > 0:
            await asyncio.sleep(delay)
        
        async with semaphore:
            start_time = time.time()
            logger.debug(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 开始执行")
            try:
                # 【关键修复】为每个任务添加超时保护
                result = await asyncio.wait_for(coro, timeout=task_timeout)
                results[idx] = result
                elapsed = time.time() - start_time
                logger.debug(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 完成 (耗时{elapsed:.1f}s)")
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.error(f"[间隔并行] ⏱️ {task_name} {idx + 1}/{len(coroutines)} 超时 (超过{task_timeout}s，实际{elapsed:.1f}s)")
                results[idx] = TimeoutError(f"{task_name} {idx + 1} 超时")
            except Exception as e:
                elapsed = time.time() - start_time
                logger.warning(f"[间隔并行] {task_name} {idx + 1}/{len(coroutines)} 失败 (耗时{elapsed:.1f}s): {e}")
                results[idx] = e
    
    # 创建所有任务
    tasks = [
        asyncio.create_task(run_with_delay(idx, coro))
        for idx, coro in enumerate(coroutines)
    ]
    
    # 等待所有任务完成
    logger.info(f"[间隔并行] 开始执行 {len(coroutines)} 个{task_name}（间隔{interval}s，最大并发{max_concurrent}，单任务超时{task_timeout}s）")
    await asyncio.gather(*tasks)
    
    # 统计结果
    success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    timeout_count = sum(1 for r in results if isinstance(r, TimeoutError))
    error_count = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, TimeoutError))
    logger.info(f"[间隔并行] 全部 {len(coroutines)} 个{task_name}执行完成 (成功:{success_count} 超时:{timeout_count} 错误:{error_count})")
    
    return results
