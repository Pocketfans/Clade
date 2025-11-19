from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

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
        concurrency_limit: int = 15,
    ) -> None:
        self.routes = defaults or {}
        self.prompts: dict[str, str] = {}
        self.api_base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.overrides: dict[str, dict[str, Any]] = {}
        
        # 并发控制
        self.concurrency_limit = concurrency_limit
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self._client_session: httpx.AsyncClient | None = None

    def set_concurrency_limit(self, limit: int) -> None:
        """Update concurrency limit (requires recreating semaphore)"""
        self.concurrency_limit = limit
        # Semaphore cannot be resized, so we replace it.
        # Note: This is safe enough for this app's usage pattern.
        self._semaphore = asyncio.Semaphore(limit)
        logger.info(f"[ModelRouter] Concurrency limit set to {limit}")

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
        
        base_url = (override.get("base_url") or self.api_base_url)
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        extra_body = override.get("extra_body") or config.extra_body

        # Format prompt
        formatted_prompt = prompt_template
        if prompt_template and use_format_placeholder:
            try:
                formatted_prompt = prompt_template.format(**payload)
            except (KeyError, ValueError) as e:
                logger.warning(f"[ModelRouter] Prompt format failed ({capability}): {e}")
                formatted_prompt = prompt_template
        
        if config.provider == "local" or not base_url or not api_key:
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

        async with self._semaphore:
            try:
                client = await self._get_client()
                logger.info(f"[ModelRouter] Async invoke {capability} start (limit={self.concurrency_limit})")
                response = await client.post(
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
                logger.error(f"[ModelRouter] Async error {capability}: {exc}")
                return {
                    **req["meta"],
                    "error": str(exc),
                }
            except Exception as e:
                logger.error(f"[ModelRouter] Async unexpected error {capability}: {e}")
                return {
                    **req["meta"],
                    "error": str(e),
                }

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
            response = await client.post(url, json=body, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _parse_content(self, content: str) -> Any:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"text": content}
