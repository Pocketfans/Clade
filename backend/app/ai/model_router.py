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
    ) -> None:
        self.routes = defaults or {}
        self.prompts: dict[str, str] = {}
        self.api_base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.overrides: dict[str, dict[str, Any]] = {}
        self.max_retries = max(1, max_retries)
        
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
            self._client_session = httpx.AsyncClient(timeout=self.timeout)
        return self._client_session

    async def close(self):
        if self._client_session and not self._client_session.is_closed:
            await self._client_session.aclose()

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
        url = f"{base_url.rstrip('/')}{endpoint}"
        
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
            print(f"[ModelRouter] Local mode: {req['result']}")
            return req["result"]
            
        try:
            print(f"[ModelRouter] Sync invoke {capability} (provider={req['meta']['provider']})")
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
                    client = await self._get_client()
                    timeout = req.get("timeout") or self.timeout
                    post_coro = client.post(
                        req["url"],
                        json=req["body"],
                        headers=req["headers"],
                        timeout=timeout,
                    )
                    try:
                        response = await asyncio.wait_for(post_coro, timeout=timeout)
                    except asyncio.TimeoutError:
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
                        logger.error(f"   当前状态: 活跃={self._active_requests} 排队={self._queued_requests} 超时率={self._total_timeouts}/{self._total_requests}")
                        if self._active_requests >= self.concurrency_limit:
                            logger.error(f"   ⚠️ 并发已满！可能是请求太多或API响应太慢")
                        logger.error("=" * 60)
                        
                        self._log_diagnostics("⏱️ 超时", capability, f"请求#{request_id}")
                        response = None
                    
                    if response is None:
                        self._active_requests -= 1
                        raise asyncio.TimeoutError(last_error)
                    
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
                except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                    last_error = str(exc)
                    self._active_requests -= 1
                    self._request_stats[capability]["error"] += 1
                    self._log_diagnostics("❌ 错误", capability, f"请求#{request_id} {exc}")
                except Exception as e:
                    last_error = str(e)
                    self._active_requests -= 1
                    self._request_stats[capability]["error"] += 1
                    self._log_diagnostics("❌ 异常", capability, f"请求#{request_id} {e}")
                    
            if attempt < self.max_retries - 1:
                self._queued_requests += 1  # 重试时重新排队
                await asyncio.sleep(min(1.0, 0.3 * (attempt + 1)))
        
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
            client = await self._get_client()
            logger.info(f"[ModelRouter] Async stream {capability} start")
            timeout = req.get("timeout") or self.timeout
            
            try:
                async with client.stream(
                    "POST",
                    req["url"],
                    json=req["body"],
                    headers=req["headers"],
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    yield self._stream_status_event(capability, "connected")
                    first_chunk = True
                    async for line in response.aiter_lines():
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
        url = f"{base_url.rstrip('/')}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
        
        headers = {"Authorization": f"Bearer {api_key}"}
        
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
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body
        
        if config.provider == "local" or not base_url or not api_key:
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        endpoint = config.endpoint or "/chat/completions"
        url = f"{base_url.rstrip('/')}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
            
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with self._semaphore:
            client = await self._get_client()
            post_coro = client.post(url, json=body, headers=headers, timeout=timeout)
            try:
                response = await asyncio.wait_for(post_coro, timeout=timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Async capability {capability} timed out after {timeout}s"
                ) from None
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

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
        url = f"{base_url.rstrip('/')}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True
        }
        if response_format:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
            
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with self._semaphore:
            client = await self._get_client()
            try:
                async with client.stream(
                    "POST", 
                    url, 
                    json=body, 
                    headers=headers, 
                    timeout=timeout
                ) as response:
                    response.raise_for_status()
                    yield self._stream_status_event(capability, "connected")
                    first_chunk = True
                    async for line in response.aiter_lines():
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
