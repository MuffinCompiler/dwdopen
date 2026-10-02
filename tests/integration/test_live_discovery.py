import pytest

from dwdopen import DWD

pytestmark = pytest.mark.live


def test_discovery_against_the_live_server():
    with DWD() as dwd:
        assert "icon-eu" in dwd.nwp.models()

        icon_eu = dwd.nwp.model("icon-eu")
        assert "T_2M" in icon_eu.parameters()

        runs = icon_eu.runs(parameter="T_2M")
        assert len(runs) >= 2
        assert runs == sorted(runs)
        assert icon_eu.latest_run(parameter="T_2M") == runs[-1]


def test_latest_run_works_without_naming_a_parameter():
    """Runs sit below a parameter, so one has to be chosen automatically.

    Checked across every model DWD publishes, because the probe list has to
    hold for all of them: PMSL would have been an obvious candidate but is
    absent from icon-eps and icon-eu-eps.
    """
    with DWD() as dwd:
        for model in dwd.nwp.models():
            assert dwd.nwp.model(model).latest_run() is not None
