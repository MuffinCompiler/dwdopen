"""A resolved 3-D request holds thousands of assets. Printing one must stay
readable, so neither dataclass may fall back to its generated repr.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from dwdopen.nwp.request import Asset, MissingStep, ResolvedRequest
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import LevelType

RUN = Run.coerce("2026-09-23T06:00")
NOW = datetime(2026, 9, 23, 8, tzinfo=UTC)
PRESSURE = LevelType.coerce("pressure")
MODEL = LevelType.coerce("model")
SOIL = LevelType.coerce("soil")


def asset(parameter="T", hours=0, level_type=None, level=None, size=800_000):
    return Asset(
        keys=(("m", "icon-eu"), ("p", parameter)),
        run=RUN,
        step=timedelta(hours=hours),
        path=f"x/{parameter}/{hours}/{level}",
        size=size,
        level_type=level_type,
        level=None if level is None else Decimal(str(level)),
    )


def plan(assets, missing=()):
    return ResolvedRequest(
        run=RUN, assets=tuple(assets), resolved_at=NOW, missing=tuple(missing)
    )


# --- Asset ----------------------------------------------------------------

def test_a_surface_asset_names_parameter_step_and_size():
    assert repr(asset("T_2M", 6)) == "Asset(T_2M, 6h, 781.2 KB)"


def test_a_pressure_asset_reads_back_in_hpa_not_pa():
    text = repr(asset("T", 0, PRESSURE, 85000))
    assert "850 hPa" in text
    assert "85000" not in text


def test_a_model_level_asset_says_level_not_a_unit():
    assert "level 60" in repr(asset("T", 0, MODEL, 60))


def test_a_soil_asset_keeps_its_fraction_of_a_metre():
    assert "0.18 m" in repr(asset("T_SO", 0, SOIL, "0.18"))
    # 0.0 should not print as "0.0 m" with a pointless trailing zero
    assert "0 m" in repr(asset("T_SO", 0, SOIL, "0.0"))


def test_an_asset_without_a_size_omits_it():
    assert repr(asset("T_2M", 0, size=None)) == "Asset(T_2M, 0h)"


# --- ResolvedRequest ------------------------------------------------------

def test_a_plan_summarises_rather_than_listing_its_assets():
    many = [asset("U", h, PRESSURE, 85000) for h in range(120)]
    text = repr(plan(many))

    assert "120 assets" in text
    assert "pressure (100)" in text
    assert "steps 0h..119h" in text
    # the whole point: no per-asset detail, however many there are
    assert "Asset(" not in text
    assert len(text) < 200


def test_one_asset_is_singular():
    assert "1 asset," in repr(plan([asset()]))


def test_an_empty_plan_says_so_instead_of_showing_an_empty_tuple():
    assert repr(plan([])) == (
        "ResolvedRequest(run=2026-09-23T06:00:00+00:00, nothing selected)"
    )


def test_a_single_step_is_not_shown_as_a_range():
    text = repr(plan([asset("T_2M", 6), asset("PMSL", 6)]))
    assert "steps 6h" in text
    assert ".." not in text


def test_many_parameters_are_counted_rather_than_listed():
    lots = [asset(f"P{i}") for i in range(9)]
    assert "9 parameters" in repr(plan(lots))


def test_few_parameters_are_named():
    text = repr(plan([asset("T_2M"), asset("PMSL")]))
    assert "PMSL, T_2M" in text


def test_missing_steps_are_reported():
    text = repr(plan([asset()], missing=[MissingStep("T", timedelta(hours=3))]))
    assert "1 missing" in text


def test_an_unknown_size_is_admitted_not_guessed():
    assert "size unknown" in repr(plan([asset(size=None)]))
