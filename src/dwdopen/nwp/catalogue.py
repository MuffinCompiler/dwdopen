from __future__ import annotations

from typing import Protocol, runtime_checkable

from dwdopen.nwp.run import Run

__all__ = ["Catalogue"]


@runtime_checkable
class Catalogue(Protocol):
    """Read-only view of what DWD Open Data currently offers.

    Several implementations can satisfy it: lazy HTTP directory traversal (the
    only one built for now), a bulk index built from the ``content.log.bz2``
    file, and some fake protocol for tests.
    """

    def models(self) -> list[str]:
        """Model names currently visible, sorted."""
        ...

    def parameters(self, model: str) -> list[str]:
        """Parameter names visible for ``model``, sorted.

        Raises:
            UnknownModelError: if ``model`` is not in the catalogue.
        """
        ...

    def runs(self, model: str, *, probe: str | None = None) -> list[Run]:
        """Runs visible for ``model``, oldest first.
        ``probe`` names the parameter used to probe for available runs. Required
        as the DWD data API layout puts ``/r/<run>/`` below the parameter.
        When ``probe`` is ``None`` the implementation picks a cheap single-level
        parameter from the catalogue.
        The result is therefore only a guess of the runs of this model, and
        a run may appear here while it is still being published but not fully
        available yet.

        Raises:
            UnknownModelError: if ``model`` is not in the catalogue.
            UnknownParameterError: if ``probe`` is given but not available.
        """
        ...

    def refresh(self) -> None:
        """Drop cached state so the next call rebuilds this catalogue."""
        ...

    def close(self) -> None:
        """Release any resources."""
        ...
