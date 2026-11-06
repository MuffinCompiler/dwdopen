"""Shared test helpers: a small fake of DWD Open Data for the CLI tests."""

from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal

import pytest

from dwdopen import DWD, LevelType, Run, UnknownModelError, UnknownParameterError
from dwdopen.nwp.request import Asset, Fetched

PRESSURE = LevelType.coerce("pressure")
MODEL_LEVEL = LevelType.coerce("model")

RUNS = [Run.coerce("2026-10-27T00:00"), Run.coerce("2026-10-27T06:00")]
STEPS = [0, 3, 6]
"""Hours published in every run."""

# Model -> parameter -> {level type: levels in server units}. An empty dict
# is a 2-D field.
FIELDS = {
    "icon-eu": {
        "T": {
            PRESSURE: [Decimal(50000), Decimal(85000)],
            MODEL_LEVEL: [Decimal(60), Decimal(61)],
        },
        "T_2M": {},
        "TOT_PREC": {},
    },
    "icon-eu-eps": {
        "T_2M": {},
    },
    "icon-art": {
        "SAT_BSC_DUST": {},
    },
}

MEMBERS = {"icon-eu-eps": [1, 2, 3]}
WAVELENGTHS = {("icon-art", "SAT_BSC_DUST"): [532, 1064]}


class FakeCatalogue:
    """Three models, two runs, steps 0h, 3h and 6h, everything published."""

    def snapshot(self):
        return nullcontext()

    def refresh(self):
        pass

    def close(self):
        """DWD.close() calls this."""

    def models(self):
        return sorted(FIELDS)

    def parameters(self, model):
        if model not in FIELDS:
            raise UnknownModelError(f"unknown model {model!r}")
        return sorted(FIELDS[model])

    def _field(self, model, parameter):
        if parameter not in self.parameters(model):
            raise UnknownParameterError(f"unknown parameter {parameter!r}")
        return FIELDS[model][parameter]

    def runs(self, model, *, parameter=None, level_type=None, level=None,
             wavelength=None):
        self.parameters(model)
        if parameter is not None:
            self._field(model, parameter)
        return list(RUNS)

    def wavelengths(self, model, parameter):
        self._field(model, parameter)
        return WAVELENGTHS.get((model, parameter), [])

    def level_types(self, model, parameter, *, wavelength=None):
        return sorted(self._field(model, parameter), key=lambda lt: lt.code)

    def levels(self, model, parameter, level_type, *, wavelength=None):
        return self._field(model, parameter)[level_type]

    def members(self, model, parameter, run, *, level_type=None, level=None,
                wavelength=None):
        return MEMBERS.get(model, [])

    def assets(self, model, parameter, run, *, level_type=None, levels=None,
               members=None, wavelength=None):
        assets = []
        for level in levels or [None]:
            for member in members or [None]:
                for hours in STEPS:
                    keys = [("m", model), ("p", parameter), ("r", str(run))]
                    if wavelength is not None:
                        keys.append(("w", str(wavelength)))
                    if level is not None:
                        keys.append(("l", str(level)))
                    if member is not None:
                        keys.append(("e", str(member)))
                    keys.append(("s", f"PT{hours:03d}H00M.grib2"))
                    assets.append(Asset(
                        keys=tuple(keys),
                        run=run,
                        step=timedelta(hours=hours),
                        path="/".join(token for _, token in keys),
                        size=1000,
                        level_type=level_type,
                        level=None if level is None else level_type.to_user(level),
                        member=member,
                        wavelength=wavelength,
                    ))
        return assets


class FakeDownloader:
    """Writes one small file per destination and records each call."""

    def __init__(self):
        self.calls = []

    def fetch(self, assets, destination, *, combine="all", temp_dir=None):
        self.calls.append((list(assets), destination, combine))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"GRIB")
        return Fetched(files=(destination,), bytes_downloaded=4)


@pytest.fixture
def fake_dwd(monkeypatch):
    """Makes the CLI use the fakes instead of the real server.

    Returns the downloader, so a test can check what was fetched.
    """
    downloader = FakeDownloader()

    def make_dwd(**options):
        return DWD(catalogue=FakeCatalogue(), downloader=downloader, **options)

    monkeypatch.setattr("dwdopen.cli.nwp.DWD", make_dwd)
    return downloader
