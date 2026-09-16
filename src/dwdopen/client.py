"""Entry point: the client and the NWP namespace."""

from __future__ import annotations

from functools import cached_property
from types import TracebackType
from typing import Self

from dwdopen.exceptions import UnknownModelError, unknown_name_message
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.model import Model

__all__ = ["DWD", "NWP"]

DEFAULT_BASE_URL = "https://opendata.dwd.de"
"""Production Open Data root.

DWD also runs a test branch at https://opendata.dwd.de/test, which currently
carries the test data for the 6 October 2026 ICON-EU grid change.
"""


class NWP:
    """Namespace for numerical weather prediction data.

    A namespace so other DWD domains (observations, radar, ...) can be added
    later without crowding DWD itself.
    """

    __slots__ = ("_catalogue",)

    def __init__(self, catalogue: Catalogue) -> None:
        self._catalogue = catalogue

    def models(self) -> list[str]:
        """Model names currently visible in the catalogue, sorted."""
        return self._catalogue.models()

    def model(self, name: str) -> Model:
        """A handle on one model.

        The name is validated against the catalogue, so a typo fails here
        rather than inside a later query. Model names use hyphens while
        parameter names use underscores.

        This is therefore the first call that may touch the network. The model
        listing is cached, so further calls are free (or until cache has been invalidated).
        """
        available = self._catalogue.models()
        if name not in available:
            raise UnknownModelError(unknown_name_message("model", name, available))
        return Model(name, self._catalogue)

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
    ) -> None:
        """
        base_url
            Open Data root. Point at .../test to read the test branch.
        timeout
            Per-request timeout in seconds.
        max_connections
            Upper bound on concurrent requests. Can be a throughput knob as we
            enumerate and download thousands of files possibly.
        catalogue
            Inject an alternative implementation, such as a fake in tests or a
            different index strategy. When None the Open Data traversal
            catalogue is built lazily on first use.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_connections = max_connections
        self._catalogue = catalogue

    @cached_property
    def nwp(self) -> NWP:
        return NWP(self._ensure_catalogue())

    def _ensure_catalogue(self) -> Catalogue:
        if self._catalogue is None:
            raise NotImplementedError(
                "the Open Data traversal catalogue is not implemented yet; "
                "pass catalogue=... explicitly"
            )
        return self._catalogue

    def refresh(self) -> None:
        """Drop cached catalogue state so the next call re-reads from the server."""
        if self._catalogue is not None:
            self._catalogue.refresh()

    def close(self) -> None:
        """Release the connection pool."""
        if self._catalogue is not None:
            self._catalogue.close()

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
