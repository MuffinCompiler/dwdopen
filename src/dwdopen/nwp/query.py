"""A semantic query describes a selection to fetch."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from dwdopen.exceptions import (
    IncompleteRunError,
    InvalidSelectorError,
    NoMatchingRunError,
    RunExpiredError,
)
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.durations import format_duration, parse_duration
from dwdopen.nwp.request import (
    Asset,
    CombineMode,
    Downloader,
    DownloadResult,
    MissingStep,
    ResolvedRequest,
)
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import (
    Between,
    Every,
    LevelScalar,
    LevelSelector,
    LevelType,
    MemberSelector,
    StepScalar,
    StepSelector,
    WavelengthSelector,
)

logger = logging.getLogger("dwdopen")

__all__ = ["Query"]

Require = Literal["complete", "partial"]

DEFAULT_SETTLE = timedelta(seconds=90)
"""Some settle time that needs to pass until a run is deemed valid.
This rejects requested runs which just arrived on the server a few
seconds ago, as we can't be sure that the file has been finished
written, and that is already present on all the DWD Open Data servers
we might contact.
DWD's own content.log tool waits 60 s.
"""


class Query:
    """A description of what to retrieve. It is deliberately not tied to a run.

    A query says "what" to retrieve; resolve() and download() say "which" run.
    Keeping the two apart is what lets one query be resolved against several runs,
    and helps us to be able to combine queries.
    Use Model.select() to construct a query.
    """

    def __init__(
        self,
        catalogue: Catalogue,
        model: str,
        *,
        parameters: tuple[str, ...],
        steps: StepSelector | None = None,
        level_type: LevelType | None = None,
        levels: LevelSelector | None = None,
        members: MemberSelector | None = None,
        wavelengths: WavelengthSelector | None = None,
        downloader: Downloader | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._model = model
        self._parameters = parameters
        self._steps = steps
        self._level_type = level_type
        self._levels = levels
        self._members = members
        self._wavelengths = wavelengths
        self._downloader = downloader

    def __repr__(self) -> str:
        vertical = "" if self._level_type is None else f", levels={self._level_type}"
        return (
            f"{type(self).__name__}(model={self._model!r}, "
            f"parameters={list(self._parameters)}{vertical})"
        )

    def latest_run(
        self,
        *,
        require: Require = "complete",
        settle: timedelta = DEFAULT_SETTLE,
    ) -> Run:
        """Newest run that actually satisfies this query.
        Tries the available runs from newest to oldest, and returns the newest
        that has all the files requested in the query available. The data on the
        server must be "settled". Thus, a run still being published is skipped, so
        this is not the same as Model.latest_run.
        Uses the cached snapshot and calls the internal implementation.
        """
        with self._catalogue.snapshot():
            return self._newest_run(require, settle)

    def _newest_run(self, require: Require, settle: timedelta) -> Run:
        """The newest run satisfying the query, inside a caller's snapshot.
        """
        first = self._parameters[0]
        probe_wavelength = self._wanted_wavelengths(first)[0]
        probe_levels = self._wanted_levels(first, probe_wavelength)
        candidates = self._catalogue.runs(
            self._model,
            parameter=first,
            level_type=self._level_type,
            level=probe_levels[0] if probe_levels else None,
            wavelength=probe_wavelength,
        )
        now = datetime.now(UTC)

        for run in reversed(candidates):
            try:
                request = self.resolve(run=run, require=require)
            except (IncompleteRunError, RunExpiredError):
                # A run can be listed for the parameter we probed with and
                # still be absent for another, because parameters are not
                # published at the same moment.
                continue
            if _still_publishing(request, now, settle):
                continue
            return request.run

        raise NoMatchingRunError(
            f"no run of {self._model!r} satisfies this query "
            f"({len(candidates)} candidates were checked)"
        )

    def resolve(
        self,
        run: RunLike | None = None,
        *,
        require: Require = "complete",
    ) -> ResolvedRequest:
        """Freeze the query against one run.

        Omitting ``run`` resolves against the newest run that satisfies the
        query, given by latest_run().
        When require="complete" is set, a step missing on any requested level
        or member raises IncompleteRunError. With "partial" it is reported in
        the missing field instead.
        Named steps (Every, a list) are expected exactly. For "all" and
        Between(), we have to make a guess as the server does not list what steps
        are expected in a full forecast. Thus, we check whether a step is only
        available on SOME levels or members. Raise IncompleteRunError when that
        is the case.
        Uses the cached snapshot and calls the helper method.
        """
        with self._catalogue.snapshot():
            return self._against(run, require)

    def _against(self, run: RunLike | None, require: Require) -> ResolvedRequest:
        if run is None:
            resolved_run = self.latest_run(require=require)
        else:
            resolved_run = Run.coerce(run)

        assets: list[Asset] = []
        missing: list[MissingStep] = []
        # To test the query availability against the given run, we must
        # check many levels and members each parameter (and wavelength) has
        # and compare them against the wanted parameters from the user query.
        sizes: dict[tuple[str, int | None], tuple[int, int]] = {}
        # Get the assets for every parameter. A parameter with wavelengths
        # (ICON-ART only) is an extra "key dimension" (keyed by param and
        # wavelength), all others have the single "wavelength" None.
        # TODO: may be worth to parallelize
        for parameter in self._parameters:
            for wavelength in self._wanted_wavelengths(parameter):
                levels = self._wanted_levels(parameter, wavelength)
                members = self._wanted_members(parameter, resolved_run, wavelength)
                # Get all available assets for the provided information.
                available = self._catalogue.assets(
                    self._model,
                    parameter,
                    resolved_run,
                    level_type=self._level_type,
                    levels=levels,
                    members=members,
                    wavelength=wavelength,
                )
                # Get the subset of assets for the user's chosen steps.
                chosen = _select_steps(available, self._steps)
                assets.extend(chosen)
                # Every requested level and member MUST have every expected
                # step. Track missing assets for that invariant.
                missing.extend(
                    _find_missing(
                        parameter,
                        chosen,
                        _named_steps(self._steps),
                        levels,
                        members,
                        wavelength,
                    )
                )
                sizes[(parameter, wavelength)] = (
                    len(levels or [None]),
                    len(members or [None]),
                )

        if missing:
            detail = _describe_missing(resolved_run, missing, sizes)
            if require == "complete":
                raise IncompleteRunError(detail)
            # Warn the user in "partial" mode what is missing from the request.
            logger.warning("%s. Continuing, require=\"partial\"", detail)

        return ResolvedRequest(
            run=resolved_run,
            assets=tuple(sorted(assets, key=Asset.sort_key)),
            resolved_at=datetime.now(UTC),
            missing=tuple(missing),
            downloader=self._downloader,
        )

    def _wanted_wavelengths(self, parameter: str) -> list[int | None]:
        """Which wavelengths to fetch for one parameter. [None] for a parameter
        without wavelengths, which is all but a few ICON-ART ones.
        """
        available = self._catalogue.wavelengths(self._model, parameter)
        wanted: list[int | None] = []
        if not available:
            wanted.append(None)
        else:
            wanted.extend(
                _select_wavelengths(available, self._wavelengths, parameter)
            )
        return wanted

    def _wanted_levels(
        self, parameter: str, wavelength: int | None = None
    ) -> list[Decimal] | None:
        """Which levels to fetch for one parameter, in server units.
        Fetches all available levels, and then selects the ones according to
        the self._levels range set by the user.
        """
        if self._level_type is None:
            return None
        available = self._catalogue.levels(
            self._model, parameter, self._level_type, wavelength=wavelength
        )
        # Return the subset of available levels that match the levels asked by the user.
        return _select_levels(available, self._levels, self._level_type)

    def _wanted_members(
        self, parameter: str, run: Run, wavelength: int | None = None
    ) -> list[int] | None:
        """Which ensemble members to fetch, None for a deterministic model.
        Needs the run, because members are below it.
        """
        # TODO: may be worth to parallelize
        # Any level will do: every level of a parameter shares its members.
        levels = self._wanted_levels(parameter, wavelength)
        available = self._catalogue.members(
            self._model,
            parameter,
            run,
            level_type=self._level_type,
            level=levels[0] if levels else None,
            wavelength=wavelength,
        )
        if not available:
            return None
        # The subset of available members that the user asked for.
        return _select_members(available, self._members)

    def download(
        self,
        destination: str | os.PathLike[str],
        *,
        run: RunLike | None = None,
        require: Require = "complete",
        combine: CombineMode = "all",
        temp_dir: str | os.PathLike[str] | None = None,
    ) -> DownloadResult:
        """Resolve against a run and fetch the result in one step.
        Convenience only. resolve() first when the download is worth inspecting
        before thousands of files start being downloaded.
        """
        return self.resolve(run=run, require=require).download(
            destination, combine=combine, temp_dir=temp_dir
        )


def _select_members(
    available: Sequence[int], selector: MemberSelector | None
) -> list[int]:
    """Pick the ensemble members a selector asks for.
    Members are plain integers with no unit to convert.
    """
    if selector is None or selector == "all":
        return list(available)

    offered = set(available)

    if isinstance(selector, Between):
        low = selector.start
        high = selector.stop
        return [
            member
            for member in available
            if (low is None or member >= low) and (high is None or member <= high)
        ]

    if isinstance(selector, Every):
        wanted = list(range(selector.start, selector.stop + 1, selector.every))
    elif isinstance(selector, int):
        wanted = [selector]
    else:
        wanted = list(selector)

    unknown = [member for member in wanted if member not in offered]
    if unknown:
        raise InvalidSelectorError(
            f"no ensemble member {', '.join(str(m) for m in unknown)}. "
            f"This model has members {min(available)}..{max(available)}"
        )
    return wanted


def _select_wavelengths(
    available: Sequence[int], selector: WavelengthSelector | None, parameter: str
) -> list[int]:
    """Pick the wavelengths a selector asks for. Leaving it out means all."""
    if selector is None or selector == "all":
        return list(available)
    if isinstance(selector, int):
        wanted = [selector]
    else:
        wanted = list(selector)

    unknown = [value for value in wanted if value not in available]
    if unknown:
        raise InvalidSelectorError(
            f"{parameter} has no wavelength "
            f"{', '.join(str(value) for value in unknown)} nm. Available: "
            f"{', '.join(str(value) for value in available)} nm"
        )
    return wanted


def _select_levels(
    available: Sequence[Decimal], selector: LevelSelector | None, kind: LevelType
) -> list[Decimal]:
    """Pick the levels a selector asks for, in the unit DWD writes.

    ``available`` comes from the catalogue and is already in server units, so
    every user-facing value is converted before it is compared.
    """
    if selector is None or selector == "all":
        return list(available)

    offered = set(available)

    if isinstance(selector, Between):
        low = None if selector.start is None else kind.to_server(selector.start)
        high = None if selector.stop is None else kind.to_server(selector.stop)
        return [
            value
            for value in available
            if (low is None or value >= low) and (high is None or value <= high)
        ]

    if isinstance(selector, Every):
        wanted = _expand_every_level(selector, kind)
    elif isinstance(selector, (int, float, Decimal)):
        wanted = [kind.to_server(selector)]
    else:
        wanted = [kind.to_server(item) for item in selector]

    unknown = [value for value in wanted if value not in offered]
    if unknown:
        raise InvalidSelectorError(
            f"{kind} has no level "
            f"{', '.join(str(kind.to_user(v)) for v in unknown)}"
            + (f" ({kind.user_unit})" if kind.user_unit else "")
            + ". Available: "
            + ", ".join(str(kind.to_user(v)) for v in sorted(available))
        )
    return wanted


def _expand_every_level(
    selector: Every[LevelScalar], kind: LevelType
) -> list[Decimal]:
    """Expand an Every selector into the level values it names.

    Every(1, 10, 1) over model levels means 1, 2, ..., 10, both ends included.
    """
    start = kind.to_server(selector.start)
    stop = kind.to_server(selector.stop)
    step = kind.to_server(selector.every)
    if step <= 0:
        raise InvalidSelectorError(
            f"the step between levels must be positive, got {step}"
        )
    values = []
    current = start
    while current <= stop:
        values.append(current)
        current += step
    return values


def _still_publishing(
    request: ResolvedRequest, now: datetime, settle: timedelta
) -> bool:
    """True while the run's newest file is younger than the settle window."""
    times = [asset.modified for asset in request.assets if asset.modified is not None]
    if not times:
        return False
    return now - max(times) < settle


def _select_steps(
    available: Sequence[Asset], selector: StepSelector | None
) -> list[Asset]:
    """Pick the assets a step selector asks for. Whether something is missing
    is checked separately, in _find_missing().
    """
    if selector is None or selector == "all":
        return list(available)

    # Between: Check every assets time and put ones in chosen that are in the interval.
    if isinstance(selector, Between):
        start = None if selector.start is None else parse_duration(selector.start)
        stop = None if selector.stop is None else parse_duration(selector.stop)
        return [
            asset
            for asset in available
            if (start is None or asset.step >= start)
            and (stop is None or asset.step <= stop)
        ]

    # Every() or specific time deltas: keep the assets on the wanted steps.
    wanted = _named_steps(selector)
    assert wanted is not None
    return [asset for asset in available if asset.step in wanted]


def _named_steps(selector: StepSelector | None) -> list[timedelta] | None:
    """The steps a selector names explicitly. None for "all" and Between(),
    which ask for whatever exists.
    """
    if selector is None or selector == "all" or isinstance(selector, Between):
        return None
    if isinstance(selector, Every):
        return _expand_every_step(selector)
    if isinstance(selector, (str, timedelta)):
        return [parse_duration(selector)]
    return [parse_duration(item) for item in selector]


def _find_missing(
    parameter: str,
    chosen: Sequence[Asset],
    named_steps: list[timedelta] | None,
    levels: Sequence[Decimal] | None,
    members: Sequence[int] | None,
    wavelength: int | None = None,
) -> list[MissingStep]:
    """Steps of one parameter that are absent on some or all of the requested
    levels and members.

    With named steps the expectation is exact: each of them, everywhere.
    Without ("all", Between) the server gives no list of expected steps, so a
    step that exists on one level or member is expected on all of them. A step
    not yet published anywhere cannot be noticed then.
    """
    if named_steps is None:
        expected = sorted({asset.step for asset in chosen})
    else:
        expected = list(named_steps)

    present = {(asset.level, asset.member, asset.step) for asset in chosen}
    wanted_levels: list[Decimal | None] = list(levels) if levels else [None]
    wanted_members: list[int | None] = list(members) if members else [None]

    missing: list[MissingStep] = []
    for step in expected:
        lacking = [
            (level, member)
            for level in wanted_levels
            for member in wanted_members
            if (level, member, step) not in present
        ]
        if len(lacking) == len(wanted_levels) * len(wanted_members):
            # Everything is missing, just add a missing step without level and member.
            missing.append(MissingStep(parameter, step, wavelength=wavelength))
        else:
            for level, member in lacking:
                missing.append(
                    MissingStep(parameter, step, level, member, wavelength)
                )
    return missing


def _describe_missing(
    run: Run,
    missing: Sequence[MissingStep],
    sizes: dict[tuple[str, int | None], tuple[int, int]],
) -> str:
    """One line for the error or warning, grouped by parameter and step:
    "W 180h (24 of 120 levels)", or just "T_2M 3h" when it is missing everywhere.
    `sizes` holds the number of levels and members requested per parameter
    and wavelength.
    """
    # Missing entries per (parameter, wavelength, step). None means missing
    # everywhere.
    counts: dict[tuple[str, int | None, timedelta], int | None] = {}
    for item in missing:
        key = (item.parameter, item.wavelength, item.step)
        if item.level is None and item.member is None:
            counts[key] = None
        else:
            counts[key] = (counts.get(key) or 0) + 1

    parts = []
    for (parameter, wavelength, step), count in counts.items():
        text = parameter
        if wavelength is not None:
            text += f" {wavelength} nm"
        text += f" {format_duration(step)}"
        if count is not None:
            levels, members = sizes[(parameter, wavelength)]
            if members == 1:
                text += f" ({count} of {levels} levels)"
            elif levels == 1:
                text += f" ({count} of {members} members)"
            else:
                text += f" ({count} of {levels * members} level/member fields)"
        parts.append(text)

    shown = ", ".join(parts[:5])
    more = " ..." if len(parts) > 5 else ""
    return f"run {run} is missing {len(parts)} requested step(s): {shown}{more}"


def _expand_every_step(selector: Every[StepScalar]) -> list[timedelta]:
    """Every("0h", "48h", "3h") -> 0h, 3h, ..., 48h (inclusive interval)."""
    start = parse_duration(selector.start)
    stop = parse_duration(selector.stop)
    every = parse_duration(selector.every)
    if every <= timedelta(seconds=0):
        raise InvalidSelectorError(
            f"the step between values must be positive, got "
            f"{format_duration(every)}"
        )
    steps = []
    current = start
    while current <= stop:
        steps.append(current)
        current += every
    return steps
