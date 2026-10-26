"""What a new user types first: select("T_2M"), type hints with the objects
they get back, and printing a run.
"""

import dwdopen
from dwdopen import Between, Every, LevelType, Query, Run
from dwdopen.nwp.model import Model


class TwoDimensional:
    """T_2M on a single level, without wavelengths."""

    def parameters(self, model):
        return ["T_2M"]

    def wavelengths(self, model, parameter):
        return []

    def level_types(self, model, parameter, wavelength=None):
        return []


def test_parameters_can_be_given_positionally():
    model = Model("icon-eu", TwoDimensional())
    query = model.select("t_2m", steps="0h")
    assert isinstance(query, Query)
    assert repr(query) == repr(model.select(parameters="T_2M", steps="0h"))


def test_the_returned_objects_can_be_imported_for_type_hints():
    for name in ("Query", "ResolvedRequest", "Asset", "MissingStep", "DownloadResult"):
        assert name in dwdopen.__all__
        assert hasattr(dwdopen, name)
        assert hasattr(dwdopen.nwp, name)


def test_a_run_prints_as_its_reference_time():
    assert repr(Run.coerce("2026-10-22T06:00")) == "Run(2026-10-22T06:00Z)"
    assert repr([Run.coerce("2026-10-22T00:00")]) == "[Run(2026-10-22T00:00Z)]"


def test_a_query_prints_like_the_select_call_that_built_it():
    query = Query(
        None,
        "icon-eu",
        parameters=("T", "U"),
        steps=Every("0h", "12h", "3h"),
        level_type=LevelType.coerce("pressure"),
        levels=[850, 500],
    )
    assert repr(query) == (
        "Query('icon-eu', ['T', 'U'], "
        "steps=Every(start='0h', stop='12h', every='3h'), "
        "level_type='pressure', levels=[850, 500])"
    )


def test_a_query_shows_members_and_wavelengths_when_given():
    members = Query(None, "icon-eu-eps", parameters=("T_2M",), members=Between(1, 5))
    assert repr(members) == (
        "Query('icon-eu-eps', ['T_2M'], members=Between(start=1, stop=5))"
    )
    art = Query(None, "icon-art", parameters=("SAT_BSC_DUST",), wavelengths=532)
    assert repr(art) == "Query('icon-art', ['SAT_BSC_DUST'], wavelengths=532)"
