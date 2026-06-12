"""Unit tests for canonical-message → provider wire-format conversion.

The task dataset stores multi-step chain history in a canonical format:
assistant tool calls as ``[{name, arguments}]`` (no call IDs) and tool
results as ``{role: "tool", content}``. Each adapter converts to its
provider's wire format. These are pure functions — no API access.
"""

from __future__ import annotations

import json
from typing import Any

from src.adapters.anthropic import convert_messages as convert_anthropic
from src.adapters.ollama import convert_messages as convert_ollama
from src.adapters.openai import convert_messages as convert_openai

CHAIN_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "You are a search agent."},
    {"role": "user", "content": "Compare indemnification across our MSAs."},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"name": "query_decompose", "arguments": {"query": "compare msas"}}
        ],
    },
    {"role": "tool", "content": '{"sub_queries": []}'},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"name": "search", "arguments": {"query": "indemnification"}}],
    },
    {"role": "tool", "content": '{"results": []}'},
]

SIMPLE_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "You are a search agent."},
    {"role": "user", "content": "Find the Corvid NDA."},
]

PARALLEL_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "You are a search agent."},
    {"role": "user", "content": "Compare indemnification across our MSAs."},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"name": "search", "arguments": {"query": "halverson"}},
            {"name": "search", "arguments": {"query": "apex"}},
        ],
    },
    {"role": "tool", "content": '{"results": ["h"]}'},
    {"role": "tool", "content": '{"results": ["a"]}'},
]


class TestOpenAIConversion:
    def test_simple_messages_pass_through(self) -> None:
        out = convert_openai(SIMPLE_MESSAGES)
        assert out == SIMPLE_MESSAGES

    def test_null_content_becomes_empty_string(self) -> None:
        out = convert_openai(CHAIN_MESSAGES)
        for m in out:
            assert m.get("content") is not None

    def test_tool_calls_get_ids_and_json_arguments(self) -> None:
        out = convert_openai(CHAIN_MESSAGES)
        assistant = out[2]
        call = assistant["tool_calls"][0]
        assert call["id"] == "call_0"
        assert call["type"] == "function"
        assert call["function"]["name"] == "query_decompose"
        assert json.loads(call["function"]["arguments"]) == {"query": "compare msas"}

    def test_tool_results_link_to_calls_in_order(self) -> None:
        out = convert_openai(CHAIN_MESSAGES)
        assert out[3]["role"] == "tool"
        assert out[3]["tool_call_id"] == "call_0"
        assert out[5]["tool_call_id"] == "call_1"

    def test_parallel_batch_results_pair_fifo(self) -> None:
        out = convert_openai(PARALLEL_MESSAGES)
        assistant = out[2]
        assert [c["id"] for c in assistant["tool_calls"]] == ["call_0", "call_1"]
        assert out[3]["tool_call_id"] == "call_0"
        assert out[4]["tool_call_id"] == "call_1"


class TestAnthropicConversion:
    def test_system_extracted(self) -> None:
        system_text, chat = convert_anthropic(CHAIN_MESSAGES)
        assert system_text == "You are a search agent."
        assert all(m["role"] != "system" for m in chat)

    def test_tool_calls_become_tool_use_blocks(self) -> None:
        _, chat = convert_anthropic(CHAIN_MESSAGES)
        assistant = chat[1]
        assert assistant["role"] == "assistant"
        block = assistant["content"][0]
        assert block["type"] == "tool_use"
        assert block["id"] == "toolu_0"
        assert block["name"] == "query_decompose"
        assert block["input"] == {"query": "compare msas"}

    def test_tool_role_becomes_user_tool_result(self) -> None:
        _, chat = convert_anthropic(CHAIN_MESSAGES)
        result_msg = chat[2]
        assert result_msg["role"] == "user"
        block = result_msg["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_0"
        assert block["content"] == '{"sub_queries": []}'

    def test_second_result_links_to_second_call(self) -> None:
        _, chat = convert_anthropic(CHAIN_MESSAGES)
        assert chat[4]["content"][0]["tool_use_id"] == "toolu_1"

    def test_no_tool_role_remains(self) -> None:
        _, chat = convert_anthropic(CHAIN_MESSAGES)
        assert all(m["role"] in ("user", "assistant") for m in chat)

    def test_parallel_batch_results_merge_into_one_user_message(self) -> None:
        _, chat = convert_anthropic(PARALLEL_MESSAGES)
        # user, assistant(2 tool_use), ONE user message with both results
        assert [m["role"] for m in chat] == ["user", "assistant", "user"]
        assistant = chat[1]
        assert [b["id"] for b in assistant["content"]] == ["toolu_0", "toolu_1"]
        results = chat[2]["content"]
        assert [b["type"] for b in results] == ["tool_result", "tool_result"]
        assert [b["tool_use_id"] for b in results] == ["toolu_0", "toolu_1"]
        assert results[0]["content"] == '{"results": ["h"]}'
        assert results[1]["content"] == '{"results": ["a"]}'


class TestOllamaConversion:
    def test_simple_messages_pass_through(self) -> None:
        out = convert_ollama(SIMPLE_MESSAGES)
        assert out == SIMPLE_MESSAGES

    def test_null_content_becomes_empty_string(self) -> None:
        out = convert_ollama(CHAIN_MESSAGES)
        for m in out:
            assert m["content"] is not None

    def test_tool_calls_preserved_as_objects(self) -> None:
        out = convert_ollama(CHAIN_MESSAGES)
        call = out[2]["tool_calls"][0]
        assert call["function"]["name"] == "query_decompose"
        assert call["function"]["arguments"] == {"query": "compare msas"}

    def test_tool_role_passes_through(self) -> None:
        out = convert_ollama(CHAIN_MESSAGES)
        assert out[3]["role"] == "tool"
        assert out[3]["content"] == '{"sub_queries": []}'
