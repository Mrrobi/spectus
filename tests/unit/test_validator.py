from __future__ import annotations

import pytest

from spectus._schemas.execution import ExtractionResult
from spectus._schemas.intent import FieldSpec, IntentSchema
from spectus._schemas.page import CompactPage
from spectus._core.validator import Validator


def _intent(fields, expected_output="array"):
    return IntentSchema(
        task_type="list_extraction" if expected_output == "array" else "single_entity_extraction",
        entity_name="thing",
        fields=tuple(fields),
        expected_output=expected_output,
    )


def _compact(containers: int = 0):
    if containers:
        from spectus._schemas.page import CandidateSection
        return CompactPage(
            url="http://x",
            candidate_sections=[
                CandidateSection(
                    selector=".x",
                    count=containers,
                    avg_text_length=100,
                    sample_texts=["a", "b"],
                    confidence=0.8,
                )
            ],
        )
    return CompactPage(url="http://x")


def test_empty_records_array_triggers_repair():
    schema = _intent([FieldSpec(name="title", type="string", required=True)])
    result = ExtractionResult(status="empty", strategy_used="repeated_dom_selector", records=[])
    rep = Validator().validate(result, schema, _compact(10))
    assert rep.needs_repair is True
    assert rep.good_enough is False


def test_full_coverage_high_score():
    schema = _intent([
        FieldSpec(name="title", type="string", required=True),
        FieldSpec(name="price", type="currency", required=True),
    ])
    records = [
        {"title": "Nike Runner", "price": "$89.99"},
        {"title": "Adidas Boost", "price": "$129.99"},
    ]
    result = ExtractionResult(
        status="success", strategy_used="repeated_dom_selector", records=records
    )
    rep = Validator().validate(result, schema, _compact(2))
    assert rep.good_enough is True
    assert rep.overall_score >= 0.80


def test_missing_required_triggers_repair():
    schema = _intent([
        FieldSpec(name="title", type="string", required=True),
        FieldSpec(name="price", type="currency", required=True),
    ])
    records = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    result = ExtractionResult(
        status="success", strategy_used="repeated_dom_selector", records=records
    )
    rep = Validator().validate(result, schema, _compact(3))
    assert rep.needs_repair is True
    assert rep.missing_required["price"] == 3


def test_duplication_detected():
    schema = _intent([FieldSpec(name="url", type="url", required=True)])
    records = [
        {"url": "https://example.com/a"},
        {"url": "https://example.com/a"},
        {"url": "https://example.com/b"},
    ]
    result = ExtractionResult(
        status="success", strategy_used="repeated_dom_selector", records=records
    )
    rep = Validator().validate(result, schema, _compact(3))
    assert rep.duplicate_count == 1
    assert rep.duplication_score < 1.0


def test_single_entity_one_record_perfect():
    schema = _intent(
        [FieldSpec(name="title", type="string", required=True)],
        expected_output="object",
    )
    records = [{"title": "Hello"}]
    result = ExtractionResult(
        status="success", strategy_used="single_dom_selector", records=records
    )
    rep = Validator().validate(result, schema, _compact())
    assert rep.record_count_score == 1.0
