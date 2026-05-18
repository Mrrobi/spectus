from __future__ import annotations

import time

import pytest

from app.errors import BudgetExceededError
from app.services.budget import BudgetTracker


def test_remaining_decreases():
    b = BudgetTracker(total_s=1.0)
    r1 = b.remaining()
    time.sleep(0.05)
    r2 = b.remaining()
    assert r1 > r2


def test_assert_at_least_raises():
    b = BudgetTracker(total_s=0.1)
    with pytest.raises(BudgetExceededError):
        b.assert_at_least(1.0, "test_step")


def test_assert_at_least_passes():
    b = BudgetTracker(total_s=10.0)
    b.assert_at_least(0.5, "tiny")


def test_remaining_for_capped():
    b = BudgetTracker(total_s=10.0)
    assert b.remaining_for("step", 3.0) <= 3.0
