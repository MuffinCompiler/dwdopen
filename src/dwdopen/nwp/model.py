"""Model handle: discovery plus query construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from dwdopen.exceptions import (
    AmbiguousSelectionError,
    InvalidSelectorError,
    NoMatchingRunError,
    UnknownParameterError,
    resolve_name,
    unknown_name_message,
)
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.durations import check_step_selector
from dwdopen.nwp.query import Query
from dwdopen.nwp.request import Downloader
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import (
    LevelSelector,
    LevelType,
    LevelTypeLike,
    MemberSelector,
    SelectorValue,
    StepSelector,
)

__all__ = ["Model", "ParameterInfo"]


@dataclass(frozen=True)
class ParameterInfo:
    """Catalogue metadata for one parameter of one model."""

    model: str
    name: str

    level_types: tuple[LevelType, ...] = ()
    """Level types this parameter appears under in the path, sorted by code.

    For example (pressure (100), model (150)) for T. Empty when DWD omits
    lvt1/lv1, which it does whenever a parameter has a single level.
    """

    qualifiers: tuple[str, ...] = ()
    """Extra path-segment keys seen for this parameter, e.g. ("wvl1",) for
    ICON-ART's SAT_BSC_DUST. DWD documents none of these, so they are
    discovered and kept."""

    def is_multi_level(self) -> bool:
        return bool(self.level_types)


class Model:
    """A handle on one NWP model.

    Obtain one from DWD().nwp.model(name), which validates the name against the
    catalogue first; this constructor trusts its input.
    """

    __slots__ = ("_catalogue", "_downloader", "_name")

    def __init__(
        self,
        name: str,
        catalogue: Catalogue,
        downloader: Downloader | None = None,
    ) -> None:
        self._name = name
        self._catalogue = catalogue
        self._downloader = downloader

    @property
    def name(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._name!r})"

    def parameters(self) -> list[str]:
        """Parameter names available for this model, sorted.
        """
        return self._catalogue.parameters(self._name)

    def parameter(self, name: str) -> ParameterInfo:
        """Catalogue metadata for one parameter of this model.

        The name is validated, symmetrically with NWP.model.
        Available steps and members are NOT part of this object, as we treat
        them as not being part of a parameter. This comes from the DWD structure:
        In the path, steps and members are located BELOW the run. As the
        "static" parameter here is not checking available runs, the steps and
        members might have no definite answer.
        """
        name = self._resolve_parameter(name)
        return ParameterInfo(
            model=self._name,
            name=name,
            level_types=tuple(self._catalogue.level_types(self._name, name)),
        )

    def _resolve_parameter(self, name: str) -> str:
        """The catalogue's own spelling of a parameter name.
        The legacy layout wrote t_2m, where v1 writes now T_2M and DWD's
        manual uses both. Basically returns the canonical name.
        """
        available = self._catalogue.parameters(self._name)
        canonical = resolve_name(name, available)
        if canonical is None:
            raise UnknownParameterError(
                unknown_name_message(
                    "parameter", name, available, context=f"model {self._name!r}"
                )
            )
        return canonical

    def levels(self, parameter: str, level_type: LevelTypeLike) -> list[Decimal]:
        """Level values this parameter is published on, in DWD's own unit.
        So Pa for pressure and metres for soil.
        """
        return self._catalogue.levels(
            self._name, self._resolve_parameter(parameter), LevelType.coerce(level_type)
        )

    def runs(self, *, parameter: str | None = None) -> list[Run]:
        """Runs currently visible, oldest first.

        Approximate by construction: DWD exposes runs per parameter, not per
        model, so this reflects whichever parameter is named. A run can appear here
        while it is still being published. Retention is short too: ICON-EU
        keeps 8 runs (~24 h), ICON-D2-RUC 32.
        Use Query.latest_run when you need a run that actually satisfies a
        specific selection.
        TODO should this be in the interface -> needs levels etc?
        """
        return self._catalogue.runs(self._name, parameter=parameter)

    def latest_run(self, *, parameter: str | None = None) -> Run:
        """Newest run visible for this model. Same issues as runs().
        It has no completeness check and no settle guard. That is Query.latest_run.
        """
        runs = self.runs(parameter=parameter)
        if not runs:
            message = f"no runs visible for model {self._name!r}"
            if parameter:
                message += f" via parameter {parameter!r}"
            raise NoMatchingRunError(message)
        return runs[-1]

    def select(
        self,
        *,
        parameters: str | Sequence[str],
        steps: StepSelector | None = None,
        level_type: LevelTypeLike | None = None,
        levels: LevelSelector | None = None,
        members: MemberSelector | None = None,
        **selectors: SelectorValue,
    ) -> Query:
        """Describe what to retrieve.
        Parameter names are validated, so this does read the p/ listing.
        What it does not do is look at availability of runs or steps: that is
        resolve(), which is why one query can be resolved against several runs.

        ``level_type`` takes a GRIB code (100), an alias ("pressure") or a
        LevelType. It may be left out while the selection is unambiguous, i.e.
        while every named parameter is only available on one, and all on the same
        level type.
        ``levels`` is in the readable unit: hPa for pressure, the bare index for
        model levels, metres for soil.
        """
        unsupported = dict(selectors)
        given = sorted(name for name, value in unsupported.items() if value is not None)
        if given:
            raise NotImplementedError(
                f"{', '.join(given)}: not supported yet. ICON-ART wavelengths TODO"
            )

        # Validate steps before accessing the network.
        check_step_selector(steps)

        names = (parameters,) if isinstance(parameters, str) else tuple(parameters)
        if not names:
            raise InvalidSelectorError("select() needs at least one parameter")

        names = tuple(self._resolve_parameter(name) for name in names)

        chosen_type = self._resolve_level_type(names, level_type, levels)
        return Query(
            self._catalogue,
            self._name,
            parameters=names,
            steps=steps,
            level_type=chosen_type,
            levels=levels,
            members=members,
            downloader=self._downloader,
        )

    def _resolve_level_type(
        self,
        parameters: tuple[str, ...],
        level_type: LevelTypeLike | None,
        levels: LevelSelector | None,
    ) -> LevelType | None:
        """Work out which vertical coordinate the selection means.
        Naming it explicitly always takes precedence. Leaving it out is allowed only if
        the level type is unambiguous. Every selected parameter must be available
        on the same level type, or on none at all.
        """
        if level_type is not None:
            return LevelType.coerce(level_type)

        per_parameter = {
            name: self._catalogue.level_types(self._name, name) for name in parameters
        }
        candidates = {lt for types in per_parameter.values() for lt in types}

        if not candidates:
            if levels is not None:
                flat = ", ".join(sorted(per_parameter))
                raise InvalidSelectorError(
                    f"levels were given but {flat} in {self._name!r} "
                    f"{'is' if len(per_parameter) == 1 else 'are'} published on "
                    f"a single level only, with no lvt1/lv1 in the path"
                )
            return None

        if len(candidates) > 1:
            ordered = sorted(candidates, key=lambda c: c.code)
            listed = ", ".join(str(lt) for lt in ordered)
            spread = "; ".join(
                f"{name}: {', '.join(str(lt) for lt in types) or 'none'}"
                for name, types in sorted(per_parameter.items())
            )
            raise AmbiguousSelectionError(
                f"level type is ambiguous for this selection ({spread}). "
                f"Pass level_type= to choose one of: {listed}"
            )

        return candidates.pop()
