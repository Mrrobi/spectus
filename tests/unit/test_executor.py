from __future__ import annotations

import pytest

from spectus.config import Settings
from spectus._schemas.intent import FieldSpec, IntentSchema
from spectus._schemas.plan import ExtractionPlan, FieldSelector
from spectus._core.extraction_executor import ExtractionExecutor
from spectus._core.normalizer import FieldNormalizer


HTML = """
<html><body>
<div class="grid">
  <article class="product-card">
    <h2 class="product-title">Nike Runner</h2>
    <span class="price">$89.99</span>
    <a class="link" href="/products/nike-runner">view</a>
  </article>
  <article class="product-card">
    <h2 class="product-title">Adidas Boost</h2>
    <span class="price">$129.99</span>
    <a class="link" href="/products/adidas-boost">view</a>
  </article>
</div>
</body></html>
"""


def _executor():
    return ExtractionExecutor(FieldNormalizer(), Settings(allow_private_targets=True))


def _schema():
    return IntentSchema(
        task_type="list_extraction",
        entity_name="product",
        fields=(
            FieldSpec(name="title", type="string", required=True),
            FieldSpec(name="price", type="currency", required=True),
            FieldSpec(name="url", type="url"),
        ),
        expected_output="array",
    )


def test_repeated_dom_selector_extracts_records():
    plan = ExtractionPlan(
        strategy="repeated_dom_selector",
        container_selector="article.product-card",
        fields=[
            FieldSelector(name="title", selector=".product-title", attribute="text", type="string"),
            FieldSelector(name="price", selector=".price", attribute="text", type="currency"),
            FieldSelector(name="url", selector="a.link", attribute="href", type="url"),
        ],
        confidence=0.9,
    )
    result = _executor().execute(plan, HTML, "https://example.com/", _schema(), 100)
    assert result.status == "success"
    assert len(result.records) == 2
    assert result.records[0]["title"] == "Nike Runner"
    assert result.records[0]["price"] == "$89.99"
    assert result.records[0]["url"].startswith("https://example.com/")


def test_disallowed_attribute_rejected_at_validation():
    with pytest.raises(Exception):
        FieldSelector(name="x", selector=".x", attribute="onclick", type="string")


def test_data_attribute_allowed():
    fs = FieldSelector(name="x", selector=".x", attribute="data-product-id", type="string")
    assert fs.attribute == "data-product-id"


def test_empty_container_returns_empty():
    plan = ExtractionPlan(
        strategy="repeated_dom_selector",
        container_selector=".missing",
        fields=[
            FieldSelector(name="title", selector="h2", attribute="text", type="string"),
        ],
        confidence=0.5,
    )
    result = _executor().execute(plan, HTML, "https://example.com/", _schema(), 100)
    assert result.status == "empty"
    assert result.records == []
