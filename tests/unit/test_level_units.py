"""Levels are in one unit wherever a user sees them: hPa for pressure.

The path has Pa (85000), but select() takes hPa (850). Discovery, assets and
missing steps give hPa too, so a value read from one can be passed to another.
"""

from datetime import timedelta
from decimal import Decimal

from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import CatalogueUnavailableError
from dwdopen.nwp.model import Model

RUN = "2026-10-21T12:00"


def listing(*names):
    """A directory listing as nginx writes it. Names ending in / are
    directories, the others are files of 100 bytes."""
    lines = ['<pre><a href="../">../</a>']
    for name in names:
        size = "-" if name.endswith("/") else "100"
        lines.append(f'<a href="{name}">{name}</a>    21-Oct-2026 13:00:00    {size}')
    lines.append("</pre>")
    return "\n".join(lines)


class ScriptedHttp:
    """Answers each path with the listing mapped to it, 404 otherwise."""

    def __init__(self, pages):
        self.pages = {f"weather/nwp/v1/{path}": html for path, html in pages.items()}

    def get_listing(self, path):
        if path not in self.pages:
            raise CatalogueUnavailableError(f"could not read {path}: 404")
        return self.pages[path]

    def close(self):
        pass


def pressure_model():
    """T on 500 and 850 hPa, steps 0h and 3h, with 3h missing on 500 hPa."""
    base = "m/icon-eu/p/T"
    pages = {
        "m/icon-eu/p/": listing("T/"),
        f"{base}/": listing("lvt1/"),
        f"{base}/lvt1/": listing("100/"),
        f"{base}/lvt1/100/lv1/": listing("50000/", "85000/"),
    }
    for level in ("50000", "85000"):
        run = f"{base}/lvt1/100/lv1/{level}/r/{RUN}"
        steps = ["PT000H00M.grib2", "PT003H00M.grib2"]
        if level == "50000":
            steps = steps[:1]
        pages[f"{base}/lvt1/100/lv1/{level}/r/"] = listing(f"{RUN}/")
        pages[f"{run}/"] = listing("s/")
        pages[f"{run}/s/"] = listing(*steps)
    return Model("icon-eu", OpenDataCatalogue(ScriptedHttp(pages)))


def test_discovered_levels_are_in_hpa():
    assert pressure_model().levels("T", "pressure") == [Decimal(500), Decimal(850)]


def test_discovered_levels_can_be_passed_back_to_select():
    model = pressure_model()
    levels = model.levels("T", "pressure")
    plan = model.select(
        parameters="T", level_type="pressure", levels=levels, steps="0h"
    ).resolve(run=RUN)
    assert len(plan.assets) == 2


def test_an_asset_carries_its_level_in_hpa():
    plan = pressure_model().select(
        parameters="T", level_type="pressure", levels=850, steps="0h"
    ).resolve(run=RUN)
    [asset] = plan.assets
    assert asset.level == Decimal(850)
    assert "/lv1/85000/" in asset.path


def test_a_missing_step_names_its_level_in_hpa():
    plan = pressure_model().select(
        parameters="T", level_type="pressure", levels="all"
    ).resolve(run=RUN, require="partial")
    [gap] = plan.missing
    assert (gap.level, gap.step) == (Decimal(500), timedelta(hours=3))
