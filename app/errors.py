from __future__ import annotations

import logging
from typing import Any, ClassVar


class ExtractionError(Exception):
    code: ClassVar[str] = "internal_error"
    http_status: ClassVar[int] = 500
    retryable: ClassVar[bool] = False
    log_level: ClassVar[int] = logging.ERROR
    user_message_template: ClassVar[str] = "Unexpected internal error."

    def __init__(self, detail: str = "", **fmt: Any) -> None:
        self.detail = detail
        self.fmt = fmt
        super().__init__(self.user_message_template.format(**fmt) if fmt else detail or self.code)

    def user_message(self) -> str:
        try:
            return self.user_message_template.format(**self.fmt)
        except (KeyError, IndexError):
            return self.user_message_template


class InvalidUrlError(ExtractionError):
    code = "invalid_url"
    http_status = 400
    retryable = False
    log_level = logging.WARNING
    user_message_template = "The URL '{url}' is not valid."


class BlockedUrlError(ExtractionError):
    code = "blocked_url"
    http_status = 400
    retryable = False
    log_level = logging.WARNING
    user_message_template = "This URL cannot be accessed: {reason}."


class BlockedByRobotsError(ExtractionError):
    code = "blocked_by_robots"
    http_status = 451
    retryable = False
    log_level = logging.WARNING
    user_message_template = "Robots.txt disallows scraping this URL."


class UnsupportedContentTypeError(ExtractionError):
    code = "unsupported_content_type"
    http_status = 415
    retryable = False
    log_level = logging.WARNING
    user_message_template = "Content type {ct} is not supported."


class RateLimitedError(ExtractionError):
    code = "rate_limited"
    http_status = 429
    retryable = True
    log_level = logging.WARNING
    user_message_template = "Slow down — too many requests to this domain."


class FetchError(ExtractionError):
    code = "fetch_failed"
    http_status = 502
    retryable = True
    log_level = logging.ERROR
    user_message_template = "Could not fetch the page: {reason}."


class BrowserRenderError(ExtractionError):
    code = "browser_render_failed"
    http_status = 502
    retryable = True
    log_level = logging.ERROR
    user_message_template = "Browser rendering failed: {reason}."


class JobTimeoutError(ExtractionError):
    code = "timeout"
    http_status = 504
    retryable = True
    log_level = logging.WARNING
    user_message_template = "The request exceeded the time budget."


class BudgetExceededError(ExtractionError):
    code = "partial_success"
    http_status = 200
    retryable = False
    log_level = logging.INFO
    user_message_template = "Partial result returned within time budget."


class LlmTransientError(ExtractionError):
    code = "llm_unavailable"
    http_status = 503
    retryable = True
    log_level = logging.ERROR
    user_message_template = "AI service temporarily unavailable."


class SchemaGenerationError(ExtractionError):
    code = "schema_generation_failed"
    http_status = 422
    retryable = False
    log_level = logging.ERROR
    user_message_template = "Could not understand the instruction."


class ExtractionPlanError(ExtractionError):
    code = "extraction_plan_failed"
    http_status = 422
    retryable = False
    log_level = logging.ERROR
    user_message_template = "Could not produce an extraction plan."


class ValidationFailedError(ExtractionError):
    code = "validation_failed"
    http_status = 200
    retryable = False
    log_level = logging.INFO
    user_message_template = "Extracted data did not pass validation."


class NoRelevantDataError(ExtractionError):
    code = "no_relevant_data_found"
    http_status = 200
    retryable = False
    log_level = logging.INFO
    user_message_template = "Could not find the requested data on this page."


class InvalidSelectorError(ExtractionError):
    code = "invalid_selector"
    http_status = 422
    retryable = False
    log_level = logging.WARNING
    user_message_template = "Selector '{selector}' is not valid."


class InternalError(ExtractionError):
    code = "internal_error"
    http_status = 500
    retryable = False
    log_level = logging.ERROR
    user_message_template = "Unexpected internal error."


SOFT_ERROR_CODES = frozenset({
    "partial_success",
    "validation_failed",
    "no_relevant_data_found",
})
