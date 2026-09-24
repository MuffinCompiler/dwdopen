from datetime import timedelta

import pytest

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.durations import (
    check_step_selector,
    format_duration,
    hours,
    minutes,
    parse_duration,
)
from dwdopen.nwp.selectors import Between, Every


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


# --- rejecting bare numbers -----------------------------------------------

@pytest.mark.parametrize("value", [0, 6, 120, 6.5])
def test_a_bare_number_is_refused_with_both_readings(value):
    """A number alone is ambiguous now that sub-hourly steps exist.

    ICON-D2 publishes every 15 minutes and ICON-D2-RUC every 5, so 6 could
    mean either. The message spells out both spellings rather than guessing.
    """
    with pytest.raises(InvalidSelectorError) as caught:
        parse_duration(value)
    message = str(caught.value)
    assert f"'{value:g}h'" in message
    assert f"'{value:g}m'" in message


@pytest.mark.parametrize("value", [None, b"6h", ["6h"]])
def test_a_wrong_type_names_the_type(value):
    with pytest.raises(InvalidSelectorError, match=type(value).__name__):
        parse_duration(value)


# --- failing before the network -------------------------------------------

@pytest.mark.parametrize(
    "selector",
    [
        [0, 6, 12],
        6,
        Between(0, 48),
        Every(0, 48, 6),
        Every("0h", 48, "6h"),
    ],
)
def test_check_rejects_every_shape_a_bare_number_can_hide_in(selector):
    with pytest.raises(InvalidSelectorError, match="needs its unit"):
        check_step_selector(selector)


@pytest.mark.parametrize(
    "selector",
    [
        None,
        "all",
        "15m",
        ["0h", "6h"],
        timedelta(hours=6),
        Between("0h", "48h"),
        Between(None, "48h"),
        Every("0h", "48h", "3h"),
    ],
)
def test_check_accepts_the_valid_shapes(selector):
    check_step_selector(selector)


def test_a_bad_step_fails_at_select_without_touching_the_network():
    """The reported bug: the error used to surface from inside resolve(),
    after the catalogue had already been read, pointing at a comprehension
    rather than at the call the user wrote.
    """
    from dwdopen.client import NWP

    class Catalogue:
        def models(self):
            return ["icon"]

        def parameters(self, model):
            raise AssertionError("select() must fail before reading the catalogue")

    model = NWP(Catalogue()).model("icon")
    with pytest.raises(InvalidSelectorError, match="needs its unit"):
        model.select(parameters=["T_2M"], steps=[0, 6, 12, 18])


# --- hours() / minutes() sugar --------------------------------------------

def test_a_list_of_plain_numbers_becomes_steps():
    """The shape a meteorologist already has: [0, 6, 12, 18]."""
    assert hours([0, 6, 12, 18]) == (
        timedelta(),
        timedelta(hours=6),
        timedelta(hours=12),
        timedelta(hours=18),
    )


def test_varargs_and_a_sequence_agree():
    assert hours(0, 6, 12) == hours([0, 6, 12])


def test_any_iterable_works_not_just_lists():
    assert hours(range(0, 25, 6)) == hours(0, 6, 12, 18, 24)
    assert hours(h for h in (0, 6)) == hours(0, 6)


def test_one_number_gives_one_duration_so_it_composes():
    # Scalar in, scalar out, following pandas.to_timedelta. This is what makes
    # Every(hours(0), hours(48), hours(3)) work.
    assert hours(6) == timedelta(hours=6)
    assert check_step_selector(Every(hours(0), hours(48), hours(3))) is None


def test_fractions_are_allowed():
    assert hours(1.5) == timedelta(hours=1, minutes=30)


def test_minutes_covers_the_sub_hourly_models():
    # ICON-D2 publishes every 15 minutes, ICON-D2-RUC every 5.
    assert minutes(0, 15, 30) == (
        timedelta(),
        timedelta(minutes=15),
        timedelta(minutes=30),
    )


def test_the_result_is_a_valid_step_selector():
    check_step_selector(hours(0, 6, 12))
    check_step_selector(minutes([0, 15]))


def test_a_negative_step_is_refused():
    with pytest.raises(InvalidSelectorError, match="cannot be negative"):
        hours(-6)


def test_a_non_number_is_refused():
    with pytest.raises(InvalidSelectorError, match="takes numbers"):
        hours("6h")


def test_no_arguments_is_refused():
    with pytest.raises(InvalidSelectorError, match="at least one"):
        hours()


def test_a_timedelta_subclass_passes_through():
    """pandas.Timedelta subclasses datetime.timedelta, so pandas users need
    no sugar at all: pd.to_timedelta([0, 6], unit="h") already works.
    """
    class Subclass(timedelta):
        pass

    check_step_selector([Subclass(hours=6)])
    assert parse_duration(Subclass(hours=6)) == timedelta(hours=6)


def test_the_bare_number_error_points_at_the_sugar():
    with pytest.raises(InvalidSelectorError, match=r"hours\(0, 6, 12\)"):
        parse_duration(6)
