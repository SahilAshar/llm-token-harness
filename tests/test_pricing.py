"""Tests for per-model pricing entries and cost computation."""

from __future__ import annotations

import pytest

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

    def test_claude_opus_4_6(self) -> None:
        pricing = PRICING["claude-opus-4-6"]
        assert pricing.input_per_mtok == 5.00
        assert pricing.output_per_mtok == 25.00

    def test_gpt_5_5_family(self) -> None:
        assert PRICING["gpt-5.5"].input_per_mtok == 5.00
        assert PRICING["gpt-5.5"].output_per_mtok == 30.00
        assert PRICING["gpt-5.5-pro"].input_per_mtok == 30.00
        assert PRICING["gpt-5.5-pro"].output_per_mtok == 180.00

    def test_gpt_5_4_family(self) -> None:
        assert PRICING["gpt-5.4-mini"].input_per_mtok == 0.75
        assert PRICING["gpt-5.4-mini"].output_per_mtok == 4.50
        assert PRICING["gpt-5.4-nano"].input_per_mtok == 0.20
        assert PRICING["gpt-5.4-nano"].output_per_mtok == 1.25


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

    def test_versioned_name_matches_longest_prefix(self) -> None:
        # OpenAI responses report versioned names; gpt-4o-mini-... must
        # match gpt-4o-mini, not the shorter gpt-4o prefix.
        pricing = get_pricing("gpt-4o-mini-2024-07-18", Provider.OPENAI)
        assert pricing is PRICING["gpt-4o-mini"]

    def test_pro_snapshot_beats_base_prefix(self) -> None:
        # gpt-5.5-pro-... must match gpt-5.5-pro, not gpt-5.5 or gpt-5.
        pricing = get_pricing("gpt-5.5-pro-2026-04-23", Provider.OPENAI)
        assert pricing is PRICING["gpt-5.5-pro"]

    def test_unknown_api_model_raises(self) -> None:
        # Silent $0 pricing for an unknown API model corrupts CPC.
        with pytest.raises(KeyError):
            get_pricing("not-a-model", Provider.OPENAI)
