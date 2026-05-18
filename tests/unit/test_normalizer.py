from __future__ import annotations

from spectus._core.normalizer import FieldNormalizer


def test_url_normalizer_resolves_relative():
    n = FieldNormalizer()
    assert (
        n.normalize("/products/1", "url", "https://example.com/category")
        == "https://example.com/products/1"
    )


def test_url_normalizer_rejects_nonhttp():
    n = FieldNormalizer()
    assert n.normalize("javascript:void(0)", "url", "https://example.com/") is None


def test_currency_extracts():
    n = FieldNormalizer()
    assert n.normalize("Only $89.99 today!", "currency") == "$89.99"


def test_number_parses():
    n = FieldNormalizer()
    assert n.normalize("Rating: 4.7 stars", "number") == 4.7


def test_integer_parses():
    n = FieldNormalizer()
    assert n.normalize("Page 12 of 30", "integer") == 12


def test_email_extracts():
    n = FieldNormalizer()
    assert n.normalize("Contact: foo@bar.com please", "email") == "foo@bar.com"


def test_phone_digits():
    n = FieldNormalizer()
    assert n.normalize("Call (555) 123-4567 now", "phone") == "5551234567"


def test_phone_too_short():
    n = FieldNormalizer()
    assert n.normalize("12345", "phone") is None


def test_date_iso():
    n = FieldNormalizer()
    assert n.normalize("January 5, 2024", "date") == "2024-01-05"


def test_boolean_in_stock():
    n = FieldNormalizer()
    assert n.normalize("In stock", "boolean") is True
    assert n.normalize("out of stock", "boolean") is False


def test_list_string_split():
    n = FieldNormalizer()
    assert n.normalize("red, blue, green", "list_string") == ["red", "blue", "green"]


def test_string_collapses_ws():
    n = FieldNormalizer()
    assert n.normalize("  hello\n  world  ", "string") == "hello world"
