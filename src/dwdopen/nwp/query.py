"""A semantic query describes a selection to fetch."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

from dwdopen.exceptions import (
    IncompleteRunError,
    InvalidSelectorError,
    NoMatchingRunError,
    RunExpiredError
)
from dwdopen.nwp.catalogue import Catalogue
from dwdopen.nwp.durations import format_duration, parse_duration
from dwdopen.nwp.request import Asset, MissingStep, ResolvedRequest
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import Between, Every, StepSelector

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
    """A description of what to retrieve, not yet tied to a run.
    The availability of the data is resolved by resolve() and latest_run().

    Use Model.select() to construct a query.
    """

    def __init__(
        self,
        catalogue: Catalogue,
        model: str,
        *,
        parameters: tuple[str, ...],
        steps: StepSelector | None = None,
        run: RunLike | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._model = model
        self._parameters = parameters
        self._steps = steps
        self._run = None if run is None else Run.coerce(run)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={self._model!r}, "
            f"parameters={list(self._parameters)})"
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
        """
        probe = self._parameters[0]
        candidates = self._catalogue.runs(self._model, probe=probe)
        now = datetime.now(UTC)

        for run in reversed(candidates):
            try:
                request = self.resolve(run=run, require=require)
            except (IncompleteRunError, RunExpiredError):
                # A run can be listed for the probe parameter and
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
        When require="complete" is set, any missing time step raises
        IncompleteRunError. With "partial" it is reported in the missing field
        instead. Open selectors such as Between() can never be incomplete.
        """
        chosen = run if run is not None else self._run
        if chosen is None:
            resolved_run = self.latest_run(require=require)
        else:
            resolved_run = Run.coerce(chosen)

        assets: list[Asset] = []
        missing: list[MissingStep] = []
        # Get the assets for every parameter.
        for parameter in self._parameters:
            available = self._catalogue.assets(self._model, parameter, resolved_run)
            wanted, absent = _select_steps(available, self._steps)
            assets.extend(wanted)
            missing.extend(MissingStep(parameter, step) for step in absent)

        # If missing but required complete, raise an error.
        if missing and require == "complete":
            shown = ", ".join(
                f"{item.parameter} {format_duration(item.step)}" for item in missing[:5]
            )
            raise IncompleteRunError(
                f"run {resolved_run} is missing {len(missing)} requested step(s): "
                f"{shown}{' ...' if len(missing) > 5 else ''}"
            )

        return ResolvedRequest(
            run=resolved_run,
            assets=tuple(sorted(assets, key=Asset.sort_key)),
            resolved_at=datetime.now(UTC),
            missing=tuple(missing),
        )

    def download(
        self,
        destination: str | os.PathLike[str],
        *,
        run: RunLike | None = None,
        require: Require = "complete",
        combine: Literal["none", "all"] = "all",
    ) -> object:
        raise NotImplementedError("downloading is not implemented yet")


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
) -> tuple[list[Asset], list[timedelta]]:
    """Pick the assets a step selector asks for.
    Only selectors that name specific forecast steps can have missing steps.
    "all" and Between() ask for whatever exists, so they never report anything missing.
    """
    if selector is None or selector == "all":
        return list(available), []

    by_step = {asset.step: asset for asset in available}

    # Between: Check every assets time and put ones in chosen that are in the interval.
    if isinstance(selector, Between):
        start = None if selector.start is None else parse_duration(selector.start)
        stop = None if selector.stop is None else parse_duration(selector.stop)
        chosen = [
            asset
            for asset in available
            if (start is None or asset.step >= start)
            and (stop is None or asset.step <= stop)
        ]
        return chosen, []

    # Every or specific time deltas: Collect the wanted forecast steps.
    if isinstance(selector, Every):
        wanted = _expand_cadence(selector)
    elif isinstance(selector, str | timedelta):
        wanted = [parse_duration(selector)]
    else:
        wanted = [parse_duration(item) for item in selector]

    # Look whether the wanted steps are available in the assets.
    found = [by_step[step] for step in wanted if step in by_step]
    absent = [step for step in wanted if step not in by_step]
    return found, absent


def _expand_cadence(selector: Every) -> list[timedelta]:
    """Every("0h", "48h", "3h") -> 0h, 3h, ..., 48h (inclusive interval)."""
    start = parse_duration(selector.start)
    stop = parse_duration(selector.stop)
    every = parse_duration(selector.every)
    if every <= timedelta(seconds=0):
        raise InvalidSelectorError(
            f"a cadence must be positive, got {format_duration(every)}"
        )
    steps = []
    current = start
    while current <= stop:
        steps.append(current)
        current += every
    return steps
