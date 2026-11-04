"""The dwdopen command line interface."""

from __future__ import annotations

import logging

import click

from dwdopen import __version__, set_log_level

__all__ = ["main"]


@click.group()
@click.version_option(__version__, prog_name="dwdopen")
@click.option("-q", "--quiet", is_flag=True, help="Only show warnings and errors.")
@click.option("-v", "--verbose", is_flag=True, help="Show debug logs.")
@click.option("--no-progress", is_flag=True, help="Do not show download progress.")
@click.pass_context
def main(ctx: click.Context, quiet: bool, verbose: bool, no_progress: bool) -> None:
    """Download weather data from DWD Open Data (https://opendata.dwd.de)."""
    if quiet and verbose:
        raise click.UsageError("-q and -v cannot be used together.")

    if quiet:
        set_log_level(logging.WARNING)
    elif verbose:
        set_log_level(logging.DEBUG)
    else:
        set_log_level(logging.INFO)

    # Set the context to be read by the client.
    ctx.obj = {"verbose": verbose, "progress": not no_progress}
