"""Turning a server path into a local file name.
The name is derived from the asset's key/token pairs, so it is deterministic.
"""

from __future__ import annotations

import os
import secrets

from dwdopen._fileserver.paths import Segment

__all__ = ["local_name", "temp_name"]

_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)
"""Allowed characters for file names. Characters that both Linux and Windows
accept and also removed some weird chars that might be awkward in shells.
(In practice, this is mainly about the ':' character on Windows)
"""


def local_name(keys: tuple[Segment, ...]) -> str:
    """Build the file name for one asset from its path keys.

    m/icon-eu, p/T_2M, r/2026-09-18T09:00, s/PT006H00M.grib2 becomes
    ``m-icon-eu_p-T_2M_r-2026-09-18T09%3A00_s-PT006H00M.grib2``.
    """
    return "_".join(f"{key}-{_escape(token)}" for key, token in keys)


def temp_name(final: str) -> str:
    """Build a partial-download name that no other writer will pick.
    The temporary name carries the process id and a random token, so
    multiple download processes won't interfere.
    """
    return f"{final}.{os.getpid()}.{secrets.token_hex(4)}.part"


def _escape(token: str) -> str:
    return "".join(c if c in _SAFE else f"%{ord(c):02X}" for c in token)
