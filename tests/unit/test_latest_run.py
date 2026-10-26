"""When no run satisfies a query, the error says why the newest ones were
skipped: a selection that never matches reads differently from a run DWD is
still publishing.
"""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from dwdopen.exceptions import NoMatchingRunError
from dwdopen.nwp.query import Query
from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run

OLDER = Run.coerce("2026-10-22T00:00")
NEWER = Run.coerce("2026-10-22T03:00")


class Publishing:
    """T_2M with two runs. The newer has only 0h so far, the older has 0h and
    3h, but its last file was written 10 s ago."""

    def __init__(self, runs=(OLDER, NEWER)):
        self._runs = list(runs)

    def snapshot(self):
        return nullcontext()

    def runs(self, model, **kw):
        return self._runs

    def wavelengths(self, model, parameter):
        return []

    def members(self, model, parameter, run, **kw):
        return []

    def assets(self, model, parameter, run, **kw):
        hours = [0] if run == NEWER else [0, 3]
        return [
            Asset(
                keys=(("m", model), ("p", parameter)),
                run=run,
                step=timedelta(hours=h),
                path=f"{run}/{h}",
                modified=datetime.now(UTC) - timedelta(seconds=10),
            )
            for h in hours
        ]


def query(catalogue):
    return Query(catalogue, "icon-eu", parameters=("T_2M",), steps=["0h", "3h"])


def test_the_error_says_why_each_run_was_skipped():
    with pytest.raises(NoMatchingRunError) as caught:
        query(Publishing()).latest_run()
    message = str(caught.value)
    assert "2 runs were checked, newest first" in message
    newer, older = message.splitlines()[1:]
    assert "2026-10-22T03:00" in newer and "missing" in newer and "T_2M 3h" in newer
    assert "2026-10-22T00:00" in older and "still being published" in older


def test_a_settled_run_is_returned():
    assert query(Publishing()).latest_run(settle=timedelta(0)) == OLDER


def test_no_runs_at_all_says_so():
    with pytest.raises(NoMatchingRunError, match="no runs of 'icon-eu' are listed"):
        query(Publishing(runs=())).latest_run()


def test_only_the_three_newest_reasons_are_listed():
    runs = [Run.coerce(f"2026-10-22T0{h}:00") for h in range(3, 9)]
    catalogue = Publishing(runs=runs)
    with pytest.raises(NoMatchingRunError, match=r"\.\.\. and 3 older runs"):
        query(catalogue).latest_run()
