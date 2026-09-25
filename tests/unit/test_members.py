"""Ensemble members.

The e/<NN>/ segment sits between the run and the steps, and its tokens are
zero-padded (01..40) while the level tokens next door are not (85000, 72). So
members follow the same rule as runs and levels: the token comes from the
listing, never from formatting a number.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from dwdopen.exceptions import InvalidSelectorError
from dwdopen.nwp.query import _select_members
from dwdopen.nwp.request import Asset, ResolvedRequest
from dwdopen.nwp.run import Run
from dwdopen.nwp.selectors import Between, Every, LevelType

RUN = Run.coerce("2026-09-25T09:00")
NOW = datetime(2026, 9, 25, 11, tzinfo=UTC)
MODEL = LevelType.coerce("model")
TWENTY = list(range(1, 21))


# --- selecting ------------------------------------------------------------

def test_all_takes_every_member():
    assert _select_members(TWENTY, "all") == TWENTY
    assert _select_members(TWENTY, None) == TWENTY


def test_a_list_and_a_scalar():
    assert _select_members(TWENTY, [1, 5, 9]) == [1, 5, 9]
    assert _select_members(TWENTY, 7) == [7]


def test_between_is_inclusive():
    assert _select_members(TWENTY, Between(3, 6)) == [3, 4, 5, 6]


def test_every_expands_a_cadence():
    assert _select_members(TWENTY, Every(1, 9, 4)) == [1, 5, 9]


def test_a_member_that_does_not_exist_names_the_real_range():
    # icon-d2-eps has 20, icon-eps 40, icon-art-eps 10, so the count is not
    # something a caller can be expected to know.
    with pytest.raises(InvalidSelectorError, match=r"1\.\.20"):
        _select_members(TWENTY, [25])


# --- the token padding ----------------------------------------------------

class FakeHttp:
    """Serves the listings one ensemble lookup walks through."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def get_listing(self, path: str) -> str:
        self.paths.append(path)
        if path.endswith("/r/"):
            return (
                '<pre><a href="2026-09-25T09%3A00/">x</a> 25-Sep-2026 09:00:00 -</pre>'
            )
        if path.endswith("/e/"):
            # Padded, exactly as the server writes them.
            rows = "".join(
                f'<a href="{n:02d}/">x</a> 25-Sep-2026 09:00:00 -\n' for n in (1, 2, 10)
            )
            return f"<pre>{rows}</pre>"
        raise AssertionError(f"unexpected path {path}")

    def close(self) -> None:
        pass


def catalogue():
    from dwdopen._fileserver.traversal import OpenDataCatalogue

    http = FakeHttp()
    return OpenDataCatalogue(http), http


def test_members_are_read_as_numbers():
    cat, _ = catalogue()
    assert cat.members("icon-d2-eps", "T_2M", RUN) == [1, 2, 10]


def test_the_padded_token_is_kept_not_rebuilt():
    """Formatting a number back would have to know that members pad and
    levels do not."""
    cat, _ = catalogue()
    tokens = cat._member_tokens("icon-d2-eps", "T_2M", RUN, None, None)
    assert tokens[1] == "01"
    assert tokens[10] == "10"


def test_a_deterministic_model_reports_no_members():
    class NoMembers(FakeHttp):
        def get_listing(self, path: str) -> str:
            if path.endswith("/e/"):
                raise __import__(
                    "dwdopen.exceptions", fromlist=["x"]
                ).CatalogueUnavailableError("404")
            return super().get_listing(path)

    from dwdopen._fileserver.traversal import OpenDataCatalogue

    assert OpenDataCatalogue(NoMembers()).members("icon-eu", "T_2M", RUN) == []


# --- ordering and naming --------------------------------------------------

def asset(member=None, hours=0, level=None):
    return Asset(
        keys=(("m", "icon-d2-eps"), ("p", "T_2M")),
        run=RUN,
        step=timedelta(hours=hours),
        path=f"x/{member}/{hours}/{level}",
        size=1000,
        level_type=None if level is None else MODEL,
        level=None if level is None else Decimal(level),
        member=member,
    )


def plan(assets):
    return ResolvedRequest(run=RUN, assets=tuple(assets), resolved_at=NOW)


def test_members_sort_within_a_step_so_the_order_stays_time_major():
    # CDO reads a multi-member file correctly in this order: it sees each
    # member as its own variable and timmean keeps them all.
    assets = [asset(m, h) for h in (1, 0) for m in (3, 1, 2)]
    ordered = sorted(assets, key=Asset.sort_key)
    assert [(a.step.seconds // 3600, a.member) for a in ordered] == [
        (0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3),
    ]


def test_one_member_is_named_in_the_file():
    # This is what makes combine="member" files tellable apart.
    assert "_e01_" in plan([asset(1)]).suggested_name()


def test_several_members_are_counted():
    assert "_3mem_" in plan([asset(m) for m in (1, 2, 3)]).suggested_name()


def test_a_deterministic_plan_has_no_member_field_in_the_name():
    name = plan([asset()]).suggested_name()
    assert "_e0" not in name
    assert "mem" not in name


def test_the_repr_reports_members():
    assert "3 members" in repr(plan([asset(m) for m in (1, 2, 3)]))
    assert "member 2" in repr(plan([asset(2)]))
