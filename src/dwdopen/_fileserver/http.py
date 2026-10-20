"""HTTP access to the Open Data file server."""

from __future__ import annotations

import logging
import time

import httpx

from dwdopen.exceptions import CatalogueUnavailableError, DownloadError

__all__ = ["HttpClient"]

logger = logging.getLogger("dwdopen")

LISTING_ATTEMPTS = 3
"""Attempts per directory listing."""

LISTING_BACKOFF = 1.0
"""Seconds before the second attempt of a listing, doubled after that."""


class HttpClient:
    """Fetches paths below a base URL and maps HTTP failures onto dwdopen errors.
    Contains separate methods for fetching a listing and fetching an actual file,
    to separate potential errors.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_connections: int = 16,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "dwdopen"},
            limits=httpx.Limits(max_connections=max_connections),
        )

    def get_listing(self, path: str) -> str:
        """Fetch a directory listing as text.
        A timeout, a dropped connection or a server error (429, 5xx) is retried
        a few times. A 404 is not retried.
        """
        attempt = 1
        while True:
            try:
                response = self._client.get(path)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                if attempt >= LISTING_ATTEMPTS or not _worth_retrying(exc):
                    raise CatalogueUnavailableError(
                        f"could not read {path}: {exc}"
                    ) from exc
                delay = LISTING_BACKOFF * 2 ** (attempt - 1)
                logger.warning(
                    "attempt %d/%d to list %s failed (%s), retrying in %.1fs",
                    attempt, LISTING_ATTEMPTS, path, exc, delay,
                )
                time.sleep(delay)
                attempt += 1

    def get_asset(self, path: str) -> bytes:
        """Fetch one file.
        The status is put in the error so the caller can decide how to recover
        from the error based on the failed state.
        """
        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DownloadError(
                f"could not download {path}: {exc}",
                status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise DownloadError(f"could not download {path}: {exc}") from exc
        return response.content

    def close(self) -> None:
        self._client.close()


def _worth_retrying(exc: httpx.HTTPError) -> bool:
    """Whether a failed request might succeed when sent again."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    # A timeout or a connection problem.
    return True
