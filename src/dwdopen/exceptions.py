from __future__ import annotations
from collections.abc import Sequence
from difflib import get_close_matches

__all__ = [
    "AmbiguousSelectionError",
    "CatalogueError",
    "DWDOpenError",
    "DownloadError",
    "IncompleteRunError",
    "InvalidSelectorError",
    "MissingAssetError",
    "NoMatchingRunError",
    "ResolutionError",
    "RunExpiredError",
    "SelectionError",
    "UnknownModelError",
    "UnknownParameterError",
    "unknown_name_message",
]


class DWDOpenError(Exception):
    """Base class for every error raised by dwdopen."""


class CatalogueError(DWDOpenError):
    """Something went wrong while reading the Open Data catalogue."""


class UnknownModelError(CatalogueError):
    """The requested model is not visible in the catalogue."""


class UnknownParameterError(CatalogueError):
    """The requested parameter is not visible for this model."""


class SelectionError(DWDOpenError):
    """The selection is invalid."""


class InvalidSelectorError(DWDOpenError):
    """..."""


class AmbiguousSelectionError(SelectionError):
    """The selection is ambiguous (e.g., several level types possible)."""


class ResolutionError(DWDOpenError):
    """A query could not be resolved."""


class NoMatchingRunError(ResolutionError):
    """No run in the catalogue satisfies the query."""


class IncompleteRunError(ResolutionError):
    """The run exists but does not (yet) contain everything that was requested."""


class MissingAssetError(ResolutionError):
    """A specific expected asset is absent from the catalogue."""


class RunExpiredError(ResolutionError):
    """Assets resolved earlier have since disappeared."""


class DownloadError(DWDOpenError):
    """A download failed."""


# helpers

def unknown_name_message(
        kind: str,
        name: str,
        available: Sequence[str],
        *,
        context: str | None = None,
        max_listed: int = 20,
) -> str:
    """Build an actionable message for an unknown model or parameter name.

    Args:
        kind: what was not found, e.g. model.
        name: the name that was asked for.
        available: the names that do exist.
        context: optional qualifier
        max_listed: list only that many avail entries.
    """
    subject = f"unknown {kind} {name!r}"
    if context:
        subject += f" for {context}"
    parts = [subject + "."]
    if close := get_close_matches(name, available, n=3, cutoff=0.6):
        parts.append("Did you mean " + " or ".join(repr(c) for c in close) + "?")
    if len(available) <= max_listed:
        parts.append("Available: " + ", ".join(available) + ".")
    else:
        parts.append(f"{len(available)} names available.")
    return " ".join(parts)
