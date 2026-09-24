from decimal import Decimal

import pytest

from dwdopen.exceptions import AmbiguousSelectionError, InvalidSelectorError
from dwdopen.nwp.query import _select_levels
from dwdopen.nwp.selectors import Between, Every, LevelType

PRESSURE = LevelType.coerce("pressure")
MODEL = LevelType.coerce("model")
SOIL = LevelType.coerce("soil")

# As the server writes them: Pa for pressure, bare indices for model levels,
# metres for soil. Soil is the awkward one, being fractions of a metre.
PRESSURE_LEVELS = [Decimal(v) for v in ("50000", "70000", "85000", "100000")]
MODEL_LEVELS = [Decimal(v) for v in range(60, 66)]
SOIL_LEVELS = [Decimal(v) for v in ("0.0", "0.005", "0.02", "0.18", "14.58")]


# --- unit handling --------------------------------------------------------

def test_pressure_is_given_in_hpa_and_stored_in_pa():
    assert PRESSURE.to_server(850) == Decimal(85000)
    assert PRESSURE.to_user(Decimal(85000)) == Decimal(850)


def test_model_and_soil_levels_are_not_rescaled():
    assert MODEL.to_server(60) == Decimal(60)
    assert SOIL.to_server(0.005) == Decimal("0.005")


def test_a_soil_level_survives_the_float_that_cannot_hold_it():
    # 0.005 has no exact binary float. Going through str() keeps the decimal
    # digits, so the value still matches the token parsed from the listing.
    assert SOIL.to_server(0.005) in SOIL_LEVELS
    # Decimal(float) is exactly the mistake being guarded against here.
    assert Decimal(0.005) not in SOIL_LEVELS  # noqa: RUF032


def test_a_level_type_is_named_by_alias_code_or_object():
    assert LevelType.coerce("pressure") is LevelType.coerce(100)
    assert LevelType.coerce(PRESSURE) is PRESSURE


def test_an_unknown_code_still_works():
    # GRIB2 reserves 192-254 for local use and DWD uses that range.
    assert LevelType.coerce(208).code == 208


def test_an_unknown_alias_is_rejected_with_the_known_ones():
    with pytest.raises(InvalidSelectorError, match="pressure"):
        LevelType.coerce("isobaric")


# --- selecting levels -----------------------------------------------------

def test_all_takes_every_level_the_catalogue_offers():
    assert _select_levels(PRESSURE_LEVELS, "all", PRESSURE) == PRESSURE_LEVELS
    assert _select_levels(PRESSURE_LEVELS, None, PRESSURE) == PRESSURE_LEVELS


def test_a_list_is_converted_before_it_is_matched():
    chosen = _select_levels(PRESSURE_LEVELS, [850, 500], PRESSURE)
    assert chosen == [Decimal(85000), Decimal(50000)]


def test_a_scalar_selects_one_level():
    assert _select_levels(MODEL_LEVELS, 62, MODEL) == [Decimal(62)]


def test_between_is_inclusive_and_in_user_units():
    chosen = _select_levels(PRESSURE_LEVELS, Between(700, 1000), PRESSURE)
    assert chosen == [Decimal(70000), Decimal(85000), Decimal(100000)]


def test_every_expands_a_cadence():
    chosen = _select_levels(MODEL_LEVELS, Every(60, 64, 2), MODEL)
    assert chosen == [Decimal(60), Decimal(62), Decimal(64)]


def test_a_level_that_does_not_exist_says_what_does():
    with pytest.raises(InvalidSelectorError, match="850"):
        _select_levels(PRESSURE_LEVELS, [999], PRESSURE)


def test_soil_levels_match_on_their_exact_decimal():
    assert _select_levels(SOIL_LEVELS, [0.005, 0.18], SOIL) == [
        Decimal("0.005"),
        Decimal("0.18"),
    ]


# --- choosing the level type ----------------------------------------------

class FakeCatalogue:
    """Just enough catalogue to exercise level-type resolution."""

    def __init__(self, types: dict[str, list[LevelType]]) -> None:
        self.types = types

    def parameters(self, model: str) -> list[str]:
        return sorted(self.types)

    def level_types(self, model: str, parameter: str) -> list[LevelType]:
        return self.types[parameter]


def model_with(types):
    from dwdopen.nwp.model import Model

    return Model("icon-eu", FakeCatalogue(types))


def test_a_single_level_type_is_inferred():
    model = model_with({"T_SO": [SOIL]})
    query = model.select(parameters="T_SO", levels="all")
    assert query._level_type is SOIL


def test_two_level_types_on_one_parameter_are_ambiguous():
    # T really is published on both pressure and model levels.
    model = model_with({"T": [PRESSURE, MODEL]})
    with pytest.raises(AmbiguousSelectionError, match="pressure"):
        model.select(parameters="T", levels=[850])


def test_two_parameters_disagreeing_are_ambiguous():
    model = model_with({"T": [PRESSURE], "W": [MODEL]})
    with pytest.raises(AmbiguousSelectionError, match="W"):
        model.select(parameters=["T", "W"], levels="all")


def test_naming_the_level_type_resolves_the_ambiguity():
    model = model_with({"T": [PRESSURE, MODEL]})
    query = model.select(parameters="T", level_type="model", levels=[60])
    assert query._level_type is MODEL


def test_a_surface_parameter_has_no_level_type():
    model = model_with({"T_2M": []})
    assert model.select(parameters="T_2M")._level_type is None


def test_levels_on_a_surface_parameter_are_rejected():
    model = model_with({"T_2M": []})
    with pytest.raises(InvalidSelectorError, match="single level"):
        model.select(parameters="T_2M", levels=[850])


# --- the multi-asset-per-step case ----------------------------------------

def test_several_levels_of_one_step_all_survive_selection():
    """Levels multiply the assets sharing a forecast step.

    Keyed by step alone, a 20-level selection would keep one asset per step and
    silently drop the other nineteen.
    """
    from datetime import timedelta

    from dwdopen.nwp.query import _select_steps
    from dwdopen.nwp.request import Asset
    from dwdopen.nwp.run import Run

    run = Run.coerce("2026-09-22T06:00")
    assets = [
        Asset(
            keys=(("m", "icon-eu"), ("p", "T")),
            run=run,
            step=timedelta(hours=hour),
            path=f"x/{hour}/{level}",
            level_type=MODEL,
            level=Decimal(level),
        )
        for hour in (0, 1)
        for level in (60, 61, 62)
    ]

    chosen, absent = _select_steps(assets, ["0h", "1h"])
    assert len(chosen) == 6
    assert absent == []

    chosen, _ = _select_steps(assets, "0h")
    assert [a.level for a in chosen] == [Decimal(60), Decimal(61), Decimal(62)]


def test_mixed_level_types_in_one_file_warn_but_are_allowed(caplog):
    """Concatenating them is legal GRIB2, so it must not be refused."""
    import logging
    from datetime import timedelta

    from dwdopen._fileserver.download import HttpDownloader
    from dwdopen.nwp.request import Asset
    from dwdopen.nwp.run import Run

    run = Run.coerce("2026-09-22T06:00")
    surface = Asset(keys=(), run=run, step=timedelta(), path="a")
    pressure = Asset(
        keys=(), run=run, step=timedelta(), path="b",
        level_type=PRESSURE, level=Decimal(85000),
    )

    with caplog.at_level(logging.WARNING, logger="dwdopen"):
        HttpDownloader._warn_about_mixed_level_types([surface, pressure])
    assert "several level types" in caplog.text
    assert "splitzaxis" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="dwdopen"):
        HttpDownloader._warn_about_mixed_level_types([pressure, pressure])
    assert caplog.text == ""


# --- time-invariant fields ------------------------------------------------

def test_an_invariant_field_is_selected_without_a_level_type():
    # HSURF, CLAT, FR_LAND and friends are plain 2-D parameters in v1.
    model = model_with({"HSURF": []})
    assert model.select(parameters="HSURF", steps="0h")._level_type is None
