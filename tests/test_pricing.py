"""Tests for per-model pricing entries and cost computation."""

from __future__ import annotations

from src.adapters.base import Provider
from src.pricing import LOCAL_PRICING, PRICING, get_pricing


class TestPricingEntries:
    def test_claude_fable_5(self) -> None:
        pricing = PRICING["claude-fable-5"]
        assert pricing.input_per_mtok == 10.00
        assert pricing.output_per_mtok == 50.00

    def test_claude_haiku_4_5(self) -> None:
        # $1.00/$5.00 per the official Anthropic pricing page.
        for key in ("claude-haiku-4-5", "claude-haiku-4-5-20251001"):
            pricing = PRICING[key]
            assert pricing.input_per_mtok == 1.00
            assert pricing.output_per_mtok == 5.00

    def test_claude_opus_4_8(self) -> None:
        pricing = PRICING["claude-opus-4-8"]
        assert pricing.input_per_mtok == 5.00
        assert pricing.output_per_mtok == 25.00


class TestCostUsd:
    def test_fable_5_cost(self) -> None:
        pricing = PRICING["claude-fable-5"]
        # 1M input + 1M output = $10 + $50
        assert pricing.cost_usd(1_000_000, 1_000_000) == 60.00

    def test_haiku_cost(self) -> None:
        pricing = PRICING["claude-haiku-4-5"]
        assert pricing.cost_usd(2_000_000, 1_000_000) == 7.00


class TestGetPricing:
    def test_known_model(self) -> None:
        assert (
            get_pricing("claude-fable-5", Provider.ANTHROPIC)
            is (PRICING["claude-fable-5"])
        )

    def test_ollama_is_free(self) -> None:
        assert get_pricing("gemma4:12b", Provider.OLLAMA) == LOCAL_PRICING

    def test_unknown_model_falls_back_to_free(self) -> None:
        assert get_pricing("not-a-model", Provider.OPENAI) == LOCAL_PRICING
