"""The `dwdopen nwp` commands against the fake server in conftest.py."""

from click.testing import CliRunner

from dwdopen.cli import main


def run(*args):
    """Run `dwdopen ARGS...` and return click's Result."""
    return CliRunner().invoke(main, list(args), prog_name="dwdopen")


def test_models_prints_one_name_per_line(fake_dwd):
    result = run("nwp", "models")
    assert result.exit_code == 0
    assert result.stdout == "icon-art\nicon-eu\nicon-eu-eps\n"


def test_params_prints_one_name_per_line(fake_dwd):
    result = run("nwp", "params", "icon-eu")
    assert result.exit_code == 0
    assert result.stdout == "T\nTOT_PREC\nT_2M\n"


def test_params_takes_the_model_in_any_case(fake_dwd):
    assert run("nwp", "params", "ICON-EU").stdout == "T\nTOT_PREC\nT_2M\n"


def test_params_of_an_unknown_model_suggests_the_right_one(fake_dwd):
    result = run("nwp", "params", "icon-uu")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error: unknown model 'icon-uu'")
    assert "icon-eu" in result.stderr


def test_params_needs_a_model(fake_dwd):
    result = run("nwp", "params")
    assert result.exit_code == 2
    assert "Missing argument 'MODEL'" in result.stderr
