from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from src.adapters.base import LLMAdapter, LLMResponse, Provider, ToolCall


def convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert canonical task messages to OpenAI chat format.

    Canonical assistant tool calls are ``[{name, arguments}]`` with no
    call IDs, and tool results are ``{role: "tool", content}``. OpenAI
    requires a ``tool_call_id`` linking each result to its call, a JSON
    string for arguments, and non-null content on every message.
    """
    converted: list[dict[str, Any]] = []
    pending_ids: list[str] = []
    counter = 0

    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                call_id = f"call_{counter}"
                counter += 1
                pending_ids.append(call_id)
                calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                )
            converted.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": calls,
                }
            )
        elif role == "tool":
            call_id = pending_ids.pop(0) if pending_ids else f"call_{counter}"
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": m.get("content") or "",
                }
            )
        else:
            converted.append({"role": role, "content": m.get("content") or ""})

    return converted


class OpenAIAdapter(LLMAdapter):
    provider = Provider.OPENAI

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # The CLI passes a provider-neutral `effort`; OpenAI calls it
        # reasoning_effort (none/low/medium/high/xhigh on gpt-5.x).
        reasoning_effort = kwargs.get("reasoning_effort") or kwargs.get("effort")

        # max_completion_tokens is the universal replacement for
        # max_tokens, which gpt-5.x reasoning models reject. Reasoning
        # models also restrict temperature, so only send it when the
        # caller explicitly passes one (mirrors the Anthropic guard).
        call_kwargs: dict[str, Any] = dict(
            model=model,
            messages=convert_messages(messages),
            max_completion_tokens=max_output_tokens,
        )
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if reasoning_effort:
            call_kwargs["reasoning_effort"] = reasoning_effort
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**call_kwargs)

        msg = resp.choices[0].message
        text = msg.content or ""

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        u = resp.usage
        prompt_details = getattr(u, "prompt_tokens_details", None)
        completion_details = getattr(u, "completion_tokens_details", None)
        return LLMResponse(
            text=text,
            input_tokens=u.prompt_tokens if u else 0,
            output_tokens=u.completion_tokens if u else 0,
            total_tokens=u.total_tokens if u else 0,
            cached_tokens=getattr(prompt_details, "cached_tokens", 0) or 0,
            reasoning_tokens=getattr(completion_details, "reasoning_tokens", 0) or 0,
            model=resp.model or model,
            response_id=resp.id or "",
            tool_calls=tool_calls,
            raw=json.loads(resp.model_dump_json()),
        )
