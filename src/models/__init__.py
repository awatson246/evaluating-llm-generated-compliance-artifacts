from .base_model import BaseModel, ModelResponse
from .openai_model import OpenAIModel
from .anthropic_model import AnthropicModel
from .huggingface_model import HuggingFaceModel
from .mistral_model import MistralModel

_REGISTRY: dict[str, type[BaseModel]] = {
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
    "huggingface": HuggingFaceModel,
    "mistral": MistralModel,
}


def build_model(provider: str, model_id: str, api_key: str, **kwargs) -> BaseModel:
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown provider '{provider}'. Available: {list(_REGISTRY)}")
    return cls(model_id=model_id, api_key=api_key, **kwargs)


__all__ = [
    "BaseModel",
    "ModelResponse",
    "OpenAIModel",
    "AnthropicModel",
    "HuggingFaceModel",
    "build_model",
]
