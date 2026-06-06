from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""
    response_id: str = ""
    raw: dict = field(default_factory=dict)


class LLMAdapter(ABC):
    provider: str

    @abstractmethod
    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float = 1.0,
        **kwargs,
    ) -> LLMResponse:
        ...

    def normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert from the canonical format (role/content strings) to provider-specific format.
        Default implementation returns messages as-is. Override for providers with different formats."""
        return messages
