from __future__ import annotations

from dataclasses import dataclass

from src.adapters.base import Provider


@dataclass(frozen=True)
class ModelPricing:
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
    "claude-sonnet-4-6": ModelPricing(input_per_mtok=3.00, output_per_mtok=15.00),
    "claude-haiku-4-5-20251001": ModelPricing(
        input_per_mtok=0.80, output_per_mtok=4.00
    ),
    "claude-opus-4-8": ModelPricing(input_per_mtok=15.00, output_per_mtok=75.00),
}


def get_pricing(model: str, provider: Provider | str) -> ModelPricing:
    if Provider(provider) == Provider.OLLAMA:
        return LOCAL_PRICING
    return PRICING.get(model, LOCAL_PRICING)
