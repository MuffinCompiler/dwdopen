from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dwdopen.exceptions import InvalidSelectorError

__all__ = ["Run", "RunLike"]


@dataclass(frozen=True, slots=True, order=True)
class Run:
    """A single model run, identified by its reference time.
    ``reference_time`` is always UTC. DWD's run directories carry no timezone
    suffix and are implicitly assumed to be UTC.
    """

    reference_time: datetime

    def __post_init__(self) -> None:
        """Make sure time zone is set."""
        if self.reference_time.tzinfo is None:
            raise InvalidSelectorError(
                f"Run.reference_time must be timezone-aware, "
                f"got {self.reference_time!r}"
            )

    @classmethod
    def coerce(cls, value: RunLike) -> Run:
        """Accept a ``Run``, a ``datetime`` or an ISO-8601 string.
        """
        match value:
            case Run():
                return value
            case datetime():
                return cls(cls._as_utc(value))
            case str():
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise InvalidSelectorError(
                        f"could not parse run {value!r} as ISO-8601"
                    ) from exc
                return cls(cls._as_utc(parsed))
            case _:
                raise InvalidSelectorError(f"cannot interpret {value!r} as a run")

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def __str__(self) -> str:
        return self.reference_time.isoformat()


type RunLike = Run | datetime | str