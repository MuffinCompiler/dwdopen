from collections.abc import Sequence
from difflib import get_close_matches


def unknown_name_message(
    kind: str, name: str, available: Sequence[str]
) -> str:
    """Build an actionable message for an unknown name, printing available names.
    Lists available candidates.
    Use ``get_close_matches`` to find possible typos in name resolution to show.
    """
    parts = [f"unknown {kind} {name!r}."]
    if close := get_close_matches(name, available, n=3, cutoff=0.6):
        parts.append("Did you mean " + " or ".join(repr(c) for c in close) + "?")
    parts.append("Available: " + ", ".join(available) + ".")
    return " ".join(parts)