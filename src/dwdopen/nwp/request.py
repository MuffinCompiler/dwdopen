"""Calling resolve() on a query produces frozen assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from dwdopen.nwp.run import Run

__all__ = ["Asset", "MissingStep", "ResolvedRequest"]


@dataclass(frozen=True)
class Asset:
    """One file on the server, identified by its path segments."""

    keys: tuple[tuple[str, str], ...]
    """Path key/token pairs in path order, for example (("m", "icon-eu"),
    ("p", "T_2M"), ("r", "2026-09-16T00:00"), ("s", "PT000H00M.grib2")).
    """

    run: Run
    step: timedelta

    path: str
    """Where the backend fetches this from.
    """

    size: int | None = None

    modified: datetime | None = None
    """Only for the guard in Query.latest_run to make sure data has settled.
    Need to be careful as the different open data servers we interact with
    might disagree on modification times slightly.
    """

    @property
    def parameter(self) -> str:
        return dict(self.keys)["p"]

    def sort_key(self) -> tuple[str, timedelta]:
        """Returns a key to sort the assets by.
        Model and run are the same for every asset in a resolved request, so
        parameter and step are all that can vary. Levels and members
        still needed TODO
        """
        return (self.parameter, self.step)


@dataclass(frozen=True)
class MissingStep:
    """A step that was requested but is not in the run."""
    parameter: str
    step: timedelta


@dataclass(frozen=True)
class ResolvedRequest:
    """A frozen plan: A resolved request contains the list of assets to download,
    basically all the URL to fetch data from.
    A later download never switches to a newer run. If files have disappeared
    in the meantime, the download fails.
    """

    run: Run
    assets: tuple[Asset, ...]
    resolved_at: datetime
    missing: tuple[MissingStep, ...] = ()

    @property
    def total_size(self) -> int | None:
        """Bytes to download, or None if the listing did not give sizes."""
        sizes = [asset.size for asset in self.assets]
        # If any size is None, return None
        if any(size is None for size in sizes):
            return None
        # Sum over all the asset sizes
        return sum(size for size in sizes if size is not None)