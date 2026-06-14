from __future__ import annotations

import pytest

from pilot_agent.agent.iteration_budget import IterationBudget


def test_iteration_budget_consumes_refunds_and_exhausts() -> None:
    budget = IterationBudget(2)

    assert budget.consume() is True
    assert budget.snapshot().remaining == 1
    budget.refund()
    assert budget.remaining == 2
    assert budget.consume(2) is True
    assert budget.consume() is False
    assert budget.snapshot().exhausted is True


def test_iteration_budget_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        IterationBudget(0)

    budget = IterationBudget(1)
    with pytest.raises(ValueError):
        budget.consume(0)
    with pytest.raises(ValueError):
        budget.refund(0)
