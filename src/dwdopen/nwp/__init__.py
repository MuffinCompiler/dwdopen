"""NWP (numerical weather prediction) domain."""

from __future__ import annotations

from dwdopen.nwp.durations import hours, minutes
from dwdopen.nwp.model import Model, ParameterInfo
from dwdopen.nwp.query import Query
from dwdopen.nwp.request import Asset, DownloadResult, MissingStep, ResolvedRequest
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import Between, Every, LevelType

__all__ = [
    "Asset",
    "Between",
    "DownloadResult",
    "Every",
    "LevelType",
    "MissingStep",
    "Model",
    "ParameterInfo",
    "Query",
    "ResolvedRequest",
    "Run",
    "RunLike",
    "hours",
    "minutes",
]
