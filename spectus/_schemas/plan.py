from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from spectus._schemas.intent import FieldType

ExtractionStrategy = Literal[
    "structured_data",
    "single_dom_selector",
    "repeated_dom_selector",
    "table_extraction",
    "article_extraction",
    "visible_text_regex",
    "semantic_extraction",
    "manual_fallback_failed",
]
AllowedAttribute = Literal["text", "href", "src", "alt", "title", "class", "id", "value"]

_DATA_ARIA_RE = re.compile(r"(data-|aria-)[a-z][a-z0-9\-]*")


class NamedFieldSelector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    selector: str
    attribute: str
    type: FieldType
    fallback_selector: str | None = None

    @field_validator("attribute")
    @classmethod
    def _allowed(cls, v: str) -> str:
        if v in get_args(AllowedAttribute):
            return v
        if _DATA_ARIA_RE.fullmatch(v):
            return v
        raise ValueError(f"attribute '{v}' not allowed")


FieldSelector = NamedFieldSelector


class NamedRegex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    pattern: str


class Pagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_pagination: bool = False
    next_selector: str | None = None


class ExtractionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: ExtractionStrategy
    container_selector: str | None = None
    fields: list[NamedFieldSelector] = Field(default_factory=list)
    table_selector: str | None = None
    regex_patterns: list[NamedRegex] | None = None
    pagination: Pagination = Field(default_factory=Pagination)
    confidence: float = 0.5
    reason: str | None = None

    def field_map(self) -> dict[str, NamedFieldSelector]:
        return {f.name: f for f in self.fields}
