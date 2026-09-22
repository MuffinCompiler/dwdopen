"""The seam between the semantic layer and whatever provides availability."""

from __future__ import annotations

from typing import Protocol

from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run

__all__ = ["Catalogue"]


class Catalogue(Protocol):
    """Read-only view of what DWD Open Data currently offers.

    This is the interface that keeps URL and path knowledge out of the other
    layer: nothing above it may know how availability is obtained.
    Several implementations can implement this knowledge.
    A lazy HTTP traversal is implemented in _fileserver/traversal.py.
    Later on, a bulk index could be built from the content,log.bz2. Or "fake"
    implementations can be used for testing,
    """

    def models(self) -> list[str]:
        """Model names currently visible, sorted."""
        ...

    def parameters(self, model: str) -> list[str]:
        """Parameter names visible for the model, sorted.

        Raises UnknownModelError if the model is not in the catalogue.
        """
        ...

    def runs(self, model: str, *, probe: str | None = None) -> list[Run]:
        """Runs visible for the model, oldest first.

        ``probe`` names the parameter used to answer this. It exists because
        the v1 layout puts /r/<run>/ below the parameter, and below lvt1/lv1
        for 3-D fields. There is therefore no run listing at model level. When
        probe is None the implementation picks a cheap single-level parameter.
        Thus, a run can appear here while it is still being published!

        Raises UnknownModelError, or UnknownParameterError if probe is given
        but not available.
        """
        ...

    def assets(self, model: str, parameter: str, run: Run) -> list[Asset]:
        """Every asset of one parameter in one run.

        Raises RunExpiredError if the run is no longer on the server.
        """
        ...

    def refresh(self) -> None:
        """Drop cached state so the next call re-builds the catalogue from the server."""
        ...

    def close(self) -> None:
        """Release any transport resources."""
        ...
