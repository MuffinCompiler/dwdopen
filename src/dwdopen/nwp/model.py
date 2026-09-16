"""Model handle: discovery plus query construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dwdopen.exceptions import (
    NoMatchingRunError,
    UnknownParameterError,
    unknown_name_message,
)
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import (
    LevelSelector,
    LevelType,
    MemberSelector,
    SelectorValue,
    StepSelector,
)

if TYPE_CHECKING:
    from dwdopen.nwp.query import Query

__all__ = ["Model", "ParameterInfo"]


@dataclass(frozen=True)
class ParameterInfo:
    """Catalogue metadata for one parameter of one model."""

    model: str
    name: str

    level_types: tuple[LevelType, ...] = ()
    """Level types this parameter appears under in the path, sorted by code.

    For example (pressure (100), model (150)) for T. Empty when DWD omits
    lvt1/lv1, which it does whenever a parameter has a single level. That says
    nothing about the GRIB level type: DEPTH_LK is documented as 1/162 and
    ASOB_T as 8, yet neither of them appears in a path.
    """

    qualifiers: tuple[str, ...] = ()
    """Extra path-segment keys seen for this parameter, e.g. ("wvl1",) for
    ICON-ART's SAT_BSC_DUST. DWD documents none of these, so they are
    discovered, never assumed."""

    def is_multi_level(self) -> bool:
        return bool(self.level_types)


class Model:
    """A handle on one NWP model.

    Obtain one from DWD().nwp.model(name), which validates the name against the
    catalogue first; this constructor trusts its input. Cheap to hold: it
    stores a name and a catalogue reference and owns nothing.

    No __eq__ is defined, so comparison is by identity. Two handles for the
    same model from two different clients read different catalogues and are
    deliberately not "equal". Compare .name if that is what you mean.
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

        Straight from the catalogue, never a hard-coded inventory, so a
        parameter DWD adds (DEN and SMI appeared in September 2026) shows up
        without a dwdopen release.
        """
        return self._catalogue.parameters(self._name)

    def parameter(self, name: str) -> ParameterInfo:
        """Catalogue metadata for one parameter of this model.

        The name is validated, symmetrically with NWP.model. That costs the
        .../p/ listing, the same one parameters() reads, so it is free once
        either has been called.
        Populating level_types and qualifiers costs two more listings:
        .../p/<NAME>/ shows which segment keys follow (lvt1, plus qualifier
        keys such as wvl1), and .../p/<NAME>/lvt1/ shows the level types.

        Available steps and members are NOT part of this object, as we treat
        them as not being part of a parameter. This mirrors the DWD structure:
        In the path, steps and members are located BELOW the run. As the
        "static" parameter here is not checking available runs, the steps and
        members might have no definite answer.
        """
        available = self._catalogue.parameters(self._name)
        if name not in available:
            raise UnknownParameterError(
                unknown_name_message(
                    "parameter", name, available, context=f"model {self._name!r}"
                )
            )
        raise NotImplementedError("ParameterInfo population is not implemented yet")

    def runs(self, *, probe: str | None = None) -> list[Run]:
        """Runs currently visible, oldest first.

        Approximate by construction: DWD exposes runs per parameter, not per
        model, so this reflects one probe parameter. A run can appear here
        while it is still being published. Retention is short too: ICON-EU
        keeps 8 runs (~24 h), ICON-D2-RUC 32.
        Use Query.latest_run when you need a run that actually satisfies a
        specific selection.
        """
        return self._catalogue.runs(self._name, probe=probe)

    def latest_run(self, *, probe: str | None = None) -> Run:
        """Newest run visible for this model. Same issues as runs().
        It has no completeness check and no settle guard. That is Query.latest_run.
        """
        runs = self.runs(probe=probe)
        if not runs:
            message = f"no runs visible for model {self._name!r}"
            if probe:
                message += f" via probe parameter {probe!r}"
            raise NoMatchingRunError(message)
        return runs[-1]

    # --- query construction -----------------------------------------------

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
        """Describe what to retrieve. Does not contact the server.

        Building a query is pure description; availability is only checked by
        resolve() or latest_run(). Thus, we can resolve one query
        against different runs.

        parameters
            Exact catalogue names, one or many.
        steps
            Durations, never integer hours. A scalar means exactly that step,
            Every(...) a cadence, Between(...) whatever exists in a range.
        level_type
            An alias ("model", "pressure", "soil") or the raw numeric GRIB
            typeOfFirstFixedSurface code (150, 100, 106). May be omitted when
            the parameter is unambiguous, as HHL only ever occurs at 150. A
            parameter on several types (T is on 100 and 150) raises
            AmbiguousSelectionError rather than guessing.
        levels
            User-facing units, not path units: pressure in hPa, converted to
            the Pa values in the path.
        members
            Plain integers; the zero-padded path form is never constructed.
        **selectors
            Escape hatch for product-specific dimensions. Keys are DWD
            path-segment keys (wvl1=1064) with a small alias table on top
            (wavelength=1064).
        """
        raise NotImplementedError
