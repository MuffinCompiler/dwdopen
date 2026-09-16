"""Catalogue built by lazy traversal of the Open Data directory tree.

One implementation of the Catalogue protocol.
TODO add caching
"""

from __future__ import annotations

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import ListingEntry, parse_listing
from dwdopen._fileserver.paths import Segment, build_path
from dwdopen.exceptions import CatalogueUnavailableError
from dwdopen.nwp.run import Run

__all__ = ["OpenDataCatalogue"]


class OpenDataCatalogue:
    """Answers availability questions by listing directories on demand.
    Takes an HttpClient, so the config is in one place and for testing we
    can pass a "fake".
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def models(self) -> list[str]:
        """Model names currently visible, sorted."""
        model_entries = self._subdirectories(key="m")
        model_names = [entry.name for entry in model_entries]
        return sorted(model_names)

    def parameters(self, model: str) -> list[str]:
        """Parameter names visible for the model, sorted.
        """
        parameter_entries = self._subdirectories(("m", model), key="p")
        parameter_names = [entry.name for entry in parameter_entries]
        return sorted(parameter_names)

    def runs(self, model: str, *, probe: str | None = None) -> list[Run]:
        """Runs visible for the model, oldest first.
        ``probe`` names the parameter to look under, because the DWD layout has
        the runs below the parameters, so we need to choose a parameter to check
        for available runs (for that parameter!).

        Note that a run can appear here that is still being published, and not yet
        completed.
        """
        if probe is None:
            raise NotImplementedError(
                "picking a probe parameter automatically is not implemented yet. "
                "pass probe=... explicitly"
            )
        run_entries = self._subdirectories(("m", model), ("p", probe), key="r")
        runs = [Run.coerce(entry.name) for entry in run_entries]
        return sorted(runs)

    def refresh(self) -> None:
        """TODO after caching"""

    def close(self) -> None:
        self._http.close()

    def _subdirectories(
        self, *segments: Segment, key: str | None = None
    ) -> list[ListingEntry]:
        """List one directory and return its subdirectories.
        Every directory addressed this way has children, so an empty result
        means the listing could not be read.
        """
        path = build_path(*segments, key=key)
        # Get the list of entries on that page that are directories.
        entries = []
        for entry in parse_listing(self._http.get_listing(path)):
            if entry.is_dir:
                entries.append(entry)

        if not entries:
            raise CatalogueUnavailableError(
                f"no subdirectories found in {path}. Either the path is wrong or "
                f"the server's listing format changed"
            )
        return entries
