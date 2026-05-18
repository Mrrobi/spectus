from __future__ import annotations

from spectus._core.repeated_detector import detect_repeated_sections

PRODUCT_LISTING = """
<html><body>
<header><nav>
  <a href="/x">x</a><a href="/y">y</a><a href="/z">z</a>
  <a href="/q">q</a><a href="/r">r</a>
</nav></header>
<main>
<div class="grid">
  <article class="product-card">
    <h2 class="product-title">Nike Runner</h2>
    <span class="price">$89.99</span>
    <span class="rating">4.7</span>
    <a class="link" href="/products/nike-runner">view</a>
    <img src="/img/nike.png">
  </article>
  <article class="product-card">
    <h2 class="product-title">Adidas Boost</h2>
    <span class="price">$129.99</span>
    <span class="rating">4.5</span>
    <a class="link" href="/products/adidas-boost">view</a>
    <img src="/img/adidas.png">
  </article>
  <article class="product-card">
    <h2 class="product-title">Puma RS</h2>
    <span class="price">$74.50</span>
    <span class="rating">4.2</span>
    <a class="link" href="/products/puma-rs">view</a>
    <img src="/img/puma.png">
  </article>
  <article class="product-card">
    <h2 class="product-title">Asics Gel</h2>
    <span class="price">$99.00</span>
    <span class="rating">4.6</span>
    <a class="link" href="/products/asics-gel">view</a>
    <img src="/img/asics.png">
  </article>
</div>
</main>
</body></html>
"""


NAV_HEAVY = """
<html><body>
<nav>
  <a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>
  <a href="/d">D</a><a href="/e">E</a>
</nav>
<main><p>nothing repeating here</p></main>
</body></html>
"""


def test_finds_product_cards():
    sections = detect_repeated_sections(PRODUCT_LISTING)
    assert len(sections) >= 1
    top = sections[0]
    assert top.count == 4
    assert "product-card" in top.selector


def test_rejects_nav_only():
    sections = detect_repeated_sections(NAV_HEAVY)
    for s in sections:
        assert "nav" not in s.selector.lower()
