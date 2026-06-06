from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from src.adapters.base import LLMAdapter, LLMResponse, Provider


class AnthropicAdapter(LLMAdapter):
    provider = Provider.ANTHROPIC

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.client = anthropic.Anthropic(api_key=key)

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> LLMResponse:
        system_text = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                content = m["content"]
                system_text = content if isinstance(content, str) else str(content)
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        call_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_output_tokens,
            temperature=temperature,
            messages=chat_messages,
        )
        if system_text:
            call_kwargs["system"] = system_text

        resp = self.client.messages.create(**call_kwargs)

        text = ""
        for block in resp.content:
            if block.type == "text":
                text += block.text

        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
            cached_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            model=resp.model or model,
            response_id=resp.id or "",
            raw=json.loads(resp.model_dump_json()),
        )
