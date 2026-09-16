"""Python access to DWD Open Data."""

from __future__ import annotations

from dwdopen.client import DWD, NWP
from dwdopen.exceptions import (
    AmbiguousSelectionError,
    CatalogueError,
    CatalogueUnavailableError,
    DownloadError,
    DWDOpenError,
    IncompleteRunError,
    InvalidSelectorError,
    MissingAssetError,
    NoMatchingRunError,
    ResolutionError,
    RunExpiredError,
    SelectionError,
    UnknownModelError,
    UnknownParameterError,
)
from dwdopen.nwp.model import Model, ParameterInfo
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import Between, Every, LevelType

__all__ = [
    "DWD",
    "NWP",
    "AmbiguousSelectionError",
    "Between",
    "CatalogueError",
    "CatalogueUnavailableError",
    "DWDOpenError",
    "DownloadError",
    "Every",
    "IncompleteRunError",
    "InvalidSelectorError",
    "LevelType",
    "MissingAssetError",
    "Model",
    "NoMatchingRunError",
    "ParameterInfo",
    "ResolutionError",
    "Run",
    "RunExpiredError",
    "SelectionError",
    "UnknownModelError",
    "UnknownParameterError",
]

__version__ = "0.1.0.dev0"
