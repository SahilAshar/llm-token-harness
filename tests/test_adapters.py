"""Smoke tests for the multi-provider adapter layer.

Run with: python -m pytest tests/test_adapters.py -v

These tests hit live APIs / local Ollama and are marked `live`.
CI runs: pytest -m "not live"
Local runs: pytest (runs everything)
"""

import os

import pytest

from src.adapters import get_adapter

MESSAGES = [
    {
        "role": "system",
        "content": "You are a calculator. Return only the numeric result.",
    },
    {"role": "user", "content": "What is 2 + 2?"},
]

HAS_OPENAI = bool(os.environ.get("OPENAI_API_KEY"))
HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture()
def ollama_available():
    try:
        from urllib.request import urlopen

        urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        pytest.skip("Ollama not running")


@pytest.mark.live
@pytest.mark.skipif(not HAS_OPENAI, reason="No OPENAI_API_KEY")
def test_openai_adapter():
    adapter = get_adapter("openai")
    resp = adapter.complete(
        model="gpt-4o-mini", messages=MESSAGES, max_output_tokens=32
    )
    assert "4" in resp.text
    assert resp.input_tokens > 0
    assert resp.output_tokens > 0


@pytest.mark.live
@pytest.mark.skipif(not HAS_ANTHROPIC, reason="No ANTHROPIC_API_KEY")
def test_anthropic_adapter():
    adapter = get_adapter("anthropic")
    resp = adapter.complete(
        model="claude-haiku-4-5-20251001",
        messages=MESSAGES,
        max_output_tokens=32,
    )
    assert "4" in resp.text
    assert resp.input_tokens > 0
    assert resp.output_tokens > 0


@pytest.mark.live
def test_ollama_adapter(ollama_available):
    adapter = get_adapter("ollama")
    resp = adapter.complete(
        model="gemma4:12b",
        messages=MESSAGES,
        max_output_tokens=256,
        temperature=0.0,
    )
    assert resp.text
    assert resp.total_tokens > 0


def test_unknown_provider():
    with pytest.raises(ValueError, match="is not a valid Provider"):
        get_adapter("unknown")
