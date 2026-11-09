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
