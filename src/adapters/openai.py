from __future__ import annotations
import json
import os
from typing import Any

from openai import OpenAI

from src.adapters.base import LLMAdapter, LLMResponse, Provider


class OpenAIAdapter(LLMAdapter):
    provider = Provider.OPENAI

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float = 1.0,
        **kwargs,
    ) -> LLMResponse:
        reasoning_effort = kwargs.get("reasoning_effort")

        call_kwargs: dict[str, Any] = dict(
            model=model,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            max_tokens=max_output_tokens,
            temperature=temperature,
        )
        if reasoning_effort:
            call_kwargs["reasoning_effort"] = reasoning_effort

        resp = self.client.chat.completions.create(**call_kwargs)

        text = resp.choices[0].message.content or ""
        u = resp.usage
        return LLMResponse(
            text=text,
            input_tokens=u.prompt_tokens if u else 0,
            output_tokens=u.completion_tokens if u else 0,
            total_tokens=u.total_tokens if u else 0,
            cached_tokens=getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0,
            reasoning_tokens=getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0,
            model=resp.model or model,
            response_id=resp.id or "",
            raw=json.loads(resp.model_dump_json()),
        )
