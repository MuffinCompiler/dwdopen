import pytest

from dwdopen import DWD
from dwdopen.nwp.selectors import Every

pytestmark = pytest.mark.live


def grib_messages(path):
    """Count GRIB2 messages by walking the self-delimiting framing.

    Done by hand rather than with eccodes so the test suite keeps working
    without a GRIB library installed. Section 0 is 16 bytes and carries the
    total message length as an 8-byte big-endian integer at offset 8.
    """
    data = path.read_bytes()
    offset = 0
    count = 0
    while offset < len(data):
        assert data[offset:offset + 4] == b"GRIB", "message does not start with GRIB"
        length = int.from_bytes(data[offset + 8:offset + 16], "big")
        assert data[offset + length - 4:offset + length] == b"7777"
        offset += length
        count += 1
    return count


def test_combined_download_is_one_valid_grib_in_time_order(tmp_path):
    with DWD() as dwd:
        query = dwd.nwp.model("icon-eu").select(
            parameters=["T_2M", "PMSL"], steps=Every("0h", "3h", "3h")
        )
        plan = query.resolve()
        # Time-major, so every field of one step sits together. CDO silently
        # drops variables from a file that is not ordered this way.
        assert [a.step for a in plan.assets] == sorted(a.step for a in plan.assets)

        result = plan.download(tmp_path / "combined.grib2", combine="all")

    assert result.assets_downloaded == 4
    assert grib_messages(result.files[0]) == 4
    assert result.bytes_downloaded == result.files[0].stat().st_size


def test_separate_download_names_files_after_their_keys(tmp_path):
    with DWD() as dwd:
        query = dwd.nwp.model("icon-eu").select(parameters="T_2M", steps="0h")
        result = query.download(tmp_path / "out", combine="none")

    assert len(result.files) == 1
    name = result.files[0].name
    assert name.startswith("m-icon-eu_p-T_2M_r-")
    assert name.endswith("_s-PT000H00M.grib2")
    assert ":" not in name  # Windows would reject the run timestamp otherwise
    assert grib_messages(result.files[0]) == 1
