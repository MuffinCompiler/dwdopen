"""The seam between the semantic layer and whatever provides availability."""

from __future__ import annotations

from typing import Protocol

from dwdopen._fileserver.listing import parse_listing
from dwdopen._fileserver.paths import build_path, Segment
from dwdopen.nwp.durations import parse_duration
from dwdopen.nwp.run import Run
from dwdopen.exceptions import RunExpiredError
from dwdopen.nwp.request import Asset

__all__ = ["Catalogue"]

GRIB_SUFFIX = ".grib2"

class Catalogue(Protocol):
    """Read-only view of what DWD Open Data currently offers.

    This is the boundary that keeps URL and path knowledge out of the semantic
    layer: nothing above it may know how availability is obtained.
    Several implementations can satisfy it. Lazy HTTP directory traversal is
    the only one built for now; a bulk index built from content.log.bz2 is
    conceivable later, and tests use a fake.
    """

    def models(self) -> list[str]:
        """Model names currently visible, sorted."""
        ...

    def parameters(self, model: str) -> list[str]:
        """Parameter names visible for the model, sorted.

        Raises UnknownModelError if the model is not in the catalogue.
        """
        ...

    def runs(self, model: str, *, probe: str | None = None) -> list[Run]:
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

    def assets(self, model: str, parameter: str, run: Run) -> list[Asset]:
        """Every asset of one parameter in one run.
        """
        where = (("m", model), ("p", parameter))
        token = self._run_token(where, parameter, run)
        listing = self._http.get_listing(build_path(*where, ("r", token), key="s"))

        assets = []
        for entry in parse_listing(listing):
            if entry.is_dir:
                continue
            keys = (*where, ("r", token), ("s", entry.name))
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

    def _run_token(self, where: tuple[Segment, ...], parameter: str, run: Run) -> str:
        """Find the directory name the server uses for this run."""
        for entry in self._subdirectories(*where, key="r"):
            if Run.coerce(entry.name) == run:
                return entry.name
        raise RunExpiredError(
            f"run {run} is not available for {parameter}. Retention is short: "
            f"ICON-EU keeps 8 runs, ICON-D2-RUC 32"
        )

    def refresh(self) -> None:
        """Drop cached state so the next call re-builds the catalogue from the server."""
        ...

    def close(self) -> None:
        """Release any transport resources."""
        ...
