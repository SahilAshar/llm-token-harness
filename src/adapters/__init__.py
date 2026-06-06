from src.adapters.base import LLMAdapter, LLMResponse
from src.adapters.openai import OpenAIAdapter
from src.adapters.anthropic import AnthropicAdapter
from src.adapters.ollama import OllamaAdapter

ADAPTERS = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "ollama": OllamaAdapter,
}

def get_adapter(provider: str, **kwargs) -> LLMAdapter:
    if provider not in ADAPTERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(ADAPTERS.keys())}")
    return ADAPTERS[provider](**kwargs)
