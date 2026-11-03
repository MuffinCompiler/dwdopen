"""The dwdopen command line interface."""

from __future__ import annotations

import click

from dwdopen import __version__

__all__ = ["main"]


@click.group()
@click.version_option(__version__, prog_name="dwdopen")
def main() -> None:
    """Download weather data from DWD Open Data (https://opendata.dwd.de)."""
