from src.adapters.anthropic import AnthropicAdapter
from src.adapters.base import LLMAdapter, Provider
from src.adapters.base import LLMResponse as LLMResponse
from src.adapters.base import ToolCall as ToolCall
from src.adapters.ollama import OllamaAdapter
from src.adapters.openai import OpenAIAdapter

ADAPTERS: dict[Provider, type[LLMAdapter]] = {
    Provider.OPENAI: OpenAIAdapter,
    Provider.ANTHROPIC: AnthropicAdapter,
    Provider.OLLAMA: OllamaAdapter,
}


def get_adapter(provider: Provider | str, **kwargs: object) -> LLMAdapter:
    key = Provider(provider)
    return ADAPTERS[key](**kwargs)
