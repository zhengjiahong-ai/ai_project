import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from services.safety_service import estimate_tokens
from services.trace_service import record_counter, trace_step

load_dotenv()


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_TRANSLATION_MODEL = "deepseek-v4-flash"


class DeepSeekLLM:
    def __init__(
        self,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        thinking_type: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        self.thinking_type = thinking_type
        self.reasoning_effort = reasoning_effort

    def _call(
        self,
        prompt: str = "",
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> str:
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY")

        resolved_messages = [
            {
                "role": str(item.get("role") or "user"),
                "content": str(item.get("content") or ""),
            }
            for item in (messages or [])
            if isinstance(item, dict)
        ]
        if not resolved_messages:
            resolved_messages = [{"role": "user", "content": str(prompt or "")}]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": resolved_messages,
            "temperature": self.temperature,
            "stream": False,
        }

        if stop:
            payload["stop"] = stop
        if self.thinking_type:
            payload["thinking"] = {"type": self.thinking_type}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        extra_body = kwargs.get("extra_body")
        if isinstance(extra_body, dict):
            payload.update(extra_body)

        timeout = float(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "120"))
        input_size = sum(len(str(item.get("content") or "")) for item in resolved_messages)
        estimated_input_tokens = sum(estimate_tokens(item.get("content") or "") for item in resolved_messages)
        with trace_step(
            "llm_call",
            input_size=input_size,
            meta={"provider": "deepseek", "model": self.model, "messageCount": len(resolved_messages)},
        ) as step:
            record_counter("llmCalls")
            record_counter("estimatedInputTokens", estimated_input_tokens)
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )

            if response.status_code >= 400:
                raise RuntimeError(f"DeepSeek request failed: {response.status_code} - {response.text}")

            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            step["outputSize"] = len(str(content or ""))
            record_counter("estimatedOutputTokens", estimate_tokens(content))
            return str(content or "")


_llm: Optional[DeepSeekLLM] = None
_translation_llm: Optional[DeepSeekLLM] = None


def get_llm() -> DeepSeekLLM:
    global _llm

    if _llm is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Please configure DEEPSEEK_API_KEY before starting the AI service.")

        _llm = DeepSeekLLM(
            model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            temperature=float(os.environ.get("DEEPSEEK_TEMPERATURE", "0.3")),
            api_key=api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            thinking_type=os.environ.get("DEEPSEEK_THINKING_TYPE", "enabled"),
            reasoning_effort=os.environ.get("DEEPSEEK_REASONING_EFFORT", "high"),
        )

    return _llm


def get_translation_llm() -> DeepSeekLLM:
    global _translation_llm

    if _translation_llm is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Please configure DEEPSEEK_API_KEY before starting the AI service.")

        _translation_llm = DeepSeekLLM(
            model=os.environ.get("DEEPSEEK_TRANSLATION_MODEL", DEFAULT_DEEPSEEK_TRANSLATION_MODEL),
            temperature=float(os.environ.get("DEEPSEEK_TRANSLATION_TEMPERATURE", "0.1")),
            api_key=api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            thinking_type=os.environ.get("DEEPSEEK_TRANSLATION_THINKING_TYPE"),
            reasoning_effort=os.environ.get("DEEPSEEK_TRANSLATION_REASONING_EFFORT"),
        )

    return _translation_llm
