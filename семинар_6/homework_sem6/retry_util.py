"""Повтор вызова при 429 Rate Limit."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 20,
    base_delay: float = 15.0,
) -> T:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = str(e).lower()
            if "429" in msg or "too many requests" in msg or "rate" in msg:
                wait = base_delay * (attempt + 1)
                print(f"  [retry {attempt + 1}/{retries}] 429, жду {wait:.0f}с...", flush=True)
                time.sleep(wait)
                continue
            raise
    assert last is not None
    raise last
