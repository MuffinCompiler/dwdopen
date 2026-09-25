"""The seam between the semantic layer and whatever provides availability."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

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

    def runs(
        self,
        model: str,
        *,
        probe: str | None = None,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
    ) -> list[Run]:
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

    def level_types(self, model: str, parameter: str) -> list[LevelType]:
        """Vertical coordinate types this parameter is published on, sorted.

        Empty for a 2-D field, which DWD writes with no lvt1 segment at all.
        Several entries mean the name alone is ambiguous, for example T exists on both
        pressure (100) and model levels (150).
        """
        ...

    def levels(
        self, model: str, parameter: str, level_type: LevelType
    ) -> list[Decimal]:
        """Level values available for one parameter on one level type, sorted.

        In the unit DWD writes, so Pa for pressure and metres for soil.
        Decimal because soil levels are fractions of a metre.
        """
        ...

    def assets(
        self,
        model: str,
        parameter: str,
        run: Run,
        *,
        level_type: LevelType | None = None,
        levels: Sequence[Decimal] | None = None,
        members: Sequence[int] | None = None,
    ) -> list[Asset]:
        """Every asset of one parameter in one run.
        ``levels`` selects which levels to fetch, in server units, and is None
        for a 2-D field.
        ``members`` selects ensemble members and is None for a deterministic
        model.

        Raises RunExpiredError if the run is no longer on the server.
        """
        ...

    def members(
        self,
        model: str,
        parameter: str,
        run: Run,
        *,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
    ) -> list[int]:
        """Ensemble members available for one parameter in one run, sorted.
        Empty for a deterministic model, which has no e/ segment at all. A 3-D
        field needs the level, because the run sits below lvt1/lv1.
        """
        ...

    def refresh(self) -> None:
        """Drop cached state so the next call re-builds the catalogue from the server."""
        ...

    def close(self) -> None:
        """Release any transport resources."""
        ...
