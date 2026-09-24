"""Forecast steps as durations.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import timedelta
from typing import overload

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.selectors import Between, Every, StepScalar, StepSelector

__all__ = [
    "check_step_selector",
    "format_duration",
    "hours",
    "minutes",
    "parse_duration",
]

# Regex to parse XXhXXm and the way DWD writes their files "PT006H00M"
# Using this regex, the matched groups are (hours, minutes).
_DURATION = re.compile(r"(?:PT)?(?:(\d+)H)?(?:(\d+)M)?", re.IGNORECASE)


def parse_duration(value: StepScalar) -> timedelta:
    """Parse a forecast step as duration."""
    if isinstance(value, timedelta):
        return value

    if not isinstance(value, str):
        # Unreachable per StepScalar, which is exactly why it is here: an
        # annotation does not stop anyone passing steps=[0, 6, 12] at runtime.
        raise InvalidSelectorError(_not_a_step(value))

    # String match
    match = _DURATION.fullmatch(value.strip())
    if match is None or not any(match.groups()):
        raise InvalidSelectorError(
            f"cannot read {value!r} as a forecast step. Expected something like "
            "'6h', '15m', '1h30m' or 'PT006H00M'"
        )
    hours, minutes = match.groups()
    return timedelta(hours=int(hours or 0), minutes=int(minutes or 0))


def _not_a_step(value: object) -> str:
    """Explain why a value cannot be a forecast step.
    """
    if isinstance(value, int | float):
        # Number is missing a unit
        return (
            f"a forecast step needs its unit, got {value!r}. Write "
            f"'{value:g}h' for hours or '{value:g}m' for minutes, or wrap a "
            f"list of numbers: steps=hours(0, 6, 12)"
        )
    # General error for parsing
    return (
        f"cannot read {value!r} of type {type(value).__name__} as a forecast "
        f"step. Expected a string like '6h', or a timedelta"
    )


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


def check_step_selector(selector: StepSelector | None) -> None:
    """Parse every step a selector resolves to, to check the validity
    of the selection. Just checks the parsing, not the availability of
    the data.
    Calls parse_duration() to check validity of every item in the selection.
    """
    if selector is None or selector == "all":
        return
    if isinstance(selector, Between):
        for bound in (selector.start, selector.stop):
            if bound is not None:
                parse_duration(bound)
    elif isinstance(selector, Every):
        for bound in (selector.start, selector.stop, selector.every):
            parse_duration(bound)
    elif isinstance(selector, str | timedelta | int | float):
        parse_duration(selector)
    else:
        for item in selector:
            parse_duration(item)


@overload
def hours(value: float, /) -> timedelta: ...
@overload
def hours(values: Iterable[float], /) -> tuple[timedelta, ...]: ...
@overload
def hours(first: float, second: float, /, *rest: float) -> tuple[timedelta, ...]: ...


def hours(*values: float | Iterable[float]) -> timedelta | tuple[timedelta, ...]:
    """Forecast steps from plain numbers of hours.

        steps=hours(0, 6, 12, 18)
        steps=hours(range(0, 25, 3))
        steps=hours([0, 6, 12, 18])
        steps=Every(hours(0), hours(48), hours(3))

    Fractions are parsed too: hours(1.5) is an hour and a half.
    """
    return _durations("hours", values)


@overload
def minutes(value: float, /) -> timedelta: ...
@overload
def minutes(values: Iterable[float], /) -> tuple[timedelta, ...]: ...
@overload
def minutes(first: float, second: float, /, *rest: float) -> tuple[timedelta, ...]: ...


def minutes(*values: float | Iterable[float]) -> timedelta | tuple[timedelta, ...]:
    """Forecast steps from plain numbers of minutes.
    Especially of use for the sub-hourly models: ICON-D2 publishes every 15 minutes and
    ICON-D2-RUC every 5.

        steps=minutes(range(0, 60, 15))
    """
    return _durations("minutes", values)


def _durations(
    unit: str, values: tuple[float | Iterable[float], ...]
) -> timedelta | tuple[timedelta, ...]:
    if not values:
        raise InvalidSelectorError(f"{unit}() needs at least one value")

    # A single iterable argument is a sequence of steps; anything else is a
    # series of scalars. Only the single-scalar case returns a duration.
    first = values[0]
    if len(values) == 1 and isinstance(first, Iterable):
        return tuple(_one(unit, value) for value in first)
    if len(values) == 1:
        return _one(unit, first)
    return tuple(_one(unit, value) for value in values)


def _one(unit: str, value: object) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidSelectorError(
            f"{unit}() takes numbers, got {value!r} of type "
            f"{type(value).__name__}"
        )
    if value < 0:
        raise InvalidSelectorError(
            f"a forecast step cannot be negative, got {unit}({value:g})"
        )
    return timedelta(**{unit: value})
