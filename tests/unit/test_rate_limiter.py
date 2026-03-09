from __future__ import annotations

import unittest

from src.control.rate_limiter import TokenBucketRateLimiter


class TokenBucketRateLimiterTests(unittest.TestCase):
    def test_second_request_waits_for_refill(self) -> None:
        state = {"now": 0.0}

        def clock() -> float:
            return state["now"]

        def sleep(seconds: float) -> None:
            state["now"] += seconds

        limiter = TokenBucketRateLimiter(1, clock=clock, sleep=sleep)

        first_wait = limiter.acquire()
        second_wait = limiter.acquire()

        self.assertEqual(first_wait, 0.0)
        self.assertAlmostEqual(second_wait, 60.0, places=3)


if __name__ == "__main__":
    unittest.main()
