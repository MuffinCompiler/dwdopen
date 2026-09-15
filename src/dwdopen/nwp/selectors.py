from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Final, Literal, Self

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

type StepScalar = str | timedelta
"""``"5m"``, ``"1h30m"``, ``"PT1H30M"`` or a ``timedelta``.
A forecast step is a duration. DWD writes them as ``PT###H##M``
so support these too.
"""

type LevelScalar = int | float | Decimal
"""A level value as the user supplies it, in user-facing units.
Pressure is given in hPa and converted to the Pa values DWD uses in the path.
"""


@dataclass(frozen=True, slots=True, order=True)
class LevelType:
    """A GRIB ``typeOfFirstFixedSurface`` value, with a readable name if available.

    The ``code`` is literally the ``lvt1`` path segment in the open data API. The
    alias is convenience only: GRIB2 table 4.5 reserves 192-254 for local
    definitions and DWD uses that range, so there are codes with no standard name at all.
    We do not want to have hardcoded level types to be more future-proof.
    """

    code: int
    alias: str | None = None
    unit: str | None = None
    """Unit of the ``lv1`` value in the path."""
    user_unit: str | None = None
    """Unit the user supplies levels in, when it differs from ``unit``."""

    @classmethod
    def of(cls, code: int) -> Self:
        return KNOWN_LEVEL_TYPES.get(code) or cls(code=code)

    def __str__(self) -> str:
        return f"{self.alias} ({self.code})" if self.alias else f"lvt1={self.code}"

# Define some user facing aliases of known level types.
KNOWN_LEVEL_TYPES: Final[Mapping[int, LevelType]] = {
    lt.code: lt
    for lt in (
        LevelType(code=100, alias="pressure", unit="Pa", user_unit="hPa"),
        LevelType(code=150, alias="model", unit="index"),
        LevelType(code=106, alias="soil", unit="m"),
    )
}

@dataclass(frozen=True, slots=True)
class Between[T]:
    start: T | None = None
    stop: T | None = None

@dataclass(frozen=True, slots=True)
class Every[T]:
    start: T
    stop: T
    every: T

type StepSelector = (
    Literal["all"] | StepScalar | Sequence[StepScalar]
    | Between[StepScalar] | Every[StepScalar]
)
type LevelSelector = (
    Literal["all"] | LevelScalar | Sequence[LevelScalar]
    | Between[LevelScalar] | Every[LevelScalar]
)


type MemberSelector = Literal["all"] | int | Sequence[int] | Between | Every

type SelectorValue = (
    str | int | float | Decimal | Sequence[str | int | float | Decimal] | Between | Every
)
"""Value type for the ``**selectors`` escape hatch, see model.select()"""