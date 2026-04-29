from __future__ import annotations

import time

from openai import AsyncOpenAI

from .base_model import BaseModel, ModelResponse


class OpenAIModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        t0 = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )
        return ModelResponse(
            model_id=self.model_id,
            raw_text=response.choices[0].message.content or "",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            latency_seconds=time.perf_counter() - t0,
        )
