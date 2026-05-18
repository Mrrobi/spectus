from __future__ import annotations

from spectus.config import Settings
from spectus.errors import SchemaGenerationError
from spectus._llm.client import LlmClient
from spectus._llm.prompts import INTENT_SYSTEM, INTENT_USER_TEMPLATE
from spectus._schemas.intent import IntentSchema


class IntentParser:
    def __init__(self, llm: LlmClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def parse(
        self, instruction: str, url: str, *, job_id: str | None = None, artifact_writer=None
    ) -> IntentSchema:
        try:
            return await self._llm.json_call(
                model=self._settings.openai_model_intent,
                system=INTENT_SYSTEM,
                user=INTENT_USER_TEMPLATE.format(url=url, instruction=instruction),
                response_model=IntentSchema,
                max_tokens=4000,
                timeout_s=self._settings.llm_intent_timeout_sec,
                temperature=0.0,
                job_id=job_id,
                step="intent",
                artifact_writer=artifact_writer,
            )
        except SchemaGenerationError:
            raise
