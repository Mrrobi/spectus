from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from selectolax.parser import HTMLParser, Node

from spectus._schemas.page import CandidateSection

_NAV_TAGS = frozenset({"nav", "footer", "aside", "header"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "br", "hr", "meta", "link", "head"})

_UNSTABLE_CLASS_RE = re.compile(
    r"^(is-|has-|active|selected|hover|open|expanded|focused|"
    r"css-[a-z0-9]+|sc-[a-z0-9]+|jsx-\d+|\d+)$"
)
_PRICE_RE = re.compile(r"(?:[$€£¥]\s?\d|\d+[\.,]\d{2})")
_WS_RE = re.compile(r"\s+")


@dataclass
class _RawCandidate:
    selector: str
    count: int
    avg_text_length: float
    sample_texts: list[str]
    score: float
    matched_text: str

    def to_model(self) -> CandidateSection:
        return CandidateSection(
            selector=self.selector,
            count=self.count,
            avg_text_length=self.avg_text_length,
            sample_texts=self.sample_texts,
            confidence=self.score,
        )


def _stable_classes(class_attr: str) -> tuple[str, ...]:
    if not class_attr:
        return ()
    tokens: list[str] = []
    for raw in class_attr.lower().split():
        if not raw:
            continue
        if len(raw) > 30:
            continue
        if _UNSTABLE_CLASS_RE.match(raw):
            continue
        tokens.append(raw)
    return tuple(sorted(set(tokens)))


def _has_ancestor_tag(node: Node | None, tags: frozenset[str]) -> bool:
    cur = node
    depth = 0
    while cur is not None and depth < 30:
        if cur.tag in tags:
            return True
        cur = cur.parent
        depth += 1
    return False


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def _structural_fingerprint(node: Node, max_depth: int = 3) -> frozenset[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    stack: list[tuple[Node, int]] = [(node, 0)]
    while stack:
        n, depth = stack.pop()
        if depth > max_depth:
            continue
        for child in n.iter(include_text=False):
            if child.tag in _SKIP_TAGS:
                continue
            out.add((child.tag, depth + 1))
            stack.append((child, depth + 1))
    return frozenset(out)


def _structural_similarity(siblings: list[Node]) -> float:
    fps = [_structural_fingerprint(s) for s in siblings]
    n = len(fps)
    if n < 2:
        return 1.0
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = fps[i], fps[j]
            if not a and not b:
                pairs.append(1.0)
                continue
            inter = len(a & b)
            union = len(a | b)
            pairs.append(inter / union if union else 0.0)
    return statistics.mean(pairs) if pairs else 1.0


def _count_descendants(node: Node) -> int:
    return sum(1 for _ in node.iter(include_text=False))


def _has_link(siblings: list[Node]) -> bool:
    return any(s.css_first("a[href]") is not None for s in siblings[:5])


def _has_image(siblings: list[Node]) -> bool:
    return any(s.css_first("img") is not None for s in siblings[:5])


def _has_price_pattern(siblings: list[Node]) -> bool:
    for s in siblings[:5]:
        if _PRICE_RE.search(s.text(strip=False) or ""):
            return True
    return False


def _score(
    count: int,
    sim: float,
    child_count: float,
    has_link: bool,
    has_price: bool,
    has_image: bool,
) -> float:
    return (
        0.30 * min(count / 20.0, 1.0)
        + 0.30 * sim
        + 0.15 * min(child_count / 6.0, 1.0)
        + 0.10 * (1.0 if has_link else 0.0)
        + 0.10 * (1.0 if has_price else 0.0)
        + 0.05 * (1.0 if has_image else 0.0)
    )


def _build_selector(tag: str, classes: tuple[str, ...]) -> str:
    if classes:
        class_part = "." + ".".join(_escape_class(c) for c in classes[:3])
        return f"{tag}{class_part}"
    return tag


def _escape_class(name: str) -> str:
    return re.sub(r"([^a-z0-9_-])", r"\\\1", name, flags=re.IGNORECASE)


def _validate_count(tree: HTMLParser, selector: str, expected: int) -> bool:
    try:
        matched = tree.css(selector)
    except Exception:
        return False
    return abs(len(matched) - expected) <= max(1, int(expected * 0.05))


def _walk_elements(root: Node) -> Iterable[Node]:
    stack: list[Node] = [root]
    while stack:
        n = stack.pop()
        for child in n.iter(include_text=False):
            yield child
            stack.append(child)


def _walk_parents(root: Node) -> Iterable[Node]:
    yield root
    stack: list[Node] = [root]
    while stack:
        n = stack.pop()
        for child in n.iter(include_text=False):
            if child.tag in _SKIP_TAGS:
                continue
            yield child
            stack.append(child)


def detect_repeated_sections(html: str) -> list[CandidateSection]:
    tree = HTMLParser(html)
    if tree.body is None:
        return []
    candidates: list[_RawCandidate] = []
    for parent in _walk_parents(tree.body):
        children = list(parent.iter(include_text=False))
        if len(children) < 3:
            continue
        groups: dict[tuple[str, tuple[str, ...]], list[Node]] = defaultdict(list)
        for c in children:
            tag = c.tag
            if not tag or tag in _SKIP_TAGS:
                continue
            classes = _stable_classes(c.attributes.get("class") or "")
            groups[(tag, classes)].append(c)

        for (tag, classes), siblings in groups.items():
            if len(siblings) < 3:
                continue
            if _has_ancestor_tag(parent, _NAV_TAGS):
                continue
            sample = siblings[:10]
            avg_children = (
                statistics.mean(_count_descendants(s) for s in sample) if sample else 0.0
            )
            if avg_children < 2:
                continue
            sim = _structural_similarity(sample)
            if sim < 0.55:
                continue
            selector = _build_selector(tag, classes)
            if not _validate_count(tree, selector, len(siblings)):
                continue
            score = _score(
                count=len(siblings),
                sim=sim,
                child_count=avg_children,
                has_link=_has_link(sample),
                has_price=_has_price_pattern(sample),
                has_image=_has_image(sample),
            )
            sample_texts = [_normalize_text(s.text(strip=False))[:200] for s in sample[:2]]
            avg_text_len = (
                statistics.mean(len(_normalize_text(s.text(strip=False))) for s in sample)
                if sample
                else 0.0
            )
            candidates.append(
                _RawCandidate(
                    selector=selector,
                    count=len(siblings),
                    avg_text_length=avg_text_len,
                    sample_texts=sample_texts,
                    score=score,
                    matched_text=" ".join(sample_texts),
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    deduped = _dedup_overlapping(candidates)
    return [c.to_model() for c in deduped[:5]]


def _dedup_overlapping(candidates: list[_RawCandidate]) -> list[_RawCandidate]:
    out: list[_RawCandidate] = []
    for c in candidates:
        is_subset = False
        for kept in out:
            if c.selector == kept.selector:
                is_subset = True
                break
            if c.matched_text and c.matched_text in kept.matched_text:
                is_subset = True
                break
        if not is_subset:
            out.append(c)
    return out
