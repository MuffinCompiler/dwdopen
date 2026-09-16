"""Selector value types and level-type semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Final, Generic, Literal, TypeVar

__all__ = [
    "KNOWN_LEVEL_TYPES",
    "Between",
    "Every",
    "LevelScalar",
    "LevelSelector",
    "LevelType",
    "MemberSelector",
    "SelectorValue",
    "StepScalar",
    "StepSelector",
]

StepScalar = str | timedelta
"""A forecast step as a duration: "5m", "1h30m", "PT1H30M" or a timedelta.

Never an integer hour. DWD writes steps as PT###H##M so support these too.
"""

LevelScalar = int | float | Decimal
"""A level value in user-facing units.

Pressure is given in hPa and converted to the Pa values DWD uses in the path.
"""


@dataclass(frozen=True)
class LevelType:
    """A GRIB typeOfFirstFixedSurface value, with a readable name if known.

    ``code`` is literally the lvt1 path segment. The alias is convenience only:
    GRIB2 table 4.5 reserves 192-254 for local definitions and DWD uses that
    range (ASOB_S_OS is documented as 208), so some codes have no standard name
    at all.
    """

    code: int
    alias: str | None = None
    unit: str | None = None
    user_unit: str | None = None

    @classmethod
    def of(cls, code: int) -> LevelType:
        """Look up a code. An unknown code yields an unnamed LevelType."""
        known = KNOWN_LEVEL_TYPES.get(code)
        if known is not None:
            return known
        return cls(code=code)

    def __str__(self) -> str:
        if self.alias:
            return f"{self.alias} ({self.code})"
        return f"lvt1={self.code}"


KNOWN_LEVEL_TYPES: Final[Mapping[int, LevelType]] = {
    lt.code: lt
    for lt in (
        LevelType(code=100, alias="pressure", unit="Pa", user_unit="hPa"),
        LevelType(code=150, alias="model", unit="index"),
        LevelType(code=106, alias="soil", unit="m"),
    )
}
"""Some known level types that actually occur in v1 paths.
It may be extended freely; unknown codes keep working via LevelType.of.
"""


T = TypeVar("T")


@dataclass(frozen=True)
class Between(Generic[T]):
    """Every value the catalogue offers inside a closed interval.

    Both bounds are inclusive, None is open-ended on that side, and Between()
    without bounds means everything available. Basically an "inclusive slice".

    Generic so that a range over steps cannot be mixed up with a range over
    levels. Between[StepScalar]("0h", 850) is a type error.
    """

    start: T | None = None
    stop: T | None = None


@dataclass(frozen=True)
class Every(Generic[T]):
    """An exact cadence with an inclusive end.
    Every("0h", "48h", "3h") means exactly 0h, 3h, ..., 48h. If one of those is
    missing the request is incomplete.
    """

    start: T
    stop: T
    every: T


StepSelector = (
    Literal["all"]
    | StepScalar
    | Sequence[StepScalar]
    | Between[StepScalar]
    | Every[StepScalar]
)
"""A scalar means exactly that one step; use Every for a cadence.
"all" is a reserved word and is never interpreted as a duration.
"""

LevelSelector = (
    Literal["all"]
    | LevelScalar
    | Sequence[LevelScalar]
    | Between[LevelScalar]
    | Every[LevelScalar]
)

MemberSelector = Literal["all"] | int | Sequence[int] | Between[int] | Every[int]
"""Members are plain integers."""

SelectorValue = (
    str
    | int
    | float
    | Decimal
    | Sequence[str | int | float | Decimal]
    | Between[object]
    | Every[object]
)
"""Value types for the **selectors escape hatch, see Model.select."""
