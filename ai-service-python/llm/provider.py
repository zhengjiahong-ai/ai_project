from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMRequest:
    prompt: str = ""
    messages: Optional[List[Dict[str, str]]] = None
    stop: Optional[List[str]] = None
    extra_body: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated: bool = False


@dataclass(frozen=True)
class LLMResult:
    provider: str
    model: str
    content: str
    usage: LLMUsage


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        retryable: bool = False,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.status_code = status_code


@runtime_checkable
class LLMProvider(Protocol):
    def invoke(self, request: LLMRequest) -> LLMResult:
        ...
