"""Calling resolve() on a query produces frozen assets, and the interface
that turns them into files.

The Downloader interface lives here rather than in its own module because
it is written in terms of Asset and ResolvedRequest returns its result.
Splitting the two apart makes the imports circular.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from dwdopen.exceptions import DownloadError
from dwdopen.nwp.run import Run

__all__ = [
    "Asset",
    "CombineMode",
    "DownloadResult",
    "Downloader",
    "Fetched",
    "MissingStep",
    "ResolvedRequest",
]

CombineMode = Literal["none", "all"]
"""How the downloaded messages are laid out on disk.
TODO add member and per parameter
"""


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

    def sort_key(self) -> tuple[timedelta, str]:
        """Returns a key to sort the assets by.
        Time first, parameter second, so that every field of one forecast step
        sits together and the steps ascend.
        Even though in general, GRIB messages can be concatenated without having
        to sort them, some other software might expect some sorting. For example,
        CDO (Climate Data Operators) refuses GRIB files whose messages are not in
        increasing time order. Sorting parameter-major would lead to a GRIB file that
        CDO rejects. So we sort here time-major.
        TODO: sort also levels, ens members...
        """
        return (self.step, self.parameter)


@dataclass(frozen=True)
class MissingStep:
    """A step that was requested but is not in the run."""
    parameter: str
    step: timedelta


@dataclass(frozen=True)
class Fetched:
    """What a Downloader actually wrote. Internal to the interface."""

    files: tuple[Path, ...]
    bytes_downloaded: int


class Downloader(Protocol):
    """Moves the bytes of a frozen plan onto disk."""

    def fetch(
        self,
        assets: Sequence[Asset],
        destination: Path,
        *,
        combine: CombineMode = "all",
        temp_dir: Path | None = None,
    ) -> Fetched:
        """Fetch every asset and lay it out under ``destination``.

        ``assets`` is taken in the order given and that order is preserved in a
        combined file, so the caller decides the message order.

        ``destination`` is a directory when combine="none" and a file when
        combine="all".

        ``temp_dir`` overrides where partial downloads are written. It must sit
        on the same filesystem as the destination: a finished file is published
        by renaming it, and a rename cannot cross filesystems. It defaults to
        the destination's own directory, which always satisfies that.
        """
        ...


@dataclass(frozen=True)
class DownloadResult:
    """What one download call produced."""

    files: tuple[Path, ...]
    run: Run
    assets_downloaded: int
    bytes_downloaded: int

    @property
    def total_size(self) -> int:
        """Bytes actually transferred."""
        return self.bytes_downloaded

    def __fspath__(self) -> str:
        """Allow a single-file result to be used where a path is expected."""
        if len(self.files) != 1:
            raise TypeError(
                f"this result holds {len(self.files)} files, so it is not a "
                f"single path. Use .files"
            )
        return os.fspath(self.files[0])


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

    downloader: Downloader | None = field(
        default=None, compare=False, repr=False
    )
    """How to fetch the assets. Not part of the plan's identity, so two plans
    resolved from different clients still compare equal."""

    def download(
        self,
        destination: str | os.PathLike[str],
        *,
        combine: CombineMode = "all",
        temp_dir: str | os.PathLike[str] | None = None,
    ) -> DownloadResult:
        """Fetch this plan.
        ``destination`` is a file for combine="all" and a directory for
        combine="none".

        ``temp_dir`` moves in-progress downloads elsewhere, for instance off
        a small home partition. It has to be on the same filesystem as the
        destination, because the finished file is published by renaming it.
        """
        if self.downloader is None:
            raise DownloadError(
                "this request was resolved without a downloader, so it cannot "
                "fetch anything. Build queries from DWD().nwp"
            )
        fetched = self.downloader.fetch(
            self.assets,
            Path(destination),
            combine=combine,
            temp_dir=None if temp_dir is None else Path(temp_dir),
        )
        return DownloadResult(
            files=fetched.files,
            run=self.run,
            assets_downloaded=len(self.assets),
            bytes_downloaded=fetched.bytes_downloaded,
        )

    @property
    def total_size(self) -> int | None:
        """Bytes to download, or None if the listing did not give sizes."""
        sizes = [asset.size for asset in self.assets]
        # If any size is None, return None
        if any(size is None for size in sizes):
            return None
        # Sum over all the asset sizes
        return sum(size for size in sizes if size is not None)
