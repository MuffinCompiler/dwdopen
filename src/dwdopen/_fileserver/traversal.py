"""Catalogue built by lazy traversal of the Open Data directory tree.

One implementation of the Catalogue protocol.
TODO add caching
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import TypeVar

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import ListingEntry, parse_listing
from dwdopen._fileserver.paths import Segment, build_path
from dwdopen.exceptions import (
    CatalogueUnavailableError,
    MissingAssetError,
    RunExpiredError,
)
from dwdopen.nwp.durations import parse_duration
from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

__all__ = ["OpenDataCatalogue"]

_T = TypeVar("_T")
_R = TypeVar("_R")

GRIB_SUFFIX = ".grib2"

RUN_KEY = "r"
"""The key that sits directly below .../p/<NAME>/ for a plain 2-D parameter.

Anything else there (lvt1 for a 3-D field, wvl1 for ICON-ART) means the run
listing is deeper down the path.
"""

LEVEL_TYPE_KEY = "lvt1"
"""GRIB typeOfFirstFixedSurface. Absent for a 2-D field."""

LEVEL_KEY = "lv1"
"""The level value, in the unit that level type uses."""

STEP_KEY = "s"
"""The key holding the step files. Always the last key of a path.

For a deterministic model it sits directly below the run. An ensemble pushes it
one level deeper, below e/<member>/, so the run of an ensemble member reads
.../r/<run>/e/<member>/s/<step>.grib2.
"""


class OpenDataCatalogue:
    """Answers availability questions by listing directories on demand.
    Takes an HttpClient, so the config is in one place and for testing we
    can pass a "fake".
    """

    def __init__(self, http: HttpClient, *, max_workers: int = 16) -> None:
        self._http = http
        self._max_workers = max_workers

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

    def runs(
        self,
        model: str,
        *,
        probe: str | None = None,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
    ) -> list[Run]:
        """Runs visible for the model, oldest first.
        ``probe`` names the parameter (and level if 3-D) to look under, because the DWD layout has
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
        run_entries = self._run_entries(
            self._prefix(model, probe, level_type, level)
        )
        runs = [Run.coerce(entry.name) for entry in run_entries]
        return sorted(runs)

    def _prefix(
        self,
        model: str,
        parameter: str,
        level_type: LevelType | None,
        level: Decimal | None,
    ) -> tuple[Segment, ...]:
        """The path down to, but not including, the run key."""
        where: tuple[Segment, ...] = (("m", model), ("p", parameter))
        if level_type is None or level is None:
            return where
        tokens = self._level_tokens(model, parameter, level_type)
        token = tokens.get(level)
        if token is None:
            raise MissingAssetError(
                f"{model}/{parameter} has no level {level} on {level_type}. "
                f"Available: {', '.join(str(v) for v in sorted(tokens))}"
            )
        return (
            *where,
            (LEVEL_TYPE_KEY, str(level_type.code)),
            (LEVEL_KEY, token),
        )

    def level_types(self, model: str, parameter: str) -> list[LevelType]:
        """Vertical coordinate types this parameter is published on, sorted."""
        below = [e.name for e in self._subdirectories(("m", model), ("p", parameter))]
        if LEVEL_TYPE_KEY not in below:
            return []
        entries = self._subdirectories(
            ("m", model), ("p", parameter), key=LEVEL_TYPE_KEY
        )
        return sorted(
            (LevelType.of(int(entry.name)) for entry in entries),
            key=lambda lt: lt.code,
        )

    def levels(
        self, model: str, parameter: str, level_type: LevelType
    ) -> list[Decimal]:
        """Level values available, in the unit DWD writes them in."""
        return sorted(self._level_tokens(model, parameter, level_type))

    def assets(
        self,
        model: str,
        parameter: str,
        run: Run,
        *,
        level_type: LevelType | None = None,
        levels: Sequence[Decimal] | None = None,
    ) -> list[Asset]:
        """Every asset of one parameter in one run in one model."""
        base = (("m", model), ("p", parameter))
        if level_type is None or levels is None:
            return self._assets_below(base, parameter, run, None, None)

        prefixes = [
            (self._prefix(model, parameter, level_type, level), level)
            for level in levels
        ]

        found: list[Asset] = []
        # Collect assets for each level.
        for batch in self._in_parallel(
            lambda item: self._assets_below(
                item[0], parameter, run, level_type, item[1]
            ),
            prefixes,
        ):
            found.extend(batch)
        return found

    def _assets_below(
        self,
        where: tuple[Segment, ...],
        parameter: str,
        run: Run,
        level_type: LevelType | None,
        level: Decimal | None,
    ) -> list[Asset]:
        """The step files under one fully-qualified prefix."""
        token = self._run_token(where, parameter, run)

        # Straight for the step files. A deterministic model has them directly
        # below the run; an ensemble hides them under e/<member>/ and this 404s.
        below_run = (*where, (RUN_KEY, token))
        try:
            listing = self._http.get_listing(build_path(*below_run, key=STEP_KEY))
        except CatalogueUnavailableError:
            self._explain_unreachable(*below_run, expected=STEP_KEY)
            raise

        assets = []
        for entry in parse_listing(listing):
            if entry.is_dir:
                continue
            keys = (*below_run, (STEP_KEY, entry.name))
            assets.append(
                Asset(
                    keys=keys,
                    run=run,
                    step=parse_duration(entry.name.removesuffix(GRIB_SUFFIX)),
                    path=build_path(*keys, directory=False),
                    size=entry.size,
                    modified=entry.modified,
                    level_type=level_type,
                    level=level,
                )
            )
        return assets

    def _level_tokens(
        self, model: str, parameter: str, level_type: LevelType
    ) -> dict[Decimal, str]:
        """Map each available level onto the exact token the server uses.
        """
        entries = self._subdirectories(
            ("m", model),
            ("p", parameter),
            (LEVEL_TYPE_KEY, str(level_type.code)),
            key=LEVEL_KEY,
        )
        return {Decimal(entry.name): entry.name for entry in entries}

    def _in_parallel(
        self, work: Callable[[_T], _R], items: Sequence[_T]
    ) -> list[_R]:
        """Run one listing job per item, bounded, preserving input order."""
        if len(items) <= 1:
            return [work(item) for item in items]
        workers = min(self._max_workers, len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(work, items))

    def _run_entries(self, where: tuple[Segment, ...]) -> list[ListingEntry]:
        """List the run directories of one parameter.

        Where the runs are is the one thing that differs between a plain 2-D
        parameter and everything else, so this is the single place that has to
        explain itself when the listing is not there.
        """
        try:
            return self._subdirectories(*where, key=RUN_KEY)
        except CatalogueUnavailableError:
            self._explain_unreachable(*where, expected=RUN_KEY)
            raise

    def _explain_unreachable(self, *where: Segment, expected: str) -> None:
        """Say what a directory holds instead of the key we just failed to read.

        Only ever called after a listing already failed, so the extra request
        costs nothing while things work. Returns quietly when it cannot improve
        on the original error, leaving the caller to re-raise that.
        """
        try:
            found = [entry.name for entry in self._subdirectories(*where)]
        except CatalogueUnavailableError:
            return
        if found == [expected]:
            # The key is there, so the failure was not about the layout.
            return
        raise NotImplementedError(
            f"{build_path(*where)} contains {'/, '.join(found)}/, not "
            f"{expected}/. Wavelengths (wvl1, ICON-ART) and ensemble members "
            f"(e) are not supported yet. For a level type pass level_type= "
            f"and levels= to select()"
        )

    def _run_token(self, where: tuple[Segment, ...], parameter: str, run: Run) -> str:
        """Find the directory name the server uses for the given run.
        Throws an error when the run is not available, otherwise returns the path.
        """
        for entry in self._run_entries(where):
            if Run.coerce(entry.name) == run:
                return entry.name
        raise RunExpiredError(
            f"run {run} is not available for {parameter}. A forecast is "
            f"available for only "
            f"about 24 hours on the DWD server. If you are within this time frame, "
            f"either the run is not published yet or not available for "
            f"other reasons. "
            f"Check the availability directly on https://opendata.dwd.de/"
        )

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
