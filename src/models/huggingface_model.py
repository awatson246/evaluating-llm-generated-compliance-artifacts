from __future__ import annotations

import time

from huggingface_hub import AsyncInferenceClient

from .base_model import BaseModel, ModelResponse


class HuggingFaceModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)
        self._client = AsyncInferenceClient(api_key=api_key)

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        t0 = time.perf_counter()
        result = await self._client.chat_completion(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )
        latency = time.perf_counter() - t0
        usage = result.usage
        return ModelResponse(
            model_id=self.model_id,
            raw_text=result.choices[0].message.content,
            usage={
                "input_tokens":  usage.prompt_tokens     if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            },
            latency_seconds=latency,
        )
