from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    selector: str
    count: int
    avg_text_length: float
    sample_texts: list[str] = Field(default_factory=list, max_length=2)
    confidence: float = Field(ge=0.0, le=1.0)


class TableSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    selector: str
    row_count: int
    col_count: int
    headers: list[str] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list, max_length=2)


class StructuredPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    payload: dict[str, Any]


class StructuredDataSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    json_ld_types: list[str] = Field(default_factory=list)
    open_graph: dict[str, str] = Field(default_factory=dict)
    twitter: dict[str, str] = Field(default_factory=dict)
    microdata_types: list[str] = Field(default_factory=list)
    next_data_present: bool = False
    nuxt_data_present: bool = False
    initial_state_present: bool = False
    raw_payloads: list[StructuredPayload] = Field(default_factory=list, max_length=5)


class LinkSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    href: str


class CompactPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    title: str | None = None
    meta_description: str | None = None
    headings: list[str] = Field(default_factory=list, max_length=30)
    visible_text_length: int = 0
    text_to_markup_ratio: float = 0.0
    candidate_sections: list[CandidateSection] = Field(default_factory=list, max_length=5)
    tables: list[TableSummary] = Field(default_factory=list, max_length=5)
    structured_data: StructuredDataSummary = Field(default_factory=StructuredDataSummary)
    links_sample: list[LinkSample] = Field(default_factory=list, max_length=20)
    page_type_hint: str = "generic_content"
    source_html_ref: str | None = None
