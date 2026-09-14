"""Entry point: the client and the NWP namespace."""

from __future__ import annotations

from functools import cached_property
from types import TracebackType
from typing import Self

from dwdopen.exceptions import UnknownModelError, unknown_name_message
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.model import Model

# Exposed imports
__all__ = ["DWD", "NWP"]

DEFAULT_BASE_URL = "https://opendata.dwd.de"


class NWP:
    """Namespace for Numerical weather prediction (NWP) data.
    Allows to add other sources (e.g., observations) later in
    separate submodules.
    """

    __slots__ = ("_catalogue",)

    def __init__(self, catalogue: Catalogue) -> None:
        self._catalogue = catalogue

    def models(self) -> list[str]:
        """Model names currently visible in the catalogue."""
        return self._catalogue.models()

    def model(self, name: str) -> Model:
        """A handle on one model.
        ``name`` is validated against the catalogue.
        Note that model names use hyphens while parameter names use underscores.

        Raises:
            UnknownModelError: if ``name`` is not in the catalogue.
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

    Holds a connection pool, so use this class preferably as::

        with DWD() as dwd:
            icon_eu = dwd.nwp.model("icon-eu")

    One client per process is the intended usage, clients do not share their caches.
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
        Args:
            base_url: Open Data root.
            timeout: per-request timeout in seconds.
            max_connections: upper bound on concurrent requests.
            catalogue: the catalogue to use, can inject a "fake" catalogue
                here for testing. When ``None`` the Open Data
                traversal catalogue is built lazily on first use.
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
            # TODO init catalogue
            raise NotImplementedError("NYI")
        return self._catalogue

    def refresh(self) -> None:
        """Drop cached catalogue state so the next call rebuilds it."""
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