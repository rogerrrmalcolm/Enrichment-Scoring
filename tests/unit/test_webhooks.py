from __future__ import annotations

import json
import unittest

from src.control.webhooks import WebhookNotifier


class WebhookNotifierTests(unittest.TestCase):
    def test_emit_posts_json_payload_to_each_url(self) -> None:
        calls: list[tuple[str, dict[str, object], float]] = []

        def transport(url: str, body: bytes, timeout_seconds: float) -> int:
            calls.append((url, json.loads(body.decode("utf-8")), timeout_seconds))
            return 200

        notifier = WebhookNotifier(
            ("https://example.test/a", "https://example.test/b"),
            timeout_seconds=3.5,
            transport=transport,
        )

        deliveries = notifier.emit("run.completed", {"run_id": "abc123"})

        self.assertEqual(len(deliveries), 2)
        self.assertEqual(calls[0][0], "https://example.test/a")
        self.assertEqual(calls[0][1]["event_type"], "run.completed")
        self.assertEqual(calls[0][1]["payload"]["run_id"], "abc123")
        self.assertEqual(calls[0][2], 3.5)


if __name__ == "__main__":
    unittest.main()
