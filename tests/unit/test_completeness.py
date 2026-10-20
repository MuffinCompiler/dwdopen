"""require="complete" means every requested field exists, on every level and
member, not just somewhere.

The Met.3D NRT client is the real case: W on 120 model levels, +180h published
for only 96 of them, and the run was still accepted as complete.
"""

from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal

import pytest

from dwdopen.exceptions import IncompleteRunError
from dwdopen.nwp.query import Query
from dwdopen.nwp.request import Asset
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import Every, LevelType

RUN = Run.coerce("2026-10-16T00:00")
MODEL = LevelType.coerce("model")


class Catalogue:
    """Serves the fields given as (level, member, hours) triples."""

    def __init__(self, fields, levels=(), members=()):
        self.fields = fields
        self.level_values = [Decimal(level) for level in levels]
        self.member_values = list(members)

    def snapshot(self):
        return nullcontext()

    def levels(self, model, parameter, level_type):
        return self.level_values

    def members(self, model, parameter, run, *, level_type=None, level=None):
        return self.member_values

    def assets(self, model, parameter, run, *, level_type=None, levels=None,
               members=None):
        return [
            Asset(
                keys=(("p", parameter), ("l", str(level)), ("s", str(hours))),
                run=run,
                step=timedelta(hours=hours),
                path=f"{parameter}/{level}/{member}/{hours}",
                level_type=None if level is None else MODEL,
                level=None if level is None else Decimal(level),
                member=member,
            )
            for level, member, hours in self.fields
        ]


def on_levels(fields, steps, levels=(1, 2, 3)):
    return Query(
        Catalogue(fields, levels=levels),
        "icon",
        parameters=("W",),
        steps=steps,
        level_type=MODEL,
        levels="all",
    )


# Three levels, steps 0/3/6h, level 3 not yet published at +6h.
HOLE = [(level, None, hours) for level in (1, 2, 3) for hours in (0, 3, 6)
        if not (level == 3 and hours == 6)]


def test_a_named_step_missing_on_one_level_is_incomplete():
    query = on_levels(HOLE, Every("0h", "6h", "3h"))
    with pytest.raises(IncompleteRunError, match=r"W 6h \(1 of 3 levels\)"):
        query.resolve(run=RUN)


def test_all_notices_a_step_that_only_some_levels_have():
    with pytest.raises(IncompleteRunError, match=r"W 6h \(1 of 3 levels\)"):
        on_levels(HOLE, "all").resolve(run=RUN)


def test_partial_downloads_what_exists_and_names_the_gap():
    plan = on_levels(HOLE, "all").resolve(run=RUN, require="partial")
    assert len(plan.assets) == 8
    assert len(plan.missing) == 1
    gap = plan.missing[0]
    assert (gap.step, gap.level, gap.member) == (timedelta(hours=6), Decimal(3), None)


def test_all_cannot_notice_a_step_no_level_has_yet():
    """The limit of "all": the server gives no list of expected steps. Naming
    the steps is the way to be sure."""
    shorter = [(level, None, hours) for level in (1, 2, 3) for hours in (0, 3)]
    assert len(on_levels(shorter, "all").resolve(run=RUN).assets) == 6

    with pytest.raises(IncompleteRunError, match=r"W 6h"):
        on_levels(shorter, Every("0h", "6h", "3h")).resolve(run=RUN)


def test_a_step_missing_everywhere_is_one_entry():
    shorter = [(level, None, hours) for level in (1, 2, 3) for hours in (0, 3)]
    plan = on_levels(shorter, ["0h", "6h"]).resolve(run=RUN, require="partial")
    assert len(plan.missing) == 1
    assert plan.missing[0].level is None and plan.missing[0].member is None


def test_a_member_missing_a_step_is_named():
    fields = [(None, member, hours) for member in (1, 2) for hours in (0, 3)
              if not (member == 2 and hours == 3)]
    query = Query(
        Catalogue(fields, members=(1, 2)),
        "icon-eps",
        parameters=("T_2M",),
        steps="all",
        members="all",
    )
    with pytest.raises(IncompleteRunError, match=r"T_2M 3h \(1 of 2 members\)"):
        query.resolve(run=RUN)

    plan = query.resolve(run=RUN, require="partial")
    assert plan.missing[0].member == 2
