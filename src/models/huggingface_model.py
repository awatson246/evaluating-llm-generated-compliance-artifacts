from __future__ import annotations

import time

import aiohttp

from .base_model import BaseModel, ModelResponse

_HF_BASE = "https://api-inference.huggingface.co/models"


class HuggingFaceModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        url = f"{_HF_BASE}/{self.model_id}"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
                "return_full_text": False,
            },
        }
        t0 = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._headers, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
        latency = time.perf_counter() - t0

        if isinstance(data, list) and data:
            raw_text = data[0].get("generated_text", "")
        else:
            raw_text = str(data)

        return ModelResponse(
            model_id=self.model_id,
            raw_text=raw_text,
            usage={},
            latency_seconds=latency,
        )
