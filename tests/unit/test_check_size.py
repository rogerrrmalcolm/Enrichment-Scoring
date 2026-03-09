from __future__ import annotations

import unittest

from src.scoring.check_size import estimate_check_size


class CheckSizeEstimatorTests(unittest.TestCase):
    def test_estimates_foundation_check_size_from_aum(self) -> None:
        estimate = estimate_check_size("$6.4B", "Foundation")

        self.assertEqual(estimate, "$64.00M-$192.00M")


if __name__ == "__main__":
    unittest.main()
