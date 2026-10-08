"""How long a listing may be reused.

The server is volatile: steps appear while a run is published and whole runs
vanish after about a day. The split that makes caching safe is the layout's own:
everything above r/ is a union over the runs present, so it only changes when
DWD changes a model, while r/ and below is availability and is kept no longer
than the operation that read it.
"""

import threading
from datetime import timedelta

import pytest

from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import CatalogueUnavailableError
from dwdopen.nwp.model import Model
from dwdopen.nwp.run import Run

RUN = Run.coerce("2026-09-16T00:00")

PARAMETERS = """<pre><a href="../">../</a>
<a href="T_2M/">T_2M/</a>    21-Aug-2026 12:06:25    -
<a href="PS/">PS/</a>        21-Aug-2026 12:06:25    -
<a href="CLCT/">CLCT/</a>    21-Aug-2026 12:06:25    -
</pre>"""

PLAIN_PARAMETER = """<pre><a href="../">../</a>
<a href="r/">r/</a>    18-Sep-2026 11:56:47    -
</pre>"""

RUNS = """<pre><a href="../">../</a>
<a href="2026-09-16T00%3A00/">2026-09-16T00:00/</a>    16-Sep-2026 02:40:29    -
</pre>"""

DETERMINISTIC_RUN = """<pre><a href="../">../</a>
<a href="s/">s/</a>    18-Sep-2026 09:08:39    -
</pre>"""

STEPS = """<pre><a href="../">../</a>
<a href="PT000H00M.grib2">PT000H00M.grib2</a>    16-Sep-2026 02:40:29    877797
<a href="PT003H00M.grib2">PT003H00M.grib2</a>    16-Sep-2026 02:41:29    864536
</pre>"""

NAMES = ("T_2M", "PS", "CLCT")


class Scripted:
    """Serves the mapped listing for a path and counts every read.

    ``pages`` stays writable so a test can publish something late, which is how
    the retry case is set up.
    """

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = {f"weather/nwp/v1/{p}": html for p, html in pages.items()}
        self.paths: list[str] = []

    def get_listing(self, path: str) -> str:
        self.paths.append(path)
        if path not in self.pages:
            raise CatalogueUnavailableError(f"could not read {path}: 404")
        return self.pages[path]

    def publish(self, path: str, html: str) -> None:
        self.pages[f"weather/nwp/v1/{path}"] = html

    def reads(self, path: str) -> int:
        return self.paths.count(f"weather/nwp/v1/{path}")

    def close(self) -> None:
        pass


def pages(names: tuple[str, ...] = NAMES) -> dict[str, str]:
    """Every listing a deterministic multi-parameter lookup walks through."""
    built = {"m/icon-eu/p/": PARAMETERS}
    for name in names:
        base = f"m/icon-eu/p/{name}"
        built[f"{base}/"] = PLAIN_PARAMETER
        built[f"{base}/r/"] = RUNS
        built[f"{base}/r/2026-09-16T00:00/"] = DETERMINISTIC_RUN
        built[f"{base}/r/2026-09-16T00:00/s/"] = STEPS
    return built


def test_structural_listings_outlive_the_operation_that_read_them():
    """A parameter list only changes when DWD changes the model."""
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)

    with catalogue.snapshot():
        catalogue.parameters("icon-eu")
    with catalogue.snapshot():
        catalogue.parameters("icon-eu")
    catalogue.parameters("icon-eu")

    assert http.reads("m/icon-eu/p/") == 1


def test_refresh_drops_the_structural_cache():
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)

    catalogue.parameters("icon-eu")
    catalogue.refresh()
    catalogue.parameters("icon-eu")

    assert http.reads("m/icon-eu/p/") == 2


def test_run_availability_is_reused_inside_one_operation():
    """One resolve() must see one view of the server, not a shifting one."""
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)

    with catalogue.snapshot():
        catalogue.runs("icon-eu", parameter="T_2M")
        catalogue.runs("icon-eu", parameter="T_2M")

    assert http.reads("m/icon-eu/p/T_2M/r/") == 1


def test_run_availability_is_re_read_by_the_next_operation():
    """The whole point: a retry reads the server again, however soon it comes."""
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)

    with catalogue.snapshot():
        catalogue.runs("icon-eu", parameter="T_2M")
    with catalogue.snapshot():
        catalogue.runs("icon-eu", parameter="T_2M")

    assert http.reads("m/icon-eu/p/T_2M/r/") == 2


def test_an_operation_keeps_its_view_when_another_one_finishes():
    """Two threads may resolve against one client. Whichever finishes first must
    not drop the listings the other is still working from, which is why the
    holders are counted rather than flagged."""
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)
    runs = "m/icon-eu/p/T_2M/r/"
    finished = threading.Event()

    def other() -> None:
        with catalogue.snapshot():
            catalogue.runs("icon-eu", parameter="T_2M")
        finished.set()

    with catalogue.snapshot():
        catalogue.runs("icon-eu", parameter="T_2M")
        thread = threading.Thread(target=other)
        thread.start()
        assert finished.wait(5), "the other operation never finished"
        thread.join()
        # That operation is over, but ours is still open and still ours.
        catalogue.runs("icon-eu", parameter="T_2M")

    assert http.reads(runs) == 1
    # Now that the last holder is gone, the next read goes to the server.
    catalogue.runs("icon-eu", parameter="T_2M")
    assert http.reads(runs) == 2


def test_nesting_shares_the_outermost_view():
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)

    with catalogue.snapshot():
        catalogue.runs("icon-eu", parameter="T_2M")
        with catalogue.snapshot():
            catalogue.runs("icon-eu", parameter="T_2M")
        # Leaving the inner block must not throw the outer view away.
        catalogue.runs("icon-eu", parameter="T_2M")

    assert http.reads("m/icon-eu/p/T_2M/r/") == 1


def test_a_missing_step_listing_is_never_remembered_as_missing():
    """A run that is not published yet must not be cached as absent.

    This is the case that makes a time based cache unusable here: the answer
    changes within minutes, and a remembered 404 would survive the retry.
    """
    incomplete = pages(("T_2M",))
    steps = "m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/"
    del incomplete[steps]
    http = Scripted(incomplete)
    catalogue = OpenDataCatalogue(http)

    with pytest.raises(CatalogueUnavailableError):
        catalogue.assets("icon-eu", "T_2M", RUN)

    http.publish(steps, STEPS)
    assert len(catalogue.assets("icon-eu", "T_2M", RUN)) == 2


def test_resolving_reads_every_listing_it_can_keep_only_once():
    """The regression guard. Before the cache a 14 parameter job spent 142
    requests on 28 distinct listings, mostly re-reading the run listing.

    Only listings that exist count here. A 404 is deliberately never kept, so
    the probes below are expected to repeat.
    """
    http = Scripted(pages())
    catalogue = OpenDataCatalogue(http)
    model = Model("icon-eu", catalogue)

    plan = model.select(parameters=list(NAMES)).resolve()

    assert len(plan.assets) == 6
    served = [path for path in http.paths if path in http.pages]
    repeated = {path for path in served if served.count(path) > 1}
    assert not repeated, f"listed more than once: {sorted(repeated)}"


def test_the_member_probe_is_the_one_request_that_still_repeats():
    """A deterministic model has no e/ directory, so every probe for one 404s,
    and a 404 must not be remembered. That leaves one probe per parameter per
    pass as the only repetition the cache does not remove, which is what the
    TODO in Query is about.
    """
    http = Scripted(pages())
    model = Model("icon-eu", OpenDataCatalogue(http))

    model.select(parameters=list(NAMES)).resolve()

    probes = [path for path in http.paths if path.endswith("/e/")]
    assert sorted(set(probes)) == sorted(
        f"weather/nwp/v1/m/icon-eu/p/{name}/r/2026-09-16T00:00/e/"
        for name in NAMES
    )
    assert len(probes) > len(set(probes)), "a failed listing was cached"


def test_resolving_twice_over_costs_one_read_of_each_listing():
    """resolve() without a run resolves every candidate to find the newest and
    then resolves the winner again. Both passes sit inside one snapshot, so the
    second is served from the cache and the run is read once.
    """
    http = Scripted(pages())
    model = Model("icon-eu", OpenDataCatalogue(http))

    plan = model.select(parameters=["T_2M"], steps=["0h", "3h"]).resolve()

    assert plan.run == RUN
    assert [asset.step for asset in plan.assets] == [
        timedelta(0), timedelta(hours=3)
    ]
    assert http.reads("m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/") == 1
    assert http.reads("m/icon-eu/p/T_2M/r/") == 1
