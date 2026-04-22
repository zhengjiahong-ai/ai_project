import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from services.trace_service import record_counter, trace_step

load_dotenv()


class CustomDashScopeLLM:
    def __init__(self, model: str = "qwen-max", temperature: float = 0.3, dashscope_api_key: Optional[str] = None):
        self.model = model
        self.temperature = temperature
        self.dashscope_api_key = dashscope_api_key

    def _call(
        self,
        prompt: str = "",
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> str:
        import dashscope
        from dashscope import Generation

        if self.dashscope_api_key:
            dashscope.api_key = self.dashscope_api_key
        elif os.environ.get("DASHSCOPE_API_KEY"):
            dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")
        else:
            raise ValueError("Missing DASHSCOPE_API_KEY")

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

        input_size = sum(len(str(item.get("content") or "")) for item in resolved_messages)
        with trace_step(
            "llm_call",
            input_size=input_size,
            meta={"model": self.model, "messageCount": len(resolved_messages)},
        ) as step:
            record_counter("llmCalls")
            response = Generation.call(
                model=self.model,
                messages=resolved_messages,
                temperature=self.temperature,
                result_format="message",
                stream=False,
            )

            if response.status_code != 200:
                raise RuntimeError(f"DashScope request failed: {response.code} - {response.message}")

            content = response.output.choices[0].message.content
            step["outputSize"] = len(str(content or ""))
            return content


_llm: Optional[CustomDashScopeLLM] = None
_translation_llm: Optional[CustomDashScopeLLM] = None


def get_llm() -> CustomDashScopeLLM:
    global _llm

    if _llm is None:
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("Please configure DASHSCOPE_API_KEY before starting the AI service.")

        _llm = CustomDashScopeLLM(
            model="qwen-max",
            temperature=0.3,
            dashscope_api_key=api_key,
        )

    return _llm


def get_translation_llm() -> CustomDashScopeLLM:
    global _translation_llm

    if _translation_llm is None:
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("Please configure DASHSCOPE_API_KEY before starting the AI service.")

        _translation_llm = CustomDashScopeLLM(
            model=os.environ.get("DASHSCOPE_TRANSLATION_MODEL", "qwen-plus"),
            temperature=0.1,
            dashscope_api_key=api_key,
        )

    return _translation_llm
