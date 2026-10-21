"""ICON-ART wavelengths: the wvl1/<nm> segment between p and lvt1.

Only a few ICON-ART parameters (SAT_BSC_DUST, CEIL_BSC_DUST) have it, so
everything here must stay out of the way of every other parameter.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from dwdopen._fileserver.naming import local_name
from dwdopen._fileserver.traversal import OpenDataCatalogue
from dwdopen.exceptions import (
    CatalogueUnavailableError,
    IncompleteRunError,
    InvalidSelectorError,
)
from dwdopen.nwp.model import Model
from dwdopen.nwp.selectors import LevelType

RUN = "2026-10-20T12:00"
MODEL = LevelType.coerce("model")


def listing(*names):
    """A directory listing as nginx writes it. Names ending in / are
    directories, the others are files of 100 bytes."""
    lines = ['<pre><a href="../">../</a>']
    for name in names:
        size = "-" if name.endswith("/") else "100"
        lines.append(f'<a href="{name}">{name}</a>    20-Oct-2026 13:00:00    {size}')
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


def art_pages(hole=None):
    """SAT_BSC_DUST on two wavelengths and two model levels, steps 0h and 6h,
    plus a plain T_2M. ``hole`` is a (wavelength, level) lacking the 6h step.
    """
    pages = {
        "m/icon-art/p/": listing("SAT_BSC_DUST/", "T_2M/"),
        "m/icon-art/p/T_2M/": listing("r/"),
        "m/icon-art/p/T_2M/r/": listing(f"{RUN}/"),
        f"m/icon-art/p/T_2M/r/{RUN}/": listing("s/"),
        f"m/icon-art/p/T_2M/r/{RUN}/s/": listing("PT000H00M.grib2"),
        "m/icon-art/p/SAT_BSC_DUST/": listing("wvl1/"),
        "m/icon-art/p/SAT_BSC_DUST/wvl1/": listing("1064/", "532/"),
    }
    for wavelength in (532, 1064):
        base = f"m/icon-art/p/SAT_BSC_DUST/wvl1/{wavelength}"
        pages[f"{base}/"] = listing("lvt1/")
        pages[f"{base}/lvt1/"] = listing("150/")
        pages[f"{base}/lvt1/150/lv1/"] = listing("89/", "90/")
        for level in (89, 90):
            run = f"{base}/lvt1/150/lv1/{level}/r/{RUN}"
            steps = ["PT000H00M.grib2", "PT006H00M.grib2"]
            if hole == (wavelength, level):
                steps = steps[:1]
            pages[f"{base}/lvt1/150/lv1/{level}/r/"] = listing(f"{RUN}/")
            pages[f"{run}/"] = listing("s/")
            pages[f"{run}/s/"] = listing(*steps)
    return pages


def art_model(hole=None):
    return Model("icon-art", OpenDataCatalogue(ScriptedHttp(art_pages(hole))))


def test_the_wavelengths_of_a_parameter_are_listed():
    model = art_model()
    assert model.parameter("SAT_BSC_DUST").wavelengths == (532, 1064)
    assert model.parameter("T_2M").wavelengths == ()


def test_the_level_type_is_found_below_the_wavelength():
    model = art_model()
    assert model.parameter("SAT_BSC_DUST").level_types == (MODEL,)
    assert model.levels("SAT_BSC_DUST", "model") == [Decimal(89), Decimal(90)]


def test_leaving_out_wavelengths_means_all_of_them():
    query = art_model().select(parameters="SAT_BSC_DUST", levels="all")
    plan = query.resolve(run=RUN)
    assert len(plan.assets) == 2 * 2 * 2
    assert {asset.wavelength for asset in plan.assets} == {532, 1064}


def test_one_wavelength_can_be_chosen():
    query = art_model().select(
        parameters="SAT_BSC_DUST", levels=[90], steps="6h", wavelengths=532
    )
    [asset] = query.resolve(run=RUN).assets
    assert asset.wavelength == 532
    assert asset.path == (
        f"weather/nwp/v1/m/icon-art/p/SAT_BSC_DUST/wvl1/532/lvt1/150/lv1/90"
        f"/r/{RUN}/s/PT006H00M.grib2"
    )
    assert "wvl1-532" in local_name(asset.keys)
    assert "532 nm" in repr(asset)


def test_a_parameter_without_wavelengths_is_untouched():
    plan = art_model().select(parameters="T_2M").resolve(run=RUN)
    [asset] = plan.assets
    assert asset.wavelength is None
    assert "wvl1" not in asset.path
    assert "nm" not in repr(asset)


def test_wavelengths_for_a_parameter_without_them_are_refused():
    with pytest.raises(InvalidSelectorError, match="T_2M"):
        art_model().select(parameters="T_2M", wavelengths=532)


def test_an_unknown_wavelength_is_refused():
    query = art_model().select(
        parameters="SAT_BSC_DUST", levels="all", wavelengths=600
    )
    with pytest.raises(InvalidSelectorError, match="532, 1064"):
        query.resolve(run=RUN)


def test_a_hole_on_one_wavelength_names_that_wavelength():
    query = art_model(hole=(532, 90)).select(parameters="SAT_BSC_DUST", levels="all")
    with pytest.raises(
        IncompleteRunError, match=r"SAT_BSC_DUST 532 nm 6h \(1 of 2 levels\)"
    ):
        query.resolve(run=RUN)

    plan = query.resolve(run=RUN, require="partial")
    [gap] = plan.missing
    assert (gap.wavelength, gap.level, gap.step) == (
        532, Decimal(90), timedelta(hours=6)
    )


def test_both_wavelengths_land_in_time_order():
    plan = art_model().select(parameters="SAT_BSC_DUST", levels=[90]).resolve(run=RUN)
    order = [(asset.step, asset.wavelength) for asset in plan.assets]
    assert order == [
        (timedelta(0), 532),
        (timedelta(0), 1064),
        (timedelta(hours=6), 532),
        (timedelta(hours=6), 1064),
    ]


def test_latest_run_works_for_a_parameter_with_wavelengths():
    query = art_model().select(parameters="SAT_BSC_DUST", levels="all")
    assert str(query.latest_run(settle=timedelta(0))).startswith("2026-10-20T12")
