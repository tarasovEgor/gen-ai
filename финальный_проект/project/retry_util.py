"""Повтор при 429."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], *, retries: int = 8, base_delay: float = 5.0) -> T:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "too many" in msg:
                wait = base_delay * (attempt + 1)
                print(f"  [retry {attempt + 1}/{retries}] жду {wait:.0f}с...", flush=True)
                time.sleep(wait)
                continue
            if "402" in msg or "insufficient balance" in msg:
                raise RuntimeError(
                    "Недостаточно баланса API (402). Пополните LLM_AUTH_TOKEN или смените endpoint в .env"
                ) from e
            raise
    assert last is not None
    raise last
