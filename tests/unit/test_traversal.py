from datetime import timedelta

import pytest

from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import CatalogueUnavailableError, RunExpiredError
from dwdopen.nwp.run import Run

MODELS = """<pre><a href="../">../</a>
<a href="icon-eu/">icon-eu/</a>    24-Aug-2026 09:55:26    -
<a href="aicon/">aicon/</a>        24-Aug-2026 09:55:26    -
</pre>"""

RUNS = """<pre><a href="../">../</a>
<a href="2026-09-16T00%3A00/">2026-09-16T00:00/</a>    16-Sep-2026 02:40:29    -
<a href="2026-09-15T18%3A00/">2026-09-15T18:00/</a>    15-Sep-2026 20:38:28    -
</pre>"""

# What .../p/<NAME>/ looks like: just r/ for a 2-D field, lvt1/ for a 3-D one.
PLAIN_PARAMETER = """<pre><a href="../">../</a>
<a href="r/">r/</a>    18-Sep-2026 11:56:47    -
</pre>"""

MULTI_LEVEL_PARAMETER = """<pre><a href="../">../</a>
<a href="lvt1/">lvt1/</a>    21-Aug-2026 12:06:28    -
</pre>"""

# What .../r/<run>/ looks like: s/ deterministic, e/ for an ensemble.
DETERMINISTIC_RUN = """<pre><a href="../">../</a>
<a href="s/">s/</a>    18-Sep-2026 09:08:39    -
</pre>"""

ENSEMBLE_RUN = """<pre><a href="../">../</a>
<a href="e/">e/</a>    18-Sep-2026 08:41:05    -
</pre>"""

STEPS = """<pre><a href="../">../</a>
<a href="PT000H00M.grib2">PT000H00M.grib2</a>    16-Sep-2026 02:40:29    877797
<a href="PT003H00M.grib2">PT003H00M.grib2</a>    16-Sep-2026 02:41:29    864536
</pre>"""


class FakeHttp:
    def __init__(self, html: str) -> None:
        self.html = html
        self.paths: list[str] = []
        self.closed = False

    def get_listing(self, path: str) -> str:
        self.paths.append(path)
        return self.html

    def close(self) -> None:
        self.closed = True


class ScriptedHttp:
    """Answers each path with the listing mapped to it.

    Unlike FakeHttp this distinguishes the levels of the tree, which is what
    the guards against 3-D and ensemble parameters need to be tested against.
    """

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = {f"weather/nwp/v1/{path}": html for path, html in pages.items()}
        self.paths: list[str] = []

    def get_listing(self, path: str) -> str:
        self.paths.append(path)
        if path not in self.pages:
            # What nginx does for a path that is not there, which is how the
            # catalogue finds out that a parameter is not plain 2-D.
            raise CatalogueUnavailableError(f"could not read {path}: 404")
        return self.pages[path]

    def close(self) -> None:
        pass


def deterministic_pages(parameter: str = "T_2M") -> dict[str, str]:
    """The four listings a single-level deterministic lookup walks through."""
    base = f"m/icon-eu/p/{parameter}"
    return {
        f"{base}/": PLAIN_PARAMETER,
        f"{base}/r/": RUNS,
        f"{base}/r/2026-09-16T00:00/": DETERMINISTIC_RUN,
        f"{base}/r/2026-09-16T00:00/s/": STEPS,
    }


def test_models_are_sorted_and_come_from_the_m_listing():
    http = FakeHttp(MODELS)
    assert OpenDataCatalogue(http).models() == ["aicon", "icon-eu"]
    assert http.paths == ["weather/nwp/v1/m/"]


def test_parameters_addresses_the_right_path():
    http = FakeHttp(MODELS)
    OpenDataCatalogue(http).parameters("icon-eu")
    assert http.paths == ["weather/nwp/v1/m/icon-eu/p/"]


def test_runs_are_parsed_as_utc_and_ordered_oldest_first():
    http = ScriptedHttp(deterministic_pages())
    runs = OpenDataCatalogue(http).runs("icon-eu", probe="T_2M")
    assert runs == [Run.coerce("2026-09-15T18:00"), Run.coerce("2026-09-16T00:00")]
    assert http.paths[-1] == "weather/nwp/v1/m/icon-eu/p/T_2M/r/"


def test_runs_without_a_probe_says_so():
    with pytest.raises(NotImplementedError, match="probe"):
        OpenDataCatalogue(FakeHttp(RUNS)).runs("icon-eu")


def test_assets_are_built_from_the_step_listing():
    catalogue = OpenDataCatalogue(ScriptedHttp(deterministic_pages()))
    assets = catalogue.assets("icon-eu", "T_2M", Run.coerce("2026-09-16T00:00"))

    assert [asset.step for asset in assets] == [timedelta(), timedelta(hours=3)]
    assert assets[0].path == (
        "weather/nwp/v1/m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/PT000H00M.grib2"
    )
    assert assets[0].parameter == "T_2M"
    assert assets[0].size == 877797


def test_assets_of_an_expired_run_say_so():
    catalogue = OpenDataCatalogue(ScriptedHttp(deterministic_pages()))
    with pytest.raises(RunExpiredError, match="2026-01-01"):
        catalogue.assets("icon-eu", "T_2M", Run.coerce("2026-01-01T00:00"))


def test_a_multi_level_parameter_says_what_is_there_instead():
    # .../p/T/r/ does not exist: the runs sit below lvt1/<type>/lv1/<level>/.
    http = ScriptedHttp({"m/icon-eu/p/T/": MULTI_LEVEL_PARAMETER})
    with pytest.raises(NotImplementedError, match="contains lvt1/, not r/"):
        OpenDataCatalogue(http).runs("icon-eu", probe="T")


def test_an_ensemble_says_what_is_there_instead():
    # .../r/<run>/s/ does not exist for an ensemble: e/<member>/ comes first,
    # so the step files are one level deeper rather than absent.
    http = ScriptedHttp(
        {
            "m/icon-eu-eps/p/T_2M/": PLAIN_PARAMETER,
            "m/icon-eu-eps/p/T_2M/r/": RUNS,
            "m/icon-eu-eps/p/T_2M/r/2026-09-16T00:00/": ENSEMBLE_RUN,
        }
    )
    with pytest.raises(NotImplementedError, match="contains e/, not s/"):
        OpenDataCatalogue(http).assets(
            "icon-eu-eps", "T_2M", Run.coerce("2026-09-16T00:00")
        )


def test_a_genuine_outage_stays_a_catalogue_error():
    # r/ is where it should be, so the failure is not about the layout and
    # must not be dressed up as an unsupported selection.
    http = ScriptedHttp({"m/icon-eu/p/T_2M/": PLAIN_PARAMETER})
    with pytest.raises(CatalogueUnavailableError):
        OpenDataCatalogue(http).runs("icon-eu", probe="T_2M")


def test_the_happy_path_costs_no_extra_listing():
    http = ScriptedHttp(deterministic_pages())
    OpenDataCatalogue(http).assets("icon-eu", "T_2M", Run.coerce("2026-09-16T00:00"))
    assert http.paths == [
        "weather/nwp/v1/m/icon-eu/p/T_2M/r/",
        "weather/nwp/v1/m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/",
    ]


def test_an_unreadable_listing_raises_instead_of_looking_empty():
    with pytest.raises(CatalogueUnavailableError, match="weather/nwp/v1/m/"):
        OpenDataCatalogue(FakeHttp("<html>something else</html>")).models()


def test_close_closes_the_client():
    http = FakeHttp(MODELS)
    OpenDataCatalogue(http).close()
    assert http.closed
