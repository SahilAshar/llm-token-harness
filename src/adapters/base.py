from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ToolCall(BaseModel, frozen=True):
    name: str
    arguments: dict[str, Any] = {}


class LLMResponse(BaseModel, frozen=True):
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""
    response_id: str = ""
    tool_calls: list[ToolCall] = []
    raw: dict[str, Any] = {}


class LLMAdapter(ABC):
    provider: Provider

    @abstractmethod
    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float = 1.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

    def normalize_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return messages
