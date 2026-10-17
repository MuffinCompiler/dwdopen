"""Progress feedback while downloading."""

from __future__ import annotations

import logging
import shutil
import sys
import threading
import time
from types import TracebackType

from dwdopen.nwp.request import human_size

__all__ = ["Progress"]

logger = logging.getLogger("dwdopen")

TERMINAL_INTERVAL = 0.1
"""Seconds between two redraws of the line on a terminal."""

LOG_INTERVAL = 10.0
"""Seconds between two progress lines in the log."""


class Progress:
    """Counts the files and bytes of one download and shows them.
    ━━━━━━━━━━━━━━━━╸━━━━━━━━━━━  57%  312/546 files  2.3 GB/4.0 GB  48.2 MB/s  ETA 0:36

    Otherwise, e.g. in a cron job, the same numbers are logged every 10 seconds.
    The download threads report each finished file and its size, so the bar
    can advance.
    Use it as a context manager around the download.
    """

    def __init__(
        self, files_total: int, bytes_total: int | None, show: bool = True
    ) -> None:
        self._files_total = files_total
        self._bytes_total = bytes_total
        self._files_done = 0
        self._bytes_done = 0
        self._lock = threading.Lock()

        self._show = show
        self._terminal = show and _is_interactive()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = time.monotonic()

    # Counting

    def add_bytes(self, count: int) -> None:
        with self._lock:
            self._bytes_done += count

    def file_done(self) -> None:
        with self._lock:
            self._files_done += 1

    def file_skipped(self, size: int | None) -> None:
        """A file already on disk. It counts as done.
        Subtracts from the total size to download as nothing is transferred.
        """
        with self._lock:
            self._files_done += 1
            if self._bytes_total is not None and size is not None:
                self._bytes_total -= size

    # Showing

    def __enter__(self) -> Progress:
        if self._show:
            self._thread = threading.Thread(
                target=self._run, name="dwdopen-progress", daemon=True
            )
            self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self._terminal:
            # The final state stays on screen, the next output starts below.
            self._draw()
            sys.stderr.write("\n")
            sys.stderr.flush()

    def _run(self) -> None:
        """Invoked when the progress thread starts running."""
        interval = TERMINAL_INTERVAL if self._terminal else LOG_INTERVAL
        # wait() returns False on timeout and True once __exit__ asks to stop.
        # On timeout, we update the display.
        while not self._stop.wait(interval):
            if self._terminal:
                self._draw()
            else:
                logger.info("progress: %s", self.stats(self._elapsed()))

    def _draw(self) -> None:
        """Redraw the line: \\r goes back to its start, \\x1b[K clears the rest
        of a previous, longer line.
        """
        line = self.line(self._elapsed(), shutil.get_terminal_size().columns)
        sys.stderr.write("\r" + line + "\x1b[K")
        sys.stderr.flush()

    def _elapsed(self) -> float:
        return time.monotonic() - self._started

    def line(self, elapsed: float, columns: int) -> str:
        """Bar and stats, at most `columns` wide. The bar is left out when the
        terminal is too narrow for it.
        """
        stats = self.stats(elapsed)
        width = min(40, columns - len(stats) - 3)
        if width < 10:
            return stats[: max(0, columns - 1)]
        return draw_bar(self.fraction(), width) + "  " + stats

    def fraction(self) -> float:
        """Share done between 0 and 1. By bytes if known, otherwise by files."""
        with self._lock:
            if self._bytes_total:
                return min(1.0, self._bytes_done / self._bytes_total)
            if self._files_total:
                return min(1.0, self._files_done / self._files_total)
            return 1.0

    def stats(self, elapsed: float) -> str:
        """Percent, files, bytes, the average rate and the time left as string."""
        percent = self.fraction() * 100
        with self._lock:
            files_done = self._files_done
            done = self._bytes_done
            total = self._bytes_total

        rate = done / elapsed if elapsed > 0 else 0.0
        parts = [f"{percent:3.0f}%", f"{files_done}/{self._files_total} files"]
        if total is None:
            parts.append(human_size(done))
        else:
            parts.append(f"{human_size(done)}/{human_size(total)}")
        parts.append(f"{human_size(int(rate))}/s")
        if total is not None and rate > 0:
            parts.append(f"ETA {format_seconds(max(0, total - done) / rate)}")
        return "  ".join(parts)


def draw_bar(fraction: float, width: int) -> str:
    """A bar `width` characters wide. The empty part is drawn dim."""
    halves = int(fraction * width * 2)
    full = halves // 2
    bar = "━" * full
    if halves % 2 == 1 and full < width:
        bar += "╸"
    empty = width - len(bar)
    if empty > 0:
        bar += "\x1b[2m" + "━" * empty + "\x1b[0m"
    return bar


def format_seconds(seconds: float) -> str:
    """0:36, 12:05 or 1:02:03."""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _is_interactive() -> bool:
    """Check whether someone watches the output, check for Jupyter and terminal."""
    if "ipykernel" in sys.modules:
        return True
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):  # stderr replaced or closed
        return False
