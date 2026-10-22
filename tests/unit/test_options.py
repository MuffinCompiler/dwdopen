"""A mistyped option raises instead of being silently taken as something else.

require="full" used to run as "partial", and members=[1] on a deterministic
model was ignored.
"""

from contextlib import nullcontext
from datetime import timedelta

import pytest

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.model import Model
from dwdopen.nwp.query import Query
from dwdopen.nwp.request import Asset, ResolvedRequest
from dwdopen.nwp.run import Run

RUN = Run.coerce("2026-10-22T00:00")


class Offline:
    """A catalogue that must not be asked: the check comes first."""

    def snapshot(self):
        return nullcontext()

    def __getattr__(self, name):
        raise AssertionError(f"the catalogue was asked for {name}()")


class Deterministic:
    """T_2M of a deterministic model, one step, no members."""

    def snapshot(self):
        return nullcontext()

    def wavelengths(self, model, parameter):
        return []

    def members(self, model, parameter, run, **kw):
        return []

    def assets(self, model, parameter, run, **kw):
        return [
            Asset(
                keys=(("m", model), ("p", parameter)),
                run=run,
                step=timedelta(0),
                path="x",
            )
        ]


def offline_query():
    return Query(Offline(), "icon-eu", parameters=("T_2M",), steps="0h")


def test_a_mistyped_require_raises():
    with pytest.raises(InvalidSelectorError, match="'complete', 'partial'"):
        offline_query().resolve(run=RUN, require="full")


def test_a_mistyped_require_raises_in_latest_run_too():
    with pytest.raises(InvalidSelectorError, match="require='full'"):
        offline_query().latest_run(require="full")


def test_a_mistyped_combine_raises_before_resolving():
    with pytest.raises(InvalidSelectorError, match="combine='al'"):
        offline_query().download("out.grib2", run=RUN, combine="al")


def test_a_mistyped_combine_raises_on_a_plan():
    plan = ResolvedRequest(run=RUN, assets=(), resolved_at=RUN.reference_time)
    with pytest.raises(InvalidSelectorError, match="'member', 'parameter'"):
        plan.download("out.grib2", combine="al")


@pytest.mark.parametrize(
    "selector",
    [{"levels": "850"}, {"members": "1"}, {"wavelengths": "532"}],
)
def test_a_word_other_than_all_is_refused(selector):
    model = Model("icon-eu", Offline())
    with pytest.raises(InvalidSelectorError, match="Give numbers"):
        model.select(parameters="T_2M", **selector)


def test_members_on_a_deterministic_model_raise():
    query = Query(Deterministic(), "icon-eu", parameters=("T_2M",), members=[1])
    with pytest.raises(InvalidSelectorError, match="no ensemble members"):
        query.resolve(run=RUN)


def test_no_members_on_a_deterministic_model_is_fine():
    query = Query(Deterministic(), "icon-eu", parameters=("T_2M",))
    assert len(query.resolve(run=RUN).assets) == 1
