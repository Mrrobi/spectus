from __future__ import annotations

from time import monotonic

from spectus.errors import BudgetExceededError


class BudgetTracker:
    def __init__(self, total_s: float = 30.0) -> None:
        self._start = monotonic()
        self._deadline = self._start + total_s
        self._total = total_s

    def remaining(self) -> float:
        return max(0.0, self._deadline - monotonic())

    def elapsed(self) -> float:
        return monotonic() - self._start

    def assert_at_least(self, seconds: float, step: str) -> None:
        if self.remaining() < seconds:
            raise BudgetExceededError(
                detail=f"step '{step}' requires {seconds:.1f}s, only {self.remaining():.1f}s left"
            )

    def remaining_for(self, step: str, max_s: float) -> float:
        rem = self.remaining()
        if rem <= 0:
            raise BudgetExceededError(detail=f"step '{step}' has 0s remaining")
        return min(max_s, rem)
