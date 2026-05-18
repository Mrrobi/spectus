from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import monotonic
from typing import Any, Type, TypeVar

from openai import APITimeoutError, AsyncOpenAI, RateLimitError
from openai import APIError as OpenAIAPIError
from openai import LengthFinishReasonError
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.errors import LlmTransientError, SchemaGenerationError
from app.logging import get_logger
from app.services.metrics import Metrics

T = TypeVar("T", bound=BaseModel)


def _is_reasoning_model(model: str) -> bool:
    """Reasoning-token-charging models: gpt-5*, o1*, o3*, o4*.
    These don't accept custom temperature and accept reasoning_effort.
    """
    name = model.lower()
    return (
        name.startswith("gpt-5")
        or name.startswith("o1")
        or name.startswith("o3")
        or name.startswith("o4")
    )


def _model_drops_temperature(model: str) -> bool:
    return _is_reasoning_model(model)


class LlmClient:
    def __init__(self, settings: Settings, metrics: Metrics) -> None:
        self._settings = settings
        self._metrics = metrics
        self._log = get_logger("llm")
        if settings.openai_api_key:
            self._client: AsyncOpenAI | None = AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            self._client = None

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def json_call(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: Type[T],
        max_tokens: int,
        timeout_s: float,
        temperature: float = 0.0,
        job_id: str | None = None,
        step: str = "llm",
        artifact_writer: Any = None,
    ) -> T:
        if self._client is None:
            raise LlmTransientError(detail="openai_not_configured")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        start = monotonic()
        parsed = await self._attempt_parse(
            model=model,
            messages=messages,
            response_model=response_model,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            temperature=temperature,
        )
        retried = False
        if isinstance(parsed, ValidationError):
            retried = True
            messages = [
                *messages,
                {"role": "assistant", "content": _safe_dump(parsed_payload(parsed))},
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed validation:\n"
                        f"{str(parsed)[:1500]}\n"
                        "Return a corrected response that satisfies the schema."
                    ),
                },
            ]
            parsed = await self._attempt_parse(
                model=model,
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
                temperature=0.0,
            )
            self._metrics.inc("llm_validation_retry_total", 1, model=model)

        elapsed_ms = int((monotonic() - start) * 1000)
        if isinstance(parsed, ValidationError):
            self._metrics.inc("llm_calls_total", 1, model=model)
            self._metrics.inc("errors_total", 1, code="schema_generation_failed")
            raise SchemaGenerationError(detail=str(parsed)[:1500])

        self._metrics.inc("llm_calls_total", 1, model=model)
        self._metrics.observe("llm_latency_ms", elapsed_ms, model=model)

        if artifact_writer is not None and job_id is not None:
            try:
                await artifact_writer.write_llm(
                    job_id=job_id,
                    step=step,
                    payload={
                        "model": model,
                        "messages": messages,
                        "response": parsed.model_dump(),
                        "retried": retried,
                        "elapsed_ms": elapsed_ms,
                    },
                )
            except Exception as e:
                self._log.warning("artifact_write_failed", step=step, error=str(e))
        return parsed

    async def _attempt_parse(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: Type[T],
        max_tokens: int,
        timeout_s: float,
        temperature: float,
    ) -> T | ValidationError:
        assert self._client is not None
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": response_model,
            "max_completion_tokens": max_tokens,
        }
        if _is_reasoning_model(model):
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["temperature"] = temperature
        try:
            completion = await asyncio.wait_for(
                self._client.beta.chat.completions.parse(**kwargs),
                timeout=timeout_s,
            )
        except (APITimeoutError, asyncio.TimeoutError) as e:
            raise LlmTransientError(detail="timeout") from e
        except RateLimitError as e:
            raise LlmTransientError(detail="rate_limited") from e
        except LengthFinishReasonError as e:
            raise LlmTransientError(detail=f"output_truncated:{e}") from e
        except ValidationError as e:
            return e
        except OpenAIAPIError as e:
            raise LlmTransientError(detail=str(e)[:500]) from e

        choice = completion.choices[0]
        usage = completion.usage
        if usage is not None:
            self._metrics.inc(
                "llm_tokens_total", usage.prompt_tokens, model=model, direction="in"
            )
            self._metrics.inc(
                "llm_tokens_total", usage.completion_tokens, model=model, direction="out"
            )

        if choice.message.refusal:
            return ValidationError.from_exception_data(
                response_model.__name__,
                [{"type": "value_error", "loc": (), "msg": choice.message.refusal, "input": None}],
            )
        parsed = choice.message.parsed
        if parsed is None:
            raw = choice.message.content or ""
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                return ValidationError.from_exception_data(
                    response_model.__name__,
                    [{"type": "json_invalid", "loc": (), "msg": str(e), "input": raw[:500]}],
                )
            try:
                return response_model.model_validate(obj)
            except ValidationError as e:
                return e
        return parsed


def parsed_payload(error: ValidationError) -> dict[str, Any]:
    try:
        return {"error": error.errors()}
    except Exception:
        return {"error": str(error)}


def _safe_dump(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)
