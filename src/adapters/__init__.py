from src.adapters.base import LLMAdapter, LLMResponse, Provider
from src.adapters.openai import OpenAIAdapter
from src.adapters.anthropic import AnthropicAdapter
from src.adapters.ollama import OllamaAdapter

ADAPTERS: dict[Provider, type[LLMAdapter]] = {
    Provider.OPENAI: OpenAIAdapter,
    Provider.ANTHROPIC: AnthropicAdapter,
    Provider.OLLAMA: OllamaAdapter,
}


def get_adapter(provider: Provider | str, **kwargs: object) -> LLMAdapter:
    key = Provider(provider)
    return ADAPTERS[key](**kwargs)
