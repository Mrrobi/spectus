from __future__ import annotations

from spectus._schemas.intent import FieldSpec, IntentSchema
from spectus._core.template_manager import goal_signature, url_pattern_glob


def _schema(names):
    return IntentSchema(
        task_type="list_extraction",
        entity_name="thing",
        fields=tuple(FieldSpec(name=n, type="string") for n in names),
        expected_output="array",
    )


def test_goal_signature_stable_across_order():
    s1 = goal_signature(_schema(["title", "price", "rating"]))
    s2 = goal_signature(_schema(["rating", "title", "price"]))
    assert s1 == s2


def test_goal_signature_differs_for_different_fields():
    s1 = goal_signature(_schema(["title", "price"]))
    s2 = goal_signature(_schema(["title", "author"]))
    assert s1 != s2


def test_url_pattern_glob_numeric():
    assert url_pattern_glob("https://x.com/products/12345") == "/products/*"


def test_url_pattern_glob_hex():
    assert (
        url_pattern_glob("https://x.com/items/abcdef1234567890")
        == "/items/*"
    )


def test_url_pattern_glob_slug_with_digit():
    assert url_pattern_glob("https://x.com/jobs/sde-12345") == "/jobs/*"


def test_url_pattern_glob_pure_text():
    assert url_pattern_glob("https://x.com/category/shoes") == "/category/shoes"
