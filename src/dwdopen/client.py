"""Entry point: the client and the NWP namespace."""

from __future__ import annotations

from functools import cached_property
from types import TracebackType
from typing import Self

from dwdopen._fileserver.download import HttpDownloader
from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import (
    UnknownModelError,
    resolve_name,
    unknown_name_message,
)
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.model import Model
from dwdopen.nwp.request import Downloader

__all__ = ["DWD", "NWP"]

DEFAULT_BASE_URL = "https://opendata.dwd.de"
"""Open Data root.
DWD also runs a test branch at https://opendata.dwd.de/test.
"""


class NWP:
    """Namespace for numerical weather prediction data.
    """

    __slots__ = ("_catalogue", "_downloader")

    def __init__(
        self, catalogue: Catalogue, downloader: Downloader | None = None
    ) -> None:
        self._catalogue = catalogue
        self._downloader = downloader

    def models(self) -> list[str]:
        """Model names currently visible in the catalogue, sorted."""
        return self._catalogue.models()

    def model(self, name: str) -> Model:
        """A handle on one model.
        The name is validated against the catalogue, case-insensitive.
        This is therefore the first call that may send a request.
        """
        available_models = self._catalogue.models()
        canonical = resolve_name(name, available_models)
        if canonical is None:
            raise UnknownModelError(
                unknown_name_message("model", name, available_models)
            )
        return Model(canonical, self._catalogue, self._downloader)

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class DWD:
    """Client for DWD Open Data.

    Constructing a client performs no I/O. The first call that needs
    availability information builds the catalogue and contacts the server.

    Holds a connection pool, so prefer this syntax to make sure the connection
    is closed properly::

        with DWD() as dwd:
            icon_eu = dwd.nwp.model("icon-eu")

    One client per process is the intended usage. Create it once and reuse it.
    Two clients do not share their caches.
    """

    def __init__(
            self,
            *,
            base_url: str = DEFAULT_BASE_URL,
            timeout: float = 30.0,
            max_connections: int = 16,
            catalogue: Catalogue | None = None,
            downloader: Downloader | None = None,
    ) -> None:
        """
        base_url
            Open Data root.
        timeout
            Per-request timeout in seconds.
        max_connections
            Upper bound on concurrent requests. Can be a throughput knob as we
            enumerate and download thousands of files possibly.
        catalogue
            The implementation of the OpenData catalogue.
        downloader
            For fetching the bytes of a resolved request.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_connections = max_connections
        self._catalogue = catalogue
        self._downloader = downloader
        self._http: HttpClient | None = None

    @cached_property
    def nwp(self) -> NWP:
        return NWP(self._ensure_catalogue(), self._ensure_downloader())

    def _ensure_http(self) -> HttpClient:
        """One connection pool, shared by the catalogue and the downloader.

        Built on demand, so a client given an injected catalogue never opens
        one, and close() has something plain to test rather than having to ask
        whether a cached property was ever read.
        """
        if self._http is None:
            self._http = HttpClient(
                self._base_url,
                timeout=self._timeout,
                max_connections=self._max_connections,
            )
        return self._http

    def _ensure_catalogue(self) -> Catalogue:
        if self._catalogue is None:
            self._catalogue = OpenDataCatalogue(
                self._ensure_http(), max_workers=self._max_connections
            )
        return self._catalogue

    def _ensure_downloader(self) -> Downloader:
        if self._downloader is None:
            self._downloader = HttpDownloader(
                self._ensure_http(), max_workers=self._max_connections
            )
        return self._downloader

    def refresh(self) -> None:
        """Drop cached catalogue state so the next call re-reads from the server."""
        if self._catalogue is not None:
            self._catalogue.refresh()

    def close(self) -> None:
        """Release the connection pool."""
        if self._catalogue is not None:
            self._catalogue.close()
        if self._http is not None:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._base_url!r})"
