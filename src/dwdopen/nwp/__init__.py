"""NWP (numerical weather prediction) domain."""

from __future__ import annotations

from dwdopen.nwp.durations import hours, minutes
from dwdopen.nwp.model import Model, ParameterInfo
from dwdopen.nwp.query import Query
from dwdopen.nwp.run import Run, RunLike
from dwdopen.nwp.selectors import Between, Every, LevelType

__all__ = [
    "Between",
    "Every",
    "LevelType",
    "Model",
    "ParameterInfo",
    "Query",
    "Run",
    "RunLike",
    "hours",
    "minutes",
]
