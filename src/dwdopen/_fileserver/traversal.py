"""Catalogue built by lazy traversal of the Open Data directory tree.

One implementation of the Catalogue protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from decimal import Decimal

from dwdopen._fileserver.cache import ListingCache
from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import ListingEntry, parse_listing
from dwdopen._fileserver.paths import Segment, build_path
from dwdopen.exceptions import (
    CatalogueError,
    CatalogueUnavailableError,
    MissingAssetError,
    RunExpiredError,
)
from dwdopen.nwp.durations import parse_duration
from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

__all__ = ["OpenDataCatalogue"]


GRIB_SUFFIX = ".grib2"

# Every key DWD uses in a v1 path, in the order they appear:
#   m/<model>/p/<param>[/wvl1/<nm>][/lvt1/<type>/lv1/<value>]
#   /r/<run>[/e/<member>]/s/<step>.grib2

PROBE_PARAMETERS = ("T_2M", "PS")
"""Parameters used to read the available runs if the caller doesn't name a
parameter. The available runs cannot be read just given a model, as the runs
are listed not for each model, but for each parameter. So we need some
"probing" parameters. The parameters above are available on all models DWD
currently offers (Oct 26).
"""

MODEL_KEY = "m"
"""The forecast model, for example icon-eu."""

PARAMETER_KEY = "p"
"""The parameter shortname, for example T_2M."""

WAVELENGTH_KEY = "wvl1"
"""The wavelength in nm, for ICON-ART's optical parameters such as
SAT_BSC_DUST. Absent for everything else. Not in DWD's documentation of the
v1 keys, but on the server.
"""

LEVEL_TYPE_KEY = "lvt1"
"""GRIB typeOfFirstFixedSurface. Absent for a 2-D field."""

LEVEL_KEY = "lv1"
"""The level value, in the unit that level type uses."""

RUN_KEY = "r"
"""The key that sits directly below .../p/<NAME>/ for a plain 2-D parameter.
Anything else there (lvt1 for a 3-D field, wvl1 for ICON-ART) means the run
listing is deeper down the path.
"""

MEMBER_KEY = "e"
"""The ensemble member. Zero padded to two digits."""

STEP_KEY = "s"
"""The key holding the step files. Always the last key of a path.
This always sits on the "deepest" level. So within the s/ subdirectory,
there will be the grib2 files to download.
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
        self._cache = ListingCache()

    def snapshot(self) -> AbstractContextManager[None]:
        """See Catalogue.snapshot."""
        return self._cache.snapshot()

    def _entries(self, path: str) -> list[ListingEntry]:
        """The parsed listing of one directory, cached.
        """
        # Check which cache we are in: runs/steps are volatile, everything
        # above is structural and therefore not volatile.
        volatile = RUN_KEY in path.strip("/").split("/")
        cached = self._cache.get(path, volatile=volatile)
        if cached is not None:
            return cached

        entries = parse_listing(self._http.get_listing(path))
        self._cache.put(path, entries, volatile=volatile)
        return entries

    def models(self) -> list[str]:
        """Model names currently visible, sorted."""
        model_entries = self._subdirectories(key=MODEL_KEY)
        model_names = [entry.name for entry in model_entries]
        return sorted(model_names)

    def parameters(self, model: str) -> list[str]:
        """Parameter names visible for the model, sorted.
        """
        parameter_entries = self._subdirectories(
            (MODEL_KEY, model), key=PARAMETER_KEY
        )
        parameter_names = [entry.name for entry in parameter_entries]
        return sorted(parameter_names)

    def runs(
        self,
        model: str,
        *,
        parameter: str | None = None,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
        wavelength: int | None = None,
    ) -> list[Run]:
        """Runs visible for the model, oldest first.

        DWD keeps the runs below the parameter, and below lvt1/lv1 for a 3-D
        field, so there is no run listing at model level. Answering the
        question therefore means picking one parameter, and one of its levels
        if it has any. Every parameter of a model normally carries the same
        runs, but one has to be named.

        A run can appear here while it is still being published.
        """
        if parameter is None:
            parameter = self._probe_parameter(model)
        run_entries = self._run_entries(
            self._above_run(model, parameter, level_type, level, wavelength)
        )
        runs = [Run.coerce(entry.name) for entry in run_entries]
        return sorted(runs)

    def _probe_parameter(self, model: str) -> str:
        """A parameter to read the available runs from.
        Has to be a 2-D field: a 3-D field stores available runs also below
        the level type and level, which would mean choosing a level as well.
        """
        available = self.parameters(model)
        for name in PROBE_PARAMETERS:
            if name in available:
                return name
        raise CatalogueUnavailableError(
            f"none of {', '.join(PROBE_PARAMETERS)} exists in {model!r}, so no "
            f"parameter could be picked to read the runs from. Pass "
            f"parameter=... naming a 2-D field of this model"
        )

    def _above_run(
        self,
        model: str,
        parameter: str,
        level_type: LevelType | None,
        level: Decimal | None,
        wavelength: int | None = None,
    ) -> tuple[Segment, ...]:
        """The path segments that sit above the run: m, p, the wavelength
        and the level.
        """
        where = self._parameter_root(model, parameter, wavelength)
        if level_type is None or level is None:
            return where
        tokens = self._level_tokens_by_value(
            model, parameter, level_type, wavelength
        )
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

    def _parameter_root(
        self, model: str, parameter: str, wavelength: int | None
    ) -> tuple[Segment, ...]:
        """The path segments of m, p, and wvl1 if a wavelength is given."""
        root: tuple[Segment, ...] = ((MODEL_KEY, model), (PARAMETER_KEY, parameter))
        if wavelength is None:
            return root
        tokens = self._wavelength_tokens_by_value(model, parameter)
        # Get the string token of the nm wavelength, which is used on server.
        token = tokens.get(wavelength)
        if token is None:
            raise MissingAssetError(
                f"{model}/{parameter} has no wavelength {wavelength} nm"
                + (f". Available: {', '.join(str(v) for v in sorted(tokens))}"
                   if tokens else "")
            )
        return (*root, (WAVELENGTH_KEY, token))

    def wavelengths(self, model: str, parameter: str) -> list[int]:
        """Wavelengths in nm this parameter is published for, sorted.
        Empty for every parameter that has no wvl1 segment, which is all but
        a few ICON-ART ones.
        """
        return sorted(self._wavelength_tokens_by_value(model, parameter))

    def _wavelength_tokens_by_value(
        self, model: str, parameter: str
    ) -> dict[int, str]:
        """Every wavelength in nm, mapped to the string token the server writes
        for it. Empty if the parameter has no wvl1 segment.
        """
        root = ((MODEL_KEY, model), (PARAMETER_KEY, parameter))
        below_parameter = [entry.name for entry in self._subdirectories(*root)]
        if WAVELENGTH_KEY not in below_parameter:
            return {}
        entries = self._subdirectories(*root, key=WAVELENGTH_KEY)
        return {int(entry.name): entry.name for entry in entries}

    def level_types(
        self, model: str, parameter: str, *, wavelength: int | None = None
    ) -> list[LevelType]:
        """Vertical coordinate types this parameter is published on, sorted."""
        root = self._parameter_root(model, parameter, wavelength)
        level_type_key_dir = [entry.name for entry in self._subdirectories(*root)]
        if LEVEL_TYPE_KEY not in level_type_key_dir:
            return [] # No level types, probably 2-D.
        entries = self._subdirectories(*root, key=LEVEL_TYPE_KEY)
        # Convert to the LevelType type, given the code.
        return sorted(
            (LevelType.of(int(entry.name)) for entry in entries),
            key=lambda lt: lt.code,
        )

    def levels(
        self,
        model: str,
        parameter: str,
        level_type: LevelType,
        *,
        wavelength: int | None = None,
    ) -> list[Decimal]:
        """Level values available, in the unit DWD writes them in."""
        return sorted(
            self._level_tokens_by_value(model, parameter, level_type, wavelength)
        )

    def assets(
        self,
        model: str,
        parameter: str,
        run: Run,
        *,
        level_type: LevelType | None = None,
        levels: Sequence[Decimal] | None = None,
        members: Sequence[int] | None = None,
        wavelength: int | None = None,
    ) -> list[Asset]:
        """Every asset of one parameter in one run in one model."""
        chosen_levels: list[Decimal | None] = (
            [None] if level_type is None or levels is None else list(levels)
        )
        chosen_members: list[int | None] = list(members) if members else [None]

        # Combinations for levels and members.
        combinations = [
            (level, member)
            for level in chosen_levels
            for member in chosen_members
        ]

        def fetch(combination: tuple[Decimal | None, int | None]) -> list[Asset]:
            level, member = combination
            return self._assets_for(
                model, parameter, run, level_type, level, member, wavelength
            )

        # Fetch assets in parallel for each of the combination.
        if len(combinations) == 1:
            batches = [fetch(combinations[0])]
        else:
            workers = min(self._max_workers, len(combinations))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                batches = list(pool.map(fetch, combinations))

        found: list[Asset] = []
        for batch in batches:
            found.extend(batch)
        return found

    def _assets_for(
        self,
        model: str,
        parameter: str,
        run: Run,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
        member: int | None = None,
        wavelength: int | None = None,
    ) -> list[Asset]:
        """The available forecast step files for one exact combination.
        """
        where = self._above_run(model, parameter, level_type, level, wavelength)
        run_token = self._run_token(where, parameter, run)
        below_run = (*where, (RUN_KEY, run_token))

        # Member for ensemble forecasts
        if member is not None:
            tokens = self._member_tokens_by_value(
                model, parameter, run, level_type, level, wavelength
            )
            if member not in tokens:
                raise MissingAssetError(
                    f"{parameter} has no member {member} in run {run}. "
                    f"Available: {min(tokens)}..{max(tokens)}" if tokens
                    else f"{parameter} has no ensemble members in run {run}"
                )
            # Add member to the access segments.
            below_run = (*below_run, (MEMBER_KEY, tokens[member]))

        # Get the listing of all available steps.
        try:
            entries = self._entries(build_path(*below_run, key=STEP_KEY))
        except CatalogueUnavailableError:
            self._explain_unreachable(*below_run, expected=STEP_KEY)
            raise

        assets = []
        # Parse entries. Each entry is one GRIB file, thus one asset.
        for entry in entries:
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
                    level=_user_level(level_type, level),
                    member=member,
                    wavelength=wavelength,
                )
            )
        return assets

    def members(
        self,
        model: str,
        parameter: str,
        run: Run,
        *,
        level_type: LevelType | None = None,
        level: Decimal | None = None,
        wavelength: int | None = None,
    ) -> list[int]:
        """Ensemble members available for one parameter in one run, sorted.
        A 3-D field needs the level too, since the run sits below lvt1/lv1.
        Empty for a deterministic model.
        """
        return sorted(
            self._member_tokens_by_value(
                model, parameter, run, level_type, level, wavelength
            )
        )

    def _member_tokens_by_value(
        self,
        model: str,
        parameter: str,
        run: Run,
        level_type: LevelType | None,
        level: Decimal | None,
        wavelength: int | None = None,
    ) -> dict[int, str]:
        """Returns a map of every member number to the token (string) the server
        uses. On the server, members are padded to two digits currently.
        (Contrary to levels that are not padded at all.)

        An empty mapping means the parameter has no e/ segment, so the model is
        deterministic.
        """
        where = self._above_run(model, parameter, level_type, level, wavelength)
        run_token = self._run_token(where, parameter, run)
        below_run = (*where, (RUN_KEY, run_token))
        try:
            entries = self._subdirectories(*below_run, key=MEMBER_KEY)
        except CatalogueUnavailableError:
            return {}
        return {int(entry.name): entry.name for entry in entries}

    def _level_tokens_by_value(
        self,
        model: str,
        parameter: str,
        level_type: LevelType,
        wavelength: int | None = None,
    ) -> dict[Decimal, str]:
        """Every available level, mapped to the token the server writes for it.
        Decimal type to avoid floating point issues with soil value heights.
        """
        entries = self._subdirectories(
            *self._parameter_root(model, parameter, wavelength),
            (LEVEL_TYPE_KEY, str(level_type.code)),
            key=LEVEL_KEY,
        )
        return {Decimal(entry.name): entry.name for entry in entries}

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
        """Throws what a directory holds instead of the key we just failed to read.
        "where" builds the path, "expected" was an expected entry at that path.
        """
        try:
            found = [entry.name for entry in self._subdirectories(*where)]
        except CatalogueUnavailableError:
            return
        if found == [expected]:
            # The key is there, so the failure was not about the layout.
            return
        raise CatalogueError(
            f"{build_path(*where)} contains {'/, '.join(found)}/, not "
            f"{expected}/, so the path needs more segments (a level, member or "
            f"wavelength) to get there"
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
        self._cache.clear()

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
        entries = [entry for entry in self._entries(path) if entry.is_dir]

        if not entries:
            raise CatalogueUnavailableError(
                f"no subdirectories found in {path}. Either the path is wrong or "
                f"the server's listing format changed"
            )
        return entries


def _user_level(
    level_type: LevelType | None, level: Decimal | None
) -> Decimal | None:
    """The level of an asset in the user-facing unit (hPa for pressure).
    """
    if level_type is None or level is None:
        return None
    return level_type.to_user(level)
