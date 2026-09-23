"""Selector value types and level-type semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Final, Generic, Literal, TypeVar

from dwdopen.exceptions import InvalidSelectorError

__all__ = [
    "KNOWN_LEVEL_TYPES",
    "Between",
    "Every",
    "LevelScalar",
    "LevelSelector",
    "LevelType",
    "LevelTypeLike",
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

    scale: Decimal = Decimal(1)
    """How many ``unit`` make one ``user_unit``.
    Pressure is the only case so far: user facing is hPa, DWD writes Pa, so the
    scale is 100 and 850 becomes the 85000 in the path. Model levels are bare
    indices and soil levels are already metres, so both stay at 1.
    """

    @classmethod
    def of(cls, code: int) -> LevelType:
        """Look up a code. An unknown code yields an unnamed LevelType."""
        known = KNOWN_LEVEL_TYPES.get(code)
        if known is not None:
            return known
        return cls(code=code)

    @classmethod
    def coerce(cls, value: LevelTypeLike) -> LevelType:
        """Accept a code, an alias such as "pressure", or a LevelType."""
        if isinstance(value, LevelType):
            return value
        if isinstance(value, int):
            return cls.of(value)
        for known in KNOWN_LEVEL_TYPES.values():
            if known.alias == value:
                return known
        raise InvalidSelectorError(
            f"unknown level type {value!r}. Use a GRIB code such as 100, or one "
            f"of: " + ", ".join(
                sorted(k.alias for k in KNOWN_LEVEL_TYPES.values() if k.alias)
            )
        )

    def to_server(self, value: LevelScalar) -> Decimal:
        """Convert a user-facing level value into what DWD writes in the path.

        Decimal throughout, and built from str(), because soil levels are
        fractions of a metre (0.005, 0.18).
        """
        return Decimal(str(value)) * self.scale

    def to_user(self, value: Decimal) -> Decimal:
        """The inverse of to_server, for error messages and repr."""
        return value / self.scale

    def __str__(self) -> str:
        if self.alias:
            return f"{self.alias} ({self.code})"
        return f"lvt1={self.code}"


KNOWN_LEVEL_TYPES: Final[Mapping[int, LevelType]] = {
    lt.code: lt
    for lt in (
        LevelType(
            code=100, alias="pressure", unit="Pa", user_unit="hPa",
            scale=Decimal(100),
        ),
        LevelType(code=150, alias="model", unit="index"),
        LevelType(code=106, alias="soil", unit="m"),
    )
}
"""Some known level types that actually occur in v1 paths.
It may be extended freely; unknown codes keep working via LevelType.of.
"""

LevelTypeLike = LevelType | int | str
"""A level type given as the object, its GRIB code (100) or its alias
("pressure"). The code is what ends up in the path."""


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
