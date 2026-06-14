from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class IterationBudgetSnapshot:
    limit: int
    consumed: int
    remaining: int

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0


class IterationBudget:
    """Thread-safe consume/refund budget for agent loop iterations."""

    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("iteration budget limit must be at least 1")
        self._limit = limit
        self._consumed = 0
        self._lock = threading.Lock()

    def consume(self, amount: int = 1) -> bool:
        if amount < 1:
            raise ValueError("consume amount must be at least 1")
        with self._lock:
            if self._consumed + amount > self._limit:
                return False
            self._consumed += amount
            return True

    def refund(self, amount: int = 1) -> None:
        if amount < 1:
            raise ValueError("refund amount must be at least 1")
        with self._lock:
            self._consumed = max(0, self._consumed - amount)

    def snapshot(self) -> IterationBudgetSnapshot:
        with self._lock:
            consumed = self._consumed
        return IterationBudgetSnapshot(
            limit=self._limit,
            consumed=consumed,
            remaining=max(0, self._limit - consumed),
        )

    @property
    def remaining(self) -> int:
        return self.snapshot().remaining

    @property
    def consumed(self) -> int:
        return self.snapshot().consumed

    @property
    def limit(self) -> int:
        return self._limit
