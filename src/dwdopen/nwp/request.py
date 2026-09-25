"""Calling resolve() on a query produces frozen assets, and the interface
that turns them into files.

The Downloader interface lives here rather than in its own module because
it is written in terms of Asset and ResolvedRequest returns its result.
Splitting the two apart makes the imports circular.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

from dwdopen.exceptions import DownloadError
from dwdopen.nwp.durations import format_duration
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

__all__ = [
    "Asset",
    "CombineMode",
    "DownloadResult",
    "Downloader",
    "Fetched",
    "MissingStep",
    "ResolvedRequest",
]

FINGERPRINT_LENGTH = 8
"""Hex characters of the plan hash kept in a generated file name.
"""

MAX_NAME_LENGTH = 120
"""Longest generated file name, in characters.
"""

logger = logging.getLogger("dwdopen")

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

    level_type: LevelType | None = None
    """None for a 2-D field."""

    level: Decimal | None = None
    """The level in the unit DWD writes, so Pa for pressure and metres for soil.
    Decimal rather than float because soil levels are fractions of a metre
    (0.005, 0.18), might become problematic with floating point representations.
    """

    @property
    def parameter(self) -> str:
        return dict(self.keys)["p"]

    @property
    def model(self) -> str:
        return dict(self.keys)["m"]

    def describe_level(self) -> str:
        """The vertical position in the unit a reader thinks in.

        Empty for a 2-D field. Pressure comes back as "850 hPa" rather than the
        85000 Pa of the path, because that is what was asked for.
        """
        if self.level_type is None or self.level is None:
            return ""
        value = self.level_type.to_user(self.level)
        unit = self.level_type.user_unit or self.level_type.unit
        if unit in (None, "index"):
            return f"level {_trim(value)}"
        return f"{_trim(value)} {unit}"

    def __repr__(self) -> str:
        parts = [self.parameter, format_duration(self.step)]
        where = self.describe_level()
        if where:
            parts.insert(1, where)
        if self.size is not None:
            parts.append(human_size(self.size))
        return f"{type(self).__name__}({', '.join(parts)})"

    def sort_key(self) -> tuple[timedelta, str, int, Decimal]:
        """Returns a key to sort the assets by.
        Time first, parameter second, then the vertical coordinate, so that
        every field of one forecast step sits together and the steps ascend.
        Even though in general, GRIB messages can be concatenated without having
        to sort them, some other software might expect some sorting. For example,
        CDO (Climate Data Operators) refuses GRIB files whose messages are not in
        increasing time order. Sorting parameter-major would lead to a GRIB file that
        CDO rejects. So we sort here time-major.
        TODO: sort also ens members...
        """
        return (
            self.step,
            self.parameter,
            -1 if self.level_type is None else self.level_type.code,
            Decimal(0) if self.level is None else self.level,
        )


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
    """How many bytes were actually downloaded."""

    skipped: int = 0
    """How many assets were already on disk and needed no transfer."""


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
    assets_skipped: int = 0
    """Assets that were already present, so nothing had to be fetched for them.
    """

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

        With combine="all" a destination that is an existing directory, or that
        ends with a separator, suggested_name() is called to generate a file name.

        ``temp_dir`` moves in-progress downloads elsewhere, for instance off
        a small home partition. It has to be on the same filesystem as the
        destination, because the finished file is published by renaming it.
        """
        if self.downloader is None:
            raise DownloadError(
                "this request was resolved without a downloader, so it cannot "
                "fetch anything. Build queries from DWD().nwp"
            )

        # Get the target file name.
        target, generated = self._target(destination, combine)

        # A generated name carries this plan's fingerprint, so a file existing
        # was produced by the exact same selection. We can skip the download then.
        if generated and target.exists():
            logger.info("%s is already downloaded, nothing to do", target)
            return DownloadResult(
                files=(target,),
                run=self.run,
                assets_downloaded=0,
                bytes_downloaded=0,
                assets_skipped=len(self.assets),
            )

        fetched = self.downloader.fetch(
            self.assets,
            target,
            combine=combine,
            temp_dir=None if temp_dir is None else Path(temp_dir),
        )
        return DownloadResult(
            files=fetched.files,
            run=self.run,
            assets_downloaded=len(self.assets) - fetched.skipped,
            bytes_downloaded=fetched.bytes_downloaded,
            assets_skipped=fetched.skipped,
        )

    def _target(
        self, destination: str | os.PathLike[str], combine: CombineMode
    ) -> tuple[Path, bool]:
        """Returns the path where the data should go.

        combine="none" already expects a directory, so it is passed through. For
        combine="all" a directory is only recognized when it exists or when the
        caller wrote a trailing separator.
        If needed, a name is generated via suggested_name().
        Returns a bool alongside whether this method generated the name.
        """
        path = Path(destination)
        if combine != "all":
            return path, False
        looks_like_a_directory = str(destination).endswith(("/", os.sep))
        if path.is_dir() or looks_like_a_directory:
            return path / self.suggested_name(), True
        return path, False

    def fingerprint(self) -> str:
        """A short hash of the plan by hashing the sorted assets.
        """
        material = "\n".join(asset.path for asset in self.assets)
        return hashlib.sha256(material.encode()).hexdigest()[:FINGERPRINT_LENGTH]

    def suggested_name(self, suffix: str = ".grib2") -> str:
        """A file name describing the resolved request, human readable.
        Contains model, the run, step range, and a hash of the plan::

            icon-eu_2026-09-24T0600_T_2M+PMSL_0h-24h_a3f91c2e.grib2
            icon_2026-09-24T0000_P_120lv_0h-180h_09c1f0c5.grib2

        More than three parameters are counted rather than listed.
        """
        if not self.assets:
            raise DownloadError("cannot name an empty plan")

        run = f"{self.run.reference_time:%Y-%m-%dT%H%M}"
        tail = [self._describe_levels(), self._describe_steps()]
        fixed = [self.assets[0].model, run, *(part for part in tail if part)]
        ending = f"_{self.fingerprint()}{suffix}"

        name = self._assemble(fixed, self._describe_parameters(), ending)
        if len(name) <= MAX_NAME_LENGTH:
            return name

        # Count parameters instead of listing them if there are too many,
        count = f"{len({a.parameter for a in self.assets})}params"
        name = self._assemble(fixed, count, ending)
        if len(name) <= MAX_NAME_LENGTH:
            return name

        # Backup: trim if too long.
        return name[: MAX_NAME_LENGTH - len(ending)].rstrip("_+.") + ending

    @staticmethod
    def _assemble(fixed: list[str], parameters: str, suffix: str) -> str:
        """Put the parameter field back in its slot, after the run."""
        return "_".join([fixed[0], fixed[1], parameters, *fixed[2:]]) + suffix

    def _describe_parameters(self) -> str:
        names = sorted({asset.parameter for asset in self.assets})
        if len(names) <= 3:
            return "+".join(names)
        return f"{len(names)}params"

    def _describe_levels(self) -> str:
        """The vertical coordinate, empty for a 2-D selection."""
        levels = {a.level for a in self.assets if a.level is not None}
        kinds = {a.level_type for a in self.assets if a.level_type is not None}
        if not kinds:
            return ""
        if len(kinds) > 1:
            # Put number of level types
            return f"{len(kinds)}lvt"
        kind = kinds.pop()
        if len(levels) == 1:
            unit = kind.user_unit or kind.unit or ""
            value = _trim(kind.to_user(levels.pop()))
            return f"{value}{unit}" if unit != "index" else f"lv{value}"
        return f"{len(levels)}lv"

    def _describe_steps(self) -> str:
        steps = sorted(asset.step for asset in self.assets)
        first, last = format_duration(steps[0]), format_duration(steps[-1])
        return first if first == last else f"{first}-{last}"

    def __repr__(self) -> str:
        """A resolved 3-D request could hold hundreds or thousands of assets.
        This here prints a "summary" of the resolved request. Use .assets to
        list them all.
        """
        if not self.assets:
            return f"{type(self).__name__}(run={self.run}, nothing selected)"

        count = len(self.assets)
        parts = [f"run={self.run}", f"{count} asset{'s' * (count != 1)}"]

        size = self.total_size
        parts.append(human_size(size) if size is not None else "size unknown")

        names = sorted({asset.parameter for asset in self.assets})
        if len(names) <= 4:
            parts.append(", ".join(names))
        else:
            parts.append(f"{len(names)} parameters")

        kinds = {a.level_type for a in self.assets if a.level_type is not None}
        if kinds:
            levels = {a.level for a in self.assets if a.level is not None}
            on = "/".join(str(k) for k in sorted(kinds, key=lambda k: k.code))
            parts.append(f"on {on}, {len(levels)} level{'s' * (len(levels) != 1)}")

        steps = sorted({asset.step for asset in self.assets})
        first, last = format_duration(steps[0]), format_duration(steps[-1])
        if len(steps) == 1:
            parts.append(f"steps {first}")
        else:
            parts.append(f"{len(steps)} steps {first}..{last}")

        if self.missing:
            parts.append(f"{len(self.missing)} missing")

        return f"{type(self).__name__}({', '.join(parts)})"

    @property
    def total_size(self) -> int | None:
        """Bytes to download, or None if the listing did not give sizes."""
        sizes = [asset.size for asset in self.assets]
        # If any size is None, return None
        if any(size is None for size in sizes):
            return None
        # Sum over all the asset sizes
        return sum(size for size in sizes if size is not None)


def human_size(size: int) -> str:
    """Bytes as something a person can read at a glance."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _trim(value: Decimal) -> str:
    """Drop the trailing zeros a Decimal keeps: 850.00 -> 850, 0.180 -> 0.18."""
    return format(value.normalize(), "f")
