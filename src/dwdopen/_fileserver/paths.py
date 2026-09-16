"""Building URL paths for accessing the server from ordered key/token pairs."""

from __future__ import annotations

__all__ = ["Segment", "build_path"]

Segment = tuple[str, str]
"""One path key and its token value, e.g. ("lvt1", "100")."""

V1_ROOT = "weather/nwp/v1"


def build_path(
    *segments: Segment,
    key: str | None = None,
    directory: bool = True,
) -> str:
    """Join key/value pairs into a path below the v1 root.
    Each key value pair describes one file attribute, for example the model,
    level type, ensemble member and so on.
    Adding a key without a token value returns a directory listing all possible
    values for that key: build_path(("m", "icon-eu"), ("p", "T"),
    key="lvt1") gives the directory whose entries are the available level type codes.

    The builder does not know or check the order of the keys. DWD's order is
    m, p, [wvl1], [lvt1, lv1], r, [e], s, where [] keys are optional, for example
    wvl1 is the wavelength for ICON ART, lvt1/lv1 is the level type and level value
    for 3-D grids (absent for 2-D), and e is the ensemble member for ensemble forecasts.

    Directories get a trailing slash because nginx answers 301 without one.
    """
    parts = [V1_ROOT]
    for segment_key, token in segments:
        parts.append(segment_key)
        parts.append(token)
    if key is not None:
        parts.append(key)
    path = "/".join(parts)
    return f"{path}/" if directory else path
