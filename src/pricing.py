from __future__ import annotations

from pydantic import BaseModel

from src.adapters.base import Provider


class ModelPricing(BaseModel, frozen=True):
    input_per_mtok: float
    output_per_mtok: float

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        input_cost = (input_tokens / 1_000_000) * self.input_per_mtok
        output_cost = (output_tokens / 1_000_000) * self.output_per_mtok
        return input_cost + output_cost


LOCAL_PRICING = ModelPricing(input_per_mtok=0.0, output_per_mtok=0.0)

PRICING: dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(input_per_mtok=2.50, output_per_mtok=10.00),
    "gpt-4o-mini": ModelPricing(input_per_mtok=0.15, output_per_mtok=0.60),
    "gpt-5": ModelPricing(input_per_mtok=1.25, output_per_mtok=10.00),
    "gpt-5.5": ModelPricing(input_per_mtok=5.00, output_per_mtok=30.00),
    "gpt-5.5-pro": ModelPricing(input_per_mtok=30.00, output_per_mtok=180.00),
    "gpt-5.4-mini": ModelPricing(input_per_mtok=0.75, output_per_mtok=4.50),
    "gpt-5.4-nano": ModelPricing(input_per_mtok=0.20, output_per_mtok=1.25),
    "claude-sonnet-4-6": ModelPricing(input_per_mtok=3.00, output_per_mtok=15.00),
    # Haiku 4.5 is $1.00/$5.00 per the official pricing page
    # (platform.claude.com/docs/en/about-claude/pricing); $0.80/$4.00 was
    # Haiku 3.5 pricing.
    "claude-haiku-4-5": ModelPricing(input_per_mtok=1.00, output_per_mtok=5.00),
    "claude-haiku-4-5-20251001": ModelPricing(
        input_per_mtok=1.00, output_per_mtok=5.00
    ),
    # Opus 4.8 is $5/$25 per the official pricing page ($15/$75 was Opus 4.1/4).
    # Correct Opus pricing matters because cost is attributed to the model the
    # response reports: any provider-side reroute or alias to claude-opus-4-8
    # would then be billed correctly. Defensive only — not an observed behavior
    # in current runs.
    "claude-opus-4-8": ModelPricing(input_per_mtok=5.00, output_per_mtok=25.00),
    "claude-opus-4-6": ModelPricing(input_per_mtok=5.00, output_per_mtok=25.00),
    "claude-fable-5": ModelPricing(input_per_mtok=10.00, output_per_mtok=50.00),
}


def get_pricing(model: str, provider: Provider | str) -> ModelPricing:
    if Provider(provider) == Provider.OLLAMA:
        return LOCAL_PRICING
    if model in PRICING:
        return PRICING[model]
    # API responses often report versioned model names (e.g.
    # gpt-4o-mini-2024-07-18); fall back to the longest matching prefix.
    prefixes = [k for k in PRICING if model.startswith(k)]
    if prefixes:
        return PRICING[max(prefixes, key=len)]
    # Never silently price an unknown API model at $0 — that corrupts CPC.
    raise KeyError(f"No pricing entry for model {model!r}; add it to PRICING.")
