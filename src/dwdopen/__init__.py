"""Python access to DWD Open Data."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

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
from dwdopen.nwp.request import DownloadResult
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
    "DownloadResult",
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

try:
    __version__ = version("dwdopen")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0.dev0"
