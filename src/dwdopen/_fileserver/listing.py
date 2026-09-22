"""Parsing of nginx directory listings.

This is the only module in the package that looks at the raw HTML
returned by the OpenData DWD server.
To the abstract layers, only ListingEntries are exposed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote

__all__ = ["ListingEntry", "parse_listing"]


@dataclass(frozen=True)
class ListingEntry:
    """One row of a directory listing.
    """

    name: str
    """The URL-decoded path."""

    is_dir: bool

    modified: datetime | None = None
    """In UTC. Used to see if files have settled. Might be not available."""

    size: int | None = None
    """Bytes. None for directories."""


# opendata.dwd.de serves nginx autoindex: one entry per line inside a single
# <pre>:
#
#   <a href="2026-09-15T06%3A00/">2026-09-15T06:00/</a>   15-Sep-2026 08:42:25   -
#   <a href="PT000H00M.grib2">PT000H00M.grib2</a>         16-Sep-2026 02:40:29   877797
#
# The href name should be parsed, as the displayed name might be truncated.
# Date and size are optional in this pattern. Thanks to Claude for the regex :)
_ENTRY = re.compile(
    r'<a\s+href="(?P<href>[^"]*)"[^>]*>.*?</a>'
    r"(?:\s+(?P<date>\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2})"
    r"\s+(?P<size>-|\d+))?",
    re.IGNORECASE,
)

# Define months, can't parse them from strptime as that one is locale based.
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_listing(html: str) -> list[ListingEntry]:
    """Parse one nginx autoindex page.

    The parent link is skipped; every other entry is a child of the listed
    directory.
    An unreadable page yields an empty list. The caller should know which
    directories have children. An empty page might be as valid, if there are
    no files yet for the chosen run.
    """
    entries: list[ListingEntry] = []
    # Iterate through regex occurrences; each match is a file or folder.
    for match in _ENTRY.finditer(html):
        href = match.group("href")
        if href == "../":
            continue

        size = match.group("size")
        entries.append(
            ListingEntry(
                name=unquote(href.rstrip("/")),
                is_dir=href.endswith("/"),
                modified=_parse_date(match.group("date")),
                size=None if size in (None, "-") else int(size), # None for directories
            )
        )
    return entries


def _parse_date(value: str | None) -> datetime | None:
    """Parse a listing date, given for example by "16-Sep-2026 02:40:29" as UTC.

    We assume the timestamps are always UTC and not locale dependent.
    Returns None if parsing fails.
    """
    if value is None:
        return None
    day, month, rest = value.split("-", 2)
    year, clock = rest.split(maxsplit=1)
    hour, minute, second = clock.split(":")
    try:
        return datetime(
            int(year), _MONTHS[month.lower()], int(day),
            int(hour), int(minute), int(second), tzinfo=UTC,
        )
    except (KeyError, ValueError):
        return None
