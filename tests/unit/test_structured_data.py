from __future__ import annotations

from spectus._core.structured_data import extract

JSON_LD_PRODUCT = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Nike Runner", "offers": {"@type": "Offer", "price": "89.99", "priceCurrency": "USD"}}
</script>
<meta property="og:title" content="Nike Runner">
<meta property="og:image" content="https://x.com/img.jpg">
</head><body></body></html>
"""


def test_json_ld_extracted():
    sd = extract(JSON_LD_PRODUCT)
    assert "Product" in sd.json_ld_types
    assert any("Nike Runner" in str(p.payload) for p in sd.raw_payloads)


def test_open_graph_extracted():
    sd = extract(JSON_LD_PRODUCT)
    assert sd.open_graph.get("og:title") == "Nike Runner"
    assert "img.jpg" in sd.open_graph.get("og:image", "")


def test_no_structured_data():
    sd = extract("<html><body><p>nothing</p></body></html>")
    assert sd.json_ld_types == []
    assert sd.open_graph == {}
    assert sd.next_data_present is False


def test_next_data_detected():
    html = '<html><body><script id="__NEXT_DATA__" type="application/json">{"props":{}}</script></body></html>'
    sd = extract(html)
    assert sd.next_data_present is True
