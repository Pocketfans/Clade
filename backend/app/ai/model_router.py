from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx


@dataclass
class ModelConfig:
    provider: str
    model: str
    endpoint: str | None = None


class ModelRouter:
    """Keeps routing between providers/models configurable per capability."""

    def __init__(
        self,
        defaults: dict[str, ModelConfig] | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.routes = defaults or {}
        self.prompts: dict[str, str] = {}
        self.api_base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.overrides: dict[str, dict[str, Any]] = {}

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

    def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = self.resolve(capability)
        prompt_template = self.prompts.get(capability)
        override = self.overrides.get(capability, {})
        base_url = (override.get("base_url") or self.api_base_url)
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        
        # 调试输出
        print(f"[ModelRouter] 调用capability={capability}, provider={config.provider}")
        print(f"[ModelRouter] override存在={capability in self.overrides}, base_url={'***' if base_url else None}, api_key={'***' if api_key else None}")
        
        # 使用 payload 填充 prompt 模板中的占位符
        formatted_prompt = prompt_template
        if prompt_template:
            try:
                formatted_prompt = prompt_template.format(**payload)
            except (KeyError, ValueError) as e:
                # 如果格式化失败，使用原始 prompt（可能 prompt 不包含占位符）
                print(f"[ModelRouter] Prompt 格式化失败 ({capability}): {e}")
                formatted_prompt = prompt_template
        
        if config.provider == "local" or not base_url or not api_key:
            print(f"[ModelRouter] 使用本地模式: provider={config.provider}, base_url={base_url is not None}, api_key={api_key is not None}")
            return {
                "provider": config.provider,
                "model": model_name,
                "prompt": formatted_prompt,
                "payload": payload,
            }
        # 修复：如果base_url已经包含/v1，则endpoint应该是/chat/completions
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
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        try:
            response = httpx.post(
                url,
                json=body,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            parsed_content: Any
            try:
                parsed_content = json.loads(content)
            except json.JSONDecodeError:
                parsed_content = {"text": content}
            return {
                "provider": config.provider,
                "model": model_name,
                "prompt": formatted_prompt,
                "payload": payload,
                "content": parsed_content,
                "raw": data,
            }
        except httpx.HTTPError as exc:
            return {
                "provider": config.provider,
                "model": model_name,
                "prompt": formatted_prompt,
                "payload": payload,
                "error": str(exc),
            }
    
    def call_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """简化的AI调用接口，直接返回内容字符串"""
        config = self.resolve(capability)
        override = self.overrides.get(capability, {})
        base_url = override.get("base_url") or self.api_base_url
        api_key = override.get("api_key") or self.api_key
        timeout = override.get("timeout") or self.timeout
        model_name = override.get("model") or config.model
        
        if config.provider == "local" or not base_url or not api_key:
            raise RuntimeError(f"Cannot call AI for capability {capability}: missing configuration")
        
        # 修复：统一使用/chat/completions，因为base_url通常已包含/v1
        endpoint = config.endpoint or "/chat/completions"
        url = f"{base_url.rstrip('/')}{endpoint}"
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        
        headers = {"Authorization": f"Bearer {api_key}"}
        
        response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content