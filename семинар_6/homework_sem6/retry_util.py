"""Повтор вызова при 429 Rate Limit."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], *, retries: int = 6, base_delay: float = 3.0) -> T:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = str(e).lower()
            if "429" in msg or "too many requests" in msg or "rate" in msg:
                time.sleep(base_delay * (attempt + 1))
                continue
            raise
    assert last is not None
    raise last
