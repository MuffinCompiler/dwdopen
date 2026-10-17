"""Progress feedback while downloading."""

import io
import logging
import sys
import time

from dwdopen._fileserver import progress as progress_module
from dwdopen._fileserver.progress import Progress, draw_bar, format_seconds

MB = 1024**2


# --- counting -------------------------------------------------------------

def test_bytes_and_files_are_counted():
    progress = Progress(files_total=2, bytes_total=100, show=False)
    progress.add_bytes(30)
    progress.add_bytes(20)
    progress.file_done()

    assert progress.fraction() == 0.5
    assert progress.stats(elapsed=1.0).startswith(" 50%  1/2 files")


def test_a_file_on_disk_is_done_but_leaves_the_byte_total():
    progress = Progress(files_total=2, bytes_total=100, show=False)
    progress.file_skipped(40)
    progress.add_bytes(30)
    assert progress.fraction() == 0.5
    assert "1/2 files" in progress.stats(elapsed=1.0)


def test_without_sizes_the_fraction_falls_back_to_files():
    progress = Progress(files_total=4, bytes_total=None, show=False)
    progress.file_done()
    assert progress.fraction() == 0.25
    assert "ETA" not in progress.stats(elapsed=1.0)


# --- the line -------------------------------------------------------------

def test_stats_show_files_bytes_rate_and_eta():
    progress = Progress(files_total=546, bytes_total=4000 * MB, show=False)
    for _ in range(312):
        progress.file_done()
    progress.add_bytes(2000 * MB)

    assert progress.stats(elapsed=40.0) == (
        " 50%  312/546 files  2.0 GB/3.9 GB  50.0 MB/s  ETA 0:40"
    )


def test_seconds_are_formatted_like_a_clock():
    assert format_seconds(36) == "0:36"
    assert format_seconds(725) == "12:05"
    assert format_seconds(3723) == "1:02:03"


def test_a_bar_has_the_asked_width():
    plain = draw_bar(0.55, 20).replace("\x1b[2m", "").replace("\x1b[0m", "")
    assert len(plain) == 20
    assert plain.startswith("━" * 11)
    assert draw_bar(1.0, 10) == "━" * 10


def test_the_line_drops_the_bar_on_a_narrow_terminal():
    progress = Progress(files_total=10, bytes_total=1000, show=False)
    assert "━" in progress.line(elapsed=1.0, columns=120)
    narrow = progress.line(elapsed=1.0, columns=40)
    assert "━" not in narrow and len(narrow) < 40


# --- showing it -----------------------------------------------------------

class Tty(io.StringIO):
    def isatty(self):
        return True


def test_on_a_terminal_the_last_line_stays_and_ends_with_a_newline(monkeypatch):
    stderr = Tty()
    monkeypatch.setattr(sys, "stderr", stderr)
    with Progress(files_total=1, bytes_total=10) as progress:
        progress.add_bytes(10)
        progress.file_done()

    output = stderr.getvalue()
    assert output.startswith("\r")
    assert "100%  1/1 files" in output
    assert output.endswith("\n")


def test_without_a_terminal_progress_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    monkeypatch.delitem(sys.modules, "ipykernel", raising=False)
    monkeypatch.setattr(progress_module, "LOG_INTERVAL", 0.01)

    with caplog.at_level(logging.INFO, logger="dwdopen"):
        with Progress(files_total=1, bytes_total=10):
            # Give the reporting thread time for a few ticks.
            time.sleep(0.1)
    assert "progress:" in caplog.text
    assert sys.stderr.getvalue() == ""


def test_show_false_prints_nothing(monkeypatch):
    stderr = Tty()
    monkeypatch.setattr(sys, "stderr", stderr)
    with Progress(files_total=1, bytes_total=10, show=False):
        pass
    assert stderr.getvalue() == ""
