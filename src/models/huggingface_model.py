from __future__ import annotations

import time
import logging

from huggingface_hub import AsyncInferenceClient

from .base_model import BaseModel, ModelResponse

logger = logging.getLogger(__name__)

# Context limits (input + output combined) for models without a config
# `context_limit`. Llama's comes from config because it depends on the backend.
HF_CONTEXT_LIMITS: dict[str, int] = {
    "Qwen/Qwen2.5-7B-Instruct": 32_768,
}

DEFAULT_CONTEXT_LIMIT = 32_768


class HuggingFaceModel(BaseModel):
    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id, api_key, **kwargs)

        # hf_provider pins one inference backend (e.g. "nscale"). Backends can
        # differ in context window and quantization, so all of a model's runs
        # should go through the same one. Default "auto" lets HF choose.
        self.hf_provider: str = kwargs.get("hf_provider", "auto")
        self._client = AsyncInferenceClient(api_key=api_key, provider=self.hf_provider)
        self._context_limit = kwargs.get("context_limit") or HF_CONTEXT_LIMITS.get(
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

    def effective_max_tokens(self, prompt: str) -> int:
        return self._safe_max_tokens(prompt, self.max_tokens)

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        requested_max = kwargs.get("max_tokens", self.max_tokens)
        safe_max = self._safe_max_tokens(prompt, requested_max)

        t0 = time.perf_counter()

        # Streamed: backends time out non-streaming requests after ~60s, which
        # silently drops exactly the longest generations (selection bias).
        stream = await self._client.chat_completion(
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
            stream=True,
            stream_options={"include_usage": True},
        )

        parts: list[str] = []
        usage = None
        served = None
        async for chunk in stream:
            served = served or getattr(chunk, "model", None)
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
            if getattr(chunk, "usage", None):
                usage = chunk.usage

        latency = time.perf_counter() - t0

        return ModelResponse(
            model_id=self.model_id,
            raw_text="".join(parts),
            usage={
                "input_tokens": (
                    usage.prompt_tokens if usage else 0
                ),
                "output_tokens": (
                    usage.completion_tokens if usage else 0
                ),
            },
            latency_seconds=latency,
            served_model=f"{served or self.model_id} via {self.hf_provider}",
        )