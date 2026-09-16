from dwdopen._fileserver.catalogue import OpenDataCatalogue
from dwdopen.exceptions import CatalogueUnavailableError
from dwdopen.nwp.run import Run
import pytest

MODELS = """<pre><a href="../">../</a>
<a href="icon-eu/">icon-eu/</a>    24-Aug-2026 09:55:26    -
<a href="aicon/">aicon/</a>        24-Aug-2026 09:55:26    -
</pre>"""

RUNS = """<pre><a href="../">../</a>
<a href="2026-09-16T00%3A00/">2026-09-16T00:00/</a>    16-Sep-2026 02:40:29    -
<a href="2026-09-15T18%3A00/">2026-09-15T18:00/</a>    15-Sep-2026 20:38:28    -
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


def test_models_are_sorted_and_come_from_the_m_listing():
    http = FakeHttp(MODELS)
    assert OpenDataCatalogue(http).models() == ["aicon", "icon-eu"]
    assert http.paths == ["weather/nwp/v1/m/"]


def test_parameters_addresses_the_right_path():
    http = FakeHttp(MODELS)
    OpenDataCatalogue(http).parameters("icon-eu")
    assert http.paths == ["weather/nwp/v1/m/icon-eu/p/"]


def test_runs_are_parsed_as_utc_and_ordered_oldest_first():
    http = FakeHttp(RUNS)
    runs = OpenDataCatalogue(http).runs("icon-eu", probe="T_2M")
    assert runs == [Run.coerce("2026-09-15T18:00"), Run.coerce("2026-09-16T00:00")]
    assert http.paths == ["weather/nwp/v1/m/icon-eu/p/T_2M/r/"]


def test_runs_without_a_probe_says_so():
    with pytest.raises(NotImplementedError, match="probe"):
        OpenDataCatalogue(FakeHttp(RUNS)).runs("icon-eu")


def test_an_unreadable_listing_raises_instead_of_looking_empty():
    with pytest.raises(CatalogueUnavailableError, match="weather/nwp/v1/m/"):
        OpenDataCatalogue(FakeHttp("<html>something else</html>")).models()


def test_close_closes_the_client():
    http = FakeHttp(MODELS)
    OpenDataCatalogue(http).close()
    assert http.closed