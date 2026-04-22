"""whyllmClient — thin HTTP client for the ingest API."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)


class whyllmClient:
    """Low-level client for sending span data to the whyllm ingest API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("WHYLLM_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("WHYLLM_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
        )

    def ingest_span(self, span: dict[str, Any]) -> None:
        """Send a single span. Swallows errors — never raises."""
        try:
            self._http.post("/v1/ingest/span", json=span)
        except Exception as exc:
            log.debug("ingest_span failed: %s", exc)

    def ingest_batch(self, spans: list[dict[str, Any]]) -> None:
        """Send a batch of spans. Raises on HTTP error (caller handles retry)."""
        resp = self._http.post("/v1/ingest/batch", json={"spans": spans})
        resp.raise_for_status()

    def verify(self) -> bool:
        """Check connectivity. Returns True if the server is reachable."""
        try:
            resp = self._http.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "whyllmClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
