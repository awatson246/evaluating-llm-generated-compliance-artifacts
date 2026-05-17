from __future__ import annotations

import time
import logging

from huggingface_hub import AsyncInferenceClient

from .base_model import BaseModel, ModelResponse

logger = logging.getLogger(__name__)

# Conservative per-model context limits (input + output combined)
HF_CONTEXT_LIMITS: dict[str, int] = {
    "meta-llama/Llama-3.1-8B-Instruct": 32_768,
    "meta-llama/Llama-3.1-70B-Instruct": 131_072,
    "mistralai/Mixtral-8x7B-Instruct-v0.1": 32_768,
    "Qwen/Qwen2.5-72B-Instruct": 131_072,
}

DEFAULT_CONTEXT_LIMIT = 32_768


class HuggingFaceModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)

        self._client = AsyncInferenceClient(api_key=api_key)
        self._context_limit = HF_CONTEXT_LIMITS.get(
            model_id,
            DEFAULT_CONTEXT_LIMIT,
        )

    def _safe_max_tokens(self, prompt: str, requested_max: int) -> int:
        """
        Rough token estimate (chars / 4) to ensure:
            input_tokens + output_tokens <= context_limit

        Leaves a small safety buffer.
        """
        estimated_input = len(prompt) // 4
        headroom = self._context_limit - estimated_input - 200

        if headroom <= 0:
            raise ValueError(
                f"Prompt alone (~{estimated_input} tokens) exceeds "
                f"context limit ({self._context_limit}) "
                f"for model {self.model_id}. "
                f"Please shorten the prompt."
            )

        if headroom < requested_max:
            logger.warning(
                f"[{self.model_id}] Reducing max_tokens "
                f"{requested_max} -> {headroom} "
                f"(estimated input: ~{estimated_input} tokens)"
            )

        return min(requested_max, headroom)

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        requested_max = kwargs.get("max_tokens", self.max_tokens)
        safe_max = self._safe_max_tokens(prompt, requested_max)

        t0 = time.perf_counter()

        result = await self._client.chat_completion(
            model=self.model_id,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            max_tokens=safe_max,
            temperature=kwargs.get(
                "temperature",
                self.temperature,
            ),
        )

        latency = time.perf_counter() - t0
        usage = result.usage

        return ModelResponse(
            model_id=self.model_id,
            raw_text=result.choices[0].message.content,
            usage={
                "input_tokens": (
                    usage.prompt_tokens if usage else 0
                ),
                "output_tokens": (
                    usage.completion_tokens if usage else 0
                ),
            },
            latency_seconds=latency,
        )