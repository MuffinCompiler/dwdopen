"""The dwdopen command line, run in-process with click's CliRunner."""

from click.testing import CliRunner

import dwdopen
from dwdopen.cli import main


def run(*args):
    """Run `dwdopen ARGS...` and return click's Result."""
    return CliRunner().invoke(main, list(args), prog_name="dwdopen")


def test_help_describes_the_tool():
    result = run("--help")
    assert result.exit_code == 0
    assert "Usage: dwdopen" in result.output
    assert "DWD Open Data" in result.output


def test_version_is_the_library_version():
    result = run("--version")
    assert result.exit_code == 0
    assert result.output == f"dwdopen, version {dwdopen.__version__}\n"
