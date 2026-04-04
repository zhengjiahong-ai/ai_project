import os
from typing import Any, List, Optional

from dotenv import load_dotenv


load_dotenv()


class CustomDashScopeLLM:
    def __init__(self, model: str = "qwen-max", temperature: float = 0.3, dashscope_api_key: Optional[str] = None):
        self.model = model
        self.temperature = temperature
        self.dashscope_api_key = dashscope_api_key

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
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

        response = Generation.call(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            result_format="message",
            stream=False,
        )

        if response.status_code != 200:
            raise RuntimeError(f"DashScope request failed: {response.code} - {response.message}")

        return response.output.choices[0].message.content


_llm: Optional[CustomDashScopeLLM] = None


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
