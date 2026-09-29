"""Python access to DWD Open Data."""

from __future__ import annotations

import logging
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
from dwdopen.nwp.durations import hours, minutes
from dwdopen.nwp.model import Model, ParameterInfo
from dwdopen.nwp.request import DownloadResult
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import Between, Every, LevelType

_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
)


def set_log_level(level: int | None = logging.INFO) -> None:
    """Sets the log level to use when printing logs.
    Set to None to disable logging.
    """
    logger = logging.getLogger("dwdopen")

    if level is None:
        logger.removeHandler(_handler)
        logger.setLevel(logging.NOTSET)
        return

    # Add the handler to the dwdopen logger only.
    if _handler not in logger.handlers:
        logger.addHandler(_handler)

    logger.setLevel(level)

# Setup default logging.
set_log_level()


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
    "set_log_level",
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
    "hours",
    "minutes",
]

try:
    __version__ = version("dwdopen")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0.dev0"
