"""Model handle: discovery plus query construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dwdopen.exceptions import NoMatchingRunError, UnknownParameterError
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import (
    LevelSelector, LevelType,
    MemberSelector,
    SelectorValue,
    StepSelector,
)

if TYPE_CHECKING:
    from dwdopen.nwp.query import Query

__all__ = ["Model", "ParameterInfo"]



@dataclass(frozen=True, slots=True, kw_only=True)
class ParameterInfo:
    """Catalogue metadata for one parameter of one model.
    """

    model: str
    name: str

    level_types: tuple[LevelType, ...] = ()
    """Level types this parameter appears under, sorted by code.
    For example, ``(pressure (100), model (150))`` for ``T``.
    Empty when the parameter has exactly one level.
    Note that this says nothgin about the GRIB level type.
    """

    qualifiers: tuple[str, ...] = ()
    """Extra path-segment keys observed for this parameter beyond the standard
    ones, e.g. ``("wvl1",)`` for ICON-ART's ``SAT_BSC_DUST``.
    """

    def is_multi_level(self) -> bool:
        return bool(self.level_types)


class Model:
    """A handle on one NWP model.

    Obtain one from ``DWD().nwp.model(name)``, which validates the name against
    the catalogue first.
    It stores a name and a catalogue reference and owns nothing.
    """

    __slots__ = ("_catalogue", "_name")

    def __init__(self, name: str, catalogue: Catalogue) -> None:
        self._name = name
        self._catalogue = catalogue

    @property
    def name(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._name!r})"

    # --- discovery --------------------------------------------------------

    def parameters(self) -> list[str]:
        """Parameter names available for this model, sorted.
        Obtained straight from the catalogue.
        """
        return self._catalogue.parameters(self._name)

    def parameter(self, name: str) -> ParameterInfo:
        """Catalogue metadata for one parameter of this model.
        ``name`` is validated against the catalogue.

        TODO: how much metadata to populate. level_types and qualifiers are cheap
            to add, steps and members might need lots of httpx requests.
        Raises:
            UnknownParameterError: if ``name`` is not available for this model.
        """
        available = self._catalogue.parameters(self._name)
        if name not in available:
            raise UnknownParameterError("unknown param")
        raise NotImplementedError("Implement pInfo population")

    def runs(self, *, probe: str | None = None) -> list[Run]:
        """Runs currently visible, oldest first.
        The server lists runs per parameter, not per model, so we need a probe parameter.
        A run can appear here while it is still being published!
        Use ``Query.latest_run`` when you need a run that actually satisfies a
        selection (e.g., fully available).
        """
        return self._catalogue.runs(self._name, probe=probe)

    def latest_run(self, *, probe: str | None = None) -> Run:
        """Newest run visible for this model.
        See runs() doc, this has no completeness check. That is ``Query.latest_run``.

        Raises:
            NoMatchingRunError: if the catalogue shows no runs at all.
        """
        runs = self.runs(probe=probe)
        if not runs:
            raise NoMatchingRunError(
                f"no runs found for model {self._name!r}"
                + (f" using probe parameter {probe!r}" if probe else "")
            )
        return runs[-1] # most recent


    def select(
        self,
        *,
        parameters: str | Sequence[str],
        run: RunLike | None = None,
        steps: StepSelector | None = None,
        level_type: str | int | None = None,
        levels: LevelSelector | None = None,
        members: MemberSelector | None = None,
        **selectors: SelectorValue,
    ) -> Query:
        """Builds the query on what to receive.
        The query is purely a description. Availability is only checked by
        ``resolve()`` or ``latest_run()``. Thus, the query be
        constructed once and resolved against different runs.

        Args:
            parameters: exact catalogue names, one or many.
            steps: forecast steps as durations. A scalar means exactly that step.
                Use ``Every(...)`` and ``Between(...)`` for ranges.
            level_type: a name alias (``"model"``, ``"pressure"``,
                ``"soil"``) or the raw numeric GRIB ``typeOfFirstFixedSurface``
                code. May be omitted when the parameter is unambiguous.
                Raises ``AmbiguousSelectionError`` if omitted but ambiguous.
            levels: user-facing units. Pressure is given in hPa.
            members: ensemble members as plain integers.
            **selectors: for product-specific dimensions. Can contain additional
                parameters, for example, ICON-ART has data for different wavelengths.

        Returns:
            A ``Query``; combine several with ``|``.
        """
        raise NotImplementedError