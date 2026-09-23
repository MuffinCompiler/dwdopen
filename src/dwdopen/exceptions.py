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

    Retention is short and differs per model. Counted on 2026-09-18: ICON-EU
    and ICON-D2 keep 8 runs (3-hourly, ~24 h), ICON and the ensembles 4
    (6-hourly, ~24 h), ICON-D2-RUC 24 (hourly). A missing asset is not proof of
    expiry though! Several servers sit behind opendata.dwd.de and they are not
    perfectly in sync.
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
    """Build an actionable message for an unknown model or parameter name.

    Only the offending name is quoted, so that a trailing space or an empty
    string is visible; suggestions and the list of available names are not,
    quotes only add noise there.

    All names are listed only when there are few of them: 13 models fit into a
    message, 95 parameters do not.
    """
    subject = f"unknown {kind} {name!r}"
    if context:
        subject += f" for {context}"
    parts = [subject + "."]

    # Fold the case before comparing. DWD's own documentation writes the same
    # parameter both ways, and the legacy layout used lowercase where v1 uses
    # uppercase, so a wrong-case name is a likely mistake rather than a typo.
    # Compared case-sensitively, "t_2m" scores below the cutoff against "T_2M"
    # and the caller gets no suggestion at all.
    folded = {item.casefold(): item for item in available}
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
