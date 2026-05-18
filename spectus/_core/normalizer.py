from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlparse

from dateutil import parser as date_parser

from spectus._schemas.intent import FieldType

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"-?\d+(?:[\.,]\d+)?")
_INT_RE = re.compile(r"-?\d+")
_CURRENCY_RE = re.compile(r"([$€£¥₹]\s?-?\d+(?:[\.,]\d+)?|-?\d+(?:[\.,]\d+)?\s?[$€£¥₹])")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DIGITS_RE = re.compile(r"\D")
_BOOLEAN_TRUE = frozenset({"true", "yes", "1", "in stock", "available"})
_BOOLEAN_FALSE = frozenset({"false", "no", "0", "out of stock", "unavailable"})


class FieldNormalizer:
    def normalize(self, raw: Any, field_type: FieldType, base_url: str | None = None) -> Any:
        if raw is None:
            return None
        if isinstance(raw, list):
            return [self.normalize(v, field_type, base_url) for v in raw]
        if isinstance(raw, (int, float, bool, Decimal)) and field_type in (
            "number",
            "integer",
            "boolean",
        ):
            return self._normalize_primitive(raw, field_type)
        text = str(raw)
        text = _WS_RE.sub(" ", text).strip()
        if not text:
            return None
        if field_type == "url":
            return self._normalize_url(text, base_url)
        if field_type == "currency":
            return self._normalize_currency(text)
        if field_type == "number":
            return self._normalize_number(text)
        if field_type == "integer":
            return self._normalize_integer(text)
        if field_type == "email":
            m = _EMAIL_RE.search(text)
            return m.group(0) if m else None
        if field_type == "phone":
            digits = _DIGITS_RE.sub("", text)
            return digits if 7 <= len(digits) <= 15 else None
        if field_type == "date":
            return self._normalize_date(text)
        if field_type == "boolean":
            return self._normalize_boolean(text)
        if field_type == "list_string":
            parts = [_WS_RE.sub(" ", p).strip() for p in re.split(r"[,;|]", text)]
            return [p for p in parts if p]
        return text

    def _normalize_primitive(self, raw: Any, field_type: FieldType) -> Any:
        if field_type == "boolean":
            return bool(raw)
        if field_type == "integer":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        if field_type == "number":
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
        return raw

    def _normalize_url(self, text: str, base_url: str | None) -> str | None:
        candidate = text.strip()
        if not candidate:
            return None
        if base_url:
            candidate = urljoin(base_url, candidate)
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https"):
            return None
        return candidate

    def _normalize_currency(self, text: str) -> str:
        m = _CURRENCY_RE.search(text)
        return m.group(0).strip() if m else text

    def _normalize_number(self, text: str) -> float | None:
        m = _NUM_RE.search(text)
        if not m:
            return None
        try:
            return float(Decimal(m.group(0).replace(",", ".")))
        except (InvalidOperation, ValueError):
            return None

    def _normalize_integer(self, text: str) -> int | None:
        m = _INT_RE.search(text)
        if not m:
            return None
        try:
            return int(m.group(0))
        except ValueError:
            return None

    def _normalize_date(self, text: str) -> str | None:
        try:
            dt = date_parser.parse(text, fuzzy=True)
        except (ValueError, OverflowError, date_parser.ParserError):
            return None
        return dt.date().isoformat()

    def _normalize_boolean(self, text: str) -> bool | None:
        low = text.lower().strip()
        if low in _BOOLEAN_TRUE:
            return True
        if low in _BOOLEAN_FALSE:
            return False
        return None
