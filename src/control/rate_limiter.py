from __future__ import annotations

import threading
import time
from typing import Callable


class TokenBucketRateLimiter:
    """Simple token-bucket limiter suitable for API request pacing.

    The implementation is intentionally dependency-free so it can be used in
    local scripts, workers, and tests without extra runtime requirements.
    """

    def __init__(
        self,
        permits_per_minute: int,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.permits_per_minute = permits_per_minute
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._capacity = float(max(1, permits_per_minute))
        self._tokens = self._capacity
        self._last_refill = self._clock()
        self._refill_rate_per_second = self._capacity / 60.0 if permits_per_minute > 0 else float("inf")

    def acquire(self, permits: float = 1.0) -> float:
        """Blocks until the requested permits are available.

        Returns the amount of time spent waiting in seconds.
        """
        if self.permits_per_minute <= 0:
            return 0.0

        waited = 0.0
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= permits:
                    self._tokens -= permits
                    return waited
                deficit = permits - self._tokens
                sleep_for = deficit / self._refill_rate_per_second
            self._sleep(sleep_for)
            waited += sleep_for

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed == 0:
            return
        self._tokens = min(self._capacity, self._tokens + (elapsed * self._refill_rate_per_second))
        self._last_refill = now
