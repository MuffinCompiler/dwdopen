"""The dwdopen command line, run in-process with click's CliRunner."""

import logging

import click
import pytest
from click.testing import CliRunner

import dwdopen
from dwdopen import set_log_level
from dwdopen.cli import main


def run(*args):
    """Run `dwdopen ARGS...` and return click's Result."""
    return CliRunner().invoke(main, list(args), prog_name="dwdopen")


@pytest.fixture
def probe():
    """A throwaway `dwdopen probe` command that records what main stored.

    main only runs its options when a command follows, and there is no real
    command yet.
    """
    seen = {}

    @click.command()
    @click.pass_context
    def probe(ctx):
        seen["obj"] = ctx.obj
        seen["level"] = logging.getLogger("dwdopen").level

    main.add_command(probe)
    yield seen
    del main.commands["probe"]
    set_log_level()


def test_help_describes_the_tool():
    result = run("--help")
    assert result.exit_code == 0
    assert "Usage: dwdopen" in result.output
    assert "DWD Open Data" in result.output


def test_version_is_the_library_version():
    result = run("--version")
    assert result.exit_code == 0
    assert result.output == f"dwdopen, version {dwdopen.__version__}\n"


def test_by_default_info_logs_and_progress_are_shown(probe):
    assert run("probe").exit_code == 0
    assert probe["level"] == logging.INFO
    assert probe["obj"] == {"verbose": False, "progress": True}


def test_quiet_shows_only_warnings(probe):
    assert run("-q", "probe").exit_code == 0
    assert probe["level"] == logging.WARNING


def test_verbose_shows_debug_logs(probe):
    assert run("--verbose", "probe").exit_code == 0
    assert probe["level"] == logging.DEBUG
    assert probe["obj"]["verbose"] is True


def test_no_progress_is_passed_on(probe):
    assert run("--no-progress", "probe").exit_code == 0
    assert probe["obj"]["progress"] is False


def test_quiet_and_verbose_together_is_a_usage_error(probe):
    result = run("-q", "-v", "probe")
    assert result.exit_code == 2
    assert "-q and -v cannot be used together" in result.output
