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


def test_params_filter_matches_part_of_the_name_in_any_case(fake_dwd):
    result = run("nwp", "params", "icon-eu", "prec")
    assert result.exit_code == 0
    assert result.stdout == "TOT_PREC\n"


def test_params_filter_matching_nothing_prints_nothing(fake_dwd):
    result = run("nwp", "params", "icon-eu", "CLCT")
    assert result.exit_code == 0
    assert result.stdout == ""


def test_runs_prints_one_run_per_line_oldest_first(fake_dwd):
    result = run("nwp", "runs", "icon-eu")
    assert result.exit_code == 0
    assert result.stdout == "2026-10-27T00:00Z\n2026-10-27T06:00Z\n"


def test_runs_of_an_unknown_model_exits_1(fake_dwd):
    result = run("nwp", "runs", "icon-uu")
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: unknown model 'icon-uu'")


def test_runs_of_one_parameter(fake_dwd):
    result = run("nwp", "runs", "icon-eu", "--param", "t_2m")
    assert result.exit_code == 0
    assert result.stdout == "2026-10-27T00:00Z\n2026-10-27T06:00Z\n"


def test_runs_of_a_parameter_on_levels(fake_dwd):
    assert run("nwp", "runs", "icon-eu", "-p", "T").exit_code == 0


def test_runs_of_an_unknown_parameter_exits_1(fake_dwd):
    result = run("nwp", "runs", "icon-eu", "-p", "T_3M")
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: unknown parameter 'T_3M'")


def test_info_of_a_parameter_on_two_level_types(fake_dwd):
    result = run("nwp", "info", "icon-eu", "t")
    assert result.exit_code == 0
    assert result.stdout == (
        "model:       icon-eu\n"
        "parameter:   T\n"
        "level types: pressure (100), model (150)\n"
    )


def test_info_of_a_2d_field(fake_dwd):
    result = run("nwp", "info", "icon-eu", "T_2M")
    assert "level types: none, a single-level (2-D) field\n" in result.stdout


def test_info_shows_wavelengths(fake_dwd):
    result = run("nwp", "info", "icon-art", "SAT_BSC_DUST")
    assert result.stdout.endswith("wavelengths: 532, 1064 nm\n")


def test_info_of_an_unknown_parameter_exits_1(fake_dwd):
    result = run("nwp", "info", "icon-eu", "T_3M")
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: unknown parameter 'T_3M'")
