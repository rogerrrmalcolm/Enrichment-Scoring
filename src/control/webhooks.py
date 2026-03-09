from __future__ import annotations

import json
import logging
from typing import Callable
from urllib import request
from urllib.parse import urlparse


LOCALHOST_WEBHOOK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class WebhookNotifier:
    """Posts pipeline lifecycle events to configured webhook endpoints."""

    def __init__(
        self,
        urls: tuple[str, ...],
        *,
        timeout_seconds: float = 5.0,
        transport: Callable[[str, bytes, float], int] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        self.urls = tuple(_validate_webhook_url(url) for url in urls)
        self.timeout_seconds = timeout_seconds
        self.transport = transport or _post_json
        self.logger = logging.getLogger(__name__)

    def emit(self, event_type: str, payload: dict[str, object]) -> list[dict[str, object]]:
        if not self.urls:
            return []

        body = json.dumps({"event_type": event_type, "payload": payload}).encode("utf-8")
        deliveries: list[dict[str, object]] = []
        for url in self.urls:
            try:
                status_code = self.transport(url, body, self.timeout_seconds)
                deliveries.append({"url": url, "status_code": status_code, "ok": True})
            except Exception as exc:
                self.logger.warning("Webhook delivery failed for %s: %s", url, exc)
                deliveries.append({"url": url, "status_code": None, "ok": False, "error": str(exc)})
        return deliveries


def _post_json(url: str, body: bytes, timeout_seconds: float) -> int:
    req = request.Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "pacezero-pipeline-webhook/1.0",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return int(getattr(response, "status", response.getcode()))


def _validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Webhook URL must use http or https, got {url!r}.")
    if not parsed.netloc:
        raise ValueError(f"Webhook URL is missing a host: {url!r}.")
    if scheme == "http" and hostname not in LOCALHOST_WEBHOOK_HOSTS:
        raise ValueError("Non-local webhook URLs must use https.")
    return url
