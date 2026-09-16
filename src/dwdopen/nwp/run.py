"""Model run (reference time)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dwdopen.exceptions import InvalidSelectorError

__all__ = ["Run", "RunLike"]


@dataclass(frozen=True, order=True)
class Run:
    """A single model run, identified by its reference time.

    ``reference_time`` is always timezone-aware UTC. DWD's run directories
    (.../r/2026-09-14T12:00/) carry no timezone suffix and are implicitly UTC;
    attaching UTC at parse time keeps that from becoming a silent offset bug.

    A Run does not store the raw path token. Per the "never construct a path
    from assumptions" rule the catalogue keeps the mapping from a Run back to
    the exact token it saw in a listing.

    ``order=True`` because runs get sorted and compared all the time.
    """

    reference_time: datetime

    def __post_init__(self) -> None:
        if self.reference_time.tzinfo is None:
            raise InvalidSelectorError(
                f"Run.reference_time must be timezone-aware, "
                f"got {self.reference_time}"
            )

    @classmethod
    def coerce(cls, value: RunLike) -> Run:
        """Creates a run from a RunLike representation, like a datetime or
        ISO string. A datetime or a string without an offset is read as UTC.
        """
        if isinstance(value, Run):
            return value
        if isinstance(value, datetime):
            return cls(_as_utc(value))
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise InvalidSelectorError(
                    f"could not parse run {value!r} as ISO-8601"
                ) from exc
            return cls(_as_utc(parsed))
        raise InvalidSelectorError(
            f"cannot interpret {value} of type {type(value).__name__} as a run"
        )

    def __str__(self) -> str:
        return self.reference_time.isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


RunLike = Run | datetime | str
