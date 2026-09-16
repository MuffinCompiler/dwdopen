import pytest

from dwdopen import DWD

pytestmark = pytest.mark.live


def test_discovery_against_the_live_server():
    with DWD() as dwd:
        assert "icon-eu" in dwd.nwp.models()

        icon_eu = dwd.nwp.model("icon-eu")
        assert "T_2M" in icon_eu.parameters()

        runs = icon_eu.runs(probe="T_2M")
        assert len(runs) >= 2
        assert runs == sorted(runs)
        assert icon_eu.latest_run(probe="T_2M") == runs[-1]