"""Param-guard tests for AnthropicAdapter using a fake client (no network).

claude-fable-5 returns HTTP 400 if the request includes `temperature` or
an explicit `thinking: {type: "disabled"}` param, so the adapter must omit
both unless explicitly asked. The optional `effort` kwarg is only sent
when provided.
"""

from __future__ import annotations

from typing import Any

from src.adapters.anthropic import AnthropicAdapter
from src.tools import ALL_TOOLS

MESSAGES = [
    {"role": "system", "content": "You are a search agent."},
    {"role": "user", "content": "Find the latest NDA."},
]


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    cache_read_input_tokens = 0


class _FakeBlock:
    type = "text"
    text = "ok"


class _FakeResponse:
    content = [_FakeBlock()]
    usage = _FakeUsage()
    model = "claude-opus-4-8"  # may differ from the requested model
    id = "msg_test"

    def model_dump_json(self) -> str:
        return "{}"


class _FakeMessages:
    def __init__(self) -> None:
        self.captured: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.captured = kwargs
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _adapter_with_fake_client() -> tuple[AnthropicAdapter, _FakeClient]:
    adapter = AnthropicAdapter(api_key="test-key")
    fake = _FakeClient()
    adapter.client = fake  # type: ignore[assignment]
    return adapter, fake


class TestParamGuards:
    def test_omits_temperature_and_thinking_by_default(self) -> None:
        adapter, fake = _adapter_with_fake_client()
        adapter.complete(
            model="claude-fable-5", messages=MESSAGES, max_output_tokens=64
        )
        assert "temperature" not in fake.messages.captured
        assert "thinking" not in fake.messages.captured
        assert "output_config" not in fake.messages.captured

    def test_temperature_sent_when_explicitly_passed(self) -> None:
        adapter, fake = _adapter_with_fake_client()
        adapter.complete(
            model="claude-sonnet-4-6",
            messages=MESSAGES,
            max_output_tokens=64,
            temperature=0.0,
        )
        assert fake.messages.captured["temperature"] == 0.0

    def test_effort_sent_only_when_provided(self) -> None:
        adapter, fake = _adapter_with_fake_client()
        adapter.complete(
            model="claude-fable-5",
            messages=MESSAGES,
            max_output_tokens=64,
            effort="medium",
        )
        assert fake.messages.captured["output_config"] == {"effort": "medium"}

    def test_tools_converted_with_auto_tool_choice(self) -> None:
        adapter, fake = _adapter_with_fake_client()
        adapter.complete(
            model="claude-fable-5",
            messages=MESSAGES,
            max_output_tokens=64,
            tools=ALL_TOOLS,
        )
        assert fake.messages.captured["tool_choice"] == {"type": "auto"}
        names = [t["name"] for t in fake.messages.captured["tools"]]
        assert names == [t["function"]["name"] for t in ALL_TOOLS]

    def test_response_model_populated_from_response(self) -> None:
        adapter, fake = _adapter_with_fake_client()
        resp = adapter.complete(
            model="claude-fable-5", messages=MESSAGES, max_output_tokens=64
        )
        # Fake responds as claude-opus-4-8 (the silent-reroute case):
        # LLMResponse.model must reflect the response, not the request.
        assert resp.model == "claude-opus-4-8"
