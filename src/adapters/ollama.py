from __future__ import annotations
import json
from typing import Any
from urllib.request import urlopen, Request

from src.adapters.base import LLMAdapter, LLMResponse, Provider


class OllamaAdapter(LLMAdapter):
    provider = Provider.OLLAMA

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float = 1.0,
        **kwargs,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_output_tokens,
            },
        }
        if "think" in kwargs:
            payload["think"] = kwargs["think"]

        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())

        msg = data.get("message", {})
        text = msg.get("content", "")
        thinking = msg.get("thinking", "")
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            reasoning_tokens=len(thinking.split()) if thinking else 0,
            model=model,
            raw=data,
        )
