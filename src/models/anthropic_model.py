from __future__ import annotations

import time

import anthropic

from .base_model import BaseModel, ModelResponse


class AnthropicModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        t0 = time.perf_counter()
        # Streamed because the SDK refuses non-streaming requests whose
        # max_tokens could run past its 10-minute limit (large caps).
        async with self.client.messages.stream(
            model=self.model_id,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = await stream.get_final_message()
        return ModelResponse(
            model_id=self.model_id,
            raw_text=response.content[0].text,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            latency_seconds=time.perf_counter() - t0,
        )
