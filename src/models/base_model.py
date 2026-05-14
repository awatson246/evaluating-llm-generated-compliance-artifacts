from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelResponse:
    model_id: str
    raw_text: str
    usage: dict[str, Any]
    latency_seconds: float


class BaseModel(ABC):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        self.model_id = model_id
        self.api_key = api_key
        self.max_tokens: int = kwargs.get("max_tokens", 6000)
        self.temperature: float = kwargs.get("temperature", 0.7)

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        """Send prompt to the model and return a structured response."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model_id={self.model_id!r})"
