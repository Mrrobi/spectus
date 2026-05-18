from __future__ import annotations

import re
import statistics
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from dateutil import parser as date_parser

from app.schemas.execution import ExtractionResult
from app.schemas.intent import FieldType, IntentSchema
from app.schemas.page import CompactPage
from app.schemas.validation import ValidationReport

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_BOOL_STRINGS = frozenset({"true", "false", "yes", "no", "0", "1"})
_NUM_TEXT_RE = re.compile(r"-?\d+(?:[\.,]\d+)?")
_INT_TEXT_RE = re.compile(r"^-?\d+$")


def _present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict, set, tuple)):
        return len(v) > 0
    return True


_MAX_LEN_FOR_TYPE: dict[FieldType, int] = {
    "string": 4000,
    "number": 30,
    "integer": 20,
    "currency": 60,
    "url": 500,
    "email": 254,
    "phone": 30,
    "date": 60,
    "boolean": 10,
    "list_string": 4000,
}


def _parses_as(v: Any, field_type: FieldType) -> bool:
    if v is None or v == "":
        return False
    if isinstance(v, str) and len(v) > _MAX_LEN_FOR_TYPE.get(field_type, 4000):
        return False
    if field_type in ("string", "list_string"):
        return isinstance(v, (str, list))
    if field_type == "url":
        if not isinstance(v, str):
            return False
        try:
            return urlparse(v).scheme in ("http", "https")
        except ValueError:
            return False
    if field_type == "email":
        return isinstance(v, str) and bool(_EMAIL_RE.fullmatch(v))
    if field_type == "phone":
        text = str(v)
        digits = re.sub(r"\D", "", text)
        return 7 <= len(digits) <= 15
    if field_type == "date":
        if isinstance(v, str):
            try:
                date_parser.parse(v, fuzzy=True)
                return True
            except (ValueError, OverflowError):
                return False
        return False
    if field_type == "boolean":
        if isinstance(v, bool):
            return True
        if isinstance(v, str):
            return v.lower().strip() in _BOOL_STRINGS
        return False
    if field_type == "integer":
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            return True
        if isinstance(v, str):
            return bool(_INT_TEXT_RE.match(v.strip()))
        return False
    if field_type == "number":
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
        if isinstance(v, str):
            try:
                Decimal(v.strip().replace(",", "."))
                return True
            except (InvalidOperation, ValueError):
                return False
        return False
    if field_type == "currency":
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
        if isinstance(v, str):
            return bool(_NUM_TEXT_RE.search(v))
        return False
    return True


def _dedup_key(record: dict[str, Any]) -> tuple:
    if record.get("url"):
        return ("url", record["url"])
    if record.get("href"):
        return ("href", record["href"])
    if record.get("name") and record.get("price"):
        return ("name+price", record["name"], record["price"])
    return ("full", tuple(sorted((k, str(v)) for k, v in record.items())))


class Validator:
    def validate(
        self,
        result: ExtractionResult,
        schema: IntentSchema,
        compact: CompactPage,
    ) -> ValidationReport:
        records = result.records
        n = len(records)
        containers = (
            compact.candidate_sections[0].count
            if compact.candidate_sections
            else max(1, n)
        )
        record_count_score = self._record_count_score(n, containers, schema.expected_output)
        required_fields = schema.required_fields()
        optional_fields = schema.optional_fields()
        missing_required = {f.name: 0 for f in required_fields}
        missing_optional = {f.name: 0 for f in optional_fields}
        invalid_types: dict[str, int] = {}
        if n == 0:
            field_coverage_score = 0.0 if required_fields else 1.0
            type_validity_score = 1.0
            duplication_score = 1.0
            duplicate_count = 0
        else:
            req_cov_per_field = []
            for f in required_fields:
                present = sum(1 for r in records if _present(r.get(f.name)))
                missing_required[f.name] = n - present
                req_cov_per_field.append(present / n)
            opt_cov_per_field = []
            for f in optional_fields:
                present = sum(1 for r in records if _present(r.get(f.name)))
                missing_optional[f.name] = n - present
                opt_cov_per_field.append(present / n)
            req_cov = statistics.mean(req_cov_per_field) if req_cov_per_field else 1.0
            opt_cov = statistics.mean(opt_cov_per_field) if opt_cov_per_field else 1.0
            field_coverage_score = 0.7 * req_cov + 0.3 * opt_cov
            total = 0
            ok = 0
            for r in records:
                for f in schema.fields:
                    v = r.get(f.name)
                    if not _present(v):
                        continue
                    total += 1
                    if _parses_as(v, f.type):
                        ok += 1
                    else:
                        invalid_types[f.name] = invalid_types.get(f.name, 0) + 1
            type_validity_score = ok / total if total else 1.0
            seen = set()
            dups = 0
            for r in records:
                k = _dedup_key(r)
                if k in seen:
                    dups += 1
                seen.add(k)
            duplicate_count = dups
            duplication_score = 1 - dups / max(n, 1)

        overall_score = (
            0.20 * record_count_score
            + 0.45 * field_coverage_score
            + 0.25 * type_validity_score
            + 0.10 * duplication_score
        )
        any_required_short = any(
            missing_required[f.name] / max(n, 1) > 0.3 for f in required_fields
        )
        critical_required_missing = n > 0 and any(
            missing_required[f.name] / n > 0.5 for f in required_fields
        )
        good_enough = overall_score >= 0.80 and not critical_required_missing
        needs_repair = (
            overall_score < 0.60
            or (overall_score < 0.80 and any_required_short)
            or critical_required_missing
            or (n == 0 and schema.expected_output == "array")
        )
        repair_hint = self._repair_hint(
            n,
            schema.expected_output,
            missing_required,
            duplication_score,
            type_validity_score,
            invalid_types,
        )
        return ValidationReport(
            overall_score=round(overall_score, 4),
            record_count_score=round(record_count_score, 4),
            field_coverage_score=round(field_coverage_score, 4),
            type_validity_score=round(type_validity_score, 4),
            duplication_score=round(duplication_score, 4),
            missing_required=missing_required,
            missing_optional=missing_optional,
            invalid_types=invalid_types,
            duplicate_count=duplicate_count,
            needs_repair=needs_repair,
            repair_hint=repair_hint,
            good_enough=good_enough,
        )

    def _record_count_score(self, n: int, containers: int, expected: str) -> float:
        if expected == "object":
            return 1.0 if n == 1 else (0.5 if n > 1 else 0.0)
        if n == 0:
            return 0.0
        ratio = n / max(containers, 1)
        if ratio <= 1.0:
            return min(1.0, ratio)
        return max(0.5, 1.0 - (ratio - 1.0) * 0.5)

    def _repair_hint(
        self,
        n: int,
        expected: str,
        missing_required: dict[str, int],
        duplication_score: float,
        type_validity_score: float,
        invalid_types: dict[str, int],
    ) -> str | None:
        if n == 0 and expected == "array":
            return "no records matched container selector"
        if n > 0:
            for name, miss in missing_required.items():
                pct = miss / n * 100
                if pct > 50:
                    return f"required field '{name}' missing in {int(pct)}% of records"
            if duplication_score < 0.7:
                return "selectors return duplicates; container selector likely too broad"
            if type_validity_score < 0.6 and invalid_types:
                worst = max(invalid_types.items(), key=lambda kv: kv[1])[0]
                return f"field type mismatches concentrated on '{worst}'"
        return None
