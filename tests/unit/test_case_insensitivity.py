"""Names are matched ignoring case.
"""

import pytest

from dwdopen.exceptions import (
    UnknownModelError,
    UnknownParameterError,
    resolve_name,
)

AVAILABLE = ["T_2M", "TOT_PREC", "PMSL", "TD_2M"]


# --- resolve_name ---------------------------------------------------------

@pytest.mark.parametrize(
    "given", ["T_2M", "t_2m", "T_2m", "t_2M"],
)
def test_any_spelling_resolves_to_the_catalogue_form(given):
    assert resolve_name(given, AVAILABLE) == "T_2M"


def test_an_exact_match_is_returned_untouched():
    assert resolve_name("TOT_PREC", AVAILABLE) == "TOT_PREC"


def test_an_unknown_name_resolves_to_nothing():
    # None rather than raising: the caller knows whether this is a model or a
    # parameter and raises the matching error.
    assert resolve_name("NOPE", AVAILABLE) is None


def test_resolution_is_not_fuzzy():
    # Only case is forgiven. A real typo must still fail.
    assert resolve_name("T_2X", AVAILABLE) is None
    assert resolve_name("T2M", AVAILABLE) is None


# --- through the client ---------------------------------------------------

class FakeCatalogue:
    def models(self):
        return ["icon-eu", "icon-d2"]

    def parameters(self, model):
        assert model == "icon-eu", f"model reached catalogue as {model!r}"
        return list(AVAILABLE)

    def level_types(self, model, parameter):
        assert parameter in AVAILABLE, f"parameter reached catalogue as {parameter!r}"
        return []


def client():
    from dwdopen.client import NWP

    return NWP(FakeCatalogue())


@pytest.mark.parametrize("given", ["icon-eu", "ICON-EU", "Icon-Eu"])
def test_a_model_name_is_canonicalised(given):
    assert client().model(given).name == "icon-eu"


def test_an_unknown_model_still_raises():
    with pytest.raises(UnknownModelError):
        client().model("icon-xx")


def test_select_hands_the_catalogue_the_canonical_parameter():
    # The FakeCatalogue asserts on what it receives, so this fails loudly if a
    # lowercase name ever reaches a path.
    query = client().model("icon-eu").select(parameters=["t_2m", "Tot_Prec"])
    assert query._parameters == ("T_2M", "TOT_PREC")


def test_parameter_info_reports_the_canonical_name():
    assert client().model("icon-eu").parameter("pmsl").name == "PMSL"


def test_an_unknown_parameter_still_raises():
    with pytest.raises(UnknownParameterError):
        client().model("icon-eu").select(parameters="nope")
