"""Fetching assets over HTTP, in parallel, onto disk."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.naming import local_name, temp_name
from dwdopen.exceptions import DownloadError
from dwdopen.nwp.request import Asset, CombineMode, Fetched, human_size
from dwdopen.nwp.selectors import LevelType

__all__ = ["HttpDownloader"]

logger = logging.getLogger("dwdopen")

LARGE_DOWNLOAD = 2 * 1024**3
"""Log when a user plans to download large amounts of data already in the
planning stage.
"""

RETRY_STATUS = frozenset({404, 408, 425, 429, 500, 502, 503, 504})
"""HTTP error statuses worth a retry. 404 is handled separately."""


class HttpDownloader:
    """Fetches assets concurrently and writes them atomically.
    Takes an HttpClient so transport configuration stays in one place.
    """

    def __init__(
        self,
        http: HttpClient,
        *,
        max_workers: int = 16,
        max_attempts: int = 4,
        backoff: float = 0.5
    ) -> None:
        """
        max_workers
            Concurrent downloads. Bounded by the client's connection pool.
        max_attempts
            Attempts per asset for a failure.
        backoff
            Seconds before the second attempt; doubles each further attempt.
        """
        self._http = http
        self._max_workers = max_workers
        self._max_attempts = max_attempts
        self._backoff = backoff

    def fetch(
        self,
        assets: Sequence[Asset],
        destination: Path,
        *,
        combine: CombineMode = "all",
        temp_dir: Path | None = None,
    ) -> Fetched:
        destination = Path(destination)
        if not assets:
            logger.info("nothing to download")
            return Fetched(files=(), bytes_downloaded=0)

        self._announce(assets, destination, combine)
        if combine == "none":
            fetched = self._fetch_separately(assets, destination, temp_dir)
        else:
            fetched = self._fetch_combined(assets, destination, temp_dir)
        self._report(fetched, combine)
        return fetched

    # --- layouts ----------------------------------------------------------

    def _fetch_separately(
        self, assets: Sequence[Asset], destination: Path, temp_dir: Path | None
    ) -> Fetched:
        """One file per asset, named after its keys, inside one directory."""
        destination.mkdir(parents=True, exist_ok=True)
        staging = temp_dir or destination

        targets = [destination / local_name(asset.keys) for asset in assets]
        sizes = self._fetch_all(assets, targets, staging)
        return Fetched(files=tuple(targets), bytes_downloaded=sum(sizes))

    def _fetch_combined(
        self, assets: Sequence[Asset], destination: Path, temp_dir: Path | None
    ) -> Fetched:
        """Every message concatenated into one GRIB2 file.
        GRIB2 messages are self-delimiting, each carrying its own length and
        terminator, so joining the bytes of several files is a valid file.
        The parts are downloaded into a directory private to this call, and the
        concatenation reads that directory's files by the list it was given.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = self._private_directory(temp_dir or destination.parent)
        try:
            parts = [staging / f"{index:08d}.part" for index in range(len(assets))]
            sizes = self._fetch_all(assets, parts, staging)

            merged = staging / "merged"
            with merged.open("wb") as out:
                for part in parts:
                    with part.open("rb") as chunk:
                        shutil.copyfileobj(chunk, out)
            os.replace(merged, destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return Fetched(files=(destination,), bytes_downloaded=sum(sizes))

    # --- transfer ---------------------------------------------------------

    def _fetch_all(
        self, assets: Sequence[Asset], targets: Sequence[Path], staging: Path
    ) -> list[int]:
        """Fetch every asset into its target, in parallel."""
        workers = max(1, min(self._max_workers, len(assets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(
                pool.map(
                    lambda pair: self._fetch_one(pair[0], pair[1], staging),
                    zip(assets, targets, strict=True),
                )
            )

    def _fetch_one(self, asset: Asset, target: Path, staging: Path) -> int:
        """Fetch one asset, write it beside its target, then rename it on."""
        payload = self._get_with_retries(asset)
        partial = staging / temp_name(target.name)
        partial.write_bytes(payload)
        os.replace(partial, target)
        logger.debug("wrote %s (%d bytes)", target, len(payload))
        return len(payload)

    def _get_with_retries(self, asset: Asset) -> bytes:
        """Fetch one path, retrying failures with exponential backoff."""
        attempt = 1
        while True:
            try:
                return self._http.get_asset(asset.path)
            except DownloadError as exc:
                # Get limit of retries for the error code.
                limit = 1
                if exc.status is None or exc.status in RETRY_STATUS:
                    limit = self._max_attempts
                if attempt >= limit:
                    raise
                delay = self._backoff * 2 ** (attempt - 1)
                logger.warning(
                    "attempt %d/%d for %s failed (%s), retrying in %.1fs",
                    attempt, limit, asset.path, exc, delay,
                )
                time.sleep(delay)
                attempt += 1

    # --- helpers ----------------------------------------------------------

    def _private_directory(self, parent: Path) -> Path:
        """A staging directory private to this process."""
        parent.mkdir(parents=True, exist_ok=True)
        staging = parent / f".dwdopen-{temp_name('merge')}-{secrets.token_hex(4)}"
        staging.mkdir()
        return staging

    def _announce(
        self, assets: Sequence[Asset], destination: Path, combine: CombineMode
    ) -> None:
        """Announcing the download before it starts (e.g. inform user about size)."""
        known = [asset.size for asset in assets if asset.size is not None]
        total = sum(known) if len(known) == len(assets) else None
        size = "unknown size" if total is None else human_size(total)
        message = "downloading %d assets (%s) to %s, combine=%s"
        args = (len(assets), size, destination, combine)
        if total is not None and total >= LARGE_DOWNLOAD:
            logger.info(message + " - this is a large request.", *args)
        else:
            logger.info(message, *args)

        if combine == "all":
            self._warn_about_mixed_level_types(assets)

    @staticmethod
    def _report(fetched: Fetched, combine: CombineMode) -> None:
        """Report the finished download.
        """
        size = human_size(fetched.bytes_downloaded)
        if combine == "none":
            logger.info(
                "saved %d files (%s) to %s",
                len(fetched.files), size, fetched.files[0].parent,
            )
        else:
            logger.info("saved %s (%s)", fetched.files[0], size)

    @staticmethod
    def _warn_about_mixed_level_types(assets: Sequence[Asset]) -> None:
        """Warn when one file will hold several vertical coordinate types.
        Concatenating them is legal GRIB2 and stays allowed, but readers do
        struggle with it. CDO in particular wants one vertical axis per file.
        """
        kinds = {
            asset.level_type.code
            for asset in assets
            if asset.level_type is not None
        }
        # A 2-D field alongside a 3-D one is also problematic.
        if any(asset.level_type is None for asset in assets):
            kinds.add(-1)
        if len(kinds) > 1:
            named = ", ".join(
                "surface" if code == -1 else str(LevelType.of(code))
                for code in sorted(kinds)
            )
            logger.warning(
                "combining several level types into one file (%s). This is valid "
                "GRIB2, but some readers want one vertical axis per file. "
                "cdo splitzaxis, or combine=\"none\", separates them",
                named,
            )
