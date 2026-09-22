"""Catalogue built by lazy traversal of the Open Data directory tree.

One implementation of the Catalogue protocol.
TODO add caching
"""

from __future__ import annotations

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import ListingEntry, parse_listing
from dwdopen._fileserver.paths import Segment, build_path
from dwdopen.exceptions import CatalogueUnavailableError, RunExpiredError
from dwdopen.nwp.durations import parse_duration
from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run

__all__ = ["OpenDataCatalogue"]

GRIB_SUFFIX = ".grib2"

RUN_KEY = "r"
"""The key that sits directly below .../p/<NAME>/ for a plain 2-D parameter.

Anything else there (lvt1 for a 3-D field, wvl1 for ICON-ART) means the run
listing is deeper down the path.
"""

STEP_KEY = "s"
"""The key holding the step files. Always the last key of a path.

For a deterministic model it sits directly below the run. An ensemble pushes it
one level deeper, below e/<member>/, so the run of an ensemble member reads
.../r/<run>/e/<member>/s/<step>.grib2. The key is never replaced, only moved,
which is why finding something other than s below the run means "look deeper",
not "this model has no steps".
"""


class OpenDataCatalogue:
    """Answers availability questions by listing directories on demand.
    Takes an HttpClient, so the config is in one place and for testing we
    can pass a "fake".
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

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

    def runs(self, model: str, *, probe: str | None = None) -> list[Run]:
        """Runs visible for the model, oldest first.
        ``probe`` names the parameter to look under, because the DWD layout has
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
        run_entries = self._run_entries((("m", model), ("p", probe)))
        runs = [Run.coerce(entry.name) for entry in run_entries]
        return sorted(runs)

    def assets(self, model: str, parameter: str, run: Run) -> list[Asset]:
        """Every asset of one parameter in one run in one model."""
        where = (("m", model), ("p", parameter))
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
                )
            )
        return assets

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
            f"{build_path(*where)} contains {'/, '.join(found)}/, "
            f"not {expected}/. levels (lvt1/lv1), wavelengths (wvl1) and "
            f"ensemble members (e) are not supported yet, only single-level "
            f"deterministic parameters"
        )

    def _run_token(self, where: tuple[Segment, ...], parameter: str, run: Run) -> str:
        """Find the directory name the server uses for the given run.
        Throws an error when the run is not available, otherwise returns the path.
        """
        for entry in self._run_entries(where):
            if Run.coerce(entry.name) == run:
                return entry.name
        raise RunExpiredError(
            f"run {run} is not available for {parameter}. Retention is short: "
            f"ICON-EU and ICON-D2 keep 8 runs, ICON and the ensembles 4, "
            f"ICON-D2-RUC 24"
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
