from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from src.adapters.base import LLMAdapter, LLMResponse, Provider, ToolCall


def convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert canonical task messages to Anthropic format.

    Returns ``(system_text, chat_messages)``. Canonical assistant tool
    calls become ``tool_use`` content blocks; ``role: "tool"`` results
    become ``tool_result`` blocks inside a user message (Anthropic has
    no tool role). Synthetic IDs pair each result with its call.
    Consecutive tool results (from a parallel call batch) are merged
    into one user message — Anthropic's documented format for parallel
    tool results.
    """
    system_text = ""
    converted: list[dict[str, Any]] = []
    pending_ids: list[str] = []
    counter = 0

    for m in messages:
        role = m["role"]
        if role == "system":
            content = m["content"]
            system_text = content if isinstance(content, str) else str(content)
        elif role == "assistant" and m.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                tool_id = f"toolu_{counter}"
                counter += 1
                pending_ids.append(tool_id)
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tc["name"],
                        "input": tc["arguments"],
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            tool_id = pending_ids.pop(0) if pending_ids else f"toolu_{counter}"
            result_block = {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": m.get("content") or "",
            }
            prev = converted[-1] if converted else None
            if (
                prev is not None
                and prev["role"] == "user"
                and isinstance(prev["content"], list)
                and prev["content"]
                and prev["content"][-1].get("type") == "tool_result"
            ):
                prev["content"].append(result_block)
            else:
                converted.append({"role": "user", "content": [result_block]})
        else:
            converted.append({"role": role, "content": m["content"]})

    return system_text, converted


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
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        system_text, chat_messages = convert_messages(messages)

        # claude-fable-5 returns HTTP 400 for `temperature` and for an
        # explicit `thinking: {type: "disabled"}` param. So: never send a
        # `thinking` param, and only send `temperature` when the caller
        # explicitly passes one.
        call_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_output_tokens,
            messages=chat_messages,
        )
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        # Optional adaptive-thinking effort level (e.g. "low" | "medium" |
        # "high"), only sent when provided.
        effort = kwargs.get("effort")
        if effort is not None:
            call_kwargs["output_config"] = {"effort": effort}
        if system_text:
            call_kwargs["system"] = system_text
        if tools:
            call_kwargs["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]
            call_kwargs["tool_choice"] = {"type": "auto"}

        resp = self.client.messages.create(**call_kwargs)

        text = ""
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(name=block.name, arguments=block.input))

        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
            cached_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            model=resp.model or model,
            response_id=resp.id or "",
            tool_calls=tool_calls,
            raw=json.loads(resp.model_dump_json()),
        )
