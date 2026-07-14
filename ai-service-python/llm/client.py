import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False

from llm.provider import LLMProviderError, LLMRequest, LLMResult, LLMUsage
from services.safety_service import estimate_tokens
from services.trace_service import record_counter, trace_step

load_dotenv()


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_TRANSLATION_MODEL = "deepseek-v4-flash"


def _resolve_messages(
    prompt: str,
    messages: Optional[List[Dict[str, str]]],
) -> List[Dict[str, Any]]:
    def _normalize_content(content: Any) -> Any:
        if isinstance(content, list):
            return content  # multimodal content blocks: [{"type": "text", ...}, {"type": "image_url", ...}]
        return str(content or "")

    resolved_messages = [
        {
            "role": str(item.get("role") or "user"),
            "content": _normalize_content(item.get("content")),
        }
        for item in (messages or [])
        if isinstance(item, dict)
    ]
    if not resolved_messages:
        resolved_messages = [{"role": "user", "content": str(prompt or "")}]
    return resolved_messages


def _normalize_usage(
    value: Any,
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> LLMUsage:
    if isinstance(value, dict):
        fields = (
            value.get("prompt_tokens"),
            value.get("completion_tokens"),
            value.get("total_tokens"),
        )
        if all(isinstance(item, int) and item >= 0 for item in fields):
            return LLMUsage(fields[0], fields[1], fields[2], estimated=False)
    return LLMUsage(
        estimated_input_tokens,
        estimated_output_tokens,
        estimated_input_tokens + estimated_output_tokens,
        estimated=True,
    )


def _validate_fixture_usage(fixture_id: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"LLM fixture {fixture_id} usage must be an object")
    fields = (value.get("inputTokens"), value.get("outputTokens"), value.get("totalTokens"))
    if not all(isinstance(item, int) and item >= 0 for item in fields):
        raise ValueError(f"LLM fixture {fixture_id} usage token fields must be non-negative integers")
    if fields[2] != fields[0] + fields[1]:
        raise ValueError(f"LLM fixture {fixture_id} usage totalTokens must equal inputTokens + outputTokens")


def _fixture_usage(
    value: Any,
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> LLMUsage:
    if isinstance(value, dict):
        return LLMUsage(
            value["inputTokens"],
            value["outputTokens"],
            value["totalTokens"],
            estimated=False,
        )
    return LLMUsage(
        estimated_input_tokens,
        estimated_output_tokens,
        estimated_input_tokens + estimated_output_tokens,
        estimated=True,
    )


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

    def invoke(self, request: LLMRequest) -> LLMResult:
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "DeepSeek credentials are not configured.",
                provider="deepseek",
                model=self.model,
            )

        resolved_messages = _resolve_messages(request.prompt, request.messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": resolved_messages,
            "temperature": self.temperature,
            "stream": False,
        }

        if request.stop:
            payload["stop"] = request.stop
        if self.thinking_type:
            payload["thinking"] = {"type": self.thinking_type}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        if request.extra_body:
            payload.update(request.extra_body)

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
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )
            except requests.RequestException as error:
                raise LLMProviderError(
                    "DeepSeek request failed.",
                    provider="deepseek",
                    model=self.model,
                    retryable=True,
                ) from error

            if response.status_code >= 400:
                raise LLMProviderError(
                    f"DeepSeek request failed with HTTP {response.status_code}.",
                    provider="deepseek",
                    model=self.model,
                    retryable=response.status_code == 429 or response.status_code >= 500,
                    status_code=response.status_code,
                )

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise LLMProviderError(
                    "DeepSeek returned an invalid response.",
                    provider="deepseek",
                    model=self.model,
                ) from error
            if not isinstance(content, str):
                raise LLMProviderError(
                    "DeepSeek returned an invalid response.",
                    provider="deepseek",
                    model=self.model,
                )

            usage = _normalize_usage(
                data.get("usage") if isinstance(data, dict) else None,
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=estimate_tokens(content),
            )
            step["outputSize"] = len(content)
            record_counter("estimatedOutputTokens", estimate_tokens(content))
            return LLMResult("deepseek", self.model, content, usage)

    def _call(
        self,
        prompt: str = "",
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> str:
        del run_manager
        extra_body = kwargs.get("extra_body")
        return self.invoke(
            LLMRequest(
                prompt=prompt,
                messages=messages,
                stop=stop,
                extra_body=extra_body if isinstance(extra_body, dict) else {},
            )
        ).content


class FixtureLLM:
    def __init__(self, fixture_path: str, client: str):
        self.fixture_path = Path(fixture_path)
        self.client = client
        self.responses = self._load_responses()

    def _load_responses(self) -> List[Dict[str, Any]]:
        try:
            payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError(f"LLM fixture file does not exist: {self.fixture_path}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"LLM fixture file is not valid JSON: {self.fixture_path}: {error}") from error

        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            raise ValueError("LLM fixture schemaVersion must be 1")
        responses = payload.get("responses")
        if not isinstance(responses, list):
            raise ValueError("LLM fixture responses must be a list")

        seen_ids = set()
        for index, response in enumerate(responses):
            if not isinstance(response, dict):
                raise ValueError(f"LLM fixture response at index {index} must be an object")
            fixture_id = str(response.get("id") or "").strip()
            if not fixture_id:
                raise ValueError(f"LLM fixture response at index {index} requires a non-empty id")
            if fixture_id in seen_ids:
                raise ValueError(f"Duplicate LLM fixture id: {fixture_id}")
            seen_ids.add(fixture_id)

            if response.get("client") not in {"default", "translation"}:
                raise ValueError(f"LLM fixture {fixture_id} client must be default or translation")
            prompt_contains = response.get("promptContains")
            if (
                not isinstance(prompt_contains, list)
                or not prompt_contains
                or any(not isinstance(marker, str) or not marker for marker in prompt_contains)
            ):
                raise ValueError(f"LLM fixture {fixture_id} promptContains must be a non-empty string list")
            output_fields = [field for field in ("output", "outputJson") if field in response]
            if len(output_fields) != 1:
                raise ValueError(f"LLM fixture {fixture_id} must define exactly one of output or outputJson")
            if "output" in response and not isinstance(response["output"], str):
                raise ValueError(f"LLM fixture {fixture_id} output must be a string")
            if "usage" in response:
                _validate_fixture_usage(fixture_id, response["usage"])

        return responses

    def invoke(self, request: LLMRequest) -> LLMResult:
        resolved_messages = _resolve_messages(request.prompt, request.messages)
        searchable_prompt = "\n".join(item["content"] for item in resolved_messages)
        matches = [
            response
            for response in self.responses
            if response["client"] == self.client
            and all(marker in searchable_prompt for marker in response["promptContains"])
        ]
        prompt_summary = " ".join(searchable_prompt.split())[:160]
        if not matches:
            raise ValueError(
                f"No fixture response matched client={self.client} prompt={prompt_summary!r}"
            )
        if len(matches) > 1:
            fixture_ids = ", ".join(str(item["id"]) for item in matches)
            raise ValueError(f"Ambiguous fixture response for prompt {prompt_summary!r}: {fixture_ids}")

        match = matches[0]
        content = (
            str(match["output"])
            if "output" in match
            else json.dumps(match["outputJson"], ensure_ascii=False)
        )
        input_size = sum(len(item["content"]) for item in resolved_messages)
        estimated_input_tokens = sum(estimate_tokens(item["content"]) for item in resolved_messages)
        usage = _fixture_usage(
            match.get("usage"),
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimate_tokens(content),
        )
        with trace_step(
            "llm_call",
            input_size=input_size,
            meta={"provider": "fixture", "model": match["id"], "messageCount": len(resolved_messages)},
        ) as step:
            record_counter("llmCalls")
            record_counter("estimatedInputTokens", estimated_input_tokens)
            step["outputSize"] = len(content)
            record_counter("estimatedOutputTokens", estimate_tokens(content))
        return LLMResult("fixture", str(match["id"]), content, usage)

    def _call(
        self,
        prompt: str = "",
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> str:
        del run_manager
        extra_body = kwargs.get("extra_body")
        return self.invoke(
            LLMRequest(
                prompt=prompt,
                messages=messages,
                stop=stop,
                extra_body=extra_body if isinstance(extra_body, dict) else {},
            )
        ).content


_llm: Optional[Any] = None
_translation_llm: Optional[Any] = None


def _get_fixture_llm(client: str) -> FixtureLLM:
    fixture_path = os.environ.get("PIXIU_LLM_FIXTURE_PATH", "").strip()
    if not fixture_path:
        raise ValueError("PIXIU_LLM_FIXTURE_PATH is required when PIXIU_LLM_MODE=fixture")
    return FixtureLLM(fixture_path=fixture_path, client=client)


def get_llm() -> Any:
    global _llm

    if _llm is None:
        mode = os.environ.get("PIXIU_LLM_MODE", "deepseek").strip().lower()
        if mode == "fixture":
            _llm = _get_fixture_llm("default")
            return _llm
        if mode != "deepseek":
            raise ValueError(f"Unsupported PIXIU_LLM_MODE: {mode}")
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


def get_translation_llm() -> Any:
    global _translation_llm

    if _translation_llm is None:
        mode = os.environ.get("PIXIU_LLM_MODE", "deepseek").strip().lower()
        if mode == "fixture":
            _translation_llm = _get_fixture_llm("translation")
            return _translation_llm
        if mode != "deepseek":
            raise ValueError(f"Unsupported PIXIU_LLM_MODE: {mode}")
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
