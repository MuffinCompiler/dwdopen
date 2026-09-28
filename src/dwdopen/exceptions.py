"""Exception hierarchy and error-message helpers."""

from __future__ import annotations

from collections.abc import Sequence
from difflib import get_close_matches

__all__ = [
    "AmbiguousSelectionError",
    "CatalogueError",
    "CatalogueUnavailableError",
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
    "resolve_name",
    "unknown_name_message",
]


class DWDOpenError(Exception):
    """Base class for every error raised by dwdopen."""


# --- catalogue / discovery -------------------------------------------------

class CatalogueError(DWDOpenError):
    """Something went wrong while reading the Open Data catalogue."""


class CatalogueUnavailableError(CatalogueError):
    """The catalogue could not be reached or parsed."""


class UnknownModelError(CatalogueError):
    """The requested model is not visible in the catalogue."""


class UnknownParameterError(CatalogueError):
    """The requested parameter is not visible for this model."""


# --- building a query ------------------------------------------------------

class SelectionError(DWDOpenError):
    """The selection is invalid, independent of availability."""


class InvalidSelectorError(SelectionError):
    """A selector value could not be interpreted."""


class AmbiguousSelectionError(SelectionError):
    """The selection matches several distinct products and must be narrowed."""


# --- resolving a query against a run ---------------------------------------

class ResolutionError(DWDOpenError):
    """A query could not be resolved into concrete assets."""


class NoMatchingRunError(ResolutionError):
    """No run in the catalogue satisfies the query."""


class IncompleteRunError(ResolutionError):
    """The run exists but does not (yet) contain everything that was requested."""


class MissingAssetError(ResolutionError):
    """A specific expected asset is absent from the catalogue."""


class RunExpiredError(ResolutionError):
    """Assets resolved earlier have since disappeared.
    Retention is short and differs per model; roughly 24 hours.
    """


# --- transport -------------------------------------------------------------

class DownloadError(DWDOpenError):
    """A download failed.
    ``status`` is the HTTP status when the server answered at all, and None for
    a timeout or a connection failure.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# --- helpers ---------------------------------------------------------------

def unknown_name_message(
    kind: str,
    name: str,
    available: Sequence[str],
    *,
    context: str | None = None,
    max_listed: int = 20,
) -> str:
    """Build a user message for an unknown model or parameter name.
    All names are listed only when there are few of them. It won't print all
    available parameters if the requested parameter does not exist.
    """
    subject = f"unknown {kind} {name!r}"
    if context:
        subject += f" for {context}"
    parts = [subject + "."]

    # Case fold the parameters before comparing.
    folded = {item.casefold(): item for item in available}
    # Look for "close" matches to help the user, for example if they made a
    # spelling error in the model or parameter.
    matches = get_close_matches(name.casefold(), list(folded), n=3, cutoff=0.6)
    close = [folded[match] for match in matches]
    if close:
        parts.append("Did you mean " + " or ".join(close) + "?")

    if len(available) <= max_listed:
        parts.append("Available: " + ", ".join(available) + ".")
    else:
        parts.append(f"{len(available)} names available.")

    return " ".join(parts)


def resolve_name(name: str, available: Sequence[str]) -> str | None:
    """Find the catalogue's own spelling of a name, ignoring case.
    Returns None when nothing matches, leaving the error to the caller.
    """
    if name in available:
        return name
    wanted = name.casefold()
    for candidate in available:
        if candidate.casefold() == wanted:
            return candidate
    return None
