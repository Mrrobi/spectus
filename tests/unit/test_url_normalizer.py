from __future__ import annotations

import pytest

from spectus._core.url_normalizer import normalize
from spectus.errors import InvalidUrlError


def test_basic_https():
    n = normalize("https://Example.COM/Path?utm_source=x&id=42")
    assert n.scheme == "https"
    assert n.host == "example.com"
    assert n.domain == "example.com"
    assert "utm_source" not in n.canonical
    assert "id=42" in n.canonical


def test_drops_default_port():
    n = normalize("https://example.com:443/")
    assert n.canonical == "https://example.com/"


def test_keeps_nondefault_port():
    n = normalize("http://example.com:8080/x")
    assert "example.com:8080" in n.canonical


def test_invalid_scheme():
    with pytest.raises(InvalidUrlError):
        normalize("ftp://example.com/x")


def test_empty_url():
    with pytest.raises(InvalidUrlError):
        normalize("")


def test_no_host():
    with pytest.raises(InvalidUrlError):
        normalize("https://")


def test_registered_domain():
    n = normalize("https://sub.example.co.uk/")
    assert n.domain == "example.co.uk"
    assert n.host == "sub.example.co.uk"


def test_query_sorted():
    n = normalize("https://example.com/?b=2&a=1")
    assert n.canonical.endswith("?a=1&b=2")
