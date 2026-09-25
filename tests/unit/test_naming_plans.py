"""Generated file names for combined downloads.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from dwdopen.exceptions import DownloadError
from dwdopen.nwp.request import MAX_NAME_LENGTH, Asset, ResolvedRequest
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

RUN = Run.coerce("2026-09-24T06:00")
NOW = datetime(2026, 9, 24, 8, tzinfo=UTC)
PRESSURE = LevelType.coerce("pressure")
MODEL = LevelType.coerce("model")
SOIL = LevelType.coerce("soil")


def asset(parameter="T_2M", hours=0, model="icon-eu", level_type=None, level=None):
    return Asset(
        keys=(("m", model), ("p", parameter)),
        run=RUN,
        step=timedelta(hours=hours),
        path="x",
        size=1000,
        level_type=level_type,
        level=None if level is None else Decimal(str(level)),
    )


def plan(assets):
    return ResolvedRequest(run=RUN, assets=tuple(assets), resolved_at=NOW)


def test_one_parameter_names_the_model_run_parameter_and_steps():
    made = plan([asset("T_2M", 0), asset("T_2M", 12)])
    assert made.suggested_name() == (
        f"icon-eu_2026-09-24T0600_T_2M_0h-12h_{made.fingerprint()}.grib2"
    )


def test_the_run_carries_no_colon_because_windows_rejects_it():
    assert ":" not in plan([asset()]).suggested_name()


def test_a_single_step_is_not_written_as_a_range():
    made = plan([asset("T_2M", 6)])
    assert f"_6h_{made.fingerprint()}" in made.suggested_name()


def test_up_to_three_parameters_are_listed():
    name = plan([asset("T_2M"), asset("PMSL"), asset("TOT_PREC")]).suggested_name()
    assert "PMSL+TOT_PREC+T_2M" in name


def test_more_parameters_are_counted_so_the_name_stays_short():
    # The real job asks for 21 at once.
    many = [asset(f"P{i:02d}") for i in range(21)]
    name = plan(many).suggested_name()
    assert "21params" in name
    assert len(name) < 60


def test_a_single_pressure_level_is_named_in_hpa():
    name = plan([asset("T", level_type=PRESSURE, level=85000)]).suggested_name()
    assert "_850hPa_" in name
    assert "85000" not in name


def test_several_levels_are_counted():
    assets = [asset("T", level_type=PRESSURE, level=lv) for lv in (85000, 50000)]
    assert "_2lv_" in plan(assets).suggested_name()


def test_a_model_level_is_labelled_rather_than_given_a_unit():
    # The unit is "index", which reads badly as a suffix.
    name = plan([asset("T", level_type=MODEL, level=60)]).suggested_name()
    assert "_lv60_" in name


def test_a_soil_level_keeps_its_metres():
    name = plan([asset("T_SO", level_type=SOIL, level="0.18")]).suggested_name()
    assert "_0.18m_" in name


def test_a_surface_selection_has_no_level_part():
    made = plan([asset("T_2M")])
    assert made.suggested_name() == (
        f"icon-eu_2026-09-24T0600_T_2M_0h_{made.fingerprint()}.grib2"
    )


def test_the_suffix_can_be_changed():
    assert plan([asset()]).suggested_name(".grb2").endswith(".grb2")


def test_an_empty_plan_cannot_be_named():
    with pytest.raises(DownloadError, match="empty plan"):
        plan([]).suggested_name()


# --- choosing between a directory and a file ------------------------------

def test_an_existing_directory_gets_a_generated_name(tmp_path):
    target, generated = plan([asset()])._target(tmp_path, "all")
    assert target.parent == tmp_path
    assert target.name == plan([asset()]).suggested_name()
    assert generated


def test_a_trailing_separator_means_a_directory(tmp_path):
    target, generated = plan([asset()])._target(str(tmp_path / "later") + "/", "all")
    assert target.parent.name == "later"
    assert target.name.endswith(".grib2")
    assert generated


def test_a_plain_path_that_does_not_exist_is_a_file(tmp_path):
    # cp reads it this way too: no trailing slash and nothing there means file.
    target, generated = plan([asset()])._target(tmp_path / "out.grib2", "all")
    assert target == tmp_path / "out.grib2"
    # We did not choose the name, so it tells us nothing about the plan.
    assert not generated


def test_combine_none_always_means_the_directory_itself(tmp_path):
    assert plan([asset()])._target(tmp_path, "none") == (tmp_path, False)


# --- staying inside a length budget ---------------------------------------

def test_the_realistic_worst_case_fits():
    """Three of ICON-ART's longest names on the longest model name."""
    longest = [
        "DUST_MAX_TOTAL_MC_LAYER",
        "ACCWETDEPO_GSP_DUSTC",
        "ACCWETDEPO_CON_DUSTA",
    ]
    assets = [
        asset(p, hours=h, model="icon-art-eu-eps")
        for p in longest
        for h in (0, 120)
    ]
    name = plan(assets).suggested_name()
    assert len(name) <= MAX_NAME_LENGTH
    # Short enough that the names are still listed, not counted.
    assert "DUST_MAX_TOTAL_MC_LAYER" in name


def test_long_names_fall_back_to_counting_rather_than_overflowing():
    assets = [asset("X" * 90), asset("Y" * 90)]
    name = plan(assets).suggested_name()
    assert len(name) <= MAX_NAME_LENGTH
    assert "2params" in name


def test_forty_surface_fields_stay_short():
    assets = [asset(f"PARAM_{i:02d}", hours=h) for i in range(40) for h in (0, 120)]
    name = plan(assets).suggested_name()
    assert "40params" in name
    assert len(name) < 60


def test_the_suffix_survives_even_a_pathological_name():
    # Only reachable with an absurd model name, but a file without its
    # extension would be worse than a truncated one.
    assets = [asset("T_2M", model="m" * 130)]
    name = plan(assets).suggested_name()
    assert len(name) <= MAX_NAME_LENGTH
    assert name.endswith(".grib2")


# --- the plan fingerprint -------------------------------------------------

def test_the_same_plan_always_fingerprints_the_same():
    assert plan([asset("T_2M")]).fingerprint() == plan([asset("T_2M")]).fingerprint()


def test_plans_that_differ_only_in_a_dropped_field_get_different_names():
    """The collision the readable fields alone could not avoid.

    Two subsets of the same parameters, same run, same steps, used to produce
    one name and silently overwrite each other.
    """
    four = [asset(f"P{i}") for i in range(4)]
    five = [asset(f"P{i}") for i in range(5)]
    # Both collapse to "Nparams", so only the hash separates them.
    assert plan(four).suggested_name() != plan(five).suggested_name()


def test_the_hash_survives_truncation():
    # It is the field that identifies the plan, so cutting it would defeat the
    # whole point of having it.
    made = plan([asset("T_2M", model="m" * 130)])
    name = made.suggested_name()
    assert len(name) <= MAX_NAME_LENGTH
    assert name.endswith(f"_{made.fingerprint()}.grib2")


def test_the_hash_tracks_steps_and_levels_not_just_parameters():
    one_step = plan([asset("T_2M", 0)])
    two_steps = plan([asset("T_2M", 0), asset("T_2M", 3)])
    assert one_step.fingerprint() != two_steps.fingerprint()
