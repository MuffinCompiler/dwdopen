from datetime import timedelta

import pytest

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.durations import format_duration, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0h", timedelta()),
        ("0m", timedelta()),
        ("6h", timedelta(hours=6)),
        ("120h", timedelta(hours=120)),
        ("5m", timedelta(minutes=5)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        # the ISO form DWD writes in filenames
        ("PT000H00M", timedelta()),
        ("PT000H05M", timedelta(minutes=5)),
        ("PT006H00M", timedelta(hours=6)),
        ("PT026H40M", timedelta(hours=26, minutes=40)),
        ("PT180H00M", timedelta(hours=180)),
        ("PT1H30M", timedelta(hours=1, minutes=30)),
    ],
)
def test_parses(text, expected):
    assert parse_duration(text) == expected


def test_timedelta_passes_through():
    assert parse_duration(timedelta(minutes=90)) == timedelta(minutes=90)


@pytest.mark.parametrize("text", ["", "   ", "6", "6s", "abc", "P1DT2H", "1m30h", "PT"])
def test_rejects(text):
    with pytest.raises(InvalidSelectorError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(), "0h"),
        (timedelta(hours=6), "6h"),
        (timedelta(minutes=5), "5m"),
        (timedelta(hours=1, minutes=30), "1h30m"),
        (timedelta(hours=26, minutes=40), "26h40m"),
    ],
)
def test_formats(delta, expected):
    assert format_duration(delta) == expected
