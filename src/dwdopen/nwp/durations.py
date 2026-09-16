"""Forecast steps as durations.
"""

from __future__ import annotations

import re
from datetime import timedelta

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.selectors import StepScalar

__all__ = ["format_duration", "parse_duration"]

# Regex to parse XXhXXm and the way DWD writes their files "PT006H00M"
# Using this regex, the matched groups are (hours, minutes).
_DURATION = re.compile(r"(?:PT)?(?:(\d+)H)?(?:(\d+)M)?", re.IGNORECASE)


def parse_duration(value: StepScalar) -> timedelta:
    """Parse a forecast step as duration."""
    if isinstance(value, timedelta):
        return value

    # String match
    match = _DURATION.fullmatch(value.strip())
    if match is None or not any(match.groups()):
        raise InvalidSelectorError(
            f"cannot read {value!r} as a forecast step. Expected something like "
            "'6h', '15m', '1h30m' or 'PT006H00M'"
        )
    hours, minutes = match.groups()
    return timedelta(hours=int(hours or 0), minutes=int(minutes or 0))


def format_duration(value: timedelta) -> str:
    """Render a forecast step as timedelta user facing, as XXhXXm.
    """
    total_minutes = int(value.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h{minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{hours}h"
