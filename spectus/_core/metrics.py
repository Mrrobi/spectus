from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def _label_key(name: str, labels: dict[str, Any]) -> str:
    if not labels:
        return name
    flat = ",".join(f"{k}={labels[k]}" for k in sorted(labels))
    return f"{name}{{{flat}}}"


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    return {
        "count": n,
        "min": sorted_v[0],
        "max": sorted_v[-1],
        "mean": statistics.mean(sorted_v),
        "p50": sorted_v[int(n * 0.5)] if n else 0,
        "p95": sorted_v[min(n - 1, int(n * 0.95))],
        "p99": sorted_v[min(n - 1, int(n * 0.99))],
    }


class Metrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.histograms: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: int = 1, **labels: Any) -> None:
        self.counters[_label_key(name, labels)] += value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        self.histograms[_label_key(name, labels)].append(float(value))

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "histograms": {k: _summary(v) for k, v in self.histograms.items()},
        }

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")

    def reset(self) -> None:
        self.counters.clear()
        self.histograms.clear()
