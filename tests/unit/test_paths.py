from dwdopen._fileserver.paths import build_path

BASE = "weather/nwp/v1"


def test_root():
    assert build_path() == f"{BASE}/"


def test_model_listing():
    assert build_path(key="m") == f"{BASE}/m/"


def test_level_type_listing_uses_a_bare_key():
    assert build_path(("m", "icon-eu"), ("p", "T"), key="lvt1") == (
        f"{BASE}/m/icon-eu/p/T/lvt1/"
    )


def test_step_listing_uses_a_bare_key():
    assert build_path(
        ("m", "icon-eu"), ("p", "T_2M"), ("r", "2026-09-16T00:00"), key="s"
    ) == f"{BASE}/m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/"


def test_single_level_deterministic_file():
    assert build_path(
        ("m", "icon-eu"),
        ("p", "T_2M"),
        ("r", "2026-09-16T00:00"),
        ("s", "PT000H00M.grib2"),
        directory=False,
    ) == f"{BASE}/m/icon-eu/p/T_2M/r/2026-09-16T00:00/s/PT000H00M.grib2"


def test_ensemble_multi_level_file():
    assert build_path(
        ("m", "icon-eu-eps"), ("p", "T"), ("lvt1", "150"), ("lv1", "74"),
        ("r", "2026-09-16T00:00"), ("e", "01"), ("s", "PT000H00M.grib2"),
        directory=False,
    ) == (
        f"{BASE}/m/icon-eu-eps/p/T/lvt1/150/lv1/74"
        "/r/2026-09-16T00:00/e/01/s/PT000H00M.grib2"
    )


def test_art_wavelength_file():
    assert build_path(
        ("m", "icon-art-eu"), ("p", "SAT_BSC_DUST"), ("wvl1", "532"),
        ("lvt1", "150"), ("lv1", "74"), ("r", "2026-09-16T00:00"),
        ("s", "PT000H00M.grib2"),
        directory=False,
    ) == (
        f"{BASE}/m/icon-art-eu/p/SAT_BSC_DUST/wvl1/532/lvt1/150/lv1/74"
        "/r/2026-09-16T00:00/s/PT000H00M.grib2"
    )


def test_unknown_keys_pass_through():
    # Check if unknown dimensions also work, to be future-proof.
    assert build_path(("m", "x"), ("lvt2", "162"), ("mode", "3")) == (
        f"{BASE}/m/x/lvt2/162/mode/3/"
    )