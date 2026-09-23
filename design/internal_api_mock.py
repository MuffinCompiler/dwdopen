"""design sketch only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence


# Entry point

class DWD:
    @property
    def nwp(self) -> "NWP":
        ...

# Have NWP as a "submodule" so we can add observation data later too

class NWP:
    def models(self) -> list[str]:
        """Returns model names available in the catalogue. Should be parsed from content.log"""
        ...

    def model(self, name: str) -> "Model":
        """Returns the specific model."""
        ...


# Discover a model

class Model:
    name: str

    def parameters(self) -> list[str]:
        """Return parameter names available for this model. -> from cached catalogue"""
        ...

    def runs(self) -> list["Run"]:
        """Return currently available runs. Might also be incomplete!"""
        ...

    def latest_run(self) -> "Run":
        """
        Return the newest run visible for the model.
        This then would also NOT imply that any selection to request is already completely available!
        """
        ...

    def parameter(self, name: str) -> "ParameterInfo":
        ...


    def select(
        self,
        *,
        parameters: str | Sequence[str],
        run: "RunLike | None" = None,
        steps: "StepSelector | None" = None,
        level_type: str | None = None, # can be optional if clear from data. But that would mean that theoretically at some point data download that always worked wouldnt if request becomes ambigiuous.. TODO
        levels: "LevelSelector | None" = None, # see above
        members: "MemberSelector | None" = None, # see above
        **selectors: Any,
    ) -> "Query":
        """
        Build a query. Basically defines what to request.
        Query doesnt yet check availability, as a query can then be exectued for a chosen run where
        the resolution happens.

        level_type, levels, members etc only constrain relevant dimensions.
        e.g., If a parameter exists with multiple vertical coordinate types and the
        selection is ambiguous, resolution should fail with a helpful error.
        Building a query doesnt do the resolution yet though.
        """
        ...


class ParameterInfo:
    name: str

    def describe(self) -> dict[str, Any]:
        """
        Return catalogue metadata
        """
        ...


@dataclass(frozen=True)
class Run:
    reference_time: datetime

    def __str__(self) -> str:
        return self.reference_time.isoformat()


RunLike = Run | datetime | str
CombineMode = Literal["none", "all", "parameter", "member"]


class Query:
    def __or__(self, other: "Query") -> "Query":
        """So we can combine multiple queries; e.g. model_level_query | pressure_level_query into one query."""
        ...

    def latest_run(
        self,
        require: Literal["complete", "partial"] = "complete",
    ) -> "Run":
        """
        Find the newest run satisfying this query.
        complete means all explicitly requested values must be resolvable (i.e.,
        all requested data must be available in the catalogue).
        """
        ...

    def resolve(
        self,
        run: "RunLike | None" = None,
        require: Literal["complete", "partial"] = "complete",
    ) -> "ResolvedRequest":
        """
        Resolve the semantic query for a provided run against the current catalogue.
        The result "freezes" the returned assets to be downloaded.
        """
        ...

    def download(
        self,
        destination: str | Path,
        run: "RunLike | None" = None,
        require: Literal["complete", "partial"] = "complete",
        combine: "CombineMode" = "all",
    ) -> "DownloadResult":
        """
        Does resolve(...).download(...)
        Combine mode whether to combine everything in one grib message, no combination,
        or maybe like by member etc.
        """
        ...


# Ready to be downloaded request, already resolved all the files.
@dataclass(frozen=True)
class ResolvedRequest:
    run: "Run"
    assets: tuple["Asset", ...]
    catalogue_time: datetime
    missing: tuple["MissingSelection", ...]

    def download(
        self,
        destination: str | Path,
        combine: "CombineMode" = "all",
    ) -> "DownloadResult":
        ...


# Selector ideas


# ---------------------------------------------------------------------------
# Selector types
# ---------------------------------------------------------------------------

StepScalar = str | timedelta # str can be 6h or 5min...
StepSelector = (
    Literal["all"]
    | StepScalar # like 6h; get full data range but only every 6h
    | slice # python slice, like just get all the data avail in the given (begin,end)
    | tuple[StepScalar, StepScalar, StepScalar] # (0h, 24h, 15min) every 15mins from +0..+24
)

# maybe levels need to be float for pressure level values, half levels??
LevelScalar = int | float
LevelSelector = (
    Literal["all"]
    | LevelScalar
    | Sequence[LevelScalar]
    | slice # all levels in (begin,end) -> could be ascending and descending?
)

MemberSelector = (
    Literal["all"]
    | int
    | Sequence[int]
    | slice
)


# One entity, one grib file to download. contains URL and metadata.
@dataclass(frozen=True)
class Asset:
    parameter: str
    url: str
    run: datetime | None = None
    step: timedelta | None = None
    level_type: str | None = None
    level: int | float | None = None
    member: int | None = None
    selectors: dict[str, Any] | None = None
    size: int | None = None  # is size known, is this in the catalogue? Would be nice to tell the user before download


@dataclass(frozen=True)
class MissingSelection: # smth missing
    reason: str
    details: dict[str, Any]


@dataclass(frozen=True)
class DownloadResult:
    files: tuple[Path, ...] # download paths for all messages
    run: Run
    assets_downloaded: int


# TODO
#  Where and how to cache content.log? Internal representation? Mark as outdated at some point?

