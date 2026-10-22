"""Every failure a user can run into is a DWDOpenError, and paths given as
"~/..." mean the home directory.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from dwdopen import DWD
from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import (
    CatalogueUnavailableError,
    ClientClosedError,
    DWDOpenError,
)
from dwdopen.nwp.model import Model
from dwdopen.nwp.request import Asset, Fetched, ResolvedRequest
from dwdopen.nwp.run import Run

RUN = Run.coerce("2026-10-22T00:00")


def listing(*names):
    lines = ['<pre><a href="../">../</a>']
    for name in names:
        lines.append(f'<a href="{name}">{name}</a>    22-Oct-2026 01:00:00    -')
    lines.append("</pre>")
    return "\n".join(lines)


class ScriptedHttp:
    def __init__(self, pages):
        self.pages = {f"weather/nwp/v1/{path}": html for path, html in pages.items()}

    def get_listing(self, path):
        if path not in self.pages:
            raise CatalogueUnavailableError(f"could not read {path}: 404")
        return self.pages[path]

    def close(self):
        pass


def test_the_runs_of_a_3d_parameter_are_read_below_its_first_level():
    """There is no r/ below p/T/: the runs sit below lvt1/<type>/lv1/<level>/."""
    base = "m/icon-eu/p/T"
    pages = {
        "m/icon-eu/p/": listing("T/"),
        f"{base}/": listing("lvt1/"),
        f"{base}/lvt1/": listing("100/", "150/"),
        f"{base}/lvt1/100/lv1/": listing("50000/", "85000/"),
        f"{base}/lvt1/100/lv1/50000/r/": listing("2026-10-22T00:00/"),
    }
    model = Model("icon-eu", OpenDataCatalogue(ScriptedHttp(pages)))
    assert model.runs(parameter="T") == [RUN]


def test_an_unexpected_layout_is_a_dwdopen_error():
    pages = {"m/icon-eu/p/T/": listing("lvt1/")}
    catalogue = OpenDataCatalogue(ScriptedHttp(pages))
    with pytest.raises(DWDOpenError, match="contains lvt1/, not r/"):
        catalogue.runs("icon-eu", parameter="T")


def test_a_closed_client_says_so():
    client = HttpClient("https://example.test")
    client.close()
    with pytest.raises(ClientClosedError, match="with DWD"):
        client.get_listing("weather/nwp/v1/m/")
    with pytest.raises(ClientClosedError):
        client.get_asset("weather/nwp/v1/m/x.grib2")


def test_a_model_used_after_the_with_block_says_so():
    with DWD() as dwd:
        http = dwd._ensure_http()
        catalogue = dwd._ensure_catalogue()
    model = Model("icon-eu", catalogue)
    assert http._closed
    with pytest.raises(ClientClosedError):
        model.parameters()


class RecordingDownloader:
    def __init__(self):
        self.destinations = []

    def fetch(self, assets, destination, *, combine="all", temp_dir=None):
        self.destinations.append((destination, temp_dir))
        return Fetched(files=(destination,), bytes_downloaded=0)


def plan_with(downloader):
    asset = Asset(
        keys=(("m", "icon-eu"), ("p", "T"), ("s", "PT000H00M.grib2")),
        run=RUN,
        step=timedelta(0),
        path="x",
        size=1,
        level=Decimal(850),
    )
    return ResolvedRequest(
        run=RUN,
        assets=(asset,),
        resolved_at=RUN.reference_time,
        downloader=downloader,
    )


def test_a_tilde_means_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "data").mkdir()
    downloader = RecordingDownloader()
    plan = plan_with(downloader)

    plan.download("~/data/", temp_dir="~/scratch")

    [(destination, temp_dir)] = downloader.destinations
    assert destination == tmp_path / "data" / plan.suggested_name()
    assert temp_dir == tmp_path / "scratch"
