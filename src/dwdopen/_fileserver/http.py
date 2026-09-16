"""HTTP access to the Open Data file server."""

from __future__ import annotations

import httpx

from dwdopen.exceptions import CatalogueUnavailableError, DownloadError

__all__ = ["HttpClient"]


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
            headers={"User-Agent": "dwdopen/0.1.0.dev0"},
            limits=httpx.Limits(max_connections=max_connections),
        )

    def get_listing(self, path: str) -> str:
        """Fetch a directory listing as text."""
        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CatalogueUnavailableError(f"could not read {path}: {exc}") from exc
        return response.text

    def get_asset(self, path: str) -> bytes:
        """Fetch one file."""
        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DownloadError(f"could not download {path}: {exc}") from exc
        return response.content

    def close(self) -> None:
        self._client.close()
